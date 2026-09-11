"""Feature construction, governed strictly by ``feature_dictionary.yaml`` (E2).

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``features``): turn the
event-grouped CDM table into (a) last-k tabular feature matrices for the tree
models (E6) and (b) padded/masked sequence tensors for the recurrent models
(E7/E8). Deterministic; no target leakage (asserted by ``tests/test_features.py``,
not merely commented).

The safety contract
-------------------
Every column admitted here is checked against the E2 dictionary at build time, in
this order — the checks are belt-and-braces on purpose, because a leak here would
silently invalidate every downstream number:

1. **Hard exclusions.** ``config.features.hard_excluded`` (``event_id``, ``risk``)
   can never appear as a raw feature column, whatever else is configured. These
   mirror the dictionary's ``unsafe`` verdicts.
2. **Dictionary verdicts.** Any column the dictionary marks ``unsafe`` is refused.
   Columns marked ``ambiguous`` are admitted only if
   ``config.features.include_ambiguous`` is true; its default is false, which is
   the dictionary's own stated conservative option for those two columns.
3. **The temporal cutoff.** Only CDMs with ``time_to_tca >= cutoff_days`` are ever
   read. The final CDM of an event — the one defining the target — is excluded by
   construction for any event whose final CDM falls inside the cutoff, and is
   never the source of a feature value.
4. **The target is never a feature.** ``target_log_risk`` and the derived event
   bookkeeping columns are excluded from the feature matrix.

Pre-cutoff risk history
-----------------------
Historical (strictly pre-cutoff) ``risk`` values are summarised into derived
features — ``risk_last``, ``risk_mean``, ``risk_trend`` and so on — only when
``config.features.risk_history`` is true. This interprets the dictionary's
``risk`` carve-out as scoped to the concurrent/final-CDM value; the conflict is
documented in DECISIONS.md and is **PROPOSED, awaiting Sidh's confirmation**.
Setting the flag false reproduces the strict reading. Under *either* setting the
raw ``risk`` column is absent from the matrix and the final-CDM value is
unreachable — that invariant does not depend on the flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .config import REPO_ROOT, Config

# Event bookkeeping columns produced by data.py — never features.
_NON_FEATURE_COLS: frozenset[str] = frozenset({
    "event_uid", "split", "cdm_index", "n_cdms",
    "target_log_risk", "target_time_to_tca", "is_high_risk",
})

# Summary statistics computed over the admissible CDM window.
_AGGREGATIONS = ("last", "mean", "min", "max", "std", "delta")


class FeatureSafetyError(ValueError):
    """Raised when a column barred by the E2 dictionary reaches the feature set."""


def load_feature_dictionary(path: str | Path | None = None) -> dict[str, Any]:
    """Load ``feature_dictionary.yaml`` (the citable E2 artifact)."""
    p = Path(path) if path is not None else REPO_ROOT / "feature_dictionary.yaml"
    if not p.exists():
        raise FileNotFoundError(f"feature dictionary not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def classify_columns(cfg: Config, dictionary: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """Partition the release's columns into admitted / refused, per the dictionary.

    Returns a dict with keys ``admitted``, ``unsafe``, ``ambiguous_excluded`` and
    ``hard_excluded`` so a report can show exactly what was let through and why.
    """
    d = dictionary if dictionary is not None else load_feature_dictionary()
    feats = d["features"]

    admitted: list[str] = []
    unsafe: list[str] = []
    ambiguous_excluded: list[str] = []
    hard_excluded: list[str] = []

    for col, entry in feats.items():
        verdict = entry["leakage_class"]
        if col in cfg.features.hard_excluded:
            hard_excluded.append(col)
        elif verdict == "unsafe":
            unsafe.append(col)
        elif verdict == "ambiguous" and not cfg.features.include_ambiguous:
            ambiguous_excluded.append(col)
        else:
            admitted.append(col)

    return {
        "admitted": sorted(admitted),
        "unsafe": sorted(unsafe),
        "ambiguous_excluded": sorted(ambiguous_excluded),
        "hard_excluded": sorted(hard_excluded),
    }


def assert_feature_safety(
    columns, cfg: Config, dictionary: dict[str, Any] | None = None
) -> None:
    """Refuse any feature-matrix column that the E2 dictionary bars.

    Raises ``FeatureSafetyError`` naming every offender. Derived columns (e.g.
    ``risk_last``) are resolved back to the raw column they summarise before being
    judged, so a barred column cannot slip through behind a new name.

    This is the assertion ``tests/test_features.py`` exercises. It runs on every
    build, not only in tests — a leak must fail the pipeline, not just the suite.
    """
    d = dictionary if dictionary is not None else load_feature_dictionary()
    feats = d["features"]

    barred: dict[str, str] = {}
    for col, entry in feats.items():
        if col in cfg.features.hard_excluded:
            barred[col] = "hard_excluded (config)"
        elif entry["leakage_class"] == "unsafe":
            barred[col] = "unsafe (dictionary)"
        elif entry["leakage_class"] == "ambiguous" and not cfg.features.include_ambiguous:
            barred[col] = "ambiguous, excluded by the conservative default (dictionary)"

    offenders: list[str] = []
    for name in columns:
        if name in barred:
            offenders.append(f"{name}: {barred[name]}")
            continue
        if name in _NON_FEATURE_COLS:
            offenders.append(f"{name}: event bookkeeping / target column")
            continue
        # Derived columns are `<raw>_<agg>`; resolve the raw source and re-judge.
        for agg in _AGGREGATIONS:
            suffix = f"_{agg}"
            if name.endswith(suffix):
                source = name[: -len(suffix)]
                if source in barred:
                    # `risk_*` summaries are the documented, flag-gated exception:
                    # they are built ONLY from strictly pre-cutoff CDMs and never
                    # from the target value (see the module docstring).
                    if source == "risk" and cfg.features.risk_history:
                        break
                    offenders.append(
                        f"{name}: derived from {source!r} which is {barred[source]}"
                    )
                break

    if offenders:
        raise FeatureSafetyError(
            "Columns barred by feature_dictionary.yaml reached the feature matrix:\n  "
            + "\n  ".join(sorted(offenders))
        )


# --- tabular (E6) ------------------------------------------------------------


@dataclass(frozen=True)
class FeatureMatrix:
    """A built feature matrix plus the bookkeeping needed to audit and split it."""

    X: pd.DataFrame
    y: np.ndarray
    event_uids: np.ndarray
    mission_ids: np.ndarray
    feature_names: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.X)


def admissible_cdms(events: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """CDMs a forecaster may legitimately see: ``time_to_tca >= cutoff_days``.

    This is the challenge's own rule (Uriot et al. §4.2 iii), read from config and
    already confirmed in E5. The final CDM defining the target is excluded here
    for every event whose target CDM lies inside the cutoff.
    """
    cut = cfg.cutoff.cutoff_days_before_tca
    return events[events["time_to_tca"] >= cut]


def build_tabular_features(
    events: pd.DataFrame,
    cfg: Config,
    *,
    split: str | None = None,
    dictionary: dict[str, Any] | None = None,
) -> FeatureMatrix:
    """Summarise each event's last-k admissible CDMs into one feature row.

    For every admitted numeric column the builder emits ``last`` (most recent
    admissible value), ``mean``, ``min``, ``max``, ``std`` and ``delta`` (last
    minus first within the window) over the last ``cfg.features.last_k`` CDMs,
    plus a handful of event-level descriptors (number of admissible CDMs, time
    span covered, time to TCA of the last admissible CDM).
    """
    d = dictionary if dictionary is not None else load_feature_dictionary()
    classes = classify_columns(cfg, d)
    admitted = classes["admitted"]

    frame = events if split is None else events[events["split"] == split]
    if frame.empty:
        raise ValueError(f"no events to build features from (split={split!r})")

    adm = admissible_cdms(frame, cfg)
    if adm.empty:
        raise ValueError("no admissible CDMs after applying the cutoff rule")

    # Keep the last-k admissible CDMs per event (largest cdm_index = closest to TCA).
    adm = adm.sort_values(["event_uid", "time_to_tca"], ascending=[True, False])
    window = adm.groupby("event_uid").tail(cfg.features.last_k)

    # Numeric admitted columns only; `mission_id` is kept but treated as categorical.
    numeric_cols = [
        c for c in admitted
        if c not in _NON_FEATURE_COLS
        and c != "mission_id"
        and pd.api.types.is_numeric_dtype(window[c])
    ]
    if cfg.features.risk_history and "risk" not in cfg.features.hard_excluded:
        raise FeatureSafetyError(
            "`risk` must remain in features.hard_excluded even when risk_history is "
            "enabled — history enters only via derived pre-cutoff summaries."
        )

    grouped = window.groupby("event_uid")
    parts: dict[str, pd.Series] = {}
    for col in numeric_cols:
        g = grouped[col]
        parts[f"{col}_last"] = g.last()
        parts[f"{col}_mean"] = g.mean()
        parts[f"{col}_min"] = g.min()
        parts[f"{col}_max"] = g.max()
        parts[f"{col}_std"] = g.std()
        parts[f"{col}_delta"] = g.last() - g.first()

    # Strictly pre-cutoff risk history, gated by config (see module docstring).
    if cfg.features.risk_history:
        g = grouped["risk"]
        parts["risk_last"] = g.last()
        parts["risk_mean"] = g.mean()
        parts["risk_min"] = g.min()
        parts["risk_max"] = g.max()
        parts["risk_std"] = g.std()
        parts["risk_delta"] = g.last() - g.first()

    # Event-level descriptors (not per-CDM columns, so not dictionary-governed).
    parts["n_admissible_cdms"] = grouped.size()
    parts["window_time_span"] = grouped["time_to_tca"].max() - grouped["time_to_tca"].min()
    parts["last_admissible_time_to_tca"] = grouped["time_to_tca"].min()

    X = pd.DataFrame(parts)
    X = X.reindex(sorted(X.columns), axis=1)

    # `mission_id` as an explicit categorical (dictionary: safe, role=group_key).
    mission = grouped["mission_id"].first()
    if "mission_id" in admitted:
        X["mission_id"] = mission.astype("category")

    # Targets, aligned by event_uid. Events with NO admissible pre-cutoff CDM are
    # absent from X entirely — they are unpredictable under the challenge's own
    # cutoff rule, exactly as in E5's persistence baseline. They are dropped and
    # COUNTED here, never imputed (CLAUDE.md §1: no silent drops in the core).
    per_event = frame.groupby("event_uid").agg(
        target=("target_log_risk", "first"),
    )
    n_total_events = len(per_event)
    per_event = per_event.loc[per_event.index.isin(X.index)]
    X = X.loc[per_event.index]
    y = per_event["target"].to_numpy(dtype=float)

    assert_feature_safety(X.columns, cfg, d)
    if not np.all(np.isfinite(y)):
        raise ValueError("non-finite target values reached the feature matrix")

    matrix = FeatureMatrix(
        X=X, y=y,
        event_uids=X.index.to_numpy(),
        mission_ids=mission.loc[X.index].to_numpy(),
        feature_names=tuple(X.columns),
    )
    # How many events were unpredictable under the cutoff rule, for the report.
    object.__setattr__(matrix, "n_dropped", n_total_events - len(per_event))
    return matrix


# --- sequence (E7/E8) --------------------------------------------------------


@dataclass(frozen=True)
class SequenceTensors:
    """Padded sequence tensors plus the mask that makes padding inert."""

    X: np.ndarray          # (n_events, max_len, n_features), padded with PAD_VALUE
    mask: np.ndarray       # (n_events, max_len) bool: True where a real CDM sits
    lengths: np.ndarray    # (n_events,) true sequence lengths
    y: np.ndarray
    event_uids: np.ndarray
    mission_ids: np.ndarray
    feature_names: tuple[str, ...]
    conditioned_features: tuple[str, ...] = ()   # columns given the arcsinh transform

    def __len__(self) -> int:
        return len(self.y)


# Columns whose magnitude exceeds this are arcsinh-conditioned before being handed
# to the neural models. Two real columns need it: `t_position_covariance_det` and
# `c_position_covariance_det` reach ~6.7e46 (they are covariance *volumes*, so
# roughly sigma^6), which overflows float32 (max ~3.4e38) and would otherwise be
# silently turned into inf and then into 0.0 by a nan_to_num sweep.
CONDITION_THRESHOLD = 1e30


def _condition_extreme_columns(
    values: np.ndarray, names: list[str]
) -> tuple[np.ndarray, tuple[str, ...]]:
    """Apply a signed-log (arcsinh) transform to columns of extreme magnitude.

    ``arcsinh(x) = log(x + sqrt(x^2 + 1))`` behaves like ``sign(x) * log(2|x|)`` in
    the tails and like ``x`` near zero, so it handles zeros and negatives without
    the shifting a plain ``log1p`` would need. This is **numerical conditioning,
    not modelling**: it is monotone, so it destroys no information, and it is
    applied only to columns that cannot survive a float32 cast intact.

    Tree models do not get this treatment — they are invariant to monotone
    transforms, so it would be a no-op there.

    Returns the conditioned array and the names of the columns that were changed.
    """
    out = values.astype(np.float64, copy=True)
    changed: list[str] = []
    finite = np.isfinite(out)
    for j, name in enumerate(names):
        col = out[..., j]
        col_finite = finite[..., j]
        if not col_finite.any():
            continue
        if np.max(np.abs(col[col_finite])) > CONDITION_THRESHOLD:
            out[..., j] = np.arcsinh(col)
            changed.append(name)
    return out, tuple(changed)


# Padding is filled with an obviously-wrong sentinel rather than 0.0, so that any
# model which fails to honour the mask produces visibly broken output instead of a
# plausible one. tests/test_sequence_masking.py perturbs these positions.
PAD_VALUE = -999.0


def build_sequence_tensors(
    events: pd.DataFrame,
    cfg: Config,
    *,
    split: str | None = None,
    dictionary: dict[str, Any] | None = None,
    feature_names: tuple[str, ...] | None = None,
) -> SequenceTensors:
    """Build per-event padded CDM sequences over admissible (pre-cutoff) CDMs.

    Sequences are **left-padded conceptually but stored right-padded with a mask**:
    row ``i`` holds ``lengths[i]`` real timesteps at positions ``0..lengths[i]-1``
    in chronological order (earliest admissible CDM first), and ``PAD_VALUE``
    afterwards. Consumers must apply ``mask``; the masking test proves they do.
    """
    d = dictionary if dictionary is not None else load_feature_dictionary()
    classes = classify_columns(cfg, d)
    admitted = classes["admitted"]

    frame = events if split is None else events[events["split"] == split]
    if frame.empty:
        raise ValueError(f"no events to build sequences from (split={split!r})")

    adm = admissible_cdms(frame, cfg)
    adm = adm.sort_values(["event_uid", "time_to_tca"], ascending=[True, False])
    max_len = cfg.features.max_sequence_length
    adm = adm.groupby("event_uid").tail(max_len)

    cols = [
        c for c in admitted
        if c not in _NON_FEATURE_COLS
        and c != "mission_id"
        and pd.api.types.is_numeric_dtype(adm[c])
    ]
    if cfg.features.risk_history:
        cols = [*cols, "risk"]
    cols = sorted(cols)
    if feature_names is not None:
        cols = list(feature_names)

    # `risk` appears here as a per-timestep value drawn ONLY from admissible
    # (pre-cutoff) CDMs — the target CDM is not in `adm` by construction.
    check_names = [f"{c}_last" if c == "risk" else c for c in cols]
    assert_feature_safety(check_names, cfg, d)

    uids = adm["event_uid"].drop_duplicates().to_numpy()
    idx = {u: i for i, u in enumerate(uids)}
    n = len(uids)

    # Assembled in float64 throughout. Casting to float32 here would overflow the
    # covariance-determinant columns (~6.7e46) into inf; conditioning happens first
    # and the float32 cast is deferred until after standardisation, by which point
    # every value is O(1).
    X = np.full((n, max_len, len(cols)), PAD_VALUE, dtype=np.float64)
    mask = np.zeros((n, max_len), dtype=bool)
    lengths = np.zeros(n, dtype=np.int64)

    for uid, block in adm.groupby("event_uid", sort=False):
        i = idx[uid]
        # Chronological order: earliest admissible CDM first.
        vals = block.sort_values("time_to_tca", ascending=False)[cols].to_numpy(dtype=np.float64)
        ln = min(len(vals), max_len)
        X[i, :ln, :] = vals[-ln:]
        mask[i, :ln] = True
        lengths[i] = ln

    per_event = frame.groupby("event_uid").agg(
        target=("target_log_risk", "first"),
        mission=("mission_id", "first"),
    ).loc[uids]

    X, conditioned = _condition_extreme_columns(X, cols)
    # Restore the sentinel: arcsinh(-999) is not -999, and padded slots must stay
    # recognisably padded for the masking tests and for apply_standardisation.
    X[~mask] = PAD_VALUE

    # Missing values in REAL positions would propagate through the RNN as NaN.
    # They are zeroed only at real positions and only after conditioning; padded
    # positions are already the sentinel and are never read by the model.
    real_nan = (~np.isfinite(X)) & mask[..., None]
    n_real_nan = int(real_nan.sum())
    X[real_nan] = 0.0

    tensors = SequenceTensors(
        X=X, mask=mask, lengths=lengths,
        y=per_event["target"].to_numpy(dtype=float),
        event_uids=uids,
        mission_ids=per_event["mission"].to_numpy(),
        feature_names=tuple(cols),
        conditioned_features=conditioned,
    )
    object.__setattr__(tensors, "_n_real_nan", n_real_nan)
    return tensors


def standardise(
    train_X: np.ndarray, mask: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Per-feature mean/std over REAL (unmasked) timesteps only.

    Computing these over padded positions would leak the sentinel into the scale
    and make the standardisation depend on how many events happened to be short.
    """
    flat = train_X[mask]                       # (n_real_timesteps, n_features)
    mean = flat.mean(axis=0)
    std = flat.std(axis=0)
    std[std < 1e-8] = 1.0
    return mean.astype(np.float32), std.astype(np.float32)


def apply_standardisation(
    X: np.ndarray, mask: np.ndarray, mean: np.ndarray, std: np.ndarray
) -> np.ndarray:
    """Standardise real timesteps; hold padded positions at ``PAD_VALUE``.

    The float32 cast happens here, after standardisation, when every real value is
    O(1) — casting the raw columns would overflow (see ``_condition_extreme_columns``).
    Standardised values are clipped to a sane range so that a single extreme
    outlier cannot saturate the network's activations.
    """
    out = (X.astype(np.float64) - mean) / std
    out = np.clip(out, -20.0, 20.0)
    out[~mask] = PAD_VALUE
    return out.astype(np.float32)
