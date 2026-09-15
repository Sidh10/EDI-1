"""Tests for the rank-invariance audit helpers and Proposition 1 itself (CLAUDE.md §4).

Proposition 1: matched-budget alerts from ``score`` equal those from ``reference`` at
every budget iff the two are order-isomorphic (``score`` is a strictly increasing
function of ``reference``). These tests check both directions on toy cases, and
that ``monotone_transform_check`` detects exactly the failures that matter —
including a WEAKLY increasing transform that merges two scores into a tie.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.decision import (
    alert_overlap,
    matched_budget_alerts,
    monotone_transform_check,
)


def _alerts_equal_at_every_budget(a, b):
    return all(
        np.array_equal(matched_budget_alerts(a, k), matched_budget_alerts(b, k))
        for k in range(a.size + 1)
    )


def test_translation_and_nonlinear_increasing_transforms_pass():
    rng = np.random.default_rng(0)
    r = rng.integers(-40, 0, size=80).astype(float) * 0.25     # ties included
    for s in (r + 17.5, np.exp(r / 6.0), 3.0 * r - 2.0):
        chk = monotone_transform_check(r, s)
        assert chk == {"strictly_increasing": True, "order_violations": 0, "tie_violations": 0}
        assert _alerts_equal_at_every_budget(r, s)


def test_decreasing_transform_fails_and_changes_alerts():
    r = np.array([1.0, 2.0, 3.0, 4.0])
    chk = monotone_transform_check(r, -r)
    assert not chk["strictly_increasing"] and chk["order_violations"] == 3
    assert not _alerts_equal_at_every_budget(r, -r)


def test_breaking_a_tie_is_detected_and_changes_alerts():
    r = np.array([1.0, 1.0, 2.0])
    s = np.array([0.0, 0.5, 3.0])
    chk = monotone_transform_check(r, s)
    assert chk["tie_violations"] == 1 and chk["order_violations"] == 0
    assert not chk["strictly_increasing"]
    assert not _alerts_equal_at_every_budget(r, s)


def test_weakly_increasing_transform_that_creates_a_tie_is_not_enough():
    """Strictness is necessary: merging two scores into a tie changes fractional alerts."""
    r = np.array([1.0, 2.0, 3.0])
    s = np.array([0.0, 0.0, 1.0])           # weakly increasing in r
    chk = monotone_transform_check(r, s)
    assert chk["order_violations"] == 1 and not chk["strictly_increasing"]
    np.testing.assert_array_equal(matched_budget_alerts(r, 2), [0.0, 1.0, 1.0])
    np.testing.assert_array_equal(matched_budget_alerts(s, 2), [0.5, 0.5, 1.0])


def test_converse_on_random_non_isomorphic_pairs():
    """Whenever the check fails, some budget gives different alerts (the converse direction)."""
    rng = np.random.default_rng(1)
    for _ in range(200):
        r = rng.integers(0, 5, size=7).astype(float)
        s = rng.integers(0, 5, size=7).astype(float)
        assert monotone_transform_check(r, s)["strictly_increasing"] == _alerts_equal_at_every_budget(r, s)


def test_check_rejects_non_finite_and_mismatched_inputs():
    with pytest.raises(ValueError):
        monotone_transform_check(np.array([1.0, np.inf]), np.array([1.0, 2.0]))
    with pytest.raises(ValueError):
        monotone_transform_check(np.array([1.0, 2.0]), np.array([1.0]))


def test_alert_overlap():
    a = np.array([1.0, 1.0, 0.0, 0.0])
    assert alert_overlap(a, a) == 1.0
    assert alert_overlap(a, np.array([0.0, 0.0, 1.0, 1.0])) == 0.0
    assert alert_overlap(a, np.array([1.0, 0.0, 1.0, 0.0])) == 0.5
    with pytest.raises(ValueError):
        alert_overlap(np.zeros(3), np.ones(3))
