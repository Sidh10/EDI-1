# Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment

Coverage-valid uncertainty quantification for satellite conjunction risk, using conformal prediction on the ESA Kelvins Collision Avoidance Challenge dataset — explicitly correcting for the dataset's documented test-set selection bias and quantifying sensitivity to known label noise.

**Status:** Phases 0–4 implemented (E0–E12, E14; E13 skipped). **Gate 1 passed** — GO on marginal coverage, PIVOT dropping group-conditional analysis. **Gate 2 passed** — GO on Contribution 1, with the exact-coverage claim scoped to *two-sided* split-conformal marginal coverage. **Assumption A4 resolved** as a PARTIAL HOLD, so Contribution 2 runs in its scoped-M7 form (Q-LBL-01 option (b)). **Gate 3 (venue tier) is open** and awaits Sidh's review of E14. See `DECISIONS.md` for every decision and its rationale.

The evaluation harness is validated: our implementation of the official challenge metric reproduces the published LRP and CRP baseline scores to 4 decimal places (E5).

## What this is

Satellite operators receive a series of warning messages (CDMs) before a possible collision, each with an updated risk estimate. Existing machine-learning work on this problem predicts a single risk number, or an unverified confidence spread, without checking whether that confidence can be trusted. This project applies conformal prediction — a method with a distribution-free statistical guarantee — and addresses two flaws in the standard benchmark that all prior work has ignored: the test set was deliberately constructed to be non-random, and the risk labels themselves come from covariance estimates known to need correction.

Full context: `PROJECT_KNOWLEDGE.md` (what and why) → `SOFTWARE_ARCHITECTURE.md` (how it's built) → `EXPERIMENT_PLAN.md` (what gets run, in order) → `OPEN_QUESTIONS.md` (what's still undecided) → `CLAUDE.md` (operating rules for AI-assisted implementation) → `IMPLEMENTATION_PLAYBOOK.md` (phase-by-phase execution strategy) → `METRICS.md` (every evaluation quantity, precisely defined) → `REVIEWER_CHECKLIST.md` (adversarial pre-mortem against likely Q1/Q2 criticism).

## Quickstart

```bash
git clone <repo-url>
cd kelvins-conformal
uv sync --extra notebooks --extra dev --extra models
kc ingest          # E0: downloads + checksum-verifies the dataset, freezes it read-only
kc audit           # E1/E2/E3: renders reports/00_data_audit.html + 00b_pc_spike.html
kc baselines       # E5: validates the challenge metric vs published baseline scores
kc power           # E4: power analysis -> the Gate 1 decision table
kc baselines-phase2 # E6/E7/E8: train baselines + audit MC-dropout coverage (slow)
kc conformal       # E9-E11 (Gate 2 batch) and E12/CQR; --only gate2|cqr|all
kc labelnoise      # E14: label-noise sensitivity -> the Gate 3 input
kc decision        # E15: decision cost at matched alert budgets (slow; refits all learners)
                   #   --only rank-audit: Proposition 1 classification; --only threshold [--smoke]: expanded analysis
```

`kc reproduce-all` regenerates every manuscript number and figure; it is not implemented yet
(it arrives with the first manuscript figures). Available commands are only those whose
experiments exist: `ingest`, `audit`, `baselines`, `power`, `baselines-phase2`, `conformal`,
`labelnoise` and `decision` today.

No GPU required for the core pipeline; see `SOFTWARE_ARCHITECTURE.md` §9 for the full technology/compute breakdown.

## Data

ESA Kelvins Collision Avoidance Challenge dataset, Zenodo DOI [10.5281/zenodo.4463683](https://doi.org/10.5281/zenodo.4463683), licensed CC-BY 4.0 by the European Space Agency. Not redistributed in this repository; `kc ingest` downloads and checksum-verifies it directly from Zenodo. If you use this dataset, cite:

> Uriot, T., Izzo, D., Simões, L. F., et al. (2022). Spacecraft collision avoidance challenge: design and results of a machine learning competition. *Astrodynamics*, 6, 121–140.

## Current phase / gate status

_Updated at every gate. See `DECISIONS.md` for the authoritative log._

- [x] Blocking pre-Phase-0 questions resolved (Q-METH-01/02/03, Q-SEL-02)
- [x] Phase 0 — Foundation, audit, feasibility spikes *(E0–E3)*
- [x] Gate 0b — Assumption A4 (Pc recomputability) *(**PARTIAL HOLD**: 65.0% of the E3 sample within the pre-registered ±0.5 log10 tolerance, below the 80% bar but above the 50% fail floor, and most accurate in the operationally relevant high-risk band. Q-LBL-01 resolved as option (b), **scoped M7**; the E3 tolerance confirmed unrevised.)*
- [x] Gate 1 — Statistical power / go-no-go *(**GO** on marginal coverage; **PIVOT** dropping group-conditional analysis — E13 skipped. Decided by Sidh, see `DECISIONS.md`.)*
- [x] Phase 2 — Baselines *(E6 GBM, E7 sequence, E8 steelmanned MC-dropout coverage audit)*
- [x] Gate 2 — Weighted conformal (Contribution 1) *(**GO**, scoped to two-sided coverage: rule-derived weighting restores marginal coverage on the official test set. Weighting does **not** restore one-sided upper bounds, nor CQR coverage (E12) — both logged as honest secondary findings, outside the claim.)*
- [x] Phase 3 — Conformal prediction *(E9 machinery validation, E10 the bias problem, E11 the correction, E12 CQR: large efficiency gain but a genuine coverage negative)*
- [x] Gate 3 — Label-noise sensitivity / venue decision (Contribution 2) *(**GO** on Contribution 2; venue tier locked at **Q2**, not contingent on Phase 5. The flat persistence curve must be reported as interval-width insensitivity, not noise-robustness. High-risk conditional coverage is flagged forward to E15. Decided by Sidh, see `DECISIONS.md`.)*
- [ ] Phase 5 — Decision-cost, robustness, release (Contribution 3)
  - **E15 matched-budget run: done.** Design reviewed by Sidh (high-risk lens, one-sided bound, cost ratios 5/10/20:1, descriptive only) and pre-registered. Formally grounded by Proposition 1 (rank invariance): the classification is confirmed for all 20 method arms (`kc decision --only rank-audit`).
  - **E15 expanded threshold analysis (absorbs E16): pre-registered; design decisions resolved by Sidh (2026-09-19).**
    - Lead times {2-day, 3-day}, both on the official test set (Q-METH-04 revised; 1-day was infeasible).
    - A fresh hyperparameter search per horizon.
    - Two-sided arms retained.
    - The grid is built on the internal validation split.
    - **Full run complete** (`kc decision --only threshold`). Results are recorded in `DECISIONS.md`, awaiting Sidh's review.
    - **Grid ceiling fixed and re-run (2026-09-20).** The original grid topped out at the operational −6, pinning 62.3% of bound
      threshold selections; the grid is now the union of point-prediction and validated-bound percentiles on `val_inner` plus −6,
      pre-registered before the re-run. Everything read at −6 is unchanged and P1a/P1b/P1c stay exactly 0; pinning on the primary
      deployable read-out fell to 26.9%, while the rule-weighted variant remains censored at 69.4% — disclosed, not corrected post hoc.
  - **E17 robustness & gap closure: run, awaiting Sidh's review** (`kc robustness`; `--from-tables` re-renders without recomputing).
    - H1 scoped to persistence/GBM/GRU. MC-dropout/E8 is excluded because it has no hyperparameter cache under the current config hash; the exclusion is disclosed in the report.
    - The coverage-restoration criterion was corrected to the one-sided guarantee (coverage ≥ nominal). Under it, the Gate-2 headline passes the mission-level cluster-bootstrap check.
    - Rule-weighting restores 1 of the 4 {split, CQR} × {two-, one-sided} cells.
    - H3's shared-mechanism test is circular by construction, so it falls back to the honest null.
  - **E18:** not started.

## Reproducibility

Every reported number is produced by versioned code from immutable, checksummed raw data — no manually-edited figures or tables. See `CLAUDE.md` for the full set of operating invariants. Environment is pinned (`uv.lock`); a Docker image is built at each gate release for independent reproduction.

## License

Code: MIT (see `LICENSE`). Dataset: CC-BY 4.0 (ESA), used under attribution, not redistributed.

## Team

Sidh — Computer Science (AI), Vishwakarma Institute of Technology, Pune. Supervised by [guide name]. Implementation assisted by AI tools under the operating rules in `CLAUDE.md`; all research decisions and gate approvals are human-owned.
