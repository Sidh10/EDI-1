"""Label regeneration under a covariance-scaling grid — E14 (Phase 4, Gate 3).

Responsibility: turn each official-test event's target-defining CDM into a
*regenerated* log-risk label under a scalar covariance-scaling factor, so E14 can
measure how known covariance miscalibration propagates into the coverage validity
established at Gate 2 (Contribution 2).

Inputs:  the target-CDM frame from ``data.official_test_target_cdms`` and a
         scaling grid (``config.labelnoise.scaling_grid``).
Outputs: per-event, per-scale regenerated labels in both forms the 2026-09-16
         E14 pre-registration declares, plus M7 eligibility bookkeeping.

Serves: EXPERIMENT_PLAN.md E14. Scope is SCOPED M7 per the 2026-09-16
Assumption-A4 / Q-LBL-01 resolution in DECISIONS.md.

The two label definitions (pre-registration §4), stated once here because every
number E14 reports is one or the other:

  (P) DIRECT      y_s = max(log10 Pc_s, floor)
      The spec's own wording — the label regenerated outright at scale ``s``. Its
      *level* mixes the rescaling effect with E3's recomputation discrepancy,
      which is real and only a PARTIAL HOLD.

  (A) ANCHORED    y_s = clip(y_reported + [log10 Pc_s - log10 Pc_1], floor, 0)
      The reported label displaced by exactly the shift rescaling induces. The
      recomputation discrepancy cancels in the difference, so this arm isolates
      label noise. Differencing uses UNFLOORED log-Pc: differencing floored values
      would silently zero out any change occurring below the sentinel.

      Arm (A) is DEFINED ONLY WHERE THE REPORTED LABEL IS NOT CENSORED, i.e.
      ``y_reported > floor``. At the sentinel the reported label means "at most
      1e-30", carrying no magnitude to displace, while the recomputation may sit
      thousands of log-units lower; adding the two produces a number that is not a
      probability at all. Those events are flagged undefined rather than patched
      (CLAUDE.md §10). The cap at 0 enforces Pc <= 1 for the same reason: a label
      above 0 would be physically impossible, not merely large.

Neither arm is privileged as "the truth"; both were declared before either was
computed, and both are reported (CLAUDE.md §3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .pc_foster import REQUIRED_FIELDS, PcComputationError, recompute_pc_for_row

# Columns the per-scale frame carries, in order.
SCALE_FRAME_COLUMNS: tuple[str, ...] = (
    "event_uid", "scale", "log10_pc_unfloored", "y_direct", "y_anchored",
    "anchored_defined", "failed",
)


def eligibility(target_cdms: pd.DataFrame) -> pd.DataFrame:
    """M7 eligibility per official-test event (pre-registration §1).

    Eligible iff the event's target-defining CDM carries every field in
    ``pc_foster.REQUIRED_FIELDS`` as a finite value. Missingness is never imputed
    (CLAUDE.md §10); ineligible events are excluded by construction and counted.
    """
    missing = pd.DataFrame(index=target_cdms.index)
    for field in REQUIRED_FIELDS:
        if field not in target_cdms.columns:
            raise KeyError(f"target-CDM frame is missing required column {field!r}")
        missing[field] = ~np.isfinite(pd.to_numeric(target_cdms[field], errors="coerce"))
    n_missing = missing.sum(axis=1).to_numpy(int)
    return pd.DataFrame({
        "event_uid": target_cdms["event_uid"].to_numpy(),
        "target_log_risk": pd.to_numeric(
            target_cdms["target_log_risk"], errors="coerce"
        ).to_numpy(float),
        "n_missing_required": n_missing,
        "m7_eligible": n_missing == 0,
    })


def regenerate_labels(
    target_cdms: pd.DataFrame,
    scales,
    *,
    floor_sentinel: float = -30.0,
    n_radial: int = 200,
    n_angular: int = 360,
) -> pd.DataFrame:
    """Regenerate labels for every (M7-eligible event, scaling factor) pair.

    Returns a long frame with one row per event per scale, carrying both label
    definitions. ``failed`` marks an event whose geometry is degenerate at some
    scale (``PcComputationError``); such events are reported, never patched, and
    the caller drops them from the analysis population *uniformly across scales*
    so the population cannot drift with ``s``.

    Deterministic: the Pc integrator is a fixed polar quadrature with no
    randomness, so the same config reproduces the same labels exactly.
    """
    scales = [float(s) for s in scales]
    if not any(abs(s - 1.0) < 1e-12 for s in scales):
        raise ValueError("the scaling grid must contain the 1.0 anchor (label arm A needs it)")

    elig = eligibility(target_cdms)
    keep = elig["m7_eligible"].to_numpy(bool)
    rows_df = target_cdms.loc[keep].reset_index(drop=True)
    uids = elig.loc[keep, "event_uid"].to_numpy()
    y_reported = elig.loc[keep, "target_log_risk"].to_numpy(float)
    records = rows_df.to_dict(orient="records")

    # Pass 1: the s = 1.0 anchor, needed by label arm (A) at every other scale.
    anchor = np.full(len(records), np.nan)
    per_scale: dict[float, np.ndarray] = {}
    failed = np.zeros(len(records), dtype=bool)
    for s in scales:
        vals = np.full(len(records), np.nan)
        for i, row in enumerate(records):
            try:
                res = recompute_pc_for_row(
                    row, floor_sentinel=floor_sentinel,
                    n_radial=n_radial, n_angular=n_angular, covariance_scale=s,
                )
            except PcComputationError:
                failed[i] = True
                continue
            if res is None:            # cannot happen post-eligibility; loud if it does
                raise RuntimeError(f"eligible event {uids[i]!r} reported missing fields")
            vals[i] = res.log10_pc_unfloored
        per_scale[s] = vals
        if abs(s - 1.0) < 1e-12:
            anchor = vals

    # The anchored arm differences against s = 1.0. It is defined only where BOTH
    # ends of that difference carry a magnitude:
    #   * the anchor must be finite (a non-degenerate geometry), and
    #   * the REPORTED label must be uncensored. At the sentinel the reported label
    #     says only "at most 1e-30" while the recomputation may sit thousands of
    #     log-units below it, so displacing one by the other yields a number that is
    #     not a probability. Flagged undefined, never patched (CLAUDE.md §10).
    # The reverse case — a finite anchor with underflow at some other s — IS well
    # defined: the shift is large and negative, the label lands on the floor.
    anchored_defined = np.isfinite(anchor) & (y_reported > floor_sentinel)

    out = []
    for s in scales:
        unfloored = per_scale[s]
        delta = np.where(anchored_defined, unfloored - np.where(anchored_defined, anchor, 0.0),
                         np.nan)
        # Clipped from above at 0 because Pc <= 1: a log10 risk above 0 is not a
        # large value, it is an impossible one.
        y_anchored = np.where(anchored_defined,
                              np.clip(y_reported + delta, floor_sentinel, 0.0), np.nan)
        out.append(pd.DataFrame({
            "event_uid": uids,
            "scale": s,
            "log10_pc_unfloored": unfloored,
            "y_direct": np.maximum(unfloored, floor_sentinel),
            "y_anchored": y_anchored,
            "anchored_defined": anchored_defined,
            "failed": failed,
        }))
    return pd.concat(out, ignore_index=True)[list(SCALE_FRAME_COLUMNS)]


def agreement_at_anchor(labels: pd.DataFrame, reported: pd.DataFrame) -> pd.DataFrame:
    """Per-event |recomputed - reported| at s = 1.0 (extends E3 to the full subset).

    E3 measured this on a 100-CDM stratified sample; the same comparison over every
    M7-eligible official-test event is what tells a reader whether the PARTIAL HOLD
    recorded for Assumption A4 also describes the population E14 actually uses.
    ``reported`` is the frame from :func:`eligibility`.
    """
    anchor = labels[np.isclose(labels["scale"], 1.0)][["event_uid", "y_direct"]]
    merged = anchor.merge(reported[["event_uid", "target_log_risk"]], on="event_uid", how="left")
    merged = merged.rename(columns={"y_direct": "log10_pc_recomputed"})
    merged["abs_delta"] = (merged["log10_pc_recomputed"] - merged["target_log_risk"]).abs()
    return merged
