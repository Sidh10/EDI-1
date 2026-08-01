"""Parse the raw Kelvins CDM archive into an event-grouped, typed table.

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``data``): read the raw
CSVs, validate the schema, type the columns, define the prediction target per the
resolved decision (Q-METH-01: raw log-risk including the floor sentinel), and
produce ``data/processed/events.parquet``. This module is the **single source of
split truth** — no other module partitions events (invariant I3).

Adaptations to the actual archive layout (documented at the top of the audit, per
E0/E1 instructions; the challenge paper describes plain CSVs):

* The training data ships as a nested zip: ``kelvins_competition_data/train_data.zip``
  containing ``train_data.csv`` (162,634 CDMs, 13,154 events).
* The public test inputs ``test_data.csv`` contain only CDMs at time_to_tca >= 2
  days (the challenge's 2-day prediction cutoff, enforced by construction).
* The ground-truth test target lives in ``test_data_private.csv`` as ``true_risk``
  (one row per event, final CDM within ~1 day of TCA — the documented recency
  filter). It is merged in as the test target; its rows are NOT input CDMs.
* ``event_id`` restarts at 0 in the test set and therefore collides numerically
  with training ids. Ids are namespaced (``train_<id>`` / ``test_<id>``) so every
  event is globally unique and split-leakage checks are meaningful.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

# The 103 columns of the release, in file order (schema is validated against this
# exact set — fail loud on any deviation, CLAUDE.md §1).
COLUMNS_103: tuple[str, ...] = (
    "event_id", "time_to_tca", "mission_id", "risk", "max_risk_estimate",
    "max_risk_scaling", "miss_distance", "relative_speed",
    "relative_position_r", "relative_position_t", "relative_position_n",
    "relative_velocity_r", "relative_velocity_t", "relative_velocity_n",
    "t_time_lastob_start", "t_time_lastob_end", "t_recommended_od_span",
    "t_actual_od_span", "t_obs_available", "t_obs_used", "t_residuals_accepted",
    "t_weighted_rms", "t_rcs_estimate", "t_cd_area_over_mass",
    "t_cr_area_over_mass", "t_sedr", "t_j2k_sma", "t_j2k_ecc", "t_j2k_inc",
    "t_ct_r", "t_cn_r", "t_cn_t", "t_crdot_r", "t_crdot_t", "t_crdot_n",
    "t_ctdot_r", "t_ctdot_t", "t_ctdot_n", "t_ctdot_rdot", "t_cndot_r",
    "t_cndot_t", "t_cndot_n", "t_cndot_rdot", "t_cndot_tdot", "c_object_type",
    "c_time_lastob_start", "c_time_lastob_end", "c_recommended_od_span",
    "c_actual_od_span", "c_obs_available", "c_obs_used", "c_residuals_accepted",
    "c_weighted_rms", "c_rcs_estimate", "c_cd_area_over_mass",
    "c_cr_area_over_mass", "c_sedr", "c_j2k_sma", "c_j2k_ecc", "c_j2k_inc",
    "c_ct_r", "c_cn_r", "c_cn_t", "c_crdot_r", "c_crdot_t", "c_crdot_n",
    "c_ctdot_r", "c_ctdot_t", "c_ctdot_n", "c_ctdot_rdot", "c_cndot_r",
    "c_cndot_t", "c_cndot_n", "c_cndot_rdot", "c_cndot_tdot", "t_span", "c_span",
    "t_h_apo", "t_h_per", "c_h_apo", "c_h_per", "geocentric_latitude", "azimuth",
    "elevation", "mahalanobis_distance", "t_position_covariance_det",
    "c_position_covariance_det", "t_sigma_r", "c_sigma_r", "t_sigma_t",
    "c_sigma_t", "t_sigma_n", "c_sigma_n", "t_sigma_rdot", "c_sigma_rdot",
    "t_sigma_tdot", "c_sigma_tdot", "t_sigma_ndot", "c_sigma_ndot", "F10", "F3M",
    "SSN", "AP",
)

NON_NUMERIC_COLS: frozenset[str] = frozenset({"c_object_type"})
TARGET_COL = "risk"
TIME_COL = "time_to_tca"
EVENT_COL = "event_id"
GROUP_COL = "mission_id"

# Columns added by this module (not part of the raw 103).
DERIVED_COLS: tuple[str, ...] = (
    "event_uid", "split", "cdm_index", "n_cdms",
    "target_log_risk", "target_time_to_tca", "is_high_risk",
)


class SchemaError(ValueError):
    """Raised when a raw file's columns deviate from the expected schema."""


# --- raw readers ------------------------------------------------------------
def _read_train(cfg: Config) -> pd.DataFrame:
    zpath = cfg.path("raw_dir") / "kelvins_competition_data" / "train_data.zip"
    with zipfile.ZipFile(zpath) as zf:
        with zf.open("train_data.csv") as fh:
            return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8"))


def _read_test_public(cfg: Config) -> pd.DataFrame:
    return pd.read_csv(cfg.path("raw_dir") / "kelvins_competition_data" / "test_data.csv")


def _read_test_private(cfg: Config) -> pd.DataFrame:
    return pd.read_csv(
        cfg.path("raw_dir") / "kelvins_competition_data" / "test_data_private.csv"
    )


# --- schema + typing --------------------------------------------------------
def _validate_columns(df: pd.DataFrame, expected: tuple[str, ...], name: str) -> None:
    cols = tuple(df.columns)
    if cols != expected:
        missing = set(expected) - set(cols)
        extra = set(cols) - set(expected)
        raise SchemaError(
            f"{name}: column schema mismatch.\n"
            f"  missing: {sorted(missing)}\n  unexpected: {sorted(extra)}\n"
            f"  (got {len(cols)} columns, expected {len(expected)})"
        )


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if col in NON_NUMERIC_COLS:
            df[col] = df[col].astype("string")
        else:
            # Numeric everywhere else; non-parseable -> NaN (surfaced in the audit
            # missingness heatmap, never silently imputed in the statistical core).
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --- event splitting (single source of split truth) -------------------------
def split_events(
    event_uids: list[str] | np.ndarray,
    fractions: dict[str, float],
    seed: int,
) -> dict[str, np.ndarray]:
    """Partition unique event uids into disjoint named subsets (event-level).

    Deterministic given ``seed``. Fractions must sum to ~1.0. This is the scaffold
    the self-split (Q-SEL-02) will use in later phases; the invariant it must hold
    forever is that **no event uid appears in more than one subset** (asserted).
    """
    uids = np.array(sorted(set(map(str, event_uids))))
    if abs(sum(fractions.values()) - 1.0) > 1e-9:
        raise ValueError(f"fractions must sum to 1.0, got {sum(fractions.values())}")
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(uids))
    shuffled = uids[perm]

    out: dict[str, np.ndarray] = {}
    start = 0
    names = list(fractions.keys())
    for i, name in enumerate(names):
        if i == len(names) - 1:
            out[name] = shuffled[start:]  # last subset absorbs rounding
        else:
            n = int(round(fractions[name] * len(uids)))
            out[name] = shuffled[start : start + n]
            start += n
    assert_events_disjoint(out)
    return out


def assert_events_disjoint(splits: dict[str, np.ndarray]) -> None:
    """Assert no event uid appears in more than one split (invariant I3).

    Raises AssertionError (loud) with the offending overlap on any violation.
    """
    seen: dict[str, str] = {}
    for name, uids in splits.items():
        for uid in map(str, uids):
            if uid in seen:
                raise AssertionError(
                    f"Event-level leakage: {uid!r} in both {seen[uid]!r} and {name!r}"
                )
            seen[uid] = name


# --- build ------------------------------------------------------------------
def _add_event_structure(df: pd.DataFrame, split: str) -> pd.DataFrame:
    """Namespace event ids, order CDMs within events, count CDMs per event."""
    df = df.copy()
    df["split"] = split
    df["event_uid"] = split + "_" + df[EVENT_COL].astype("int64").astype(str)
    # CDM order within an event: index 0 = earliest (largest time_to_tca),
    # last = closest to TCA (smallest time_to_tca).
    df = df.sort_values(["event_uid", TIME_COL], ascending=[True, False]).reset_index(drop=True)
    df["cdm_index"] = df.groupby("event_uid").cumcount()
    df["n_cdms"] = df.groupby("event_uid")["event_uid"].transform("size")
    return df


def build_events(cfg: Config) -> pd.DataFrame:
    """Parse raw files into the unified, typed, event-grouped CDM table.

    Target definition (Q-METH-01, resolved): raw log-risk of the FINAL CDM of each
    event, floor/sentinel values included as-is. For train the final CDM is the
    smallest-time_to_tca row of the event; for test it is ``true_risk`` from the
    private file (the target-defining CDM within ~1 day of TCA).
    """
    train = _coerce_types(_read_train(cfg))
    test_pub = _coerce_types(_read_test_public(cfg))
    _validate_columns(train, COLUMNS_103, "train_data.csv")
    _validate_columns(test_pub, COLUMNS_103, "test_data.csv")

    # Private test file: identical schema except `risk` -> `true_risk`.
    priv = _read_test_private(cfg)
    priv_expected = tuple("true_risk" if c == "risk" else c for c in COLUMNS_103)
    _validate_columns(priv, priv_expected, "test_data_private.csv")

    train = _add_event_structure(train, "train")
    test_pub = _add_event_structure(test_pub, "test")

    # --- targets ---
    # Train: final-CDM risk per event = risk at max cdm_index (min time_to_tca).
    final_rows = train.sort_values("cdm_index").groupby("event_uid").tail(1)
    train_target = final_rows.set_index("event_uid")[TARGET_COL]
    train_target_time = final_rows.set_index("event_uid")[TIME_COL]

    # Test: true_risk from the private file, keyed by namespaced uid.
    priv = priv.copy()
    priv["event_uid"] = "test_" + priv[EVENT_COL].astype("int64").astype(str)
    test_target = priv.set_index("event_uid")["true_risk"]
    test_target_time = priv.set_index("event_uid")[TIME_COL]

    train["target_log_risk"] = train["event_uid"].map(train_target)
    train["target_time_to_tca"] = train["event_uid"].map(train_target_time)
    test_pub["target_log_risk"] = test_pub["event_uid"].map(test_target)
    test_pub["target_time_to_tca"] = test_pub["event_uid"].map(test_target_time)

    if train["target_log_risk"].isna().any():
        raise SchemaError("Some train events have no derivable final-CDM target.")
    if test_pub["target_log_risk"].isna().any():
        missing = test_pub.loc[test_pub["target_log_risk"].isna(), "event_uid"].nunique()
        raise SchemaError(f"{missing} test events missing a true_risk target after merge.")

    events = pd.concat([train, test_pub], ignore_index=True)
    events["is_high_risk"] = events["target_log_risk"] > cfg.high_risk_threshold

    # Invariant I3: train and test events must be globally disjoint.
    assert_events_disjoint(
        {
            "train": events.loc[events["split"] == "train", "event_uid"].unique(),
            "test": events.loc[events["split"] == "test", "event_uid"].unique(),
        }
    )
    return events


def write_events_parquet(cfg: Config, events: pd.DataFrame) -> Path:
    """Write the events table atomically (temp -> fsync -> rename, invariant §9)."""
    out = cfg.path("events_parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    events.to_parquet(tmp, index=False)
    # Flush to disk before the rename (durability). fsync needs a writable fd,
    # so reopen the finished file read-write rather than read-only (Windows raises
    # EBADF on fsync of a read handle).
    fd = os.open(tmp, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, out)
    return out


def load_events(cfg: Config) -> pd.DataFrame:
    """Load the processed events table (raising if it has not been built)."""
    path = cfg.path("events_parquet")
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `kc audit` (or data.build_events) first."
        )
    return pd.read_parquet(path)


def training_pool_splits(events: pd.DataFrame, cfg) -> dict[str, np.ndarray]:
    """Partition the TRAINING POOL into the four event-level subsets Phase 2+ needs.

    Returns ``{"fit_inner", "val_inner", "calibration", "self_test"}``, all disjoint
    and all drawn from the training split only — the official test set is never
    touched here.

    Layering (invariant I3, and Q-SEL-02's resolved self-split design):

      * the training pool is first split into ``fit`` / ``calibration`` /
        ``self_test`` using ``cfg.splits.self_split_fractions``;
      * ``fit`` is then sub-split into ``fit_inner`` / ``val_inner`` using
        ``cfg.model_split.inner_validation_fraction``.

    The nesting matters. Phase 2 does all early stopping and hyperparameter
    selection on ``val_inner``, which is carved out of ``fit`` — so the Phase-3
    ``calibration`` and ``self_test`` subsets stay genuinely untouched and remain
    exchangeable with fresh data when the conformal layer is built. Validating on
    ``calibration`` instead would quietly destroy that property.

    Deterministic given ``cfg.seed``.
    """
    train_uids = events.loc[events["split"] == "train", "event_uid"].unique()
    if len(train_uids) == 0:
        raise ValueError("no training events available to split")

    fractions = dict(cfg.raw["splits"]["self_split_fractions"])
    outer = split_events(train_uids, fractions, seed=cfg.seed)

    inner_val_frac = cfg.model_split.inner_validation_fraction
    inner = split_events(
        outer["fit"],
        {"fit_inner": 1.0 - inner_val_frac, "val_inner": inner_val_frac},
        seed=cfg.seed,
    )

    out = {
        "fit_inner": inner["fit_inner"],
        "val_inner": inner["val_inner"],
        "calibration": outer["calibration"],
        "self_test": outer["self_test"],
    }
    assert_events_disjoint(out)
    return out


def challenge_eligible_events(
    events: pd.DataFrame,
    *,
    cutoff_days: float,
    recency_days: float,
    min_cdms: int = 2,
) -> pd.Index:
    """Event uids satisfying the challenge's own test-set eligibility rules.

    Transcribed from Uriot et al., arXiv:2008.03069v2 §4.2, which lists three
    constraints on events eligible for the test set:

      i.   the event contains at least 2 CDMs ("one to learn from and one to use
           as the target");
      ii.  the last CDM released for the event is within 1 day of TCA
           (``time_to_tca < recency_days``);
      iii. the first CDM is at least 2 days before TCA
           (``time_to_tca >= cutoff_days``).

    This is the documented *selection mechanism* behind the official test split.
    E5 needs it to reproduce the paper's training-set baseline row, which applies
    the same filter to training events. It is provided here — in the single source
    of split truth — rather than re-derived per notebook.

    Returns an Index of ``event_uid`` values; it never mutates or filters in place.
    """
    grouped = events.groupby("event_uid").agg(
        n_cdms=(TIME_COL, "size"),
        last_time_to_tca=(TIME_COL, "min"),
        first_time_to_tca=(TIME_COL, "max"),
    )
    mask = (
        (grouped["n_cdms"] >= min_cdms)
        & (grouped["last_time_to_tca"] < recency_days)
        & (grouped["first_time_to_tca"] >= cutoff_days)
    )
    return grouped.index[mask]


def event_level_frame(events: pd.DataFrame) -> pd.DataFrame:
    """Collapse to one row per event (target + group + basic series stats).

    Used by the audit for event-count / high-risk-prevalence / recency figures so
    each event contributes exactly once (avoids CDM-level pseudo-replication, I3).
    """
    g = events.groupby("event_uid", as_index=False)
    per_event = g.agg(
        split=("split", "first"),
        mission_id=(GROUP_COL, "first"),
        n_cdms=("n_cdms", "first"),
        target_log_risk=("target_log_risk", "first"),
        target_time_to_tca=("target_time_to_tca", "first"),
        is_high_risk=("is_high_risk", "first"),
        last_input_time_to_tca=(TIME_COL, "min"),
        last_input_risk=(TARGET_COL, "last"),
    )
    return per_event
