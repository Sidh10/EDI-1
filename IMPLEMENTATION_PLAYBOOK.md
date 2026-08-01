# IMPLEMENTATION_PLAYBOOK.md

**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Purpose:** The execution strategy — how the work actually gets done, phase by phase, optimized for autonomous execution by Claude Code with Sidh supervising at gates.
**Reads with:** CLAUDE.md (operating rules), EXPERIMENT_PLAN.md (what to run), SOFTWARE_ARCHITECTURE.md (where code lives), OPEN_QUESTIONS.md (what must be decided first).

---

## How to use this playbook

**For Claude Code:** Execute one phase per brief. Never begin a phase whose predecessor's checkpoint is unsigned. At every phase end, produce the checkpoint artifact and **stop** — do not proceed on the assumption that passing tests implies approval. Approval is a human act recorded in `DECISIONS.md`.

**For Sidh:** Each phase ends with a review criteria block written so you can evaluate the work without reading every line of code. If you cannot answer the review questions from the checkpoint artifact alone, the artifact is inadequate — send it back rather than approving on faith.

**Autonomy boundary (applies to every phase):** Claude Code may decide *how* to implement. Claude Code may not decide *what counts as a valid result*, *whether a gate is passed*, or *anything flagged "blocks implementation" in OPEN_QUESTIONS.md*. When blocked, write the question to `DECISIONS.md` under "Pending" and stop.

**Blocking questions to resolve before Phase 0 begins:** Q-METH-01 (target definition), Q-METH-02 (prediction cutoff rules), Q-METH-03 (interval sidedness), Q-SEL-02 (which test sets are evaluated). These four are cheap for Sidh to answer and expensive to retrofit. Do not start without them.

---

## PHASE 0 — Foundation, Audit, and Feasibility Spikes
*Experiments: E0, E1, E2, E3 · Duration: ~1 week · Autonomy: HIGH (mostly mechanical)*

### Objective
Establish an immutable, verified data foundation; characterize the dataset (including the selection bias the project depends on); classify every feature for leakage safety; and resolve the project's largest technical unknown (can Pc be recomputed?) before any modeling investment.

### Files created
```
pyproject.toml, uv.lock, Dockerfile, Makefile, README.md, .gitignore
CLAUDE.md, DECISIONS.md                        (copied in / initialized)
config/default.yaml                            (seeds, thresholds, paths, cutoffs)
.github/workflows/ci.yaml
src/kelvins_conformal/{__init__,config,ingest,data}.py
src/kelvins_conformal/labelnoise/pc_foster.py  (spike version only)
src/kelvins_conformal/cli.py                   (ingest, audit commands only)
tests/{test_config,test_ingest,test_splits_leakage,test_pc_foster}.py
notebooks/00_data_audit.ipynb
notebooks/00b_pc_spike.ipynb
feature_dictionary.yaml
```

### Expected outputs
- `data/raw/` populated, checksum-verified, permissions set read-only.
- `data/processed/events.parquet` — event-grouped, typed, schema-validated.
- `reports/00_data_audit.html` with: counts vs. published figures; risk distribution train vs. test; time-to-TCA-of-latest-CDM train vs. test; CDMs-per-event; missingness heatmap; per-group event counts.
- `reports/figures/` — selection-bias evidence figures (PNG + PDF), destined for manuscript Figure 1.
- `feature_dictionary.yaml` — all 103 features classified safe / unsafe / ambiguous with rationale.
- `reports/00b_pc_spike.html` — recomputed-vs-reported risk scatter, error table, missing-field prevalence.
- `DECISIONS.md` — factual findings summary, no recommendations.

### Tests
- `test_ingest`: checksum mismatch raises and aborts; raw directory is unwritable after ingest.
- `test_config`: config loads with type validation; config hash is stable and changes when any value changes.
- `test_splits_leakage`: no event ID appears in more than one split; assertion runs on every split construction.
- `test_pc_foster`: Pc computation reproduces known analytic values on constructed toy geometries (before it is ever run on real data).
- CI: lint + tests + tiny-subset smoke run under 10 minutes.

### Validation
- Published dataset statistics reproduced exactly; any deviation flagged prominently at the top of the audit report, not buried.
- Selection bias (high-risk enrichment; latest-CDM recency filter) visible in the plotted distributions — if not visible, this is a critical anomaly requiring re-reading of the challenge paper before proceeding.
- Pc spike: agreement between recomputed and reported risk quantified against the tolerance recorded in `DECISIONS.md` **before** the spike was run.

### Checkpoint (artifact Sidh receives)
Two rendered HTML reports, the feature dictionary, and a `DECISIONS.md` entry containing: dataset counts vs. published, high-risk prevalence per split, feature classification tallies, Pc spike agreement statistics, and any anomalies. Plus a one-screen artifact checklist with file paths.

### Review criteria (Sidh answers these from the checkpoint alone)
1. Do the counts match the published dataset description? If not, is the discrepancy explained?
2. Is the selection bias visible and quantified in the figures?
3. Is every feature classified, and are the ambiguous ones few enough to handle conservatively?
4. Did the Pc recomputation succeed against the pre-set tolerance? **(This resolves Assumption A4 / Q-LBL-01 — a project-shaping answer.)**
5. Is a usable group/mission identifier present? **(Resolves Q-DATA-01; determines whether E13 survives.)**

### Rollback strategy
- Data ingest failure → re-download, re-verify; if Zenodo is unavailable, use archived copy; if the checksum genuinely differs from documentation, halt and investigate before any processing.
- Schema deviation from expectations → adapt parsing, document the deviation at the top of the audit report, do not silently guess column meanings.
- **Pc spike fails (A4 falsified)** → do not attempt workarounds autonomously. Record the failure and stop; Sidh invokes the pre-agreed Contribution-2 fallback (label-noise analysis reframed around published covariance-scaling results rather than recomputed labels). This is a scope decision, not an engineering problem.
- Any invariant violation (writable raw data, non-deterministic output) → fix before proceeding; no phase advances with a broken invariant.

### Next phase
Phase 1 begins only after Sidh records the Phase 0 checkpoint decision, including explicit answers to review criteria 4 and 5, which determine downstream scope.

---

## PHASE 1 — The Go/No-Go Gate
*Experiments: E4, E5 · Duration: ~2 weeks · Autonomy: HIGH (well-specified computation)*

### Objective
Answer the question the entire project rests on: can coverage be estimated with useful precision given how few high-risk events exist? And validate the evaluation harness by reproducing published baseline scores — establishing that our metrics can be trusted before any of them are used to make a claim.

### Files created
```
src/kelvins_conformal/metrics.py               (challenge loss, coverage, PIT, bootstrap)
src/kelvins_conformal/baselines.py             (persistence, constant)
src/kelvins_conformal/power.py
tests/test_metrics.py                          (hand-computed toy cases — mandatory)
tests/test_bootstrap.py                        (event-level resampling correctness)
notebooks/01_power_analysis.ipynb
notebooks/01b_baseline_validation.ipynb
```

### Expected outputs
- `reports/01_power_analysis.html` — CI half-width on coverage vs. calibration-set size, marginal and per group; **the Gate 1 decision table**.
- `reports/01b_baseline_validation.html` — our baseline scores vs. published challenge scores, with bootstrap CIs.
- Group-merging threshold recommendation derived from the power results (input to Q-CONF-02).
- `DECISIONS.md` — findings, stated factually, with the go/no-go decision left blank for Sidh.

### Tests
- `test_metrics`: challenge loss matches hand-computed values on constructed toy cases; F2 and MSE_HR components tested separately; threshold edge cases (exactly at the high-risk boundary) covered explicitly.
- `test_bootstrap`: resampling is at event level, not row level; reproducible under fixed seed; CI width behaves correctly on synthetic data with known variance.
- Determinism test: power analysis produces identical results across runs with the same seed.

### Validation
- **Hard requirement:** baseline scores reproduce published values within the pre-agreed tolerance. If they do not, the metric implementation is wrong and nothing downstream is trustworthy. This is non-negotiable and blocks everything.
- Power analysis run with ≥2,000 bootstrap resamples per configuration, reported with explicit resample counts.

### Checkpoint
The Gate 1 decision table plus the baseline validation table, both rendered, with a plain-language summary of what precision is achievable marginally and per group.

### Review criteria (Gate 1 — the project's primary decision point)
1. Do our baselines match published scores? **If no, everything stops until fixed.**
2. Can marginal coverage on high-risk events be estimated within the precision needed to make a claim?
3. How many groups (if any) support group-conditional coverage analysis?
4. Given 1–3: **GO** (proceed as planned) / **PIVOT** (drop or scope down group-conditional claims, elevate label-noise contribution) / **NO-GO** (marginal coverage not estimable → fundamental redesign).

### Rollback strategy
- Baseline mismatch → debug the metric implementation against the official scoring definition; re-read the challenge scoring page; do not adjust the baselines to fit the metric.
- Power insufficient for groups → PIVOT is pre-agreed, not a crisis: E13 is dropped, Contributions 1 and 2 proceed unchanged, and the paper's claims are scoped to marginal coverage. Record explicitly.
- Power insufficient even marginally → NO-GO. Stop. This outcome, though unlikely, is why the gate exists before Phase 2's modeling investment.

### Next phase
Phase 2 begins only on a recorded GO or PIVOT. On PIVOT, the Phase 3 brief is amended to remove E13 before that phase starts, not during it.

---

## PHASE 2 — Predictors and the Bayesian Baseline
*Experiments: E6, E7, E8 · Duration: ~4 weeks · Autonomy: MEDIUM (model choices need review)*

### Objective
Build competent point predictors as the substrate for the conformal layer, and faithfully reproduce the prior-art Bayesian uncertainty method — steelmanned — so that its coverage deficiency (the project's motivating evidence) is demonstrated rather than asserted.

### Files created
```
src/kelvins_conformal/features.py              (governed by feature_dictionary.yaml)
src/kelvins_conformal/models/{gbm,sequence,bayesian}.py
config/experiments/{E6,E7,E8}.yaml
tests/test_features.py                         (leakage assertions per feature dictionary)
tests/test_determinism.py                      (multi-seed reproducibility)
notebooks/02_baselines.ipynb
```

### Expected outputs
- Trained model artifacts with config-hash-keyed identities; per-event predictions on calibration and test sets.
- `reports/02_baselines.html` — performance table (persistence vs. GBM vs. LSTM) with bootstrap CIs and ≥3 seeds; MC-dropout coverage audit with reliability diagram and PIT histogram.
- Quantile-regression heads validated (monotonic, sane pinball loss) for downstream CQR use.

### Tests
- `test_features`: no feature marked unsafe in the dictionary appears in any built feature set; assertion fails loudly on violation.
- `test_determinism`: same config + seed produces identical predictions.
- Sequence padding/masking test: padded positions provably do not influence outputs.

### Validation
- Every model reported across ≥3 seeds with variation shown.
- Official test set touched once per experiment, for final scoring only — hyperparameter selection uses the internal validation split exclusively.
- MC-dropout baseline tuned for its *own* coverage performance before being audited (steelmanning is a validation requirement, not an optional courtesy).

### Checkpoint
Performance comparison table with CIs; MC-dropout coverage table and reliability diagram; a short written statement of the hyperparameter search budget used per method (equal budgets across methods).

### Review criteria
1. Do models perform in the expected range (comparable to or modestly above persistence)? A large unexplained jump is a leakage signal, not a success.
2. Was the MC-dropout baseline genuinely steelmanned — can we defend the tuning budget against a reviewer's "you nerfed the baseline" charge (REVIEWER_CHECKLIST M6)?
3. Does MC-dropout show the hypothesized coverage deficiency? **If it is well-calibrated, the project's motivation weakens and framing must be revisited** — surface this immediately rather than proceeding.
4. Are quantile heads well-formed for CQR?

### Rollback strategy
- Suspiciously strong performance → treat as a leakage bug until proven otherwise: re-audit features against the dictionary, check cutoff logic for off-by-one errors, verify split integrity. Do not report the number until cleared.
- Sequence model unstable across seeds → simplify architecture (fewer layers, smaller hidden size) rather than seed-shopping; if instability persists, proceed with GBM as the primary base learner (pre-agreed under R11) and document.
- MC-dropout unexpectedly well-calibrated → stop and escalate; this is a framing question for Sidh, not an engineering one.

### Next phase
Phase 3 begins after checkpoint sign-off. If review criterion 3 came back unexpectedly, the Phase 3 brief must be rewritten before proceeding.

---

## PHASE 3 — The Core Contribution
*Experiments: E9, E10, E11 (Gate 2), then E12, E13 · Duration: ~5 weeks · Autonomy: LOW-MEDIUM (contribution code needs close review)*

### Objective
Deliver Contribution 1 in three deliberate steps: prove the conformal machinery is correct where its assumptions hold (E9), demonstrate its failure where they do not (E10), and correct that failure with weighted conformal prediction (E11). Then extend with CQR (E12) and group-conditional calibration (E13, if Gate 1 permitted).

### Files created
```
src/kelvins_conformal/conformal/{split,cqr,grouped,weighted}.py
src/kelvins_conformal/conformal/diagnostics.py   (effective sample size, positivity, weight distribution)
config/experiments/{E9,E10,E11,E12,E13}.yaml
tests/test_conformal_split.py                    (coverage on synthetic exchangeable data)
tests/test_conformal_weighted.py                 (analytic covariate-shift toy cases — mandatory)
tests/test_conformal_edge_cases.py               (tiny calibration sets, ties, extreme weights)
notebooks/03_conformal.ipynb
```

### Expected outputs
- `reports/03_conformal.html` containing, in narrative order: self-split coverage validation (E9) → naive coverage on the biased official test set (E10) → weighted coverage restoring validity (E11) → CQR efficiency comparison (E12) → per-group forest plot (E13, if applicable).
- **Headline figure:** naive vs. weighted coverage side by side, nominal line, CI bands.
- Weight diagnostics: distribution, effective sample size, positivity/overlap violations, clipping cap effects.
- Both rule-derived and estimated-propensity weight variants, per Q-SEL-01's dual-specification defense.

### Tests
- `test_conformal_split`: achieves nominal coverage on synthetic exchangeable data across multiple nominal levels — the implementation is proven on data where the right answer is known before touching real data.
- `test_conformal_weighted`: recovers correct coverage on synthetic data with a *known, constructed* covariate shift. This is the single most important test in the repository — the headline claim depends on this code being right.
- Edge cases: calibration sets near the minimum viable size, tied nonconformity scores, weights near zero and near the clipping cap.
- Library-behavior regression test: pinned conformal library versions produce expected outputs on fixed toy inputs (guards against silent quantile-convention changes on upgrade).

### Validation
- E9 must pass before E10 runs; E10 must complete before E11. This ordering is not optional — it is what separates "our code is broken" from "the test set is biased," and it is the answer to REVIEWER_CHECKLIST X2.
- Coverage reported with formal tests (binomial/Clopper–Pearson) plus bootstrap CIs, never as a bare number or a visual impression.
- Interval width reported alongside every coverage figure (REVIEWER_CHECKLIST EV2 — coverage without efficiency is trivially gameable).
- Pre-registration of the primary contrast and success margin recorded in `DECISIONS.md` **before** E11 runs.

### Checkpoint (Gate 2)
The full E9→E10→E11 narrative in one rendered report, with the headline figure, the naive-vs-weighted comparison table, and complete weight diagnostics. Plus a statement of which weight specification was used and how the alternative specification compared.

### Review criteria (Gate 2)
1. Does E9 confirm the conformal implementation achieves nominal coverage under exchangeability? **If not, there is a bug and nothing after it means anything.**
2. Does E10 show a meaningful, statistically supported coverage deficit on the official test set?
3. Does E11 close that gap while keeping intervals operationally useful (not vacuous)?
4. Do the two weight specifications agree? Disagreement is a finding to report, not a problem to hide (REVIEWER_CHECKLIST M1).
5. Are positivity violations bounded and characterized?
6. Is this ready to timestamp as an arXiv preprint?

### Rollback strategy
- E9 fails → implementation bug. Halt the phase entirely; do not proceed to E10 or E11. Debug against the synthetic tests, then re-run.
- E10 shows no coverage gap → the selection bias may be weaker than expected. Do not manufacture one. Report honestly, and note that Contributions 2 and 3 stand independently; Sidh decides whether the paper's spine shifts toward label noise.
- E11 fails to restore coverage → escalate to the Q-SEL-01 design review rather than iterating on weight formulations autonomously. Trying variants until coverage looks right is exactly the forking-paths behavior the pre-registration exists to prevent.
- Exploding weights / positivity failure → apply the pre-registered clipping cap, report the excluded subpopulation explicitly; do not tune the cap to improve results.

### Next phase
Phase 4 after Gate 2 sign-off. Tag `gate2-weighted-conformal` and post the arXiv preprint at this point — scoop protection is time-sensitive and this is the earliest defensible moment.

---

## PHASE 4 — Label-Noise Sensitivity
*Experiment: E14 · Duration: ~4 weeks · Autonomy: MEDIUM*

### Objective
Deliver Contribution 2: quantify how known covariance miscalibration in the risk labels propagates into coverage validity — converting the project's most awkward conceptual vulnerability (REVIEWER_CHECKLIST M3) into a measured result.

### Files created
```
src/kelvins_conformal/labelnoise/{pc_foster,rescale}.py   (full version, beyond Phase 0 spike)
config/experiments/E14.yaml                                (scaling grid, pre-registered)
tests/test_pc_foster_full.py                               (cross-validation vs. reference implementation)
tests/test_rescale.py                                      (scaling factor 1.0 is identity — critical sanity check)
notebooks/04_label_noise.ipynb
```

### Expected outputs
- `reports/04_label_noise.html` — coverage vs. covariance-scaling-factor curves with CI bands and nominal reference line (**second headline figure**).
- Rescaled label sets for the complete-covariance-field subset.
- M7-subset representativeness analysis (subset vs. full test set label distributions).
- Scaling grid anchored to published ESA covariance-realism figures, cited with actual source numbers.

### Tests
- `test_pc_foster_full`: agreement with an authoritative reference implementation on sample cases, reported quantitatively (this becomes a supplementary figure answering REVIEWER_CHECKLIST RP4).
- `test_rescale`: scaling factor 1.0 reproduces original labels exactly — if this fails, every rescaled result is contaminated.
- Grid completeness test: all pre-registered grid points computed and reported, including unfavorable ones.

### Validation
- The full grid is reported regardless of which portions are favorable (REVIEWER_CHECKLIST M7).
- Representativeness of the analyzed subset explicitly tested and reported, not assumed.
- Trend analysis (monotonicity) reported with its uncertainty, not asserted from a visual impression.

### Checkpoint (Gate 3)
The sensitivity curve, the representativeness analysis, the reference-implementation agreement, and a plain-language statement of what the results mean for the paper's central claim.

### Review criteria (Gate 3)
1. Is the Pc recomputation validated against an authoritative reference?
2. Is the analyzed subset representative enough to support the claim?
3. Is there a clear, interpretable relationship between label miscalibration and coverage?
4. **Venue decision:** given Gate 2 and Gate 3 results together, Q2 (Advances in Space Research / Journal of Space Safety Engineering) or Q1 stretch (Acta Astronautica)?

### Rollback strategy
- Subset too small or unrepresentative → run the pre-agreed reduced version: sensitivity framed around published covariance-scaling results applied to existing intervals, without full label recomputation. Weaker, but honest and still a contribution.
- No interpretable relationship found (coverage insensitive to label scaling) → this is a legitimate, publishable finding (it would mean conclusions are robust to the label-noise concern), not a failure. Report it as such.
- Reference-implementation disagreement → halt; a Pc computation we cannot validate cannot support a published claim.

### Next phase
Phase 5 after Gate 3, with the venue decision recorded (it shapes the manuscript's framing and length).

---

## PHASE 5 — Operational Evaluation, Robustness, and Release
*Experiments: E15, E16, E17, E18 · Duration: ~8 weeks · Autonomy: MEDIUM-HIGH for E15–E17, LOW for manuscript*

### Objective
Deliver Contribution 3 (decision-cost evaluation), establish operational relevance across lead times, consolidate robustness checks, and produce the release artifact plus manuscript-ready figures and tables.

### Files created
```
src/kelvins_conformal/{decision,horizons}.py
src/kelvins_conformal/reporting.py               (provenance stamping, figure/table export)
config/experiments/{E15,E16,E17}.yaml
tests/test_decision.py                           (cost-ratio logic on toy cases)
notebooks/{05_decision_cost,06_lead_time,07_robustness}.ipynb
reports/manuscript_{figures,tables}/
```

### Expected outputs
- Decision-cost tradeoff curves across methods and cost ratios (E15) — the answer to "so what" (REVIEWER_CHECKLIST X4).
- Lead-time analysis: coverage validity maintained, interval width degrading with earlier prediction (E16).
- Robustness supplement: cluster bootstrap, clipping-cap sensitivity, multiple-comparison policy applied (E17).
- Final figure/table set, every item provenance-stamped and regenerable from a tagged commit (E18).
- Released artifact: cleaned repo, Docker image, `kc reproduce-all` verified on a clean machine by someone other than the implementer, Zenodo DOI.

### Tests
- `test_decision`: maneuver/no-maneuver logic correct on hand-constructed cases at each cost ratio.
- Full-pipeline reproduction test: `kc reproduce-all` from a clean container regenerates every manuscript number.
- Provenance test: every figure and table file carries a resolvable git SHA and config hash.

### Validation
- Independent reproduction by a non-implementer before submission (this is success metric A1, not an optional nicety).
- Every manuscript figure and table traceable to a specific experiment run — REVIEWER_CHECKLIST F-series and T-series requirements (CIs present, sample sizes reported, colorblind-safe, self-contained captions) checked item by item.
- Full REVIEWER_CHECKLIST walkthrough: any criticism whose supporting experiment is incomplete either gets the experiment run or the corresponding claim softened.

### Checkpoint
Complete results package plus the manuscript draft, accompanied by a completed REVIEWER_CHECKLIST audit showing every top-five rejection risk has a completed supporting experiment.

### Review criteria
1. Does calibrated uncertainty demonstrably change decisions in at least one realistic cost regime — or is the honest negative clearly characterized?
2. Do headline conclusions survive every robustness variant? Any reversal must be disclosed prominently, not buried.
3. Is the artifact genuinely reproducible by an outsider?
4. Does the REVIEWER_CHECKLIST audit show no unaddressed top-five risk?
5. Is the manuscript's language audited for overclaiming ("guarantee," "ensure," "prove," "reliable")?

### Rollback strategy
- Calibrated methods show no decision advantage → report honestly as a finding about the data's information content (pre-agreed acceptable outcome); the paper's contribution shifts weight to Contributions 1 and 2, which stand on their own.
- Robustness variant reverses a headline conclusion → this is a stop-and-reassess event, not a paragraph to soften. Sidh decides whether claims are narrowed or the result is reframed.
- Reproduction fails on a clean machine → not submittable until fixed; this is a hard blocker regardless of schedule pressure.
- Timeline pressure → the pre-agreed MVP paper is Contributions 1 and 2 with the toolkit; E16 and portions of E17 can be deferred to a follow-up without invalidating the core claims.

### Next phase
Submission. Post-submission: maintain the repository, respond to reviews, and treat reviewer criticisms as inputs to a revised REVIEWER_CHECKLIST for the next paper.

---

## Cross-Phase Standing Protocols

**Every phase, without exception:**
1. Begin by re-reading CLAUDE.md and the relevant EXPERIMENT_PLAN.md specifications. Do not work from memory of a prior phase.
2. Verify all dependencies are satisfied and recorded in `DECISIONS.md` before starting; an unrecorded resolution counts as unresolved.
3. Work on a branch named for the phase or experiment; one logical change per PR; CI green before merge.
4. Every result carries: bootstrap CIs, ≥3 seeds where stochastic, git SHA, config hash, seed set.
5. End with the checkpoint artifact and **stop**. Passing tests is not approval.
6. Tag the repository at every gate.

**Escalation triggers — stop and ask, do not proceed:**
- Any result that looks surprisingly good (leakage until proven otherwise).
- Any blocking OPEN_QUESTIONS item encountered without a recorded resolution.
- Any conflict between documents in the authority hierarchy.
- Any temptation to adjust a statistical procedure after seeing its result.
- Any gate outcome that does not match the pre-agreed GO / PIVOT / NO-GO options.

**What autonomous execution means here:** Claude Code owns implementation, testing, debugging, and report generation. Claude Code does not own scope, statistical validity judgments, gate decisions, or claims about what results mean. The playbook is designed so that a phase can run end-to-end without intervention *and* so that it halts cleanly at exactly the points where human judgment is irreplaceable.
