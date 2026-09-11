"""Analytic tests for Conformalized Quantile Regression (E12; CLAUDE.md §4, I5).

CQR is a statistical-core method, so it is validated against known behaviour before
real data:
  1. On exchangeable data with well-specified quantile predictors, plain CQR hits
     nominal coverage.
  2. Weighted CQR restores coverage under a known covariate shift where naive CQR
     (with a non-adaptive band) under-covers — the E12 weighted arm.
  3. CQR is ADAPTIVE: with heteroscedastic truth, interval width varies across
     events (unlike constant-width split conformal).
  4. The score/interval reduce correctly: degenerate quantiles (q_lo=q_hi) make CQR
     coincide with split conformal on absolute residuals.
  5. Quantile-crossing repair and edge cases behave as documented.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.conformal.cqr import (
    cqr_interval,
    cqr_scores,
    enforce_monotone_quantiles,
)
from kelvins_conformal.conformal.split import (
    absolute_residual_scores,
    conformal_quantile,
    split_interval,
)

Z95 = 1.6448536269514722  # Phi^{-1}(0.95): oracle 90% band half-width per unit sd


def _sd(x, b):
    """Heteroscedastic noise scale used by the synthetic truths below."""
    return 0.5 + b * np.abs(x)


# --- 1. nominal coverage on exchangeable data --------------------------------
def test_plain_cqr_hits_nominal_on_exchangeable_data():
    rng = np.random.default_rng(0)
    alpha = 0.1
    reps, n_cal, n_test = 200, 800, 800
    covs = []
    for _ in range(reps):
        x_cal = rng.normal(0, 1, n_cal)
        x_test = rng.normal(0, 1, n_test)
        y_cal = rng.normal(0, _sd(x_cal, 0.5))
        y_test = rng.normal(0, _sd(x_test, 0.5))
        s = cqr_scores(y_cal, -Z95 * _sd(x_cal, 0.5), Z95 * _sd(x_cal, 0.5))
        iv = cqr_interval(-Z95 * _sd(x_test, 0.5), Z95 * _sd(x_test, 0.5), s, alpha)
        covs.append(np.mean(iv.covers(y_test)))
    assert abs(np.mean(covs) - (1 - alpha)) < 0.02


# --- 2. weighted CQR restores coverage under known shift ---------------------
def test_weighted_cqr_restores_coverage_under_covariate_shift():
    """Weighted CQR must correct a shift a NON-adaptive band cannot absorb.

    CQR with oracle scale-tracking quantiles is inherently robust to a pure scale
    shift, so to isolate the weighting effect we give it a CONSTANT band and
    heteroscedastic truth whose scale is larger on the shifted test set. Naive CQR
    then under-covers; the true likelihood ratio restores it. Adaptivity itself is
    covered by ``test_cqr_interval_width_is_adaptive``.
    """
    rng = np.random.default_rng(1)
    alpha = 0.1
    reps, n_cal, n_test = 200, 900, 900
    c = 1.0
    naive, weighted = [], []
    for _ in range(reps):
        x_cal = rng.normal(0, 1, n_cal)
        x_test = rng.normal(1, 1, n_test)
        y_cal = rng.normal(0, _sd(x_cal, 0.6))
        y_test = rng.normal(0, _sd(x_test, 0.6))
        s = cqr_scores(y_cal, np.full(n_cal, -c), np.full(n_cal, c))
        iv_n = cqr_interval(np.full(n_test, -c), np.full(n_test, c), s, alpha)
        naive.append(np.mean(iv_n.covers(y_test)))
        w = np.exp(x_cal - 0.5)  # true LR for N(1,1)/N(0,1)
        tw = float(np.mean(np.exp(x_test - 0.5)))
        iv_w = cqr_interval(np.full(n_test, -c), np.full(n_test, c), s, alpha,
                            weights=w, test_weight=tw)
        weighted.append(np.mean(iv_w.covers(y_test)))
    assert np.mean(naive) < (1 - alpha) - 0.015
    assert abs(np.mean(weighted) - (1 - alpha)) < 0.02
    assert np.mean(weighted) > np.mean(naive)


# --- 3. adaptivity ------------------------------------------------------------
def test_cqr_interval_width_is_adaptive():
    rng = np.random.default_rng(2)
    n = 2000
    x = rng.normal(0, 1, n)
    sd = _sd(x, 0.8)
    y = rng.normal(0, sd)
    s = cqr_scores(y, -Z95 * sd, Z95 * sd)
    iv = cqr_interval(-Z95 * sd, Z95 * sd, s, 0.1)
    w = iv.width
    assert np.std(w) > 1e-6
    assert np.corrcoef(w, np.abs(x))[0, 1] > 0.9


# --- 4. reduction to split conformal -----------------------------------------
def test_degenerate_quantiles_reduce_to_split_conformal():
    """q_lo = q_hi = point prediction -> CQR score = |y - point|, interval = pt +/- Q."""
    rng = np.random.default_rng(3)
    y_cal = rng.normal(size=300)
    pt_cal = rng.normal(size=300)
    pt_test = rng.normal(size=50)
    s_cqr = cqr_scores(y_cal, pt_cal, pt_cal)
    s_split = absolute_residual_scores(y_cal, pt_cal)
    np.testing.assert_allclose(s_cqr, s_split)
    iv_cqr = cqr_interval(pt_test, pt_test, s_cqr, 0.1)
    iv_split = split_interval(pt_test, s_split, 0.1, sided="two")
    np.testing.assert_allclose(iv_cqr.lo, iv_split.lo)
    np.testing.assert_allclose(iv_cqr.hi, iv_split.hi)


# --- 5. mechanics -------------------------------------------------------------
def test_cqr_score_negative_inside_positive_outside():
    y = np.array([0.0, 5.0, -5.0])
    qlo = np.array([-1.0, -1.0, -1.0])
    qhi = np.array([1.0, 1.0, 1.0])
    s = cqr_scores(y, qlo, qhi)
    assert s[0] == pytest.approx(-1.0)   # inside -> negative
    assert s[1] == pytest.approx(4.0)    # above hi by 4
    assert s[2] == pytest.approx(4.0)    # below lo by 4


def test_cqr_quantile_can_shrink_overwide_band():
    """If the predicted band is far too wide, Q is negative and CQR narrows it."""
    y = np.zeros(500)
    qlo = np.full(500, -10.0)
    qhi = np.full(500, 10.0)
    s = cqr_scores(y, qlo, qhi)
    q = conformal_quantile(s, 0.1)
    assert q < 0
    iv = cqr_interval(np.array([-10.0]), np.array([10.0]), s, 0.1)
    assert iv.width[0] < 20.0


def test_enforce_monotone_repairs_crossing():
    qlo = np.array([1.0, 5.0, -2.0])
    qhi = np.array([3.0, 2.0, -1.0])   # 2nd pair crosses
    lo, hi = enforce_monotone_quantiles(qlo, qhi)
    assert np.all(hi >= lo)
    assert lo.tolist() == [1.0, 2.0, -2.0]
    assert hi.tolist() == [3.0, 5.0, -1.0]


def test_cqr_interval_rejects_crossed_test_quantiles():
    with pytest.raises(ValueError, match="crossing"):
        cqr_interval(np.array([2.0]), np.array([1.0]), np.array([0.0, 0.1, 0.2]), 0.1)


def test_cqr_small_calibration_gives_infinite_interval():
    """n < 1/alpha - 1 -> unbounded interval (finite-sample honesty)."""
    s = cqr_scores(np.zeros(3), np.full(3, -1.0), np.full(3, 1.0))
    iv = cqr_interval(np.array([-1.0]), np.array([1.0]), s, 0.1)  # n=3, alpha=0.1
    assert not np.isfinite(iv.hi[0]) and not np.isfinite(iv.lo[0])
