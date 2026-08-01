"""E4 — statistical power analysis for coverage estimation (the Gate 1 engine).

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``power``): answer the
question the whole project rests on — *given how few high-risk events exist, can
empirical coverage be estimated with useful precision?* — marginally and per
mission group. It consumes counts and labels only; no model is required or used
(EXPERIMENT_PLAN.md E4 inputs).

The simulation model
--------------------
Two independent sources of randomness govern how precisely a coverage number can
be pinned down. Both are simulated; conflating them would understate uncertainty.

1. **Calibration-set randomness.** For split conformal with ``n_cal`` calibration
   points at nominal level ``1 - alpha``, the coverage *achieved on a fresh test
   point*, conditional on the calibration draw, is a random variable:

       C | calibration  ~  Beta(n_cal + 1 - l,  l),      l = floor(alpha * (n_cal + 1))

   This is the standard finite-sample result for the coverage distribution of
   split-conformal prediction sets (Vovk 2012; Angelopoulos & Bates, §3.2). Its
   mean is at least ``1 - alpha``, and its spread shrinks as ``n_cal`` grows —
   this is precisely what varying the calibration fraction changes.

2. **Test-set estimation noise.** Having drawn a conditional coverage ``p``, the
   observed indicator for each of ``n_test`` evaluation events is Bernoulli(p), so
   the empirical coverage estimate is ``Binomial(n_test, p) / n_test``.

For each configuration we repeat (1) then (2), and on each repetition compute an
event-level bootstrap percentile CI for the coverage estimate. The reported
precision is the **median 95% CI half-width** across repetitions, in percentage
points, together with the spread across repetitions.

Everything here is a pure function of (config, seed). No test-set outcome, model
output, or fitted quantity enters — E4 is a Monte Carlo study of achievable
precision, not an evaluation of any predictor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


def conformal_coverage_beta_params(n_cal: int, alpha: float) -> tuple[float, float]:
    """Beta parameters of split-conformal coverage given ``n_cal`` calibration points.

    Returns ``(a, b)`` for ``Beta(a, b) = Beta(n_cal + 1 - l, l)`` with
    ``l = floor(alpha * (n_cal + 1))``.

    Raises if ``n_cal`` is too small for the nominal level to be attainable at all
    (``l < 1``), which is itself a meaningful power finding rather than an error to
    paper over: with fewer than ``1/alpha - 1`` calibration points, split conformal
    cannot produce a finite interval at that level.
    """
    if n_cal < 1:
        raise ValueError(f"n_cal must be >= 1, got {n_cal}")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    ell = int(np.floor(alpha * (n_cal + 1)))
    if ell < 1:
        raise ValueError(
            f"n_cal={n_cal} is too small for nominal level {1 - alpha:.2f}: "
            f"floor(alpha*(n_cal+1)) = {ell} < 1, so no finite conformal interval exists"
        )
    return float(n_cal + 1 - ell), float(ell)


def clopper_pearson_half_width_pp(k: int, n: int, level: float = 0.95) -> float:
    """Half-width (in percentage points) of the exact Clopper-Pearson interval.

    Why this exists alongside the bootstrap
    ---------------------------------------
    The percentile bootstrap of a proportion is **degenerate** when the sample is
    all-ones or all-zeros: every resample then has the same mean, so the interval
    has exactly zero width. At this project's group sizes that is not a rare corner
    — with n = 5 evaluation events at 90% coverage, all five are covered in
    ``0.9^5 = 59%`` of draws, so the *median* bootstrap half-width across
    simulations is literally 0. Taken at face value that would make a 5-event group
    look infinitely precise, which is obviously false.

    Clopper-Pearson is exact and non-degenerate at the boundaries: for ``k == n`` it
    returns ``[alpha^(1/n), 1]``, correctly reporting a wide interval. It is used as
    the PRIMARY precision measure here, with the bootstrap reported alongside as
    EXPERIMENT_PLAN.md E4 specifies. OPEN_QUESTIONS.md Q-STAT-03 already recommends
    reporting both (option (c)), so this is the documented intent, not an ad hoc
    substitution.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if not (0 <= k <= n):
        raise ValueError(f"k must be in [0, n], got k={k}, n={n}")
    alpha = 1.0 - level
    lo = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return 100.0 * 0.5 * (hi - lo)


@dataclass(frozen=True)
class PrecisionResult:
    """Achievable precision of a coverage estimate for one configuration.

    ``median_cp_half_width_pp`` is the primary measure (exact, non-degenerate);
    ``median_half_width_pp`` is the bootstrap measure EXPERIMENT_PLAN.md E4 asks
    for, reported alongside together with ``degenerate_fraction`` so its small-n
    failure mode is visible rather than silently believed.
    """

    n_cal: int
    n_test: int
    nominal: float
    n_simulations: int
    median_half_width_pp: float          # bootstrap (degenerates at small n)
    q05_half_width_pp: float
    q95_half_width_pp: float
    median_cp_half_width_pp: float       # Clopper-Pearson exact (primary)
    degenerate_fraction: float           # share of sims with a zero-width bootstrap CI
    mean_coverage_estimate: float
    sd_coverage_estimate_pp: float
    beta_sd_pp: float          # spread contributed by calibration randomness alone
    binomial_sd_pp: float      # spread contributed by test-set noise alone

    def meets(self, bar_pp: float) -> bool:
        """Whether the achievable precision meets ``bar_pp`` percentage points.

        Judged on the exact Clopper-Pearson half-width, because the bootstrap
        statistic is degenerate exactly where the question matters most (small
        groups). See ``clopper_pearson_half_width_pp``.
        """
        return self.median_cp_half_width_pp <= bar_pp


def _bootstrap_half_widths(
    indicators: np.ndarray, n_boot: int, level: float, rng: np.random.Generator
) -> float:
    """Percentile-bootstrap CI half-width (in pp) for the mean of 0/1 indicators.

    Vectorised over resamples: draws an (n_boot, n) index matrix and averages.
    Equivalent to looping through ``metrics.bootstrap_statistic`` with
    ``np.mean``, but fast enough to sit inside a Monte Carlo loop.
    """
    n = indicators.size
    idx = rng.integers(0, n, size=(n_boot, n))
    draws = indicators[idx].mean(axis=1)
    alpha = 1.0 - level
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return 100.0 * 0.5 * (hi - lo)


def simulate_precision(
    n_cal: int,
    n_test: int,
    *,
    nominal: float = 0.90,
    n_simulations: int = 2000,
    n_bootstrap: int = 2000,
    level: float = 0.95,
    seed: int = 42,
) -> PrecisionResult:
    """Monte Carlo the achievable precision of a coverage estimate.

    Parameters
    ----------
    n_cal:
        Calibration-set size (number of events used to calibrate the interval).
    n_test:
        Number of evaluation events the coverage is measured on — for this project
        typically the number of HIGH-RISK events, which is the binding constraint.
    nominal:
        Nominal coverage level (1 - alpha).
    n_simulations:
        Repetitions of the (calibration draw -> test draw -> bootstrap) experiment.
    n_bootstrap:
        Bootstrap resamples per repetition (>= 2,000 per CLAUDE.md §9).

    Deterministic given ``seed``.
    """
    if n_test < 1:
        raise ValueError(f"n_test must be >= 1, got {n_test}")
    alpha = 1.0 - nominal
    a, b = conformal_coverage_beta_params(n_cal, alpha)

    rng = np.random.default_rng(seed)

    # 1. Calibration-induced conditional coverage, one draw per repetition.
    p_cond = rng.beta(a, b, size=n_simulations)
    # 2. Test-set outcome given that conditional coverage.
    successes = rng.binomial(n_test, p_cond)
    estimates = successes / n_test

    half_widths = np.empty(n_simulations, dtype=float)
    cp_half_widths = np.empty(n_simulations, dtype=float)
    for s in range(n_simulations):
        indicators = np.zeros(n_test, dtype=float)
        indicators[: successes[s]] = 1.0
        half_widths[s] = _bootstrap_half_widths(indicators, n_bootstrap, level, rng)
        cp_half_widths[s] = clopper_pearson_half_width_pp(int(successes[s]), n_test, level)

    beta_sd = np.sqrt(a * b / ((a + b) ** 2 * (a + b + 1.0)))
    binom_sd = np.sqrt(nominal * (1.0 - nominal) / n_test)

    return PrecisionResult(
        n_cal=int(n_cal), n_test=int(n_test), nominal=float(nominal),
        n_simulations=int(n_simulations),
        median_half_width_pp=float(np.median(half_widths)),
        q05_half_width_pp=float(np.percentile(half_widths, 5)),
        q95_half_width_pp=float(np.percentile(half_widths, 95)),
        median_cp_half_width_pp=float(np.median(cp_half_widths)),
        degenerate_fraction=float(np.mean(half_widths <= 0.0)),
        mean_coverage_estimate=float(np.mean(estimates)),
        sd_coverage_estimate_pp=float(100.0 * np.std(estimates, ddof=1)),
        beta_sd_pp=float(100.0 * beta_sd),
        binomial_sd_pp=float(100.0 * binom_sd),
    )


def minimum_group_size(
    n_cal: int,
    *,
    bar_pp: float,
    size_grid,
    nominal: float = 0.90,
    n_simulations: int = 500,
    n_bootstrap: int = 500,
    seed: int = 42,
) -> int | None:
    """Smallest group size on ``size_grid`` whose median CI half-width meets ``bar_pp``.

    This is the Q-CONF-02 merging floor under option (b) — derived from the power
    table rather than fixed by fiat. Returns ``None`` if **no** size on the grid
    meets the bar, which is itself a reportable Gate-1 finding.

    Uses lighter simulation settings than the headline table because it sweeps many
    sizes; the headline numbers for the chosen sizes are always recomputed at full
    settings by ``simulate_precision``.
    """
    for n in sorted(int(s) for s in size_grid):
        res = simulate_precision(
            n_cal, n, nominal=nominal, n_simulations=n_simulations,
            n_bootstrap=n_bootstrap, seed=seed,
        )
        if res.meets(bar_pp):
            return n
    return None
