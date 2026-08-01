# Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment

Coverage-valid uncertainty quantification for satellite conjunction risk, using conformal prediction on the ESA Kelvins Collision Avoidance Challenge dataset — explicitly correcting for the dataset's documented test-set selection bias and quantifying sensitivity to known label noise.

**Status:** Phase 0 (E0–E3) and Phase 1 (E4–E5) implemented; **awaiting Sidh's Gate 1 review**. Nothing from Phase 2 (E6 onward) is built. Open for decision: the Gate 1 GO/PIVOT/NO-GO call, the Assumption-A4 call, and confirmation of the pre-registered tolerances/bars — see `DECISIONS.md`.

The evaluation harness is validated: our implementation of the official challenge metric reproduces the published LRP and CRP baseline scores to 4 decimal places (E5).

## What this is

Satellite operators receive a series of warning messages (CDMs) before a possible collision, each with an updated risk estimate. Existing machine-learning work on this problem predicts a single risk number, or an unverified confidence spread, without checking whether that confidence can be trusted. This project applies conformal prediction — a method with a distribution-free statistical guarantee — and addresses two flaws in the standard benchmark that all prior work has ignored: the test set was deliberately constructed to be non-random, and the risk labels themselves come from covariance estimates known to need correction.

Full context: `PROJECT_KNOWLEDGE.md` (what and why) → `SOFTWARE_ARCHITECTURE.md` (how it's built) → `EXPERIMENT_PLAN.md` (what gets run, in order) → `OPEN_QUESTIONS.md` (what's still undecided) → `CLAUDE.md` (operating rules for AI-assisted implementation) → `IMPLEMENTATION_PLAYBOOK.md` (phase-by-phase execution strategy) → `METRICS.md` (every evaluation quantity, precisely defined) → `REVIEWER_CHECKLIST.md` (adversarial pre-mortem against likely Q1/Q2 criticism).

## Quickstart

```bash
git clone <repo-url>
cd kelvins-conformal
uv sync --extra notebooks --extra dev
kc ingest          # E0: downloads + checksum-verifies the dataset, freezes it read-only
kc audit           # E1/E2/E3: renders reports/00_data_audit.html + 00b_pc_spike.html
kc baselines       # E5: validates the challenge metric vs published baseline scores
kc power           # E4: power analysis -> the Gate 1 decision table
```

`kc reproduce-all` regenerates every manuscript number and figure; it is not implemented yet
(it arrives with the first manuscript figures in Phase 1+). Available commands are only those
whose experiments exist — `kc ingest` and `kc audit` today.

No GPU required for the core pipeline; see `SOFTWARE_ARCHITECTURE.md` §9 for the full technology/compute breakdown.

## Data

ESA Kelvins Collision Avoidance Challenge dataset, Zenodo DOI [10.5281/zenodo.4463683](https://doi.org/10.5281/zenodo.4463683), licensed CC-BY 4.0 by the European Space Agency. Not redistributed in this repository; `kc ingest` downloads and checksum-verifies it directly from Zenodo. If you use this dataset, cite:

> Uriot, T., Izzo, D., Simões, L. F., et al. (2022). Spacecraft collision avoidance challenge: design and results of a machine learning competition. *Astrodynamics*, 6, 121–140.

## Current phase / gate status

_Updated at every gate. See `DECISIONS.md` for the authoritative log._

- [x] Blocking pre-Phase-0 questions resolved (Q-METH-01/02/03, Q-SEL-02)
- [x] Phase 0 — Foundation, audit, feasibility spikes *(E0–E3 run; reports rendered; **awaiting Sidh's checkpoint review** — the A4 go/no-go and the E3 tolerance confirmation are not made)*
- [ ] Gate 1 — Statistical power / go-no-go *(E4 + E5 run; harness validated against published scores; **decision table ready, awaiting Sidh's GO/PIVOT/NO-GO**)*
- [ ] Phase 2 — Baselines
- [ ] Gate 2 — Weighted conformal (Contribution 1)
- [ ] Gate 3 — Label-noise sensitivity / venue decision (Contribution 2)
- [ ] Phase 5 — Decision-cost, robustness, release (Contribution 3)

## Reproducibility

Every reported number is produced by versioned code from immutable, checksummed raw data — no manually-edited figures or tables. See `CLAUDE.md` for the full set of operating invariants. Environment is pinned (`uv.lock`); a Docker image is built at each gate release for independent reproduction.

## License

Code: MIT (see `LICENSE`). Dataset: CC-BY 4.0 (ESA), used under attribution, not redistributed.

## Team

Sidh — Computer Science (AI), Vishwakarma Institute of Technology, Pune. Supervised by [guide name]. Implementation assisted by AI tools under the operating rules in `CLAUDE.md`; all research decisions and gate approvals are human-owned.
