"""Analytic covariate-shift validation of weighted conformal (CLAUDE.md §4, I5, R4).

This is the highest-stakes test in the project: a weighted-CP implementation error
would invalidate the headline contribution (PROJECT_KNOWLEDGE R4, "Very High").
The construction is validated against a covariate shift known in closed form,
BEFORE it touches real data:

  1. Under a KNOWN covariate shift, naive split conformal UNDER-covers on the
     shifted test set, and weighted conformal with the true likelihood ratio
     RESTORES coverage to nominal. (The E10 -> E11 story, in a controlled setting.)
  2. Uniform weights make weighted conformal identical to naive split conformal.
  3. The diagnostics behave as specified: n_eff <= n; Pareto k_hat bands; ASMD
     moves toward the shifted mean; clipping triggers only on heavy tails and
     records its bias.
  4. gamma_divergence is ~1 for matching weights and large for mismatched ones.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.conformal import diagnostics as diag
from kelvins_conformal.conformal.split import split_interval
from kelvins_conformal.conformal.weighted import weighted_interval
from kelvins_conformal.conformal.weights import (
    WeightVector,
    classifier_weights,
    gamma_divergence,
    rule_derived_weights,
)


# --- 1. the headline property: weighting restores coverage under known shift ---
def test_weighting_restores_coverage_under_known_covariate_shift():
    """Calibration X ~ N(0,1); test X ~ N(1,1). Y|X has X-dependent noise scale,
    so the shift genuinely breaks naive coverage. The true likelihood ratio
    w(x) = p_test(x)/p_train(x) = exp(x - 0.5) must restore it."""
    rng = np.random.default_rng(100)
    alpha = 0.1
    n_cal, n_test, reps = 800, 800, 200

    naive_cov, weighted_cov = [], []
    for _ in range(reps):
        x_cal = rng.normal(0.0, 1.0, size=n_cal)
        x_test = rng.normal(1.0, 1.0, size=n_test)
        # Heteroscedastic truth: residual scale grows with x, so the test region
        # (larger x) has systematically larger residuals -> naive under-covers.
        def resid(x):
            return rng.normal(0.0, 0.5 + 0.5 * np.abs(x))
        r_cal = np.array([resid(v) for v in x_cal])
        r_test = np.array([resid(v) for v in x_test])
        scores = np.abs(r_cal)

        # naive
        iv_n = split_interval(np.zeros(n_test), scores, alpha, sided="two")
        naive_cov.append(np.mean(iv_n.covers(r_test)))

        # weighted with the TRUE likelihood ratio for N(1,1)/N(0,1) = exp(x-0.5)
        w = np.exp(x_cal - 0.5)
        wv = WeightVector(w=w, method="rule", test_weight=float(np.mean(np.exp(x_test - 0.5))))
        res = weighted_interval(np.zeros(n_test), scores, wv, alpha, sided="two",
                                enable_clip=False)
        weighted_cov.append(np.mean(res.interval.covers(r_test)))

    naive = float(np.mean(naive_cov))
    weighted = float(np.mean(weighted_cov))
    # Naive under-covers materially; weighted is restored close to nominal.
    assert naive < (1 - alpha) - 0.02, f"expected naive under-coverage, got {naive:.3f}"
    assert abs(weighted - (1 - alpha)) < 0.02, f"weighted not restored: {weighted:.3f}"
    assert weighted > naive, "weighting should improve coverage under this shift"


# --- 2. uniform weights == naive ---------------------------------------------
def test_uniform_weights_reduce_to_naive_split():
    rng = np.random.default_rng(101)
    scores = np.abs(rng.normal(size=300))
    pred = rng.normal(size=50)
    wv = WeightVector(w=np.ones(300), method="rule", test_weight=1.0)
    res = weighted_interval(pred, scores, wv, 0.1, sided="two", enable_clip=False)
    iv = split_interval(pred, scores, 0.1, sided="two")
    np.testing.assert_allclose(res.interval.lo, iv.lo)
    np.testing.assert_allclose(res.interval.hi, iv.hi)


# --- 3. diagnostics -----------------------------------------------------------
def test_effective_sample_size_bounds():
    assert diag.effective_sample_size(np.ones(100)) == pytest.approx(100.0)
    # One dominant weight -> n_eff near 1.
    w = np.array([1e6] + [1.0] * 99)
    assert diag.effective_sample_size(w) < 2.0
    # n_eff never exceeds n.
    rng = np.random.default_rng(7)
    w = rng.uniform(0.1, 5, size=200)
    assert diag.effective_sample_size(w) <= 200.0 + 1e-9


def test_pareto_khat_bands():
    rng = np.random.default_rng(8)
    # Light tail (uniform weights) -> low k_hat.
    light = diag.pareto_khat(rng.uniform(0.5, 1.5, size=4000))
    assert light < 0.5 or np.isnan(light)
    # Heavy tail (Pareto-distributed weights) -> high k_hat.
    heavy = diag.pareto_khat(rng.pareto(a=1.2, size=4000) + 1)
    assert heavy > 0.5
    assert "k" in diag.khat_band(heavy)


def test_khat_band_labels():
    assert "stable" in diag.khat_band(0.3)
    assert "flagged" in diag.khat_band(0.6)
    assert "clipping required" in diag.khat_band(0.85)
    assert "invalid" in diag.khat_band(1.5)
    assert "undiagnosable" in diag.khat_band(float("nan"))


def test_asmd_moves_toward_weighted_mean():
    x = np.array([0.0, 0.0, 0.0, 10.0, 10.0, 10.0])
    # Weights favouring the high values move the mean up -> positive ASMD.
    w = np.array([1.0, 1.0, 1.0, 9.0, 9.0, 9.0])
    assert diag.asmd(x, w) > 0.5
    # Uniform weights -> zero ASMD (no movement).
    assert diag.asmd(x, np.ones(6)) == pytest.approx(0.0, abs=1e-9)


def test_conditional_clip_only_triggers_on_heavy_tail():
    rng = np.random.default_rng(9)
    light = rng.uniform(0.5, 1.5, size=3000)
    res_light = diag.conditional_clip(light)
    assert not res_light.clipped

    heavy = rng.pareto(a=1.1, size=3000) + 1
    res_heavy = diag.conditional_clip(heavy)
    if res_heavy.khat_before > 0.7:
        assert res_heavy.clipped
        assert res_heavy.bias_delta > 0
        assert res_heavy.clipped_fraction > 0
        assert res_heavy.khat_after <= res_heavy.khat_before


def test_positivity_partition_counts_and_flags_unsupported():
    recency = np.array([True, True, False, True, False])
    p = diag.positivity_partition(recency)
    assert p.n_supported == 3
    assert p.n_unsupported == 2
    assert p.supported.tolist() == [True, True, False, True, False]


# --- 4. weight constructions --------------------------------------------------
def test_rule_derived_weights_upweight_highrisk_and_zero_nonrecency():
    recency = np.array([True, True, False, True])
    risk_proxy = np.array([-4.0, -20.0, -4.0, -8.0])   # threshold -6
    wv = rule_derived_weights(
        recency, risk_proxy,
        test_high_risk_prevalence=0.069, train_high_risk_prevalence=0.028,
        high_risk_threshold=-6.0,
    )
    # High-risk-proxy & recency event gets the largest weight.
    assert np.argmax(wv.w) == 0
    # Non-recency event gets exactly zero (hard filter, default epsilon=0).
    assert wv.w[2] == 0.0
    # Enrichment factor ~ 0.069/0.028 applied to the high bucket.
    assert wv.w[0] == pytest.approx(0.069 / 0.028, rel=1e-6)


def test_classifier_weights_are_odds():
    p = np.array([0.5, 0.9, 0.1])
    wv = classifier_weights(p)
    np.testing.assert_allclose(wv.w, [1.0, 9.0, 1.0 / 9.0], rtol=1e-6)


def test_gamma_divergence_is_one_for_proportional_weights():
    rng = np.random.default_rng(11)
    w = rng.uniform(0.1, 3, size=200)
    assert gamma_divergence(w, w) == pytest.approx(1.0, abs=1e-9)
    assert gamma_divergence(w, 5.0 * w) == pytest.approx(1.0, abs=1e-9)  # scale-invariant


def test_gamma_divergence_large_for_mismatch():
    rng = np.random.default_rng(12)
    w1 = rng.uniform(0.1, 1, size=200)
    w2 = rng.uniform(0.1, 1, size=200)  # independent -> shapes disagree
    assert gamma_divergence(w1, w2) > 2.0


def test_weighted_interval_reports_full_diagnostic_set():
    rng = np.random.default_rng(13)
    scores = np.abs(rng.normal(size=400))
    pred = rng.normal(size=100)
    w = np.exp(rng.normal(size=400))
    wv = WeightVector(w=w, method="rule", test_weight=1.0)
    res = weighted_interval(pred, scores, wv, 0.1, sided="two",
                            cal_covariates={"risk": rng.normal(size=400)})
    d = res.diagnostics
    for key in ("n_calibration", "n_effective", "pareto_khat", "khat_band",
                "weight_summary", "asmd", "clipped", "quantile", "test_weight"):
        assert key in d, f"diagnostic {key} missing"
    assert d["n_effective"] <= d["n_calibration"]
    assert "risk" in d["asmd"]
