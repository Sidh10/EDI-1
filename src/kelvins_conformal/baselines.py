"""The two naive challenge baselines: persistence (LRP) and constant (CRP).

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``baselines``): reproduce
the challenge's own baseline predictors so that E5 can validate our metric
implementation against the published scores. Only the two *naive* baselines live
here — the learned predictors (LightGBM, sequence models) belong to Phase 2 and are
deliberately absent (CLAUDE.md §2, §7).

Both definitions are transcribed from Uriot et al., arXiv:2008.03069v2 §4.4:

  * **CRP (Constant Risk Prediction)** — ``r_hat_i = -5`` for every event.
    Published overall score: L = 2.5.

  * **LRP (Latest Risk Prediction)** — the clipped naive forecast

        r_hat_i = r_{-2,i}   if r_{-2,i} >= -6
                  -6.001     otherwise

    where ``r_{-2,i}`` is "the latest known risk for the i-th event (the subscript
    -2 reminds us that the latest known risk for a close approach event is
    associated to a CDM released at least two days before TCA)".
    Published test-set score: L = 0.694 (MSE_HR = 0.513, F2 = 0.739).

Note that LRP's own -6.001 fallback and the metric's global prediction clipping
(§4.3) are the same operation applied at the same point, so applying both is
idempotent, not a double correction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import EVENT_COL, TIME_COL  # noqa: F401  (documents the schema contract)

TARGET_COL = "risk"
UID_COL = "event_uid"


def latest_risk_at_or_before_cutoff(
    events: pd.DataFrame,
    *,
    cutoff_days: float,
    time_col: str = "time_to_tca",
    risk_col: str = "risk",
    uid_col: str = UID_COL,
) -> pd.Series:
    """``r_{-2}``: each event's risk from its latest CDM at least ``cutoff_days`` before TCA.

    "Latest" means the smallest ``time_to_tca`` among CDMs that still satisfy
    ``time_to_tca >= cutoff_days`` — i.e. the most recent message a forecaster is
    allowed to have seen under the challenge's 2-day prediction cutoff.

    Returns a Series indexed by ``event_uid``. Events with **no** admissible CDM are
    absent from the result rather than filled with a guess — the caller decides what
    to do with them and must report the count (no silent imputation, CLAUDE.md §1).
    """
    admissible = events[events[time_col] >= cutoff_days]
    if admissible.empty:
        raise ValueError(
            f"no CDM satisfies {time_col} >= {cutoff_days}; check the cutoff configuration"
        )
    # Smallest admissible time_to_tca per event = the latest usable CDM.
    idx = admissible.groupby(uid_col)[time_col].idxmin()
    latest = admissible.loc[idx].set_index(uid_col)[risk_col]
    return latest.astype(float)


def persistence_predict(
    latest_risk: pd.Series | np.ndarray,
    *,
    threshold: float = -6.0,
    epsilon: float = 0.001,
) -> pd.Series | np.ndarray:
    """LRP: pass ``r_{-2}`` through, flooring anything below ``threshold``.

    Implements §4.4's piecewise definition literally.
    """
    if isinstance(latest_risk, pd.Series):
        values = latest_risk.to_numpy(dtype=float)
        out = np.where(values >= threshold, values, threshold - epsilon)
        return pd.Series(out, index=latest_risk.index, name="lrp_prediction")
    values = np.asarray(latest_risk, dtype=float)
    return np.where(values >= threshold, values, threshold - epsilon)


def constant_predict(n: int, value: float = -5.0) -> np.ndarray:
    """CRP: the same constant risk for every event (§4.4 uses -5)."""
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    return np.full(int(n), float(value), dtype=float)


def build_baseline_frame(
    events: pd.DataFrame,
    *,
    split: str,
    cutoff_days: float,
    threshold: float = -6.0,
    epsilon: float = 0.001,
    constant_value: float = -5.0,
) -> pd.DataFrame:
    """Assemble the per-event truth + both baseline predictions for one split.

    Returns one row per event with columns
    ``[event_uid, mission_id, y_true, r_minus_2, pred_lrp, pred_crp]``.
    Events lacking an admissible pre-cutoff CDM are dropped and counted by the
    caller via the ``n_dropped`` attribute on the returned frame's ``attrs``.
    """
    sub = events[events["split"] == split]
    if sub.empty:
        raise ValueError(f"no events in split {split!r}")

    per_event = (
        sub.groupby(UID_COL)
        .agg(mission_id=("mission_id", "first"), y_true=("target_log_risk", "first"))
    )

    latest = latest_risk_at_or_before_cutoff(sub, cutoff_days=cutoff_days)
    frame = per_event.join(latest.rename("r_minus_2"), how="left")

    n_total = len(frame)
    missing = frame["r_minus_2"].isna()
    n_dropped = int(missing.sum())
    frame = frame[~missing].copy()

    frame["pred_lrp"] = persistence_predict(
        frame["r_minus_2"], threshold=threshold, epsilon=epsilon
    )
    frame["pred_crp"] = constant_predict(len(frame), constant_value)

    frame = frame.reset_index()
    frame.attrs["n_total_events"] = int(n_total)
    frame.attrs["n_dropped_no_admissible_cdm"] = n_dropped
    frame.attrs["split"] = split
    frame.attrs["cutoff_days"] = float(cutoff_days)
    return frame
