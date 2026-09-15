"""Analytic tests for one-sided CQR upper bounds (E15; CLAUDE.md §4, I5).

One-sided CQR is new at E15 — E12 computed two-sided CQR only — so it is checked
against known behaviour before real data:
  1. with a well-specified upper quantile head it hits nominal one-sided coverage
     on exchangeable data;
  2. it stays valid on exchangeable data even with a badly misspecified head (the
     conformal step, not the head, carries the guarantee);
  3. with a constant head it reduces EXACTLY to one-sided split conformal, plain
     and weighted — i.e. it reuses the tested finite-sample quantile;
  4. a calibration set too small for the level gives the honest unbounded bound.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.conformal.cqr import cqr_upper_bound, cqr_upper_scores
from kelvins_conformal.conformal.split import signed_residual_scores, split_interval

Z90 = 1.2815515655446004  # Phi^{-1}(0.90): oracle one-sided 90% head per unit sd


def _sd(x):
    """Heteroscedastic noise scale of the synthetic truth."""
    return 0.5 + 0.5 * np.abs(x)


def _mean_coverage(head, seed, alpha=0.1, reps=200, n_cal=800, n_test=800):
    rng = np.random.default_rng(seed)
    covs = []
    for _ in range(reps):
        x_cal = rng.normal(0, 1, n_cal)
        x_test = rng.normal(0, 1, n_test)
        y_cal = rng.normal(0, _sd(x_cal))
        y_test = rng.normal(0, _sd(x_test))
        ub = cqr_upper_bound(head(x_test), cqr_upper_scores(y_cal, head(x_cal)), alpha)
        covs.append(np.mean(ub.covers(y_test)))
    return float(np.mean(covs))


def test_one_sided_cqr_hits_nominal_on_exchangeable_data():
    assert abs(_mean_coverage(lambda x: Z90 * _sd(x), seed=0) - 0.9) < 0.02


def test_one_sided_cqr_stays_valid_with_a_misspecified_head():
    assert abs(_mean_coverage(lambda x: 3.0 * x - 1.0, seed=1) - 0.9) < 0.02


@pytest.mark.parametrize("weighted", [False, True])
def test_constant_head_reduces_to_one_sided_split_conformal(weighted):
    rng = np.random.default_rng(2)
    y_cal = rng.normal(size=300)
    head_cal = np.full(300, 0.7)
    head_test = np.full(50, 0.7)
    w = rng.uniform(0.5, 2.0, 300) if weighted else None
    tw = 1.3 if weighted else None
    ub = cqr_upper_bound(head_test, cqr_upper_scores(y_cal, head_cal), 0.1, weights=w, test_weight=tw)
    ref = split_interval(
        head_test, signed_residual_scores(y_cal, head_cal), 0.1,
        sided="upper", weights=w, test_weight=tw,
    )
    np.testing.assert_array_equal(ub.hi, ref.hi)
    assert np.all(np.isneginf(ub.lo))


def test_too_small_calibration_set_gives_unbounded_bound():
    ub = cqr_upper_bound(np.zeros(4), cqr_upper_scores(np.ones(5), np.zeros(5)), 0.05)
    assert np.all(np.isposinf(ub.hi))


def test_shape_mismatch_is_rejected():
    with pytest.raises(ValueError):
        cqr_upper_scores(np.zeros(3), np.zeros(4))
