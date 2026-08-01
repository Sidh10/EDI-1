# PROJECT_KNOWLEDGE.md
**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment — A Conformal Prediction Approach under Selection Bias and Label Noise
**Status:** Pre-implementation. This document is the single source of truth for project understanding. Implementation, architecture, and tooling decisions are explicitly out of scope here and will be made in separate, later documents.
**Owner:** Sidh (student researcher, VIT Pune) — all gate decisions. AI tools assist under supervision.
**Last updated:** July 2026.

---

## 1. Executive Summary

Satellite operators receive a stream of standardized warning messages (Conjunction Data Messages, CDMs) in the days before a potential collision between their satellite and another tracked object. Each message updates a collision-risk estimate; operators must decide, before a decision deadline, whether to perform a costly avoidance maneuver. Existing machine-learning research on this problem predicts a single risk number and — where uncertainty is estimated at all — never verifies that the stated uncertainty is trustworthy.

This project produces collision-risk forecasts with *statistically guaranteed* uncertainty intervals (conformal prediction), on the public ESA Kelvins Collision Avoidance Challenge dataset, while explicitly handling two documented flaws every prior work ignores: the benchmark test set was deliberately constructed in a biased way, and the ground-truth risk labels are themselves noisy. Outputs: a peer-reviewed manuscript (Q2 target, Q1 stretch), an open reproducible toolkit, and quantified evidence about when calibrated uncertainty changes operational decisions.

The project is a research project first and a software project second: the "product" is defensible knowledge plus a reusable evaluation artifact, not a deployed operational system.

## 2. Problem Statement

**The real-world problem.** Low Earth orbit is increasingly congested (mega-constellations, debris from past collisions and anti-satellite events). Agencies screen for close approaches and issue CDM series per event. Risk estimates in early CDMs are noisy; they typically stabilize only close to the time of closest approach (TCA) — often after the practical maneuver-decision deadline. Operators therefore decide under uncertainty, and today they are given point estimates without reliable statements of how much those estimates can be trusted.

**Who experiences it.** Satellite operators (commercial, governmental, scientific) making maneuver decisions; agency conjunction-assessment teams (ESA Space Debris Office, NASA CARA) who produce and interpret CDMs; downstream, every user of satellite services affected by either a collision (catastrophic) or excessive false-alarm maneuvers (fuel depletion, service interruption, shortened mission life).

**Why it matters.** A missed high-risk event can destroy spacecraft and generate debris fields that endanger entire orbital regimes for decades. An over-cautious policy wastes finite fuel and operational capacity. The quantity that rationally arbitrates this tradeoff is *calibrated* risk — a risk statement that means what it says. Both ESA (via its 2019 ML challenge and follow-ups) and NASA (via its CARA AI/ML research program, active as of 2025) have publicly identified reliable ML-assisted conjunction assessment as unsolved. Additionally, a theoretical literature within this field (the "false confidence theorem") shows that common probabilistic uncertainty treatments can systematically understate collision risk — making *validity-guaranteed* uncertainty not a nicety but a domain-specific necessity.

**The research-specific problem.** On the standard public benchmark, prior work exhibits three compounding gaps: (1) no coverage-verified uncertainty of any kind; (2) silent inheritance of a documented, deliberate test-set selection bias that violates the statistical assumptions of most uncertainty methods; (3) no analysis of how known miscalibration in the label-generating process (covariance unrealism) corrupts conclusions built on those labels.

## 3. Target Users

**Primary users (of the research + toolkit):**
- Researchers in space situational awareness / astrodynamics ML who need a rigorous uncertainty-evaluation harness and corrected baselines for the Kelvins dataset.
- The project team itself and its successors at VIT, for follow-on work.

**Secondary users:**
- Satellite-operations analysts and agency teams (ESA Space Debris Office, NASA CARA) who may consume the findings (not the software operationally) as evidence about trustworthiness of ML risk predictions.
- Statistics/ML researchers seeking a documented real-world case of conformal prediction under known selection bias and label noise.
- Journal reviewers and editors (in the practical sense that the manuscript must serve them).

**Stakeholders:**
- Sidh and team members (publication, learning outcomes, degree requirements).
- Project guide and VIT CS(AI) department (supervision, academic credit, institutional research output).
- ESA/NASA contacts if outreach succeeds (potential data guidance; goodwill obligations to share results).
- The open-science community (toolkit users; reproducibility expectations).

**Pain points (mapped to users):**
- Researchers: no standardized uncertainty benchmark exists on this dataset; prior results are hard to compare; the selection bias silently contaminates every published evaluation.
- Operators/agencies: point predictions without trust statements are operationally unusable for automated decision support; Bayesian-style uncertainty in prior work is unverified and theoretically suspect in this domain.
- Student team: must produce Q1/Q2-defensible rigor within a 6–9 month window with no institutional aerospace lab.

**User goals:**
- Reproduce any reported number from released code with one command.
- Determine, per conjunction event and per lead time, an interval on final risk with a stated and *verified* coverage level.
- Understand how conclusions degrade under the dataset's known flaws (selection bias, label noise) rather than pretending the flaws don't exist.

## 4. Existing Solutions

**Operational practice (non-ML):** Agencies compute collision probability (Pc) per CDM using analytic methods (e.g., Foster-type integrals under Gaussian assumptions) and apply fixed thresholds (e.g., ~1e-4 in LEO) plus human analyst judgment. Limitation: per-message snapshot, no forecasting of risk evolution, known covariance-realism problems, and the probability-dilution pathology under noisy data.

**Research literature (verified during scoping; full annotated review with per-paper gaps maintained in the separate literature-review document):**
- ESA Kelvins challenge paper (Uriot et al., 2022, Astrodynamics) — defines dataset/task; documents that ML barely beats a naive persistence baseline; documents (without correcting) the biased test-set construction.
- Conventional ML benchmarking (Tulczyjew et al., 2021, J. Space Safety Eng.) — point prediction only.
- Bayesian deep learning on CDM sequences (Pinto et al., 2020, NeurIPS workshop) — heuristic uncertainty (MC dropout), never coverage-audited. Closest prior art.
- ESA Space Debris Conference benchmarking study (2021) — multiple model families incl. Bayesian NNs; leaderboard metrics only; itself points to covariance handling as the open lever.
- CDM arrival-process modeling (Caldas et al., 2023) — orthogonal sub-problem (timing, not trust).
- False confidence theorem (Balch, Martin, Ferson, 2019, Proc. Roy. Soc. A) and 2025 confidence-distribution follow-up (Entropy) — theoretical demand for frequentist-valid uncertainty; no data-driven method supplied.
- MDP maneuver-decision framework (2025) — optimizes decisions assuming trustworthy risk inputs that no one has certified.
- Physics-informed GAN augmentation (Dec 2025) — improves high-risk recall via synthetic data; no uncertainty; may distort calibration (unmeasured).
- Conformal time-series methods (EnbPI, CQR, weighted conformal; 2019–2021 statistics literature) — the imported toolkit; never applied to conjunction data.
- Conformalized quantile regression for solar-flare forecasting (Mar 2026) — proves toolkit migration into adjacent space science; conjunction domain untouched.

**Competitors (in the priority-race sense):** the Lisbon-area cluster (NOVA/Neuraspace: Caldas, Soares, Pinto lineage), ESA-affiliated researchers, NASA CARA's internal AI/ML effort. Any could plausibly move toward conformal methods; none have published it.

**Open-source alternatives:** Kessler (conjunction-event simulation/ML library from the challenge ecosystem); general conformal-prediction libraries (domain-agnostic); NASA CARA's released CA analysis tools (analytic Pc computation, not ML uncertainty). No existing open artifact provides an uncertainty-evaluation harness for this dataset — Papers-with-Code lists zero benchmarks for it.

**Limitations of everything above → opportunities:** the intersection (coverage-guaranteed forecasts + selection-bias correction + label-noise sensitivity + decision-cost framing + open toolkit) is unoccupied. The dataset's documented flaws, treated by prior work as nuisances, are re-cast here as the research contributions.

## 5. Project Goals

**Primary goals:**
1. Produce coverage-valid prediction intervals for final conjunction risk from partial CDM sequences, with empirical verification of coverage (marginal and, power permitting, per mission group).
2. Correct for the documented test-set selection mechanism via weighted conformal methods; demonstrate the size of the error made by ignoring it.
3. Quantify sensitivity of coverage/conclusions to label noise induced by covariance miscalibration.
4. Publish a manuscript in a Q2 journal (Advances in Space Research / Journal of Space Safety Engineering), with Q1 (Acta Astronautica) attempted if Phase-4 results justify it.

**Secondary goals:**
5. Release a reproducible open-source evaluation toolkit + cleaned benchmark harness for the dataset (candidate first standardized benchmark on Papers-with-Code).
6. Reproduce prior baselines (persistence, gradient-boosted point prediction, MC-dropout uncertainty) faithfully enough to serve as the field's comparison points.
7. Frame results in operational decision-cost terms (maneuver economy vs. missed-alert rate; lead-time tradeoffs).
8. Establish priority via a mid-project arXiv preprint.
9. Build the team's demonstrated capability (and institutional relationship credibility, incl. any ESA/NASA correspondence) for follow-on research.

**Long-term vision:** a recognized, citable reference point for uncertainty-aware conjunction assessment; extension to newer/larger CDM archives if agency outreach yields data; a template for "calibration-first" re-examinations of other aerospace ML benchmarks.

**Success criteria:** see §13.

## 6. Non-Goals

- **No operational deployment.** This is not a live decision-support product for real satellite operations, and will not be represented as one.
- **No new point-prediction architecture.** We are not trying to win the original challenge leaderboard or beat state-of-the-art accuracy; point predictors are commodity components here.
- **No orbit determination, tracking, or propagation research.** Raw sensor processing, catalog maintenance, and orbit-propagation improvements are out of scope; CDMs are taken as given inputs.
- **No maneuver trajectory optimization.** We evaluate decisions' costs; we do not compute optimal avoidance maneuvers (the 2025 MDP literature owns that layer).
- **No synthetic-data generation contribution.** We may *use* simulation for stress tests, but generating better synthetic CDMs (the P-GAN paper's territory) is not a contribution we claim.
- **No real-time / streaming system requirements.** Batch research computation only.
- **No proprietary or restricted data.** If agency outreach yields non-public data, its use becomes a separate, renegotiated project phase — the core paper must stand on the public dataset alone.
- **No general UI/product frontend beyond what the research artifact needs.** Any dashboard is illustrative, not a deliverable the paper depends on.
- **No claims about post-2019 orbital environments** beyond an explicit limitations discussion; the dataset is 2015–2019.

## 7. Functional Requirements

Grouped by module (module = unit of research function, not architecture).

**M1 — Data acquisition & integrity**
- FR1.1 Obtain the public dataset from its canonical DOI; verify checksum; record provenance.
- FR1.2 Preserve an immutable raw copy; all downstream artifacts derive via scripted, versioned transformations.
- FR1.3 Parse CDM records into event-grouped time series with documented schema, including handling of missing fields.

**M2 — Data audit & bias characterization**
- FR2.1 Reproduce and report the dataset's published statistics (event counts, features, CDMs/event) and flag deviations.
- FR2.2 Quantify and visualize the test-set selection mechanism (high-risk enrichment; latest-CDM recency filter) — outputs double as manuscript figures.
- FR2.3 Characterize class imbalance (high-risk prevalence), per-mission composition, missingness patterns, and label distribution.

**M3 — Evaluation harness**
- FR3.1 Implement the official challenge metric exactly, validated against published baseline scores.
- FR3.2 Implement coverage, interval-width, reliability-diagram, and probability-integral-transform diagnostics.
- FR3.3 Implement decision-cost evaluation: thresholded maneuver/no-maneuver outcomes under explicit cost ratios; F-beta style summaries; lead-time (prediction horizon) breakdowns.
- FR3.4 Support event-level train/calibration/test splitting with temporal-integrity options; all metrics reported with bootstrap confidence intervals and multi-seed aggregation.

**M4 — Statistical power gate**
- FR4.1 Estimate, by simulation, the attainable precision of coverage estimates given high-risk event counts, marginally and per candidate group; produce the go/no-go decision table.

**M5 — Baseline predictors (reproduction)**
- FR5.1 Naive persistence and degenerate constant baselines.
- FR5.2 A gradient-boosted point/quantile predictor on engineered CDM features.
- FR5.3 A recurrent sequence model on CDM series; an MC-dropout variant and small ensemble reproducing prior-art uncertainty for audit.

**M6 — Conformal uncertainty layer (core contribution)**
- FR6.1 Split-conformal intervals over any M5 predictor.
- FR6.2 Conformalized quantile regression for heteroskedastic intervals.
- FR6.3 Group-conditional calibration (per mission / merged orbit groups, subject to M4 power).
- FR6.4 Weighted conformal prediction encoding the documented test-set selection mechanism; contrasted against naive conformal to demonstrate the bias's effect.

**M7 — Label-noise sensitivity (core contribution)**
- FR7.1 Recompute target collision probability from CDM state/covariance fields under a grid of covariance scaling factors, cross-checked against an authoritative analytic implementation.
- FR7.2 Re-evaluate coverage/decision metrics against rescaled labels; produce sensitivity curves of guarantee-degradation vs. label miscalibration.

**M8 — Reporting & artifact**
- FR8.1 Every phase ends in a rendered, reviewable report; every reported number is produced by code.
- FR8.2 A decisions log capturing each gate outcome and rationale (becomes the reproducibility appendix).
- FR8.3 Public release: cleaned repository, one-command reproduction, archived with its own DOI; manuscript sources.
- FR8.4 (Optional, non-blocking) an illustrative visualization of per-event risk-interval evolution for the paper/defense.

## 8. Non-Functional Requirements

- **Reproducibility (paramount):** deterministic seeds; pinned environments; immutable raw data; scripted pipelines; ≥3 seeds for stochastic components; bootstrap CIs (≥2,000 resamples) on all headline metrics; one-command end-to-end reproduction.
- **Scientific integrity:** no manual result editing; negative results reported; every claim in the manuscript traceable to a script and a commit.
- **Performance/latency:** research-batch tolerances — full pipeline reproducible within roughly a day on a single modern consumer GPU or CPU-only for tree models; no interactive latency requirements.
- **Scalability:** dataset is small (~190k rows); design need only accommodate ~10× growth (in case agency data arrives later); no distributed computing.
- **Maintainability:** modular separation of data/metrics/models/conformal layers; unit tests on all metric and statistical code (the parts whose bugs would invalidate the science); documented public API for the toolkit.
- **Reliability:** pipeline failures must be loud (checksum mismatch, schema deviation, coverage-computation anomalies abort with explicit errors rather than degrade silently).
- **Security:** minimal surface — no user data, no credentials, no services; standard supply-chain hygiene (pinned dependencies).
- **Privacy:** the dataset is anonymized by ESA at source (mission identities obfuscated); the project introduces no personal data. Any future agency-provided data handled under whatever agreement accompanies it.
- **Accessibility:** released documentation readable by non-aerospace ML researchers and non-ML aerospace researchers alike (glossary, plain-language summaries); figures colorblind-safe.
- **Availability:** repository and archived artifacts publicly and permanently retrievable (DOI-backed); no service uptime obligations.
- **Cost constraints:** near-zero cash budget; free/consumer compute (personal machines, free notebook GPU tiers); free-tier hosting for code; publication venue selection must consider APC-free or fee-waiver options (relevant venues offer subscription tracks with no author fee).

## 9. Assumptions

1. The Zenodo dataset remains publicly available and unchanged (checksum-verifiable) for the project duration.
2. The dataset's published documentation of its own construction (selection filters on the test set) is accurate — our weighted-conformal correction depends on this description being truthful.
3. The final-CDM risk value is an acceptable *operational* prediction target (as established by the challenge), even though it is a noisy proxy for true collision probability — and our label-noise analysis (M7) explicitly stress-tests this assumption rather than taking it on faith.
4. CDM covariance/state fields in the public data are sufficient to recompute collision probability analytically (required for M7). *If falsified, M7 is redesigned around published covariance-realism scaling results instead — flagged as the project's largest single technical unknown.*
5. High-risk events, though rare (~2–3% prevalence), are numerous enough in absolute terms to estimate marginal coverage meaningfully. *Explicitly tested at the M4 gate rather than trusted.*
6. Prior-art baselines are reproducible to within honest tolerance from paper descriptions (official code may not exist for all).
7. No conformal-on-CDM paper is currently in press elsewhere; scoping searches (through July 2026) found none, but unpublished work is invisible — mitigated by the mid-project preprint.
8. AI-assisted implementation supervised by the team meets the rigor bar, with human review at every gate; the guide and department accept this working model.
9. Team availability of roughly 6–9 months alongside coursework holds.
10. English-language Q2 aerospace venues will review a student-authored, single-dataset methodological study on its merits (venue norms support this; applied rigor is valued over architectural novelty).
11. Agency outreach (ESA/NASA) may yield guidance but is assumed to yield *no additional data* for planning purposes; any data received is upside, not dependency.

## 10. Constraints

- **Technical:** single public dataset (2015–2019 era, ~190k CDMs, 103 partially-documented features, anonymized missions); severe class imbalance; short heterogeneous sequences; consumer-grade compute only.
- **Business/academic:** must satisfy VIT department requirements (synopsis approval, guide checkpoints, timeline reporting); publication timeline coupled to academic calendar; team is students, not domain specialists — domain knowledge acquired en route.
- **Legal:** dataset license CC-BY 4.0 (attribution obligations on redistribution); released code under an OSI license compatible with dependencies; no export-control-sensitive content (public data, non-operational research); mandatory attribution of ESA as data originator.
- **Research:** contributions must remain defensible against a hostile Reviewer 2 — every gap claim anchored to the verified literature review; the three headline contributions are locked and drift toward "we applied conformal prediction" is prohibited by project rule.
- **Deployment:** none (research artifact only) — but the artifact must run on a stranger's machine, which is a real constraint on how everything is built.
- **Time:** ~24 working weeks across 6–9 calendar months; hard internal gates at weeks 3 (power), 12 (preprint), 16 (venue tier).
- **Budget:** effectively ₹0 cash; free tooling and compute only; publication fees avoided via venue selection or waivers.

## 11. Technical Challenges

1. **Recomputing Pc from CDM fields** (M7): reconstructing an analytic collision-probability computation from the dataset's covariance/state columns, validating it against authoritative implementations, and handling events where required fields are missing or the anonymization degrades them. The project's #1 technical unknown.
2. **Correct weighted-conformal implementation:** likelihood-ratio weighting under the documented selection mechanism must be derived, implemented, and unit-tested from scratch (it is a contribution, not a library call); subtle errors here would invalidate the headline result.
3. **Event-level vs. message-level statistics:** calibration, splitting, and bootstrap procedures must respect event grouping to avoid leakage and pseudo-replication — an easy silent-failure zone.
4. **Faithful baseline reproduction** without official code for every prior method; disputes over reproduction fidelity are a classic reviewer attack.
5. **Metric fidelity:** the official challenge loss has sharp definitional edges (thresholding, high-risk-only MSE); must match published baseline scores exactly before anything else is trusted.
6. **Small-sample uncertainty about uncertainty:** reporting honest error bars *on coverage itself* with few high-risk events; avoiding overclaiming from noise.
7. **Heterogeneous short sequences:** models and conformal wrappers must handle 1–20+ CDMs/event without padding artifacts leaking signal.
8. **Reproducibility engineering under zero budget:** deterministic multi-seed pipelines on heterogeneous student hardware.

## 12. Research Challenges

**Open questions the project itself answers:**
- Is marginal (and per-group) coverage estimable with useful precision given high-risk scarcity? (Gate M4 — the project's go/no-go.)
- How large is the coverage error induced by ignoring the test-set selection bias? (Could be dramatic or modest; either is publishable, but the narrative differs.)
- How fast do conformal guarantees degrade as label miscalibration grows? Is there a covariance-scaling regime where guarantees become vacuous?
- Do calibrated intervals actually change decisions at operational cost ratios, or are they too wide to matter at useful lead times? (A "too wide to be useful" finding is an honest, reportable outcome.)

**Unknowns / risks to the research story:**
- The selection mechanism, though documented, may be only partially specified — the weights may capture it incompletely; residual bias must then be bounded and discussed rather than eliminated.
- Exchangeability violations *within* the training/calibration data (temporal drift 2015→2019) beyond the documented test-set issue.
- A competing conformal-on-CDM publication appearing mid-project (mitigation: preprint at week 12; differentiating contributions 2 and 3, which remain unusual even in that scenario).
- The false-confidence framing invites scrutiny from statisticians: the manuscript must be precise that conformal guarantees are about *coverage of the noisy operational label*, not metaphysical collision probability — sloppiness here would be a fair rejection reason.
- Anonymization may make per-mission grouping too coarse/opaque for meaningful group-conditional claims.

## 13. Success Metrics

**Scientific (primary):**
- S1. Empirical coverage of nominal 90% intervals within ±[power-analysis-determined margin] of nominal on held-out events — marginal, and per group where powered.
- S2. Demonstrated, quantified coverage gap between naive and selection-bias-weighted conformal on the official test set (the headline number).
- S3. A monotone, interpretable sensitivity curve of coverage vs. covariance-scaling factor (Contribution 2's deliverable), or a well-characterized null.
- S4. Decision-cost results at ≥2 lead times and ≥2 cost ratios, with calibrated methods dominating or matching uncalibrated baselines at equal alert budgets.
- S5. Reproduced baselines within honest tolerance of published figures (validating the harness).

**Publication:**
- P1. arXiv preprint by ~week 12.
- P2. Submission to a Q2 venue by month ~7–8; acceptance (possibly post-revision) is the success bar; a Q1 submission attempt is stretch, not requirement.

**Artifact:**
- A1. Public repository with one-command reproduction verified on a clean machine by someone other than the implementer.
- A2. Archived, DOI-bearing release cited in the manuscript.

**Process:**
- PR1. Every gate passed with a written decision record; zero undocumented scope drift from the three locked contributions.

## 14. Risks

| # | Risk | Category | Likelihood | Impact | Mitigation |
|---|------|----------|-----------|--------|------------|
| R1 | High-risk events too scarce for precise coverage estimation | Dataset/Research | Medium | High | M4 gate before investment; fallback to marginal-only claims with elevated label-noise contribution |
| R2 | CDM fields insufficient to recompute Pc (breaks M7 as designed) | Dataset/Technical | Medium | High | Early feasibility spike in Phase 0; fallback redesign using published covariance-scaling results |
| R3 | Scooped by conformal-on-CDM publication | Research/Business | Low–Medium | High | Week-12 preprint; contributions 2–3 remain differentiating; monitor forward citations of the challenge paper |
| R4 | Weighted-conformal implementation error invalidating headline claim | Technical | Medium | Very High | Unit tests vs. analytic toy cases; independent re-derivation review at Phase-3 gate |
| R5 | Baseline reproduction disputed by reviewers | Research | Medium | Medium | Use released code where it exists; document deviations; report tolerance honestly |
| R6 | Reviewer rejects "coverage of a noisy label" framing | Research | Medium | Medium | Precise scoping language; M7 sensitivity analysis is the direct answer; false-confidence literature as framing ally |
| R7 | Timeline slip vs. academic calendar | Business/Time | Medium | Medium | Gated phases; MVP-paper definition (contributions 1–2 alone are submittable if Phase 5 compresses) |
| R8 | AI-assisted implementation introduces subtle unreviewed errors | AI | Medium | High | Human review at every gate; unit-tested statistical core; every number traced to code; multi-seed cross-checks |
| R9 | Dataset withdrawn/altered upstream | Infrastructure | Low | Medium | Immutable local archive + checksum from day 1; CC-BY permits preservation |
| R10 | Team bandwidth loss (exams, attrition) | Business | Medium | Medium | Phase structure allows pause/resume; decision log preserves context |
| R11 | Compute insufficiency for sequence models | Infrastructure | Low | Low | Dataset is small; tree-based models carry the paper if deep models are cut |
| R12 | Security/supply-chain issue in dependencies | Security | Low | Low | Pinned, minimal dependency set |
| R13 | Publication fees unaffordable | Business | Medium | Low | Choose no-fee tracks; request waivers; preprint guarantees dissemination regardless |

## 15. Future Scope

- Extension to newer/larger CDM archives if ESA/NASA outreach or public releases materialize (the toolkit is designed to ingest ~10× data).
- Conformal risk control variants targeting operational quantities directly (false-negative-rate control rather than interval coverage).
- Online/streaming conformal updating as CDMs arrive (bridging to the arrival-process literature).
- Integration of certified risk intervals into the maneuver-decision (MDP) layer — closing the loop the 2025 decision literature left open.
- Cross-domain replication: the same "calibration-first under documented selection bias" protocol applied to other flawed-benchmark aerospace datasets.
- Community benchmark stewardship: standardized leaderboard with uncertainty metrics for the Kelvins dataset.
- Follow-on manuscript on the label-noise methodology as a general technique for model-output-as-label learning problems.

## 16. Glossary

| Term | Meaning |
|---|---|
| **CDM (Conjunction Data Message)** | Standardized warning message about a predicted close approach between two space objects, containing state vectors, covariances, and a collision-risk estimate. Issued repeatedly per event as tracking updates arrive. |
| **Conjunction / event** | One potential close approach, described by its series of CDMs (typically ~7–12) over about a week. |
| **TCA (Time of Closest Approach)** | The predicted moment of minimum distance between the two objects. |
| **Pc / collision risk** | Probability of collision, computed per CDM from geometry and uncertainty (covariances), typically via Foster-type analytic integrals under Gaussian assumptions. The dataset's prediction target is the *final* CDM's risk value. |
| **Maneuver** | Propulsive avoidance action; costly (fuel, operations, service interruption), hence the decision problem. |
| **Persistence / naive baseline** | Predicting the final risk to equal the most recent observed CDM's risk. Documented as surprisingly hard to beat. |
| **Point prediction** | A single-number forecast with no uncertainty statement. |
| **Prediction interval** | A range asserted to contain the true value with stated probability (e.g., 90%). |
| **Coverage** | The empirical rate at which stated intervals actually contain the truth; the audit of an uncertainty claim. |
| **Calibration** | Agreement between stated confidence and observed frequency of correctness. |
| **Conformal prediction** | A distribution-free statistical framework converting any predictor into intervals with finite-sample coverage guarantees, assuming exchangeability between calibration and test data. |
| **CQR (Conformalized Quantile Regression)** | Conformal variant producing intervals that widen/narrow per example (heteroskedastic). |
| **Weighted conformal prediction** | Conformal variant restoring validity under known covariate shift by reweighting calibration examples via likelihood ratios. |
| **Exchangeability** | The assumption that calibration and test data are statistically interchangeable — violated by the dataset's deliberate test-set construction. |
| **Selection bias (here)** | The documented, non-random construction of the test split: enriched in high-risk events and restricted to events whose latest CDM falls within one day of TCA. |
| **Label noise (here)** | Error in the ground-truth risk values themselves, inherited from miscalibrated covariances in the CDM-generation process. |
| **Covariance realism** | Whether reported state-uncertainty covariances match actual error statistics; ESA analyses indicate operational covariances require rescaling. |
| **False confidence theorem** | Result (Balch et al., 2019) showing epistemic-probability uncertainty treatments can systematically understate collision risk (via "probability dilution") in conjunction analysis. |
| **Probability dilution** | Pathology where noisier data yields *lower* computed collision probability. |
| **MC dropout** | Heuristic Bayesian-approximation technique using randomized network passes to produce an uncertainty spread; carries no coverage guarantee. |
| **F2 / challenge metric** | The competition's official score combining recall-weighted classification (β=2) with regression error on high-risk events. |
| **Decision-cost evaluation** | Scoring forecasts by operational consequences (missed high-risk events vs. unnecessary maneuvers) under explicit cost ratios. |
| **Q1/Q2** | Top-quartile / second-quartile journal rankings (SJR/JCR) — the project's publication bar. |
| **Kelvins dataset** | The ESA Collision Avoidance Challenge dataset (2015–2019 CDMs; 13,154 train / 2,167 test events; Zenodo DOI 10.5281/zenodo.4463683; CC-BY 4.0). |
