"""Analytic validation of the conformal quantile + split interval (CLAUDE.md §4, I5).

The finite-sample correction is validated against results known in closed form
BEFORE the primitive touches real data:
  1. Uniform weights reproduce the standard split-conformal quantile
     (ceil((n+1)(1-alpha))-th smallest score) exactly.
  2. The +inf atom fires exactly when n < 1/alpha - 1.
  3. Equal weights give identical output to the uniform path (the reduction).
  4. On genuinely exchangeable synthetic data, empirical coverage hits nominal
     within Monte-Carlo error, marginally over calibration/test draws.
  5. Coverage is monotone and ordered across nominal levels.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.conformal.split import (
    absolute_residual_scores,
    conformal_quantile,
    signed_residual_scores,
    split_interval,
)


# --- 1. reproduce the standard split quantile --------------------------------
@pytest.mark.parametrize("n,alpha", [(19, 0.05), (99, 0.1), (200, 0.1), (39, 0.05)])
def test_uniform_matches_standard_split_quantile(n, alpha):
    rng = np.random.default_rng(0)
    scores = rng.uniform(0, 10, size=n)
    q = conformal_quantile(scores, alpha)
    # Standard: the k-th smallest with k = ceil((n+1)(1-alpha)) (1-indexed).
    k = int(np.ceil((n + 1) * (1 - alpha)))
    if k > n:
        assert np.isinf(q)
    else:
        assert q == pytest.approx(np.sort(scores)[k - 1])


# --- 2. the +inf atom --------------------------------------------------------
def test_infinite_quantile_when_too_few_calibration_points():
    rng = np.random.default_rng(1)
    # alpha=0.05 needs n >= 19 for a finite quantile; n=18 must give +inf.
    assert np.isinf(conformal_quantile(rng.uniform(size=18), 0.05))
    assert np.isfinite(conformal_quantile(rng.uniform(size=19), 0.05))


def test_infinite_quantile_boundary_alpha_010():
    rng = np.random.default_rng(2)
    # alpha=0.1 needs n >= 9.
    assert np.isinf(conformal_quantile(rng.uniform(size=8), 0.10))
    assert np.isfinite(conformal_quantile(rng.uniform(size=9), 0.10))


# --- 3. equal weights reduce to uniform --------------------------------------
def test_equal_weights_reduce_to_uniform():
    rng = np.random.default_rng(3)
    scores = rng.normal(size=120)
    for c in (0.3, 1.0, 7.5):
        q_w = conformal_quantile(scores, 0.1, weights=np.full(120, c), test_weight=c)
        q_u = conformal_quantile(scores, 0.1)
        assert q_w == pytest.approx(q_u)


def test_default_test_weight_makes_weighted_path_match_uniform():
    """With no explicit test_weight, uniform weights must still match split CP."""
    rng = np.random.default_rng(4)
    scores = rng.normal(size=80)
    q_w = conformal_quantile(scores, 0.1, weights=np.ones(80))  # test_weight defaults to mean=1
    assert q_w == pytest.approx(conformal_quantile(scores, 0.1))


# --- 4. empirical coverage on exchangeable data hits nominal -----------------
@pytest.mark.parametrize("alpha", [0.2, 0.1, 0.05])
def test_split_conformal_achieves_nominal_coverage_when_exchangeable(alpha):
    """The core guarantee: exchangeable (calibration, test) -> coverage >= 1-alpha,
    and close to it (not wildly conservative)."""
    rng = np.random.default_rng(20)
    n_cal, n_test, reps = 400, 400, 300
    covered = []
    for _ in range(reps):
        # Exchangeable: predictions are arbitrary; residuals are what matter.
        resid_cal = rng.standard_t(df=5, size=n_cal) * 2.0
        resid_test = rng.standard_t(df=5, size=n_test) * 2.0
        scores = np.abs(resid_cal)
        pred_test = np.zeros(n_test)
        y_test = resid_test  # since pred=0, y=residual
        interval = split_interval(pred_test, scores, alpha, sided="two")
        covered.append(np.mean(interval.covers(y_test)))
    mean_cov = float(np.mean(covered))
    # Split conformal is valid (>= nominal in expectation) and tight (~ nominal).
    assert mean_cov >= (1 - alpha) - 0.02, f"under-coverage: {mean_cov:.3f} vs {1-alpha}"
    assert mean_cov <= (1 - alpha) + 0.05, f"too conservative: {mean_cov:.3f} vs {1-alpha}"


def test_one_sided_upper_coverage_when_exchangeable():
    rng = np.random.default_rng(21)
    alpha, n_cal, n_test, reps = 0.1, 500, 500, 200
    covered = []
    for _ in range(reps):
        resid_cal = rng.normal(size=n_cal)
        resid_test = rng.normal(size=n_test)
        scores = signed_residual_scores(resid_cal, np.zeros(n_cal))
        iv = split_interval(np.zeros(n_test), scores, alpha, sided="upper")
        covered.append(np.mean(iv.covers(resid_test)))
    assert abs(np.mean(covered) - (1 - alpha)) < 0.03


# --- 5. ordering across levels -----------------------------------------------
def test_quantile_monotone_in_alpha():
    rng = np.random.default_rng(5)
    scores = rng.uniform(0, 5, size=300)
    q80 = conformal_quantile(scores, 0.2)
    q90 = conformal_quantile(scores, 0.1)
    q95 = conformal_quantile(scores, 0.05)
    assert q80 <= q90 <= q95  # higher confidence -> wider


# --- guards ------------------------------------------------------------------
def test_rejects_non_finite_scores():
    with pytest.raises(ValueError):
        conformal_quantile(np.array([1.0, np.nan, 2.0]), 0.1)


def test_rejects_bad_alpha():
    with pytest.raises(ValueError):
        conformal_quantile(np.array([1.0, 2.0]), 1.5)


def test_absolute_residual_scores_are_nonnegative():
    s = absolute_residual_scores(np.array([1.0, -2.0]), np.array([0.0, 0.0]))
    assert np.all(s >= 0)
