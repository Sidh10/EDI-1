"""Tests for the event-level bootstrap engine (CLAUDE.md §4, invariant I3).

The bootstrap underpins every confidence interval in the project, and resampling
at the wrong grouping level would silently make every metric look more precise
than it is (METRICS.md §12, "failure cases"). These tests assert:

  1. Resampling happens over EVENT units, not CDM rows — verified structurally by
     showing that a multi-row-per-event table bootstrapped through this engine
     moves whole events together.
  2. CI width behaves correctly against a known analytic variance.
  3. CI width shrinks as ~1/sqrt(n).
  4. Undefined resamples are excluded and COUNTED, not treated as zero.
  5. Determinism: same seed -> identical interval; different seed -> different.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.metrics import (
    bootstrap_challenge_score,
    bootstrap_statistic,
    challenge_score,
)


# --- 1. event-level, not row-level -------------------------------------------
def test_resampling_is_event_level_not_row_level():
    """Each bootstrap draw must select whole events, carrying all their rows.

    We encode 4 events, each with a different number of CDM rows, as an object
    array whose first axis is the EVENT. If the engine resampled rows it would be
    impossible for every drawn unit to be an intact event block.
    """
    events = np.empty(4, dtype=object)
    events[0] = np.array([1.0, 1.0, 1.0])       # event 0: 3 CDMs
    events[1] = np.array([2.0, 2.0])            # event 1: 2 CDMs
    events[2] = np.array([3.0])                 # event 2: 1 CDM
    events[3] = np.array([4.0, 4.0, 4.0, 4.0])  # event 3: 4 CDMs

    seen_blocks = []

    def statistic(sample):
        for block in sample:
            seen_blocks.append(block)
            # every drawn unit is an intact, internally-constant event block
            assert len(set(block.tolist())) == 1
        return float(np.mean([b.mean() for b in sample]))

    res = bootstrap_statistic(events, statistic, n_resamples=50, seed=0)
    assert res.n_resamples == 50
    # Every block seen must be one of the original event blocks, unmodified.
    originals = {tuple(e.tolist()) for e in events}
    assert {tuple(b.tolist()) for b in seen_blocks} <= originals


def test_each_resample_has_same_number_of_units_as_the_sample():
    values = np.arange(10, dtype=float)
    sizes = []

    def statistic(sample):
        sizes.append(len(sample))
        return float(np.mean(sample))

    bootstrap_statistic(values, statistic, n_resamples=25, seed=1)
    assert set(sizes) == {10}


# --- 2/3. CI width against known variance ------------------------------------
def test_ci_width_matches_analytic_normal_theory():
    """For the mean of n iid draws, the 95% bootstrap CI half-width should be
    close to 1.96 * sd / sqrt(n)."""
    rng = np.random.default_rng(12345)
    n, sigma = 2000, 3.0
    values = rng.normal(loc=5.0, scale=sigma, size=n)

    res = bootstrap_statistic(values, np.mean, n_resamples=2000, level=0.95, seed=7)

    analytic_half_width = 1.96 * values.std(ddof=1) / np.sqrt(n)
    assert res.half_width == pytest.approx(analytic_half_width, rel=0.10)
    assert res.lo < res.point < res.hi


def test_ci_width_shrinks_as_inverse_sqrt_n():
    rng = np.random.default_rng(99)
    base = rng.normal(0.0, 1.0, size=8000)

    hw = {}
    for n in (250, 1000, 4000):
        res = bootstrap_statistic(base[:n], np.mean, n_resamples=1000, seed=3)
        hw[n] = res.half_width

    # Quadrupling n should roughly halve the half-width.
    assert hw[1000] / hw[250] == pytest.approx(0.5, rel=0.30)
    assert hw[4000] / hw[1000] == pytest.approx(0.5, rel=0.30)


def test_ci_width_matches_binomial_theory_for_a_proportion():
    """Coverage is a proportion; check the engine against binomial theory."""
    rng = np.random.default_rng(4)
    n, p = 1500, 0.9
    flags = (rng.random(n) < p).astype(float)

    res = bootstrap_statistic(flags, np.mean, n_resamples=2000, level=0.95, seed=11)
    phat = flags.mean()
    analytic = 1.96 * np.sqrt(phat * (1 - phat) / n)
    assert res.half_width == pytest.approx(analytic, rel=0.15)


# --- 4. undefined resamples ---------------------------------------------------
def test_undefined_resamples_are_excluded_and_counted():
    """A statistic that is NaN on some resamples must be excluded, not zeroed."""
    values = np.array([1.0, 2.0, 3.0, 4.0])

    def sometimes_undefined(sample):
        # Undefined whenever the resample happens to contain a 4.0
        if np.any(sample == 4.0):
            return float("nan")
        return float(np.mean(sample))

    res = bootstrap_statistic(values, sometimes_undefined, n_resamples=500, seed=2)
    assert res.n_undefined > 0
    assert res.n_valid + res.n_undefined == 500
    assert np.isfinite(res.lo) and np.isfinite(res.hi)
    # If undefined resamples had been silently treated as 0, the lower bound would
    # be dragged to 0; the smallest defined mean here is 1.0.
    assert res.lo >= 1.0


def test_all_undefined_raises_rather_than_reporting():
    values = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="undefined on every"):
        bootstrap_statistic(values, lambda s: float("nan"), n_resamples=20, seed=0)


def test_bootstrap_rejects_empty_sample():
    with pytest.raises(ValueError):
        bootstrap_statistic(np.array([]), np.mean, n_resamples=10)


# --- 5. determinism -----------------------------------------------------------
def test_same_seed_gives_identical_interval():
    values = np.random.default_rng(0).normal(size=300)
    a = bootstrap_statistic(values, np.mean, n_resamples=500, seed=42)
    b = bootstrap_statistic(values, np.mean, n_resamples=500, seed=42)
    assert (a.point, a.lo, a.hi) == (b.point, b.lo, b.hi)


def test_different_seed_gives_different_interval():
    values = np.random.default_rng(0).normal(size=300)
    a = bootstrap_statistic(values, np.mean, n_resamples=500, seed=42)
    b = bootstrap_statistic(values, np.mean, n_resamples=500, seed=43)
    assert (a.lo, a.hi) != (b.lo, b.hi)


# --- challenge-score bootstrap ------------------------------------------------
def test_bootstrap_challenge_score_recomputes_components_before_dividing():
    """L's CI must come from recomputing MSE_HR and F2 inside each resample.

    Checked behaviourally: the point estimate of the L bootstrap must equal the
    directly computed L (not the ratio of the two component point estimates'
    bootstrap means, and not a resampling of a precomputed ratio).
    """
    rng = np.random.default_rng(5)
    y_true = np.concatenate([rng.normal(-4.0, 1.0, 60), rng.normal(-20.0, 3.0, 240)])
    y_pred = y_true + rng.normal(0.0, 0.5, y_true.size)

    direct = challenge_score(y_true, y_pred)
    boot = bootstrap_challenge_score(y_true, y_pred, n_resamples=300, seed=42)

    assert boot["loss"].point == pytest.approx(direct.loss)
    assert boot["mse_hr"].point == pytest.approx(direct.mse_hr)
    assert boot["f2"].point == pytest.approx(direct.f2)
    for key in ("loss", "mse_hr", "f2"):
        assert boot[key].lo <= boot[key].point <= boot[key].hi


def test_bootstrap_challenge_score_is_deterministic():
    rng = np.random.default_rng(6)
    y_true = np.concatenate([rng.normal(-4.0, 1.0, 40), rng.normal(-20.0, 3.0, 160)])
    y_pred = y_true + rng.normal(0.0, 0.5, y_true.size)

    a = bootstrap_challenge_score(y_true, y_pred, n_resamples=200, seed=42)
    b = bootstrap_challenge_score(y_true, y_pred, n_resamples=200, seed=42)
    for key in ("loss", "mse_hr", "f2"):
        assert (a[key].lo, a[key].hi) == (b[key].lo, b[key].hi)
