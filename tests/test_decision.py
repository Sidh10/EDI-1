"""Hand-computed tests for the E15 decision-cost core (CLAUDE.md §4).

``decision.py`` produces the numbers E15 reports, so it is checked against
hand-computed toy cases before it touches real data:
  1. matched-budget alerting, including fractional tie sharing and edge budgets;
  2. the two identities the report relies on — rank invariance and the
     matched-budget cost identity;
  3. confusion counts and metrics on a hand-worked example;
  4. the vectorised bootstrap: agreement with direct resampling, determinism,
     undefined-resample accounting, and the paired difference.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.conformal.split import signed_residual_scores, split_interval
from kelvins_conformal.decision import (
    bootstrap_count_matrix,
    bootstrap_decision_intervals,
    bootstrap_paired_difference,
    cost_key,
    decision_counts,
    decision_metrics,
    matched_budget_alerts,
)

RATIOS = (5.0, 10.0, 20.0)


# --- 1. matched-budget alerting ----------------------------------------------
def test_alerts_top_k_without_ties():
    a = matched_budget_alerts(np.array([3.0, 1.0, 2.0, 0.0]), 2)
    np.testing.assert_array_equal(a, [1.0, 0.0, 1.0, 0.0])


def test_alerts_share_boundary_ties_equally():
    a = matched_budget_alerts(np.array([5.0, 2.0, 2.0, 2.0, 0.0]), 2)
    np.testing.assert_allclose(a, [1.0, 1 / 3, 1 / 3, 1 / 3, 0.0])
    assert a.sum() == pytest.approx(2.0)


def test_alerts_sum_to_budget_for_every_k():
    rng = np.random.default_rng(1)
    score = rng.integers(0, 6, size=40).astype(float)   # heavy ties
    for k in range(41):
        assert matched_budget_alerts(score, k).sum() == pytest.approx(k)


def test_alerts_edge_budgets_and_infinite_scores():
    s = np.array([0.5, np.inf, -1.0])
    np.testing.assert_array_equal(matched_budget_alerts(s, 0), [0.0, 0.0, 0.0])
    np.testing.assert_array_equal(matched_budget_alerts(s, 3), [1.0, 1.0, 1.0])
    np.testing.assert_array_equal(matched_budget_alerts(s, 1), [0.0, 1.0, 0.0])


@pytest.mark.parametrize("bad", [-1, 4, 1.5])
def test_alerts_reject_invalid_budget(bad):
    with pytest.raises(ValueError):
        matched_budget_alerts(np.array([1.0, 2.0, 3.0]), bad)


def test_alerts_reject_nan():
    with pytest.raises(ValueError):
        matched_budget_alerts(np.array([1.0, np.nan]), 1)


# --- 2. the identities ---------------------------------------------------------
def test_identity_rank_invariance_under_shift_and_monotone_transform():
    rng = np.random.default_rng(2)
    score = rng.integers(-30, 0, size=60).astype(float) * 0.25   # exact binary, with ties
    for k in (1, 7, 15, 30):
        base = matched_budget_alerts(score, k)
        np.testing.assert_array_equal(matched_budget_alerts(score + 20.5, k), base)
        np.testing.assert_array_equal(matched_budget_alerts(np.exp(score / 8), k), base)


def test_identity_split_conformal_upper_bound_alerts_like_its_point_prediction():
    """A one-sided split-conformal bound (one shared Q) alerts exactly like its point prediction."""
    rng = np.random.default_rng(3)
    pred_cal = rng.integers(-40, 0, size=200) * 0.5
    y_cal = pred_cal + rng.integers(-8, 9, size=200) * 0.5
    pred_test = rng.integers(-40, 0, size=120) * 0.5
    bound = split_interval(
        pred_test, signed_residual_scores(y_cal, pred_cal), 0.1, sided="upper"
    ).hi
    for k in (5, 12, 40):
        np.testing.assert_array_equal(
            matched_budget_alerts(bound, k), matched_budget_alerts(pred_test, k)
        )


def test_identity_cost_at_matched_budget():
    rng = np.random.default_rng(4)
    score = rng.normal(size=300)
    h = rng.random(300) < 0.1
    for k in (10, 30, 90):
        c = decision_counts(matched_budget_alerts(score, k), h)
        m = decision_metrics(c, RATIOS)
        for r in RATIOS:
            assert m[cost_key(r)] == pytest.approx((r + 1) * c.fn + k - h.sum())


# --- 3. counts and metrics, hand-worked ---------------------------------------
def test_counts_and_metrics_hand_computed():
    alerts = np.array([1.0, 1 / 3, 1 / 3, 1 / 3, 0.0])
    hr = np.array([True, True, False, False, True])
    c = decision_counts(alerts, hr)
    assert (c.tp, c.fn, c.fp, c.tn) == pytest.approx((4 / 3, 5 / 3, 2 / 3, 4 / 3))
    m = decision_metrics(c, RATIOS)
    assert m["missed_high_risk"] == pytest.approx(5 / 3)
    assert m["miss_rate_high_risk"] == pytest.approx(5 / 9)
    assert m["recall_high_risk"] == pytest.approx(4 / 9)
    assert m["unnecessary_maneuvers"] == pytest.approx(2 / 3)
    assert m["false_positive_rate"] == pytest.approx(1 / 3)
    assert m["precision"] == pytest.approx(2 / 3)
    # F2 = 5 p q / (4 p + q), p = 2/3, q = 4/9  ->  10/21
    assert m["f2"] == pytest.approx(10 / 21)
    assert m[cost_key(5)] == pytest.approx(5 * 5 / 3 + 2 / 3)
    assert m[cost_key(20)] == pytest.approx(20 * 5 / 3 + 2 / 3)


def test_perfect_ranking_at_prevalence_budget_misses_nothing():
    hr = np.array([0, 1, 0, 1, 1, 0, 0], dtype=bool)
    c = decision_counts(matched_budget_alerts(hr.astype(float), int(hr.sum())), hr)
    assert c.fn == 0.0 and c.fp == 0.0


def test_rates_are_undefined_without_high_risk_events():
    c = decision_counts(np.array([1.0, 0.0]), np.array([False, False]))
    m = decision_metrics(c, RATIOS)
    assert np.isnan(m["miss_rate_high_risk"]) and np.isnan(m["recall_high_risk"])


def test_counts_reject_out_of_range_alerts():
    with pytest.raises(ValueError):
        decision_counts(np.array([1.2, 0.0]), np.array([True, False]))


def test_cost_key_is_stable_for_int_and_float_ratios():
    assert cost_key(5) == cost_key(5.0) == "cost_5to1"


# --- 4. vectorised bootstrap -----------------------------------------------------
def test_count_matrix_matches_direct_resampling():
    n, b, seed = 50, 300, 7
    W = bootstrap_count_matrix(n, b, seed)
    assert W.shape == (b, n)
    np.testing.assert_array_equal(W.sum(axis=1), np.full(b, n))
    idx = np.random.default_rng(seed).integers(0, n, size=(b, n))
    v = np.arange(n, dtype=float) ** 2
    np.testing.assert_allclose(W @ v, v[idx].sum(axis=1))


def test_bootstrap_intervals_are_deterministic_and_bracket_the_point():
    rng = np.random.default_rng(8)
    n = 800
    h = rng.random(n) < 0.15
    score = h * 1.0 + rng.normal(0, 1, n)
    alerts = matched_budget_alerts(score, int(h.sum()))
    ci1 = bootstrap_decision_intervals(alerts, h, RATIOS, bootstrap_count_matrix(n, 1000, seed=42))
    ci2 = bootstrap_decision_intervals(alerts, h, RATIOS, bootstrap_count_matrix(n, 1000, seed=42))
    point = decision_metrics(decision_counts(alerts, h), RATIOS)
    assert set(ci1) == set(point)
    for name, iv in ci1.items():
        np.testing.assert_array_equal(iv["lo"], ci2[name]["lo"])
        np.testing.assert_array_equal(iv["hi"], ci2[name]["hi"])
        assert iv["lo"][0] <= point[name] <= iv["hi"][0], name


def test_bootstrap_matches_scalar_metrics_on_a_single_resample():
    """Row b of the vectorised draws equals decision_metrics on resample b, done by hand."""
    rng = np.random.default_rng(10)
    n = 60
    h = rng.random(n) < 0.3
    alerts = matched_budget_alerts(rng.normal(size=n), 15)
    idx = np.random.default_rng(5).integers(0, n, size=(1, n))[0]
    by_hand = decision_metrics(decision_counts(alerts[idx], h[idx]), RATIOS)
    ci = bootstrap_decision_intervals(alerts, h, RATIOS, bootstrap_count_matrix(n, 1, seed=5))
    for name, value in by_hand.items():
        if np.isfinite(value):
            assert ci[name]["lo"][0] == pytest.approx(value), name


def test_undefined_resamples_are_excluded_and_counted():
    n = 20
    h = np.zeros(n, dtype=bool)
    h[0] = True
    alerts = matched_budget_alerts(np.arange(n, dtype=float), 3)
    ci = bootstrap_decision_intervals(alerts, h, RATIOS, bootstrap_count_matrix(n, 500, seed=1))
    assert ci["miss_rate_high_risk"]["n_undefined"][0] > 0
    assert ci["missed_high_risk"]["n_undefined"][0] == 0


def test_paired_difference_is_zero_for_identical_alerts_and_correctly_signed():
    rng = np.random.default_rng(9)
    n = 400
    h = rng.random(n) < 0.2
    W = bootstrap_count_matrix(n, 500, seed=3)
    a = matched_budget_alerts(rng.normal(size=n), 80)
    d0 = bootstrap_paired_difference(a, a, h, W)
    assert d0 == {"point": 0.0, "lo": 0.0, "hi": 0.0}
    perfect = matched_budget_alerts(h.astype(float), 80)
    d = bootstrap_paired_difference(a, perfect, h, W)   # random ranking misses more
    assert d["point"] > 0 and d["lo"] > 0
