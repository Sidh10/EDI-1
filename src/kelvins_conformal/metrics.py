"""Official challenge metric, coverage diagnostics, and the event-level bootstrap.

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``metrics``): implement the
competition's scoring rule exactly, plus the bootstrap machinery every reported
number depends on. This is statistical-core code (CLAUDE.md §1, §4): it is
unit-tested against hand-computed cases before it is trusted on real data.

The metric is the challenge's own, not ours. Definitions below are transcribed
from Uriot et al., arXiv:2008.03069v2 (the preprint of the Astrodynamics 2022
paper), §4.1 and §4.3:

  * §4.1 — an event is *high risk* iff its risk value satisfies ``r >= -6``
    (log10 Pc; the challenge fixed the notification threshold at 1e-6).
  * §4.3 Eq. (1) — ``L(r_hat) = MSE_HR(r, r_hat) / F2``, where F2 is computed over
    the WHOLE evaluated set using the two classes (high risk: r >= -6, low risk:
    r < -6), and MSE_HR is computed ONLY over the true-high-risk events:

        MSE_HR = (1 / N*) * sum_i  1_i * (r_i - r_hat_i)^2,
        1_i = 1 if r_i >= -6 else 0,   N* = sum_i 1_i

    Note carefully that the indicator uses the TRUE risk, not the prediction.
  * §4.3 — ``F_beta = (1 + beta^2) * p * q / (beta^2 * p + q)`` with beta = 2,
    p = precision and q = recall of the induced binary classification.
  * §4.3 — predictions are clipped: "all risk predictions can be clipped at a
    value slightly lower than 1e-6 to improve the overall score ... the scores of
    the various teams are reported after the clipping has been applied, using
    eps = 0.001". So a prediction below the threshold becomes ``-6 - 0.001``.

Undefined cases are DEFINED conventions here, never silent NaNs (METRICS.md §1/§2):
  * ``F2 == 0``  -> L is +inf, and ``ChallengeScore.f2_is_zero`` is set. The caller
    must surface the flag; the value is never quietly dropped.
  * ``n_HR == 0`` -> MSE_HR and therefore L are undefined; both are NaN and
    ``ChallengeScore.n_high_risk_true == 0`` marks the subset as unscorable.
  * F2 with zero precision AND zero recall -> 0.0 by convention (METRICS.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# --- binary classification pieces -------------------------------------------


@dataclass(frozen=True)
class ConfusionCounts:
    """Confusion matrix of the induced high/low-risk classification."""

    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        """TP / (TP + FP); 0.0 by convention when nothing is predicted positive."""
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        """TP / (TP + FN); 0.0 by convention when there are no true positives."""
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0


def confusion_counts(
    y_true: np.ndarray, y_pred: np.ndarray, threshold: float
) -> ConfusionCounts:
    """Confusion counts from thresholding both truth and prediction at ``threshold``.

    High risk is ``value >= threshold`` (challenge §4.1: ``r >= -6``).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError(f"shape mismatch: y_true {y_true.shape} vs y_pred {y_pred.shape}")
    if y_true.size == 0:
        raise ValueError("cannot compute confusion counts on an empty set")
    if not np.all(np.isfinite(y_true)) or not np.all(np.isfinite(y_pred)):
        raise ValueError("y_true/y_pred contain non-finite values; refusing to score")

    t = y_true >= threshold
    p = y_pred >= threshold
    return ConfusionCounts(
        tp=int(np.sum(t & p)),
        fp=int(np.sum(~t & p)),
        fn=int(np.sum(t & ~p)),
        tn=int(np.sum(~t & ~p)),
    )


def f_beta(counts: ConfusionCounts, beta: float = 2.0) -> float:
    """F_beta = (1 + beta^2) * p * q / (beta^2 * p + q), 0.0 when p == q == 0.

    The zero convention is explicit (METRICS.md §2): "must be handled as a defined
    convention (typically 0) rather than a silent NaN".
    """
    p = counts.precision
    q = counts.recall
    denom = (beta * beta * p) + q
    if denom == 0.0:
        return 0.0
    return (1.0 + beta * beta) * p * q / denom


# --- the challenge score ----------------------------------------------------


def clip_predictions(y_pred: np.ndarray, threshold: float, epsilon: float) -> np.ndarray:
    """Apply the challenge's documented prediction clipping (§4.3).

    Any prediction below ``threshold`` is set to ``threshold - epsilon``. Predictions
    at or above the threshold are untouched. With the challenge's values this maps
    everything below -6 to exactly -6.001.
    """
    y_pred = np.asarray(y_pred, dtype=float)
    return np.where(y_pred < threshold, threshold - epsilon, y_pred)


@dataclass(frozen=True)
class ChallengeScore:
    """Result of the official challenge metric, with its edge-case flags."""

    loss: float           # L = MSE_HR / F2  (+inf if F2 == 0; NaN if n_HR == 0)
    mse_hr: float         # NaN if n_HR == 0
    f2: float
    n_events: int
    n_high_risk_true: int
    n_high_risk_pred: int
    counts: ConfusionCounts
    f2_is_zero: bool      # True -> loss is +inf by the documented convention
    high_risk_empty: bool  # True -> subset is unscorable (MSE_HR undefined)

    @property
    def is_defined(self) -> bool:
        """Whether ``loss`` is a finite, interpretable number."""
        return not (self.f2_is_zero or self.high_risk_empty)


def challenge_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    threshold: float = -6.0,
    beta: float = 2.0,
    clip_epsilon: float | None = 0.001,
) -> ChallengeScore:
    """Compute the official challenge loss L = MSE_HR / F2.

    Parameters
    ----------
    y_true, y_pred:
        Per-EVENT true and predicted final log10 risk. One entry per event — never
        per CDM row (invariant I3).
    threshold:
        High-risk threshold on the log10 risk (challenge: -6.0).
    beta:
        F-score beta (challenge: 2.0).
    clip_epsilon:
        If not None, apply the challenge's documented prediction clipping before
        scoring (predictions below ``threshold`` become ``threshold - epsilon``).
        Pass None to score raw, unclipped predictions.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if clip_epsilon is not None:
        y_pred = clip_predictions(y_pred, threshold, clip_epsilon)

    counts = confusion_counts(y_true, y_pred, threshold)
    f2 = f_beta(counts, beta=beta)

    is_hr_true = y_true >= threshold
    n_hr = int(np.sum(is_hr_true))

    if n_hr == 0:
        # Documented convention: MSE_HR over an empty set is undefined, so the
        # subset cannot be scored with L at all (METRICS.md §1, §3).
        return ChallengeScore(
            loss=float("nan"), mse_hr=float("nan"), f2=f2,
            n_events=int(y_true.size), n_high_risk_true=0,
            n_high_risk_pred=counts.tp + counts.fp, counts=counts,
            f2_is_zero=(f2 == 0.0), high_risk_empty=True,
        )

    mse_hr = float(np.mean((y_true[is_hr_true] - y_pred[is_hr_true]) ** 2))

    if f2 == 0.0:
        # Documented convention: L is undefined by division by zero -> +inf,
        # explicitly flagged. Never silently dropped (METRICS.md §1).
        loss = float("inf")
    else:
        loss = mse_hr / f2

    return ChallengeScore(
        loss=loss, mse_hr=mse_hr, f2=f2,
        n_events=int(y_true.size), n_high_risk_true=n_hr,
        n_high_risk_pred=counts.tp + counts.fp, counts=counts,
        f2_is_zero=(f2 == 0.0), high_risk_empty=False,
    )


# --- coverage ---------------------------------------------------------------


def empirical_coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Fraction of events whose truth lies within [lo, hi] (METRICS.md §4).

    Interval endpoints are inclusive.
    """
    y_true = np.asarray(y_true, dtype=float)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if not (y_true.shape == lo.shape == hi.shape):
        raise ValueError("y_true, lo and hi must have identical shapes")
    if y_true.size == 0:
        raise ValueError("cannot compute coverage on an empty set")
    if np.any(hi < lo):
        raise ValueError("found hi < lo: interval endpoints are reversed")
    return float(np.mean((y_true >= lo) & (y_true <= hi)))


# --- event-level bootstrap --------------------------------------------------


@dataclass(frozen=True)
class BootstrapResult:
    """Percentile bootstrap interval plus the bookkeeping needed to audit it."""

    point: float
    lo: float
    hi: float
    n_resamples: int
    n_valid: int          # resamples on which the statistic was defined
    n_undefined: int      # resamples excluded because the statistic was undefined
    level: float

    @property
    def half_width(self) -> float:
        return 0.5 * (self.hi - self.lo)


def bootstrap_statistic(
    values: np.ndarray,
    statistic,
    *,
    n_resamples: int = 2000,
    level: float = 0.95,
    seed: int = 42,
    rng: np.random.Generator | None = None,
) -> BootstrapResult:
    """Percentile bootstrap CI for ``statistic`` over EVENT-level units.

    ``values`` is an array whose FIRST axis indexes independent units (events).
    Each resample draws ``len(values)`` units with replacement and recomputes the
    statistic. This is the only resampling entry point in the project, so that the
    event-level requirement (invariant I3, METRICS.md §12) is enforced in one place
    rather than re-implemented per experiment.

    A resample on which ``statistic`` is undefined (returns NaN — e.g. MSE_HR when
    the resample happens to contain no high-risk events) is EXCLUDED and counted,
    not silently treated as zero (METRICS.md §12 edge case).

    Determinism: given ``seed`` (or an explicit ``rng``) the result is exactly
    reproducible.
    """
    values = np.asarray(values)
    n = len(values)
    if n == 0:
        raise ValueError("cannot bootstrap an empty sample")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1, got {n_resamples}")
    if not (0.0 < level < 1.0):
        raise ValueError(f"level must be in (0, 1), got {level}")

    generator = rng if rng is not None else np.random.default_rng(seed)
    point = float(statistic(values))

    draws = np.empty(n_resamples, dtype=float)
    for b in range(n_resamples):
        idx = generator.integers(0, n, size=n)
        draws[b] = statistic(values[idx])

    finite = np.isfinite(draws)
    n_valid = int(np.sum(finite))
    if n_valid == 0:
        raise ValueError(
            "the statistic was undefined on every bootstrap resample; "
            "refusing to report an interval (fail loud, CLAUDE.md §1)"
        )
    alpha = 1.0 - level
    lo, hi = np.percentile(draws[finite], [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return BootstrapResult(
        point=point, lo=float(lo), hi=float(hi),
        n_resamples=n_resamples, n_valid=n_valid,
        n_undefined=int(n_resamples - n_valid), level=level,
    )


def bootstrap_challenge_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    threshold: float = -6.0,
    beta: float = 2.0,
    clip_epsilon: float | None = 0.001,
    n_resamples: int = 2000,
    level: float = 0.95,
    seed: int = 42,
) -> dict[str, BootstrapResult]:
    """Event-level bootstrap CIs on L, MSE_HR and F2.

    Both components are recomputed inside each resample and only then divided —
    the ratio is never resampled directly (METRICS.md §1, confidence-intervals
    entry). Resamples where L is undefined (no high-risk events drawn, or F2 == 0)
    are excluded and counted by ``bootstrap_statistic``.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    paired = np.stack([y_true, y_pred], axis=1)  # first axis = events

    def _score(rows: np.ndarray, field: str) -> float:
        s = challenge_score(
            rows[:, 0], rows[:, 1],
            threshold=threshold, beta=beta, clip_epsilon=clip_epsilon,
        )
        value = getattr(s, field)
        # +inf (F2 == 0) is non-finite and is therefore excluded-and-counted by the
        # bootstrap driver, exactly like the undefined-MSE_HR case.
        return float(value)

    out = {}
    for field in ("loss", "mse_hr", "f2"):
        out[field] = bootstrap_statistic(
            paired, lambda rows, f=field: _score(rows, f),
            n_resamples=n_resamples, level=level, seed=seed,
        )
    return out
