"""Likelihood-ratio weights for weighted conformal prediction (Q-SEL-01, resolved).

Weighted conformal corrects a covariate shift P_test(X) != P_train(X) while
assuming P(Y|X) is unchanged. The weights are the likelihood ratio
w(x) = dP_test/dP_train (x). Crucially they are functions of OBSERVABLE covariates
only: the test INPUTS are observable (the shift is known/estimable from unlabeled
test inputs), while the test LABELS remain hidden. Weighting on the true high-risk
label would not be covariate shift and would forfeit the exact finite-sample
guarantee — so we never do it (see the module note below).

Two constructions (Q-SEL-01, resolved 2026-09-15):
  * RULE-DERIVED (primary): a bucketed likelihood ratio over the two selection axes
    the dataset's creators documented and Phase 0 (E1) confirmed — the
    latest-CDM-within-1-day recency filter and the high-risk enrichment, the latter
    operationalised on an OBSERVABLE pre-cutoff risk proxy (r_last), not the label.
    Because the official test set satisfies the recency filter ~100%, the recency
    axis behaves as a near-hard filter; the resulting loss of calibration support is
    not hidden — it is exactly what the Q-SEL-03 effective-sample-size and
    positivity diagnostics report.
  * CLASSIFIER-ESTIMATED (secondary robustness check): a probabilistic classifier
    p_hat(x) discriminating calibration-pool from official-test events on safe
    covariates, giving w_hat(x) = p_hat(x) / (1 - p_hat(x)).

The exact finite-sample coverage claim is entitled ONLY to the rule-derived
weights; classifier-weighted results carry a weaker (non-exact) guarantee and must
be labelled as such (Q-SEL-01 binding manuscript-language requirement). Agreement
between the two is quantified by ``gamma_divergence``.

References:
  Tibshirani et al. (2019), "Conformal Prediction Under Covariate Shift" — the
    weighted construction; the known-test-input-distribution case notes that
    knowing it "absolves the need for density estimation" and permits exact weights.
  Sugiyama, Suzuki, Kanamori (2012), density-ratio estimation — the
    classifier/probabilistic-classification density-ratio form w = p/(1-p).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class WeightVector:
    """Calibration weights plus the bookkeeping the diagnostics and report need."""

    w: np.ndarray                 # unnormalized, >= 0, one per calibration event
    method: str                   # "rule" | "classifier"
    test_weight: float            # representative w(x) for a test point
    supported: np.ndarray | None = None  # bool mask: calibration events with w > 0

    def normalized(self) -> np.ndarray:
        total = self.w.sum()
        if total <= 0:
            raise ValueError("weights sum to zero")
        return self.w / total


def rule_derived_weights(
    recency_ok: np.ndarray,
    risk_proxy: np.ndarray,
    *,
    test_high_risk_prevalence: float,
    train_high_risk_prevalence: float,
    high_risk_threshold: float,
    recency_epsilon: float = 0.0,
) -> WeightVector:
    """Rule-derived likelihood ratio from the two documented selection axes.

    Parameters
    ----------
    recency_ok:
        Boolean per calibration event: does its FINAL CDM fall within the documented
        recency window of TCA? (observable timing, not a label).
    risk_proxy:
        Observable pre-cutoff risk level per calibration event (r_last), used as the
        covariate proxy for the enrichment axis. NOT the target label.
    test_high_risk_prevalence, train_high_risk_prevalence:
        The documented / E1-measured high-risk prevalence in test vs. train, whose
        ratio is the enrichment factor.
    high_risk_threshold:
        The challenge high-risk cutoff (log10 Pc), applied to ``risk_proxy``.
    recency_epsilon:
        Weight floor for events failing the recency filter. Default 0.0 makes the
        filter hard (the honest likelihood ratio, since the test set puts ~zero mass
        there); a tiny positive value can be used to study sensitivity.

    Returns
    -------
    ``WeightVector`` with ``method="rule"``. The enrichment factor up-weights
    high-proxy events and down-weights low-proxy events so the reweighted calibration
    high-proxy prevalence moves toward the documented test prevalence.
    """
    recency_ok = np.asarray(recency_ok, dtype=bool)
    risk_proxy = np.asarray(risk_proxy, dtype=float)
    if recency_ok.shape != risk_proxy.shape:
        raise ValueError("recency_ok and risk_proxy must have the same shape")
    if not (0.0 < test_high_risk_prevalence < 1.0):
        raise ValueError("test_high_risk_prevalence must be in (0, 1)")
    if not (0.0 < train_high_risk_prevalence < 1.0):
        raise ValueError("train_high_risk_prevalence must be in (0, 1)")

    high = risk_proxy >= high_risk_threshold
    # Likelihood ratio on the observable risk-proxy bucket: P_test(bucket)/P_train(bucket).
    lr_high = test_high_risk_prevalence / train_high_risk_prevalence
    lr_low = (1.0 - test_high_risk_prevalence) / (1.0 - train_high_risk_prevalence)
    w_risk = np.where(high, lr_high, lr_low)

    w_recency = np.where(recency_ok, 1.0, recency_epsilon)
    w = w_risk * w_recency

    supported = w > 0
    # Representative test-point weight: a test event satisfies recency and carries the
    # test-marginal mix of proxy buckets.
    test_weight = float(
        test_high_risk_prevalence * lr_high + (1.0 - test_high_risk_prevalence) * lr_low
    )
    return WeightVector(w=w, method="rule", test_weight=test_weight, supported=supported)


def classifier_weights(
    p_test: np.ndarray,
    *,
    clip_p: float = 1e-6,
) -> WeightVector:
    """Density-ratio weights from a discriminative classifier, w = p/(1-p).

    ``p_test`` is the fitted probability that each calibration event belongs to the
    official-test distribution (from a classifier trained on safe covariates only).
    Secondary/robustness method: its guarantee is non-exact (Q-SEL-01).
    """
    p = np.clip(np.asarray(p_test, dtype=float), clip_p, 1.0 - clip_p)
    w = p / (1.0 - p)
    return WeightVector(
        w=w, method="classifier", test_weight=float(np.mean(w)), supported=w > 0
    )


def gamma_divergence(w_rule: np.ndarray, w_classifier: np.ndarray) -> float:
    """Maximum multiplicative divergence gamma_hat between two weight specs.

    gamma_hat = sup_x max{ w_hat(x)/w(x), w(x)/w_hat(x) }, treating the rule-derived
    weight as the oracle (Q-SEL-01). gamma_hat -> 1 corroborates the classifier;
    large gamma_hat flags misspecification/overfitting. Both weight vectors are
    normalized to mean 1 first so the ratio measures shape, not scale.
    """
    w_rule = np.asarray(w_rule, dtype=float)
    w_hat = np.asarray(w_classifier, dtype=float)
    if w_rule.shape != w_hat.shape:
        raise ValueError("weight vectors must have the same shape")
    # Compare only where the rule-derived oracle has support (elsewhere the ratio is
    # undefined; those events are handled by the positivity partition, not here).
    mask = w_rule > 0
    if not np.any(mask):
        raise ValueError("rule-derived weights have no support")
    a = w_rule[mask] / np.mean(w_rule[mask])
    denom = np.mean(w_hat[mask])
    b = w_hat[mask] / denom if denom > 0 else w_hat[mask]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.maximum(a / b, b / a)
    ratio = ratio[np.isfinite(ratio)]
    return float(np.max(ratio)) if ratio.size else float("inf")
