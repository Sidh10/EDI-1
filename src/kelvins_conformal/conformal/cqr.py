"""Conformalized Quantile Regression (CQR) — E12.

CQR turns a pair of quantile predictors into a conformal interval whose width
adapts per event, in contrast to split conformal's constant half-width. It reuses
the exact same finite-sample conformal quantile as split/weighted CP
(``split.conformal_quantile``), so plain and weighted CQR differ only in the
weights passed to that one primitive — the finite-sample correction lives in a
single place (invariant I5).

Method (Romano, Patterson & Candès 2019, "Conformalized Quantile Regression",
NeurIPS), for a target level 1 - alpha with lower/upper quantile predictors
q_lo(x), q_hi(x) fit at alpha/2 and 1 - alpha/2:

  * nonconformity score  E_i = max( q_lo(x_i) - y_i ,  y_i - q_hi(x_i) )
    — signed distance outside the predicted band (negative when y is strictly
    inside, positive when outside; this is CQR's key trick, it both widens and
    *narrows* the band as the calibration data dictate);
  * conformal quantile  Q = (1 - alpha) [weighted] quantile of {E_i} with the
    +inf test atom (``split.conformal_quantile``);
  * interval  [ q_lo(x) - Q ,  q_hi(x) + Q ].

Weighted CQR (the selection-bias-corrected variant, E12's weighted arm) is
obtained by passing the E11 likelihood-ratio weights to the same quantile — no
separate machinery, because the score above is just another nonconformity score.

Implementation-boundary note (Q-CONF-03, non-blocking, resolved (b) for CQR):
the CQR score is written in-house rather than via MAPIE/crepes. The weighted-CQR
variant must combine this score with the in-house likelihood-ratio weights, which
a black-box library does not expose cleanly, so vendoring a two-line score is
simpler and avoids a new pinned dependency. Recorded in DECISIONS.md.
"""

from __future__ import annotations

import numpy as np

from .split import Interval, conformal_quantile


def cqr_scores(
    y_cal: np.ndarray, q_lo_cal: np.ndarray, q_hi_cal: np.ndarray
) -> np.ndarray:
    """CQR nonconformity score E_i = max(q_lo - y, y - q_hi) (Romano et al. 2019).

    Negative when ``y`` lies strictly inside [q_lo, q_hi]; positive by the amount it
    falls outside. One score per event (Q-CONF-01).
    """
    y_cal = np.asarray(y_cal, dtype=float)
    q_lo = np.asarray(q_lo_cal, dtype=float)
    q_hi = np.asarray(q_hi_cal, dtype=float)
    if not (y_cal.shape == q_lo.shape == q_hi.shape):
        raise ValueError("y_cal, q_lo_cal, q_hi_cal must share a shape")
    return np.maximum(q_lo - y_cal, y_cal - q_hi)


def cqr_interval(
    q_lo_test: np.ndarray,
    q_hi_test: np.ndarray,
    scores_cal: np.ndarray,
    alpha: float,
    *,
    weights: np.ndarray | None = None,
    test_weight: float | None = None,
) -> Interval:
    """Assemble the CQR interval [q_lo - Q, q_hi + Q] on the test points.

    ``weights`` None gives plain CQR (E12 naive arm); a likelihood-ratio vector
    gives weighted CQR (E12 weighted arm), reusing the exact conformal quantile of
    split/weighted CP. ``Q`` may be negative — CQR legitimately shrinks an
    over-wide predicted band — or +inf when the calibration set is too small for the
    level (the honest unbounded interval).
    """
    q_lo = np.asarray(q_lo_test, dtype=float)
    q_hi = np.asarray(q_hi_test, dtype=float)
    if q_lo.shape != q_hi.shape:
        raise ValueError("q_lo_test and q_hi_test must share a shape")
    if np.any(q_hi < q_lo):
        raise ValueError("q_hi_test < q_lo_test: quantile crossing in the test predictions")
    q = conformal_quantile(scores_cal, alpha, weights=weights, test_weight=test_weight)
    if np.isinf(q):
        return Interval(lo=np.full_like(q_lo, -np.inf), hi=np.full_like(q_hi, np.inf))
    return Interval(lo=q_lo - q, hi=q_hi + q)


def enforce_monotone_quantiles(
    q_lo: np.ndarray, q_hi: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Repair quantile crossing (q_lo > q_hi) by sorting each event's pair.

    Independently-fit quantile heads (E6) can cross for some events; CQR requires
    q_lo <= q_hi. Sorting the pair is the standard, order-preserving repair and is
    applied identically to calibration and test predictions so the score and the
    interval stay consistent. Returns the repaired (q_lo, q_hi).
    """
    q_lo = np.asarray(q_lo, dtype=float)
    q_hi = np.asarray(q_hi, dtype=float)
    lo = np.minimum(q_lo, q_hi)
    hi = np.maximum(q_lo, q_hi)
    return lo, hi


# --- one-sided (upper-bound) CQR — E15 -------------------------------------------
def cqr_upper_scores(y_cal: np.ndarray, q_hi_cal: np.ndarray) -> np.ndarray:
    """One-sided CQR score E_i = y_i - q_hi(x_i), for an UPPER bound (E15, D2).

    The upper half of the CQR construction (Romano, Patterson & Candès 2019): only
    the upper quantile predictor is kept, so this is split conformal on the signed
    residual of that predictor. Finite-sample validity follows from the same
    exchangeability argument as ``split.signed_residual_scores`` (Lei et al. 2018),
    and the weighted version from Tibshirani et al. (2019).

    E12 computed TWO-SIDED CQR only; this one-sided variant is new at E15 and is
    validated on the exchangeable self-test split before it is trusted.
    """
    y_cal = np.asarray(y_cal, dtype=float)
    q_hi = np.asarray(q_hi_cal, dtype=float)
    if y_cal.shape != q_hi.shape:
        raise ValueError("y_cal and q_hi_cal must share a shape")
    return y_cal - q_hi


def cqr_upper_bound(
    q_hi_test: np.ndarray,
    scores_cal: np.ndarray,
    alpha: float,
    *,
    weights: np.ndarray | None = None,
    test_weight: float | None = None,
) -> Interval:
    """One-sided CQR upper bound ``(-inf, q_hi(x) + Q]`` on the test points.

    ``Q`` is the (weighted) finite-sample conformal quantile of ``cqr_upper_scores``
    — the same primitive as every other interval here (invariant I5). ``Q`` may be
    negative (the head is too high) or ``+inf`` (calibration set too small for the
    level), in which case the honest bound is unbounded.
    """
    q_hi = np.asarray(q_hi_test, dtype=float)
    q = conformal_quantile(scores_cal, alpha, weights=weights, test_weight=test_weight)
    hi = np.full_like(q_hi, np.inf) if np.isinf(q) else q_hi + q
    return Interval(lo=np.full_like(q_hi, -np.inf), hi=hi)
