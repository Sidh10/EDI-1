"""Weighted split-conformal intervals — Contribution 1 (E11).

Assembles the pieces: a likelihood-ratio weight vector (``weights``), the
finite-sample weighted quantile (``split.conformal_quantile``), and the mandatory
Q-SEL-03 diagnostics (``diagnostics``) into per-test-event intervals plus a
diagnostic bundle. Per-test-point weighting follows Tibshirani et al. (2019): the
threshold depends on the test point's own weight w(x), so in principle it varies
per event. For the rule-derived construction w(x) is (near-)constant across
supported test events — they all satisfy recency and carry the same test-marginal
proxy mix — so a single representative ``test_weight`` yields one shared threshold;
this is stated, not assumed away.

Nothing here inspects test labels. The weights are built from observable covariates
only (``weights`` module note), so applying them is legitimate covariate-shift
correction, and the exact finite-sample guarantee is entitled for the rule-derived
weights (Q-SEL-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import diagnostics as diag
from .split import Interval, conformal_quantile
from .weights import WeightVector


@dataclass(frozen=True)
class WeightedResult:
    interval: Interval
    alpha_effective: float          # target after any clipping bias inflation
    alpha_nominal: float
    weight_method: str
    diagnostics: dict = field(default_factory=dict)


def weighted_interval(
    pred_test: np.ndarray,
    scores_cal: np.ndarray,
    weights: WeightVector,
    alpha: float,
    *,
    sided: str = "two",
    cal_covariates: dict[str, np.ndarray] | None = None,
    enable_clip: bool = True,
) -> WeightedResult:
    """Weighted split-conformal interval on the test points, with full diagnostics.

    Parameters
    ----------
    pred_test:
        Base-learner point predictions on the test events.
    scores_cal:
        Calibration nonconformity scores (one per event; absolute residuals for
        ``sided="two"``, signed for ``sided="upper"``).
    weights:
        A ``WeightVector`` aligned with ``scores_cal``.
    alpha:
        Nominal miscoverage level.
    cal_covariates:
        Optional {name: array} of calibration covariates for ASMD balance reporting
        (E1-flagged covariates: risk level, time-to-TCA of the latest CDM).
    enable_clip:
        Whether to apply the conditional (k_hat-triggered) clipping policy.
    """
    pred_test = np.asarray(pred_test, dtype=float)
    scores_cal = np.asarray(scores_cal, dtype=float)
    w = np.asarray(weights.w, dtype=float)
    if w.shape != scores_cal.shape:
        raise ValueError("weights and calibration scores must align (one per event)")

    # --- mandatory diagnostics on the raw weights (Q-SEL-03 Decision A) ---
    n = int(w.size)
    n_eff = diag.effective_sample_size(w)
    k_hat = diag.pareto_khat(w)
    summary = diag.weight_summary(w)
    asmd_report = {}
    if cal_covariates:
        for name, vals in cal_covariates.items():
            asmd_report[name] = diag.asmd(np.asarray(vals, dtype=float), w)

    # --- conditional clipping (Q-SEL-03 Decision B) ---
    alpha_eff = alpha
    clip = diag.conditional_clip(w) if enable_clip else None
    w_used = w
    if clip is not None and clip.clipped:
        w_used = clip.w
        # Inflate the target coverage to absorb the clip-induced downward bias:
        # aim slightly higher so the realised level is restored toward nominal.
        alpha_eff = max(alpha - clip.bias_delta, 1e-6)

    # --- the weighted quantile and interval ---
    q = conformal_quantile(
        scores_cal, alpha_eff, weights=w_used, test_weight=weights.test_weight
    )
    if sided == "two":
        interval = Interval(lo=pred_test - q, hi=pred_test + q)
    elif sided == "upper":
        interval = Interval(lo=np.full_like(pred_test, -np.inf), hi=pred_test + q)
    else:
        raise ValueError(f"sided must be 'two' or 'upper', got {sided!r}")

    diagnostics = {
        "n_calibration": n,
        "n_effective": n_eff,
        "n_over_neff": (n / n_eff) if n_eff > 0 else float("inf"),
        "pareto_khat": k_hat,
        "khat_band": diag.khat_band(k_hat),
        "weight_summary": summary,
        "asmd": asmd_report,
        "clipped": bool(clip.clipped) if clip is not None else False,
        "clip_bound": float(clip.bound) if clip is not None else float("inf"),
        "clipped_fraction": float(clip.clipped_fraction) if clip is not None else 0.0,
        "clip_bias_delta": float(clip.bias_delta) if clip is not None else 0.0,
        "quantile": float(q),
        "test_weight": float(weights.test_weight),
        "weight_method": weights.method,
    }
    return WeightedResult(
        interval=interval, alpha_effective=alpha_eff, alpha_nominal=alpha,
        weight_method=weights.method, diagnostics=diagnostics,
    )
