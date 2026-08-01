"""Tests for the E4 power-analysis engine (CLAUDE.md §4).

The power analysis is the Gate 1 deliverable, so its machinery is checked against
analytic expectations before its table is believed:

  1. The split-conformal coverage Beta parameters match the textbook formula and
     the distribution's mean is >= nominal.
  2. Precision improves (half-width shrinks) as the evaluation set grows, and
     tracks binomial theory.
  3. The calibration-size effect goes the right way and is small relative to the
     test-set effect at this project's counts.
  4. Determinism: same seed -> identical results.
  5. Degenerate configurations fail loud instead of returning a number.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.power import (
    clopper_pearson_half_width_pp,
    conformal_coverage_beta_params,
    minimum_group_size,
    simulate_precision,
)


# --- 0. the degenerate-bootstrap failure mode (regression) --------------------
# A percentile bootstrap of a proportion has ZERO width when the sample is all
# ones. At 90% coverage with n=5 that happens 59% of the time, so the MEDIAN
# bootstrap half-width is exactly 0 and a 5-event group would look perfectly
# precise. These tests pin the fix: precision is judged on Clopper-Pearson.
def test_clopper_pearson_is_wide_when_all_events_are_covered():
    """k == n must NOT produce a zero-width interval."""
    hw = clopper_pearson_half_width_pp(5, 5, level=0.95)
    assert hw > 20.0, f"CP half-width at 5/5 should be wide, got {hw}"
    # Exact: lower bound is alpha^(1/n) = 0.025^(1/5); upper bound is 1.
    expected = 100 * 0.5 * (1.0 - 0.025 ** (1 / 5))
    assert hw == pytest.approx(expected, rel=1e-6)


def test_clopper_pearson_is_wide_when_no_events_are_covered():
    hw = clopper_pearson_half_width_pp(0, 5, level=0.95)
    expected = 100 * 0.5 * (1.0 - 0.025 ** (1 / 5))
    assert hw == pytest.approx(expected, rel=1e-6)


def test_clopper_pearson_narrows_with_n():
    assert (clopper_pearson_half_width_pp(5, 5)
            > clopper_pearson_half_width_pp(50, 50)
            > clopper_pearson_half_width_pp(500, 500))


def test_bootstrap_degeneracy_is_detected_and_reported():
    """The simulation must expose how often the bootstrap CI collapsed."""
    res = simulate_precision(
        2000, 5, nominal=0.90, n_simulations=300, n_bootstrap=200, seed=1
    )
    # ~0.9^5 = 59% of simulations have every event covered.
    assert res.degenerate_fraction > 0.4
    assert res.median_half_width_pp == pytest.approx(0.0, abs=1e-9)  # the broken stat
    assert res.median_cp_half_width_pp > 20.0                        # the honest one


def test_tiny_group_does_not_spuriously_meet_the_bar():
    """The regression this whole section exists for."""
    res = simulate_precision(
        2000, 5, nominal=0.90, n_simulations=300, n_bootstrap=200, seed=2
    )
    assert not res.meets(5.0)
    assert not res.meets(10.0)


def test_clopper_pearson_rejects_invalid_counts():
    with pytest.raises(ValueError):
        clopper_pearson_half_width_pp(6, 5)
    with pytest.raises(ValueError):
        clopper_pearson_half_width_pp(0, 0)


# --- 1. Beta parameters -------------------------------------------------------
def test_beta_params_match_textbook_formula():
    # n_cal = 999, alpha = 0.1 -> l = floor(0.1 * 1000) = 100
    a, b = conformal_coverage_beta_params(999, 0.10)
    assert (a, b) == (900.0, 100.0)


def test_beta_mean_is_at_least_nominal():
    """Split conformal is conservative: E[coverage] >= 1 - alpha."""
    for n_cal in (50, 100, 500, 1000, 5000):
        a, b = conformal_coverage_beta_params(n_cal, 0.10)
        assert a / (a + b) >= 0.90 - 1e-12


def test_beta_spread_shrinks_with_calibration_size():
    def sd(n_cal):
        a, b = conformal_coverage_beta_params(n_cal, 0.10)
        return np.sqrt(a * b / ((a + b) ** 2 * (a + b + 1.0)))

    assert sd(100) > sd(1000) > sd(10000)


def test_too_few_calibration_points_raises_loudly():
    """With n_cal < 1/alpha - 1 no finite interval exists; that must not be hidden."""
    with pytest.raises(ValueError, match="too small for nominal level"):
        conformal_coverage_beta_params(5, 0.10)   # floor(0.1*6) = 0


def test_invalid_alpha_raises():
    with pytest.raises(ValueError):
        conformal_coverage_beta_params(100, 1.5)


# --- 2. precision vs evaluation-set size --------------------------------------
def test_half_width_shrinks_as_test_set_grows():
    hw = {}
    for n_test in (25, 100, 400):
        res = simulate_precision(
            2000, n_test, nominal=0.90, n_simulations=60, n_bootstrap=300, seed=1
        )
        hw[n_test] = res.median_half_width_pp
    assert hw[25] > hw[100] > hw[400]
    # Quadrupling n should roughly halve the half-width.
    assert hw[100] / hw[25] == pytest.approx(0.5, rel=0.35)


def test_half_width_tracks_binomial_theory():
    """At large n_cal the calibration term is negligible, so the half-width should
    be close to 1.96 * sqrt(p(1-p)/n) in percentage points."""
    n_test = 150
    res = simulate_precision(
        20000, n_test, nominal=0.90, n_simulations=200, n_bootstrap=800, seed=2
    )
    analytic_pp = 100 * 1.96 * np.sqrt(0.9 * 0.1 / n_test)
    assert res.median_half_width_pp == pytest.approx(analytic_pp, rel=0.20)


def test_binomial_and_beta_components_are_reported_separately():
    res = simulate_precision(
        1000, 150, nominal=0.90, n_simulations=40, n_bootstrap=200, seed=3
    )
    assert res.binomial_sd_pp > 0
    assert res.beta_sd_pp > 0
    # At this project's counts the test-set term dominates the calibration term.
    assert res.binomial_sd_pp > res.beta_sd_pp


# --- 3. calibration-size effect -----------------------------------------------
def test_larger_calibration_set_does_not_worsen_precision():
    small = simulate_precision(
        200, 150, nominal=0.90, n_simulations=150, n_bootstrap=400, seed=4
    )
    large = simulate_precision(
        4000, 150, nominal=0.90, n_simulations=150, n_bootstrap=400, seed=4
    )
    assert large.sd_coverage_estimate_pp <= small.sd_coverage_estimate_pp + 0.5


# --- 4. determinism ------------------------------------------------------------
def test_simulate_precision_is_deterministic():
    kwargs = {"nominal": 0.90, "n_simulations": 50, "n_bootstrap": 200, "seed": 42}
    a = simulate_precision(1000, 150, **kwargs)
    b = simulate_precision(1000, 150, **kwargs)
    assert a == b


def test_different_seed_changes_result():
    a = simulate_precision(1000, 150, n_simulations=50, n_bootstrap=200, seed=42)
    b = simulate_precision(1000, 150, n_simulations=50, n_bootstrap=200, seed=43)
    assert a.median_half_width_pp != b.median_half_width_pp


# --- 5. merging floor ----------------------------------------------------------
def test_minimum_group_size_finds_a_floor_on_a_generous_bar():
    n = minimum_group_size(
        2000, bar_pp=15.0, size_grid=[10, 25, 50, 100, 200],
        n_simulations=40, n_bootstrap=200, seed=5,
    )
    assert n is not None and n in (10, 25, 50, 100, 200)


def test_minimum_group_size_returns_none_when_bar_unreachable():
    """An unattainable bar must return None, not silently pick the largest size."""
    n = minimum_group_size(
        2000, bar_pp=0.01, size_grid=[10, 25, 50],
        n_simulations=20, n_bootstrap=100, seed=6,
    )
    assert n is None


def test_minimum_group_size_is_monotone_in_the_bar():
    """A looser bar can never require a larger group than a tighter bar."""
    grid = [10, 25, 50, 100, 200, 400]
    tight = minimum_group_size(
        3000, bar_pp=5.0, size_grid=grid, n_simulations=40, n_bootstrap=200, seed=7
    )
    loose = minimum_group_size(
        3000, bar_pp=10.0, size_grid=grid, n_simulations=40, n_bootstrap=200, seed=7
    )
    assert tight is not None and loose is not None
    assert loose <= tight


def test_rejects_empty_test_set():
    with pytest.raises(ValueError):
        simulate_precision(1000, 0)
