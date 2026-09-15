"""Tests for the one-sided Gaussian predictive upper bound (E15 Bayesian baseline)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from kelvins_conformal.models.bayesian import PredictiveDistribution


def _dist(mean, std):
    mean = np.asarray(mean, dtype=float)
    std = np.asarray(std, dtype=float)
    return PredictiveDistribution(
        mean=mean, std=std, epistemic_std=std, aleatoric_std=0.0, samples=np.stack([mean, mean])
    )


def test_upper_bound_is_the_level_quantile_of_the_gaussian():
    d = _dist([0.0, -5.0, 2.0], [1.0, 2.0, 0.5])
    np.testing.assert_allclose(d.upper_bound(0.9), d.mean + stats.norm.ppf(0.9) * d.std)
    assert d.upper_bound(0.9)[0] == pytest.approx(1.2815515655446004)


def test_one_sided_bound_differs_from_the_two_sided_upper_edge():
    """D2: the one-sided 90% bound is NOT the two-sided 90% upper edge (that is the 95% quantile)."""
    d = _dist([0.0], [1.0])
    _, hi_two = d.interval(0.9)
    assert d.upper_bound(0.9)[0] < hi_two[0]
    np.testing.assert_allclose(d.upper_bound(0.95), hi_two)


def test_upper_bound_has_nominal_coverage_on_gaussian_data():
    rng = np.random.default_rng(0)
    mean = rng.normal(size=20000)
    std = rng.uniform(0.5, 3.0, 20000)
    y = rng.normal(mean, std)
    assert abs(np.mean(y <= _dist(mean, std).upper_bound(0.8)) - 0.8) < 0.01


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.2])
def test_upper_bound_rejects_invalid_level(bad):
    with pytest.raises(ValueError):
        _dist([0.0], [1.0]).upper_bound(bad)
