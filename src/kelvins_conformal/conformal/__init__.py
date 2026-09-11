"""In-house conformal prediction layer (Phase 3, E9-E12).

This package is the project's headline contribution (Contribution 1: selection-
bias-aware weighted conformal prediction). Per SOFTWARE_ARCHITECTURE.md §9 the
*commodity* parts (plain split conformal) could in principle come from a library,
but the weighted correction is written in-house and unit-tested against analytic
covariate-shift toy cases, because a reviewer must be able to read our correction
rather than a dependency's internals (PROJECT_KNOWLEDGE.md R4: a weighted-CP
implementation error would invalidate the headline claim — "Very High" impact).

Modules:
  * ``split``       — the finite-sample conformal quantile (uniform and weighted),
                      the shared primitive; plain split-conformal intervals.
  * ``weights``     — rule-derived and classifier-estimated likelihood-ratio
                      weights, and the gamma-divergence agreement diagnostic
                      (Q-SEL-01).
  * ``diagnostics`` — effective sample size, Pareto k-hat tail diagnostic,
                      ASMD balance, weight summaries, conditional clipping with
                      explicit bias correction, and the positivity partition
                      (Q-SEL-03).
  * ``weighted``    — weighted split-conformal intervals assembled from the above
                      (E11, Contribution 1).

Calibration unit (Q-CONF-01, resolved 2026-09-15): exactly ONE nonconformity
score per event, calibrated separately per prediction horizon; within-event scores
across horizons are never pooled. All calibration draws from the full eligible
training pool, never a high-risk-only subset.
"""
