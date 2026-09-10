"""Weight diagnostics, conditional clipping, and positivity partition (Q-SEL-03).

Every weighted result in E11 (and E12's weighted variant) reports the full
mandatory diagnostic set below without exception, because a skewed weight
distribution can silently revive calibration-side imprecision that the Gate 1
analysis had ruled out for the UNWEIGHTED case (that finding was established for
uniform calibration; weighting can change it, and this must be visible in the
results, not discovered afterward).

Pareto k-hat bands (Q-SEL-03, confirmed against Vehtari, Gelman, Gabry, Simpson &
Yao — Pareto Smoothed Importance Sampling):
    k_hat < 0.5   : reliable, finite variance
    0.5 <= k < 0.7: flagged but PSIS-stabilised and empirically reliable
    k_hat > 0.7   : truncation bias dominates RMSE, standard-error estimates fail
                    -> clipping required
    k_hat > 1     : the weight mean does not exist -> importance weighting invalid

Clipping (Decision B) is NOT prophylactic — it triggers only when k_hat > 0.7.
When it triggers, the induced bias Delta_B = 1 - mean(min(w, B)) is computed
explicitly and the target coverage is inflated to absorb it (reported alongside).

Positivity (Decision C): test events split into a supported and an unsupported
region by a pre-registered threshold; coverage is claimed only on the supported
region, and the unsupported subpopulation is reported with its count and
composition, never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


def effective_sample_size(w: np.ndarray) -> float:
    """Kish effective sample size n_hat = (sum w)^2 / sum(w^2).

    Reported side by side with the raw calibration size n. A large n / n_hat gap
    means the weights concentrate on few events, shrinking the information the
    calibration set actually carries.
    """
    w = np.asarray(w, dtype=float)
    w = w[w > 0]
    if w.size == 0:
        return 0.0
    s1 = w.sum()
    s2 = np.sum(w * w)
    return float(s1 * s1 / s2) if s2 > 0 else 0.0


def pareto_khat(w: np.ndarray, *, tail_frac: float = 0.2, min_tail: int = 20) -> float:
    """Estimate the generalized-Pareto tail-shape k_hat of the weight distribution.

    Fits a generalized Pareto distribution to the upper-tail exceedances of the
    (positive) weights and returns its shape parameter k_hat, interpreted on the
    bands in the module docstring (heavy tail -> k_hat large; bounded/light tail ->
    k_hat < 0).

    Implementation note (flagged for the record): the Q-SEL-03 resolution names the
    Vehtari et al. PSIS diagnostic, whose k_hat IS the GPD shape parameter estimated
    by the Zhang & Stephens (2009) method. We estimate that same shape parameter by
    scipy's maximum-likelihood GPD fit rather than the Zhang-Stephens variant,
    because a vetted, tested estimator is preferable to a hand-rolled one for a
    correctness-critical statistical-core quantity (CLAUDE.md §1/§4). The
    interpretive bands (0.5/0.7/1.0) are defined on the shape parameter and are
    unchanged. This is a deliberate implementation deviation, recorded in the E9-E11
    checkpoint for Sidh.

    Returns nan when the positive tail is too short to fit (``< 2*min_tail`` positive
    weights) — undiagnosable, which the caller must report rather than treat as
    stable — and -inf for a degenerate all-equal tail (perfectly stable).
    """
    w = np.asarray(w, dtype=float)
    w = np.sort(w[w > 0])
    n = w.size
    if n < min_tail * 2:
        return float("nan")
    n_tail = max(min_tail, int(np.ceil(tail_frac * n)))
    n_tail = min(n_tail, n - 1)
    thresh = w[-n_tail - 1]
    x = w[-n_tail:] - thresh
    if np.allclose(x, 0.0):
        return float("-inf")
    x = x[x > 0]
    if x.size < min_tail:
        return float("nan")
    # scipy MLE GPD shape on the exceedances (location fixed at 0).
    shape, _loc, _scale = stats.genpareto.fit(x, floc=0.0)
    return float(shape)


def khat_band(k_hat: float) -> str:
    """Map k_hat to its interpretive band label."""
    if np.isnan(k_hat):
        return "undiagnosable (tail too short)"
    if k_hat < 0.5:
        return "stable (k<0.5)"
    if k_hat < 0.7:
        return "flagged, PSIS-stabilised (0.5<=k<0.7)"
    if k_hat <= 1.0:
        return "unreliable, clipping required (0.7<k<=1)"
    return "invalid, mean does not exist (k>1)"


def weight_summary(w: np.ndarray) -> dict:
    """Five-number summary plus max-weight-ratio Q_S of a weight distribution."""
    w = np.asarray(w, dtype=float)
    pos = w[w > 0]
    total = w.sum()
    return {
        "n": int(w.size),
        "n_positive": int(pos.size),
        "min": float(np.min(w)),
        "q25": float(np.percentile(w, 25)),
        "median": float(np.median(w)),
        "q75": float(np.percentile(w, 75)),
        "max": float(np.max(w)),
        "mean": float(np.mean(w)),
        "max_weight_ratio_Qs": float(np.max(w) / total) if total > 0 else float("nan"),
    }


def asmd(values: np.ndarray, w: np.ndarray) -> float:
    """Absolute Standardized Mean Difference of ``values`` before vs after weighting.

    ASMD = |mean_w - mean_unw| / sd_unw, on the covariates E1 flagged as divergent
    between splits (risk level, time-to-TCA of the latest CDM). A post-weighting
    value < 0.1 is the conventional adequate-balance threshold. Here it measures how
    far weighting moves the calibration covariate mean toward the test profile.
    """
    values = np.asarray(values, dtype=float)
    w = np.asarray(w, dtype=float)
    if values.shape != w.shape:
        raise ValueError("values and weights must have the same shape")
    sd = np.std(values, ddof=1)
    if sd == 0:
        return 0.0
    mean_unw = np.mean(values)
    total = w.sum()
    if total <= 0:
        return float("nan")
    mean_w = np.sum(w * values) / total
    return float(abs(mean_w - mean_unw) / sd)


@dataclass(frozen=True)
class ClipResult:
    w: np.ndarray
    clipped: bool
    bound: float
    clipped_fraction: float
    bias_delta: float          # Delta_B = 1 - mean(min(w_norm, B_norm)) ; 0 if not clipped
    khat_before: float
    khat_after: float


def conditional_clip(w: np.ndarray, *, khat_trigger: float = 0.7, quantile: float = 0.99) -> ClipResult:
    """Clip weights ONLY if the Pareto k_hat diagnostic indicates instability.

    Not prophylactic (Q-SEL-03 Decision B). If ``pareto_khat(w) > khat_trigger`` the
    weights are clipped at the pre-registered bound B = the ``quantile`` of the
    weight distribution, the clipped fraction and induced bias Delta_B are computed,
    and both are returned so the caller can inflate the target coverage and report
    them. If k_hat is in-band, the weights pass through unchanged.
    """
    w = np.asarray(w, dtype=float)
    k_before = pareto_khat(w)
    if np.isnan(k_before) or k_before <= khat_trigger:
        return ClipResult(w=w.copy(), clipped=False, bound=float("inf"),
                          clipped_fraction=0.0, bias_delta=0.0,
                          khat_before=k_before, khat_after=k_before)
    bound = float(np.quantile(w, quantile))
    w_clipped = np.minimum(w, bound)
    clipped_fraction = float(np.mean(w > bound))
    # Bias on the mean-1-normalized scale: how much total mass the clip removed.
    wn = w / np.mean(w)
    bn = bound / np.mean(w)
    bias_delta = float(1.0 - np.mean(np.minimum(wn, bn)))
    return ClipResult(
        w=w_clipped, clipped=True, bound=bound, clipped_fraction=clipped_fraction,
        bias_delta=bias_delta, khat_before=k_before, khat_after=pareto_khat(w_clipped),
    )


@dataclass(frozen=True)
class PositivityPartition:
    supported: np.ndarray       # bool mask over TEST events with adequate support
    n_supported: int
    n_unsupported: int
    threshold: float


def positivity_partition(
    test_recency_ok: np.ndarray,
    *,
    recency_required: bool = True,
) -> PositivityPartition:
    """Partition test events into supported / unsupported regions (Q-SEL-03 C).

    Under the rule-derived weights, a test event has calibration support only if the
    calibration pool contains events resembling it. The hard recency filter means a
    test event outside the supported covariate region has effectively zero support.
    The coverage guarantee is reported on the supported region; the unsupported
    subpopulation is counted and characterised by the caller, never dropped.

    (For the documented mechanism the recency filter is the binding positivity axis,
    so support is defined by it here; the threshold is pre-registered, not tuned.)
    """
    ok = np.asarray(test_recency_ok, dtype=bool)
    supported = ok if recency_required else np.ones_like(ok, dtype=bool)
    return PositivityPartition(
        supported=supported,
        n_supported=int(supported.sum()),
        n_unsupported=int((~supported).sum()),
        threshold=1.0,
    )
