"""The finite-sample conformal quantile (the shared primitive) and split conformal.

Both plain split conformal and weighted conformal reduce to the same object: the
weighted (1-alpha) quantile of the calibration nonconformity scores AUGMENTED with
a point mass at +infinity for the (unseen) test score. Plain split conformal is the
special case of equal weights. Implementing them as one primitive keeps the
finite-sample correction in exactly one place.

Reference (the construction and its exactness):
  Tibshirani, Barber, Candès, Ramdas (2019), "Conformal Prediction Under Covariate
  Shift", NeurIPS. Eq. (2)-(3): for calibration scores V_1..V_n with normalized
  weights p_i(x) = w(X_i) / (sum_j w(X_j) + w(x)) and test-point mass
  p_{n+1}(x) = w(x) / (sum_j w(X_j) + w(x)), the level-(1-alpha) prediction set is
  { y : V(x, y) <= Q_{1-alpha}( sum_i p_i delta_{V_i} + p_{n+1} delta_{+inf} ) }.
  With w == const this recovers standard split conformal, whose quantile is the
  ceil((n+1)(1-alpha))-th smallest calibration score (Vovk et al. 2005; Lei et al.
  2018), and is +inf when n < 1/alpha - 1.

The +inf atom is the finite-sample correction: when the test point could itself be
the largest score with probability exceeding alpha, no finite threshold can
guarantee coverage and the honest interval is unbounded. We return +inf rather than
silently clamping — a vacuous-but-valid interval is a real result (CLAUDE.md §1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_EPS = 1e-12


def conformal_quantile(
    scores: np.ndarray,
    alpha: float,
    *,
    weights: np.ndarray | None = None,
    test_weight: float | None = None,
) -> float:
    """Level-(1-alpha) conformal quantile of ``scores`` with the +inf test atom.

    Parameters
    ----------
    scores:
        Calibration nonconformity scores V_1..V_n (one per event; Q-CONF-01).
    alpha:
        Miscoverage level; the interval targets coverage >= 1 - alpha.
    weights:
        Unnormalized, strictly positive calibration weights w(X_i). ``None`` means
        uniform (plain split conformal).
    test_weight:
        The test point's weight w(x). Defaults to the mean calibration weight, the
        natural choice that makes uniform weights reproduce plain split conformal
        exactly. Ignored when ``weights`` is None (uniform uses w(x)=1).

    Returns
    -------
    The threshold Q (possibly ``+inf``). For a two-sided symmetric residual score
    the interval is ``pred +/- Q``; for a signed one-sided score it is the
    corresponding half-line.
    """
    scores = np.asarray(scores, dtype=float)
    if scores.ndim != 1 or scores.size == 0:
        raise ValueError("scores must be a non-empty 1-D array")
    if not np.all(np.isfinite(scores)):
        raise ValueError("calibration scores must be finite")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    n = scores.size
    if weights is None:
        w = np.ones(n, dtype=float)
        wt = 1.0
    else:
        w = np.asarray(weights, dtype=float)
        if w.shape != scores.shape:
            raise ValueError("weights must have the same shape as scores")
        if np.any(w < 0) or not np.all(np.isfinite(w)):
            raise ValueError("weights must be finite and non-negative")
        if w.sum() <= 0:
            raise ValueError("weights sum to zero — no calibration support")
        wt = float(np.mean(w)) if test_weight is None else float(test_weight)
        if wt < 0 or not np.isfinite(wt):
            raise ValueError(f"test_weight must be finite and non-negative, got {wt}")

    order = np.argsort(scores, kind="mergesort")
    s = scores[order]
    p = w[order]
    total = p.sum() + wt
    p = p / total
    p_inf = wt / total

    # Quantile is +inf exactly when the test atom alone exceeds alpha: then even
    # placing all calibration mass below the threshold cannot reach 1 - alpha.
    if p_inf > alpha + _EPS:
        return float("inf")

    cum = np.cumsum(p)
    # Smallest score whose cumulative mass reaches 1 - alpha.
    idx = int(np.searchsorted(cum, 1.0 - alpha - _EPS, side="left"))
    idx = min(idx, n - 1)
    return float(s[idx])


@dataclass(frozen=True)
class Interval:
    """A prediction interval (two-sided or one-sided) per event."""

    lo: np.ndarray
    hi: np.ndarray

    def covers(self, y: np.ndarray) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        return (y >= self.lo) & (y <= self.hi)

    @property
    def width(self) -> np.ndarray:
        return self.hi - self.lo


def absolute_residual_scores(y_cal: np.ndarray, pred_cal: np.ndarray) -> np.ndarray:
    """Two-sided nonconformity score V_i = |y_i - pred_i| (symmetric intervals)."""
    return np.abs(np.asarray(y_cal, dtype=float) - np.asarray(pred_cal, dtype=float))


def signed_residual_scores(y_cal: np.ndarray, pred_cal: np.ndarray) -> np.ndarray:
    """One-sided upper-bound score V_i = y_i - pred_i (Q-METH-03 upper interval).

    The induced set is ``(-inf, pred + Q]`` — the operationally relevant bound,
    since under-estimating collision risk is the dangerous error.
    """
    return np.asarray(y_cal, dtype=float) - np.asarray(pred_cal, dtype=float)


def split_interval(
    pred_test: np.ndarray,
    scores_cal: np.ndarray,
    alpha: float,
    *,
    sided: str = "two",
    weights: np.ndarray | None = None,
    test_weight: float | None = None,
) -> Interval:
    """Assemble a (possibly weighted) split-conformal interval on the test points.

    ``sided="two"`` uses a symmetric ``pred +/- Q`` interval (expects absolute-
    residual calibration scores); ``sided="upper"`` uses ``(-inf, pred + Q]``
    (expects signed scores). ``weights`` / ``test_weight`` are passed straight to
    ``conformal_quantile`` — uniform (None) gives plain split conformal (E9/E10),
    a likelihood-ratio vector gives weighted conformal (E11).
    """
    pred_test = np.asarray(pred_test, dtype=float)
    q = conformal_quantile(scores_cal, alpha, weights=weights, test_weight=test_weight)
    if sided == "two":
        return Interval(lo=pred_test - q, hi=pred_test + q)
    if sided == "upper":
        hi = pred_test + q
        return Interval(lo=np.full_like(pred_test, -np.inf), hi=hi)
    raise ValueError(f"sided must be 'two' or 'upper', got {sided!r}")
