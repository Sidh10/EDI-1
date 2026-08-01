"""Hand-computed toy cases for the official challenge metric (CLAUDE.md §4).

The metric is the credibility gate for every later number, so it is validated
against cases whose value can be derived by hand on paper before it is run on
real data. Definitions under test come from Uriot et al., arXiv:2008.03069v2
§4.1/§4.3 (see metrics.py's module docstring).

Covered:
  1. A fully hand-computed L / MSE_HR / F2 on a small labelled set.
  2. The threshold boundary (r == -6 is HIGH risk: the rule is `r >= -6`).
  3. F2 == 0 -> L is +inf and flagged, never NaN and never dropped silently.
  4. n_HR == 0 -> MSE_HR and L undefined, subset flagged unscorable.
  5. Prediction clipping at -6.001 behaves as documented and is idempotent.
  6. Perfect prediction -> L == 0; F2 == 1.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.metrics import (
    ChallengeScore,
    challenge_score,
    clip_predictions,
    confusion_counts,
    empirical_coverage,
    f_beta,
)

THR = -6.0


# --- 1. fully hand-computed case --------------------------------------------
def test_challenge_score_matches_hand_computation():
    # Six events. Truth vs prediction, threshold -6 (high risk iff >= -6).
    #
    #   i | y_true | y_pred | true HR | pred HR | note
    #   0 |  -4.0  |  -4.5  |  yes    |  yes    | TP, sq err 0.25
    #   1 |  -5.0  |  -7.0  |  yes    |  no     | FN, pred clipped to -6.001,
    #     |        |        |         |         |     sq err (-5 - (-6.001))^2
    #   2 |  -6.0  |  -5.5  |  yes    |  yes    | TP (boundary), sq err 0.25
    #   3 |  -8.0  |  -5.0  |  no     |  yes    | FP
    #   4 | -10.0  | -12.0  |  no     |  no     | TN
    #   5 | -20.0  | -30.0  |  no     |  no     | TN
    y_true = np.array([-4.0, -5.0, -6.0, -8.0, -10.0, -20.0])
    y_pred = np.array([-4.5, -7.0, -5.5, -5.0, -12.0, -30.0])

    s = challenge_score(y_true, y_pred, threshold=THR, beta=2.0, clip_epsilon=0.001)

    # Confusion: TP=2 (i=0, 2), FP=1 (i=3), FN=1 (i=1), TN=2 (i=4, 5)
    assert (s.counts.tp, s.counts.fp, s.counts.fn, s.counts.tn) == (2, 1, 1, 2)

    # precision = 2/3, recall = 2/3
    p = 2 / 3
    q = 2 / 3
    assert s.counts.precision == pytest.approx(p)
    assert s.counts.recall == pytest.approx(q)

    # F2 = 5pq / (4p + q) = 5*(4/9) / (8/3 + 2/3) = (20/9) / (10/3) = 2/3
    assert s.f2 == pytest.approx(2 / 3)

    # MSE_HR over the three TRUE high-risk events (i = 0, 1, 2), using the CLIPPED
    # predictions: -4.5, -6.001, -5.5
    expected_mse = np.mean([
        (-4.0 - -4.5) ** 2,
        (-5.0 - -6.001) ** 2,
        (-6.0 - -5.5) ** 2,
    ])
    assert s.n_high_risk_true == 3
    assert s.mse_hr == pytest.approx(expected_mse)

    # L = MSE_HR / F2
    assert s.loss == pytest.approx(expected_mse / (2 / 3))
    assert s.is_defined


# --- 2. threshold boundary ---------------------------------------------------
def test_threshold_boundary_is_inclusive_high_risk():
    """The challenge rule is `r >= -6`, so exactly -6 counts as HIGH risk."""
    s = challenge_score(np.array([-6.0, -20.0]), np.array([-6.0, -20.0]),
                        threshold=THR, clip_epsilon=None)
    assert s.n_high_risk_true == 1
    assert s.counts.tp == 1

    # A hair below the threshold is LOW risk.
    s2 = challenge_score(np.array([-6.0000001, -20.0]), np.array([-20.0, -20.0]),
                         threshold=THR, clip_epsilon=None)
    assert s2.n_high_risk_true == 0
    assert s2.high_risk_empty


def test_confusion_counts_boundary_on_prediction_side():
    c = confusion_counts(np.array([-4.0]), np.array([-6.0]), THR)
    assert (c.tp, c.fp, c.fn, c.tn) == (1, 0, 0, 0)  # pred exactly at threshold = HR


# --- 3. F2 == 0 --------------------------------------------------------------
def test_f2_zero_gives_infinite_loss_and_is_flagged():
    """Deliberately constructed F2 = 0: real high-risk events, none ever flagged.

    Truth has high-risk events; the model predicts low risk for everything, so
    TP = 0 -> precision = recall = 0 -> F2 = 0. L must be +inf and FLAGGED, per
    METRICS.md §1 ("report as inf or excluded with a flag, never silently dropped").
    """
    y_true = np.array([-4.0, -5.0, -20.0, -25.0])
    y_pred = np.array([-30.0, -30.0, -30.0, -30.0])

    s = challenge_score(y_true, y_pred, threshold=THR, clip_epsilon=0.001)
    assert s.counts.tp == 0
    assert s.f2 == 0.0
    assert s.f2_is_zero is True
    assert np.isinf(s.loss) and s.loss > 0
    assert not np.isnan(s.loss)          # explicitly NOT a silent NaN
    assert not s.is_defined
    assert s.n_high_risk_true == 2       # MSE_HR itself is still well-defined
    assert np.isfinite(s.mse_hr)


def test_f_beta_zero_convention_directly():
    from kelvins_conformal.metrics import ConfusionCounts

    c = ConfusionCounts(tp=0, fp=0, fn=5, tn=10)
    assert c.precision == 0.0
    assert c.recall == 0.0
    assert f_beta(c, beta=2.0) == 0.0    # defined convention, not NaN


# --- 4. n_HR == 0 ------------------------------------------------------------
def test_no_true_high_risk_events_is_unscorable_and_flagged():
    """MSE_HR over an empty set is undefined -> the subset cannot be scored."""
    y_true = np.array([-20.0, -25.0, -30.0])
    y_pred = np.array([-19.0, -30.0, -30.0])

    s = challenge_score(y_true, y_pred, threshold=THR, clip_epsilon=0.001)
    assert s.n_high_risk_true == 0
    assert s.high_risk_empty is True
    assert np.isnan(s.mse_hr)
    assert np.isnan(s.loss)
    assert not s.is_defined


def test_empty_input_raises_rather_than_returning_a_number():
    with pytest.raises(ValueError):
        challenge_score(np.array([]), np.array([]))


def test_non_finite_input_raises():
    with pytest.raises(ValueError):
        challenge_score(np.array([-4.0, np.nan]), np.array([-4.0, -4.0]))


# --- 5. clipping -------------------------------------------------------------
def test_clip_predictions_matches_documented_rule():
    pred = np.array([-4.0, -6.0, -6.0001, -7.0, -30.0])
    out = clip_predictions(pred, THR, 0.001)
    # At or above -6 untouched; strictly below -6 -> exactly -6.001.
    assert out == pytest.approx(np.array([-4.0, -6.0, -6.001, -6.001, -6.001]))


def test_clipping_is_idempotent():
    pred = np.array([-3.0, -9.0, -30.0])
    once = clip_predictions(pred, THR, 0.001)
    twice = clip_predictions(once, THR, 0.001)
    assert once == pytest.approx(twice)


def test_clipping_changes_the_score_as_expected():
    """Clipping only ever helps MSE_HR on false negatives — the paper's rationale."""
    y_true = np.array([-5.0, -20.0])
    y_pred = np.array([-30.0, -30.0])
    unclipped = challenge_score(y_true, y_pred, threshold=THR, clip_epsilon=None)
    clipped = challenge_score(y_true, y_pred, threshold=THR, clip_epsilon=0.001)
    assert clipped.mse_hr < unclipped.mse_hr


# --- 6. perfect prediction ---------------------------------------------------
def test_perfect_prediction_gives_zero_loss():
    y = np.array([-4.0, -5.5, -8.0, -30.0])
    s = challenge_score(y, y.copy(), threshold=THR, clip_epsilon=None)
    assert s.f2 == pytest.approx(1.0)
    assert s.mse_hr == pytest.approx(0.0)
    assert s.loss == pytest.approx(0.0)
    assert s.is_defined


def test_score_is_a_pure_function_of_inputs():
    """Same inputs -> identical output object (determinism, CLAUDE.md §1)."""
    y_true = np.array([-4.0, -7.0, -6.0, -20.0])
    y_pred = np.array([-4.2, -5.0, -6.5, -21.0])
    a = challenge_score(y_true, y_pred)
    b = challenge_score(y_true, y_pred)
    assert isinstance(a, ChallengeScore)
    assert a == b


# --- coverage ----------------------------------------------------------------
def test_empirical_coverage_hand_computed():
    y = np.array([0.0, 1.0, 2.0, 3.0])
    lo = np.array([-1.0, 0.5, 5.0, 2.9])
    hi = np.array([1.0, 1.5, 6.0, 3.1])
    # covered: y0 in [-1,1] yes; y1 in [0.5,1.5] yes; y2=2 in [5,6] no; y3 in [2.9,3.1] yes
    assert empirical_coverage(y, lo, hi) == pytest.approx(0.75)


def test_coverage_endpoints_are_inclusive():
    assert empirical_coverage(np.array([1.0]), np.array([1.0]), np.array([1.0])) == 1.0


def test_coverage_rejects_reversed_intervals():
    with pytest.raises(ValueError):
        empirical_coverage(np.array([0.0]), np.array([1.0]), np.array([-1.0]))
