"""kelvins_conformal — calibrated collision-risk forecasting toolkit.

Layered batch research pipeline (SOFTWARE_ARCHITECTURE.md §1): immutable data ->
deterministic computation -> evaluation -> reporting. This package holds the
statistical core; every stochastic component is seeded and every artifact is a
pure function of (raw data, config, code version, seed).

Phase 0 (E0-E3) modules only: config, ingest, data, labelnoise.pc_foster, cli.
Later phases add features, baselines, seqmodels, conformal/*, metrics, decision,
power, reporting (see EXPERIMENT_PLAN.md execution order).
"""

__version__ = "0.0.0"
