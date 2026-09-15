"""The budget sweep equals per-budget matched alerting (E15 tradeoff figure; CLAUDE.md §4)."""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.decision import budget_sweep, decision_counts, matched_budget_alerts


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_sweep_matches_per_budget_alerting_with_ties_and_infinities(seed):
    rng = np.random.default_rng(seed)
    n = 57
    score = rng.integers(0, 9, size=n).astype(float)   # heavy ties
    score[rng.integers(0, n, size=3)] = np.inf          # unbounded bounds rank first
    h = rng.random(n) < 0.25
    sw = budget_sweep(score, h)
    np.testing.assert_array_equal(sw["budget"], np.arange(1, n + 1))
    for k in range(1, n + 1):
        c = decision_counts(matched_budget_alerts(score, k), h)
        assert sw["missed_high_risk"][k - 1] == pytest.approx(c.fn)
        assert sw["unnecessary_maneuvers"][k - 1] == pytest.approx(c.fp)


def test_sweep_hand_computed_without_ties():
    h = np.array([True, False, True, False])
    sw = budget_sweep(np.array([4.0, 3.0, 2.0, 1.0]), h)
    np.testing.assert_allclose(sw["missed_high_risk"], [1.0, 1.0, 0.0, 0.0])
    np.testing.assert_allclose(sw["unnecessary_maneuvers"], [0.0, 1.0, 1.0, 2.0])


def test_sweep_rejects_nan():
    with pytest.raises(ValueError):
        budget_sweep(np.array([1.0, np.nan]), np.array([True, False]))
