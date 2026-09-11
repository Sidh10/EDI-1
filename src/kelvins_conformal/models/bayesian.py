"""E8 — steelmanned Bayesian uncertainty baseline (MC-dropout + deep ensemble).

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``seqmodels``/MC-dropout):
faithfully reproduce the closest prior-art uncertainty method — MC-dropout over
the E7 architecture family, as in Pinto et al. — and expose predictive
distributions so its *coverage* can be audited.

This is the paper's motivating evidence, so the baseline is deliberately
**steelmanned** (Q-BASE-02, resolved option (c)): its hyperparameters are tuned
for **its own best coverage**, on the internal validation split, using a search
budget equal to what E6 and E7 received. The budgets are reported side by side in
the E8 report so the fairness claim is auditable rather than asserted
(CLAUDE.md §10: never weaken a baseline to flatter our own method).

What "predictive distribution" means here
-----------------------------------------
MC-dropout gives an ensemble of point predictions ``{f_t(x)}`` from ``T`` stochastic
forward passes. Following the standard treatment (Gal & Ghahramani; Kendall &
Gal), the predictive distribution combines that **epistemic** spread with an
**aleatoric** noise term estimated on held-out data:

    mu(x)    = mean_t f_t(x)
    var(x)   = var_t f_t(x)  +  sigma^2

where ``sigma^2`` is the residual variance measured on the internal validation
split. Omitting the aleatoric term is the single most common way to make an
MC-dropout baseline look artificially bad on coverage — it would produce absurdly
narrow intervals and a coverage failure that is an artifact of our reproduction
rather than a property of the method. Including it is part of the steelman.

Intervals are Gaussian by default (``mu ± z * sqrt(var)``) with an empirical
quantile mode available; the choice is reported, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from scipy import stats

from .sequence import SequenceRegressor, SequenceResult, _forward_all, set_torch_seed


@dataclass(frozen=True)
class PredictiveDistribution:
    """Per-event predictive moments plus the raw MC samples behind them."""

    mean: np.ndarray            # (n_events,)
    std: np.ndarray             # (n_events,) total predictive sd
    epistemic_std: np.ndarray   # (n_events,) MC spread only
    aleatoric_std: float        # scalar residual noise estimated on validation
    samples: np.ndarray         # (n_samples, n_events) raw stochastic passes

    def interval(self, level: float, *, mode: str = "gaussian") -> tuple[np.ndarray, np.ndarray]:
        """Central predictive interval at nominal ``level``.

        ``mode="gaussian"`` uses ``mu ± z_{(1+level)/2} * std`` (the standard
        MC-dropout treatment). ``mode="empirical"`` takes percentiles of the MC
        samples *inflated* by the aleatoric term, which is the fairer empirical
        analogue when the sample distribution is skewed.
        """
        if not (0.0 < level < 1.0):
            raise ValueError(f"level must be in (0, 1), got {level}")
        alpha = 1.0 - level
        if mode == "gaussian":
            z = float(stats.norm.ppf(1.0 - alpha / 2.0))
            return self.mean - z * self.std, self.mean + z * self.std
        if mode == "empirical":
            lo_q, hi_q = 100 * alpha / 2, 100 * (1 - alpha / 2)
            lo = np.percentile(self.samples, lo_q, axis=0)
            hi = np.percentile(self.samples, hi_q, axis=0)
            # Widen by the aleatoric component the MC spread does not capture.
            z = float(stats.norm.ppf(1.0 - alpha / 2.0))
            return lo - z * self.aleatoric_std, hi + z * self.aleatoric_std
        raise ValueError(f"unknown interval mode: {mode!r}")


def mc_dropout_predict(
    result: SequenceResult,
    X: np.ndarray,
    lengths: np.ndarray,
    *,
    n_samples: int,
    aleatoric_std: float,
    seed: int,
    batch_size: int = 512,
) -> PredictiveDistribution:
    """Run ``n_samples`` stochastic forward passes with dropout ACTIVE.

    Dropout is enabled at inference by putting the module in train mode
    (``_forward_all(train_mode=True)``); no weights are updated because the whole
    pass is under ``torch.no_grad()``.
    """
    if n_samples < 2:
        raise ValueError(f"n_samples must be >= 2 to estimate a spread, got {n_samples}")
    set_torch_seed(seed)
    samples = np.stack([
        _forward_all(result.model, X, lengths, batch_size=batch_size, train_mode=True)
        for _ in range(n_samples)
    ])
    mean = samples.mean(axis=0)
    epistemic = samples.std(axis=0, ddof=1)
    total = np.sqrt(epistemic**2 + aleatoric_std**2)
    return PredictiveDistribution(
        mean=mean, std=total, epistemic_std=epistemic,
        aleatoric_std=float(aleatoric_std), samples=samples,
    )


def ensemble_predict(
    results: list[SequenceResult],
    X: np.ndarray,
    lengths: np.ndarray,
    *,
    aleatoric_std: float,
) -> PredictiveDistribution:
    """Deep-ensemble predictive distribution from independently-seeded members."""
    if len(results) < 2:
        raise ValueError("a deep ensemble needs at least 2 members")
    samples = np.stack([r.predict(X, lengths) for r in results])
    mean = samples.mean(axis=0)
    epistemic = samples.std(axis=0, ddof=1)
    total = np.sqrt(epistemic**2 + aleatoric_std**2)
    return PredictiveDistribution(
        mean=mean, std=total, epistemic_std=epistemic,
        aleatoric_std=float(aleatoric_std), samples=samples,
    )


def estimate_aleatoric_std(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Residual standard deviation on held-out data (the aleatoric term).

    Measured on the INTERNAL validation split — never on the official test set.
    """
    resid = np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float)
    if resid.size < 2:
        raise ValueError("need at least 2 residuals to estimate a standard deviation")
    return float(np.std(resid, ddof=1))


# --- calibration diagnostics -------------------------------------------------


def pit_values(
    y_true: np.ndarray, dist: PredictiveDistribution, *, mode: str = "gaussian"
) -> np.ndarray:
    """Probability-integral-transform values (METRICS.md §9).

    Under a perfectly calibrated predictive distribution these are Uniform(0, 1).
    """
    y_true = np.asarray(y_true, dtype=float)
    if mode == "gaussian":
        return np.asarray(stats.norm.cdf(y_true, loc=dist.mean, scale=dist.std), dtype=float)
    if mode == "empirical":
        return np.mean(dist.samples <= y_true[None, :], axis=0)
    raise ValueError(f"unknown PIT mode: {mode!r}")


def pit_uniformity_test(pit: np.ndarray) -> tuple[float, float]:
    """KS test of PIT values against Uniform(0, 1). Returns ``(statistic, p)``."""
    pit = np.asarray(pit, dtype=float)
    if pit.size < 2:
        raise ValueError("need at least 2 PIT values for a KS test")
    res = stats.kstest(pit, "uniform")
    return float(res.statistic), float(res.pvalue)


def reliability_curve(
    y_true: np.ndarray, dist: PredictiveDistribution, levels, *, mode: str = "gaussian"
) -> dict[float, float]:
    """Empirical coverage at each nominal level — the reliability diagram's data."""
    y_true = np.asarray(y_true, dtype=float)
    out: dict[float, float] = {}
    for level in levels:
        lo, hi = dist.interval(float(level), mode=mode)
        out[float(level)] = float(np.mean((y_true >= lo) & (y_true <= hi)))
    return out


def coverage_binomial_test(n_covered: int, n_total: int, nominal: float) -> float:
    """Two-sided binomial p-value for observed coverage against ``nominal``."""
    if n_total < 1:
        raise ValueError("n_total must be >= 1")
    return float(stats.binomtest(int(n_covered), int(n_total), float(nominal)).pvalue)


def make_mc_dropout_model(
    base: SequenceResult, dropout: float
) -> SequenceResult:
    """Return ``base`` with its dropout probability overridden.

    Used by the E8 steelman search, which tunes the *inference-time* dropout rate
    for coverage without retraining — the standard MC-dropout knob.
    """
    model = base.model
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.p = float(dropout)
    return base


def count_parameters(model: SequenceRegressor) -> int:
    """Trainable parameter count (reported alongside the search budgets)."""
    return int(sum(p.numel() for p in model.parameters() if p.requires_grad))
