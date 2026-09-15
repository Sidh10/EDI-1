"""Hand-computed tests for the threshold-rule core (expanded E15; CLAUDE.md §4).

Covers: the inclusive alert rule, grid-wide (weighted) counts against direct
counting, the pre-registered grid's deduplication, cost-minimising selection with
its tie rule, the paired-difference quantities, and Corollary 4 of Proposition 1 —
a translation shifts the operating point at a fixed threshold by exactly Q but
leaves the operating locus unchanged (predictions P1a and P1b).
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.decision import (
    bootstrap_count_matrix,
    bootstrap_paired_difference,
    budget_sweep,
    cost_minimizing_threshold,
    threshold_alerts,
    threshold_counts,
    threshold_grid,
)


def test_threshold_alerts_are_inclusive_at_the_threshold():
    np.testing.assert_array_equal(threshold_alerts(np.array([-7.0, -6.0, -5.0]), -6.0), [0.0, 1.0, 1.0])


def test_threshold_alerts_reject_nan_scores_and_non_finite_thresholds():
    with pytest.raises(ValueError):
        threshold_alerts(np.array([1.0, np.nan]), 0.0)
    with pytest.raises(ValueError):
        threshold_alerts(np.array([1.0, 2.0]), np.inf)


@pytest.mark.parametrize("weighted", [False, True])
def test_threshold_counts_match_direct_counting(weighted):
    rng = np.random.default_rng(0)
    s = rng.integers(-20, 0, size=90) * 0.5
    s[:3] = np.inf
    h = rng.random(90) < 0.2
    w = rng.uniform(0.2, 3.0, 90) if weighted else np.ones(90)
    grid = np.array([-12.0, -6.0, -5.5, -0.5, 0.0, 5.0])     # includes values equal to scores
    c = threshold_counts(s, h, grid, event_weights=w if weighted else None)
    for j, t in enumerate(grid):
        a = threshold_alerts(s, t)
        assert c["tp"][j] == pytest.approx(np.sum(w * a * h))
        assert c["fn"][j] == pytest.approx(np.sum(w * (1 - a) * h))
        assert c["fp"][j] == pytest.approx(np.sum(w * a * ~h))
        assert c["tn"][j] == pytest.approx(np.sum(w * (1 - a) * ~h))
        assert c["n_alerts"][j] == pytest.approx(np.sum(w * a))


def test_corollary_4_translation_shifts_the_operating_point_but_not_the_locus():
    rng = np.random.default_rng(1)
    p = rng.integers(-80, 0, size=300) * 0.25
    h = rng.random(300) < 0.15
    q = 7.75
    grid = np.arange(-20.0, 10.0, 0.25)
    shifted = threshold_counts(p + q, h, grid)
    reference = threshold_counts(p, h, grid - q)
    for key in ("tp", "fn", "fp", "tn"):
        np.testing.assert_array_equal(shifted[key], reference[key])          # P1a
    at_same_t = threshold_counts(p, h, grid)
    assert np.any(shifted["n_alerts"] != at_same_t["n_alerts"])             # the alert set DOES change
    sb, sp = budget_sweep(p + q, h), budget_sweep(p, h)
    np.testing.assert_array_equal(sb["missed_high_risk"], sp["missed_high_risk"])  # P1b
    np.testing.assert_array_equal(sb["unnecessary_maneuvers"], sp["unnecessary_maneuvers"])


def test_threshold_grid_dedupes_the_floor_atom_and_adds_the_operational_threshold():
    pooled = np.r_[np.full(700, -30.0), np.linspace(-20.0, -1.0, 300)]
    g = threshold_grid(pooled, [5, 10, 50, 70, 95], [-6.0])
    # 5th, 10th and 50th all land on the floor (-30): 3 values collapse to 1.
    assert g["n_duplicates_removed"] == 2
    assert -6.0 in g["thresholds"]
    assert list(g["thresholds"]) == sorted(g["thresholds"])
    assert g["percentile_values"][3] == pytest.approx(-27.0)   # 70th: 0.3 of the way from -30 to -20


@pytest.mark.parametrize("bad", [[0, 50], [50, 100], []])
def test_threshold_grid_rejects_invalid_percentiles(bad):
    with pytest.raises(ValueError):
        threshold_grid(np.linspace(-30, 0, 50), bad, [-6.0])


def test_cost_minimizing_threshold_hand_computed_with_tie_to_the_highest_threshold():
    s = np.array([1.0, 2.0, 3.0, 4.0])
    h = np.array([False, True, False, True])
    grid = np.array([0.5, 1.5, 2.5, 3.5, 4.5])
    # (FN, FP) by threshold: (0,2) (0,1) (1,1) (1,0) (2,0)
    r1 = cost_minimizing_threshold(s, h, grid, 1.0)      # costs 2,1,2,1,2 -> tie 1.5 / 3.5 -> 3.5
    assert (r1["threshold"], r1["cost"]) == (3.5, 1.0)
    r5 = cost_minimizing_threshold(s, h, grid, 5.0)      # costs 2,1,6,5,10 -> 1.5
    assert (r5["threshold"], r5["missed_high_risk"], r5["unnecessary_maneuvers"]) == (1.5, 0.0, 1.0)
    # Weighting the one false alarm at 2.0 heavily moves the optimum above it.
    w = np.array([1.0, 1.0, 10.0, 1.0])
    rw = cost_minimizing_threshold(s, h, grid, 5.0, event_weights=w)   # costs 12,11,15,5,10 -> 3.5
    assert rw["threshold"] == 3.5


def test_paired_difference_quantities():
    h = np.array([True, False, True, False])
    a = np.array([1.0, 1.0, 0.0, 0.0])      # FN 1, FP 1
    b = np.array([1.0, 0.0, 1.0, 0.0])      # FN 0, FP 0
    W = bootstrap_count_matrix(4, 200, seed=0)
    assert bootstrap_paired_difference(a, b, h, W)["point"] == 1.0
    assert bootstrap_paired_difference(a, b, h, W, quantity="unnecessary_maneuvers")["point"] == 1.0
    assert bootstrap_paired_difference(a, b, h, W, quantity="cost", ratio=5)["point"] == 6.0
    with pytest.raises(ValueError):
        bootstrap_paired_difference(a, b, h, W, quantity="cost")
    with pytest.raises(ValueError):
        bootstrap_paired_difference(a, b, h, W, quantity="bogus")
