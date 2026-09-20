# EXPERIMENT_PLAN.md
**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Basis:** PROJECT_KNOWLEDGE.md (goals, non-goals, requirements, risks), consistent with SOFTWARE_ARCHITECTURE.md (module boundaries) and OPEN_QUESTIONS.md (unresolved design choices, referenced but not re-litigated here).
**Assumption:** No code exists yet. This document specifies *what must be run and why*, in dependency order; module names refer to the architecture document's planned components.
**Convention:** Every experiment has a Gate/Go-No-Go marker where applicable. "CI" = bootstrap confidence interval unless stated otherwise. Runtimes are rough estimates for a single modern laptop CPU (8 cores) unless GPU is noted; actuals confirmed once Q-COMP-01 (hardware audit) resolves.

---

## Execution Order Summary

| ID | Experiment | Phase | Gate? |
|---|---|---|---|
| E0 | Dataset acquisition & integrity verification | 0 | — |
| E1 | Data audit & selection-bias characterization | 0 | — |
| E2 | Feature dictionary & leakage audit | 0 | — |
| E3 | Collision-probability (Pc) recomputation feasibility spike | 0 | Gate 0b (Assumption A4) |
| E4 | Statistical power analysis | 1 | **Gate 1 (go/no-go)** |
| E5 | Baseline validation vs. published scores | 1 | Gate 1 input |
| E6 | Point-prediction baseline (gradient boosting) | 2 | — |
| E7 | Sequence-model baseline (recurrent point prediction) | 2 | — |
| E8 | Bayesian uncertainty baseline (MC-dropout / ensemble, steelmanned) | 2 | — |
| E9 | Split conformal on exchangeable self-split (machinery validation) | 3 | — |
| E10 | Naive split conformal on official (biased) test set | 3 | — |
| E11 | Weighted conformal — selection-bias correction | 3 | **Gate 2** |
| E12 | Conformalized quantile regression (CQR) | 3 | — |
| ~~E13~~ | ~~Group-conditional calibration~~ — **SKIPPED — Gate 1 PIVOT, see DECISIONS.md** | 3 | — |
| E14 | Label-noise sensitivity analysis | 4 | **Gate 3 (venue tier decision input)** |
| E15 | Decision-cost evaluation (expanded: matched-budget + rank-invariance proof + threshold-based analysis across 2-day/3-day horizons + cost-ratio optimization) — **COMPLETE** | 5 | — |
| E16 | Lead-time / horizon tradeoff analysis — **MERGED INTO E15**, do not re-run separately; see the E16 entry below and DECISIONS.md 2026-09-19 | 5 | — |
| E17 | Robustness, consistency & gap-closure consolidation (expanded: H1 robustness, H2 one-sided CQR coverage backfill, H3 cross-experiment synthesis) | 5 | — |
| E18 | Final manuscript figure/table consolidation + reviewer-checklist dry run (expanded) | 5 | — |

---

## E0 — Dataset Acquisition & Integrity Verification

- **Objective:** Obtain the canonical dataset and establish a checksummed, immutable raw store.
- **Hypothesis:** N/A (infrastructure step, not a scientific test).
- **Dataset split:** N/A — full raw archive only.
- **Inputs:** Zenodo record (DOI 10.5281/zenodo.4463683), documented md5 `d19dc8875229f2f6893253c38adddc87`.
- **Outputs:** `data/raw/` (read-only after this step), provenance manifest (download timestamp, checksum, source URL).
- **Metrics:** Checksum match (binary pass/fail).
- **Statistical tests:** None.
- **Confidence intervals:** None.
- **Figures produced:** None.
- **Tables produced:** Provenance manifest (not a results table).
- **Failure criteria:** Checksum mismatch, unreadable archive, or schema wildly inconsistent with documentation.
- **Success criteria:** Verified checksum; files unpack; column structure roughly matches the challenge paper's description.
- **Expected runtime:** <30 minutes (mostly download time).
- **Compute requirements:** Network access, ~1 GB disk.
- **Dependencies:** None (first experiment).

---

## E1 — Data Audit & Selection-Bias Characterization

- **Objective:** Verify the dataset matches published statistics and directly visualize the documented test-set construction bias.
- **Hypothesis:** H1: Published event/feature counts (13,154 train / 2,167 test events, 103 features) match the release exactly. H2: The test split is measurably enriched in high-risk events and restricted to late-arriving CDMs relative to train, consistent with the challenge paper's stated construction.
- **Dataset split:** Full train + full test (both examined descriptively; no modeling).
- **Inputs:** `data/raw/` from E0.
- **Outputs:** `data/processed/events.parquet` (parsed, typed, event-grouped); audit report.
- **Metrics:** Event/CDM counts; per-split risk distribution (log scale); per-split time-to-TCA distribution of latest CDM; high-risk prevalence (train vs. test); missingness rate per feature.
- **Statistical tests:** Two-sample comparison of risk distributions and time-to-TCA distributions (train vs. test) — Kolmogorov–Smirnov or Mann–Whitney U, purely descriptive/confirmatory (not a hypothesis we could "fail," since the bias is documented — this quantifies its magnitude).
- **Confidence intervals:** Bootstrap CI (event-level, 2,000 resamples) on high-risk prevalence per split.
- **Figures produced:** (a) risk-value histogram, train vs. test, log scale, threshold marked; (b) time-to-TCA-of-latest-CDM histogram, train vs. test; (c) CDMs-per-event distribution; (d) missingness heatmap across 103 features.
- **Tables produced:** Dataset statistics table (counts vs. published values); per-mission event/high-risk counts table.
- **Failure criteria:** Published counts do not match within rounding (triggers investigation before proceeding); H2 not observed (would undercut the entire selection-bias contribution — treated as a critical anomaly requiring re-reading of the challenge paper, not a normal "negative result").
- **Success criteria:** Counts match; H2 confirmed with visibly distinct distributions — these two figures become manuscript Figure 1.
- **Expected runtime:** 1–2 hours (parsing + notebook execution).
- **Compute requirements:** CPU only, <4 GB RAM.
- **Dependencies:** E0.

---

## E2 — Feature Dictionary & Leakage Audit

- **Objective:** Classify all 103 features as safe/unsafe for use at each candidate prediction cutoff, preventing target leakage.
- **Hypothesis:** A non-trivial subset of features are either directly derived from the final CDM or otherwise unavailable at earlier cutoffs (unconfirmed prior to review).
- **Dataset split:** Train set only (descriptive review; no test-set access needed).
- **Inputs:** `data/processed/events.parquet`, challenge documentation/column descriptions.
- **Outputs:** `feature_dictionary.yaml` (per-column: description, availability rule, safe/unsafe flag, rationale); filtered feature builder configuration.
- **Metrics:** Count of features classified safe vs. unsafe vs. ambiguous.
- **Statistical tests:** None (manual/documented classification, spot-checked by correlation-with-target screening on training data only as a secondary leakage smell test).
- **Confidence intervals:** None.
- **Figures produced:** None (optional: correlation-with-target bar chart for ambiguous features, supplementary).
- **Tables produced:** Feature dictionary table (this is itself a citable artifact/appendix).
- **Failure criteria:** More than a handful of features remain genuinely ambiguous after review (would require a conservative-exclusion fallback policy).
- **Success criteria:** Every feature has a documented, defensible safe/unsafe classification before any feature builder code is written.
- **Expected runtime:** 3–5 hours (manual/documentation-driven).
- **Compute requirements:** None beyond a text editor / notebook.
- **Dependencies:** E1.

---

## E3 — Collision-Probability (Pc) Recomputation Feasibility Spike

- **Objective:** Determine whether Assumption A4 holds — can collision probability be recomputed from public CDM state/covariance fields closely enough to the reported risk to support label-noise sensitivity analysis (Contribution 2)?
- **Hypothesis:** An analytic (Foster-type) Pc computation on the public state/covariance columns reproduces each CDM's reported risk value within acceptable numerical tolerance on a representative sample.
- **Dataset split:** Random sample of ~100 CDMs (stratified across risk levels), train set.
- **Inputs:** `data/processed/events.parquet` state/covariance columns; a reference Pc algorithm implementation (cross-checked against NASA CARA's public conjunction-assessment code where feasible).
- **Outputs:** Recomputed-vs-reported risk comparison dataset; go/no-go recommendation for M7 scope.
- **Metrics:** Absolute and relative error between recomputed and reported log-risk; proportion of sample within tolerance (e.g., within 0.5 log-units); failure mode categorization (missing fields, numerical instability, systematic offset).
- **Statistical tests:** Paired comparison (recomputed vs. reported), e.g., Wilcoxon signed-rank on log-risk differences; correlation coefficient as a secondary check.
- **Confidence intervals:** Bootstrap CI on mean absolute error and on proportion-within-tolerance.
- **Figures produced:** Scatter plot, recomputed vs. reported log-risk, y=x reference line.
- **Tables produced:** Error summary table; missing-field prevalence table for the fields Pc computation requires.
- **Failure criteria:** Systematic, large, unexplained divergence, or field unavailability on a large fraction of events → Assumption A4 fails.
- **Success criteria:** Recomputed risk tracks reported risk closely enough (per pre-set tolerance, recorded in DECISIONS.md before running) on most of the sample → full M7 proceeds as designed.
- **Expected runtime:** 1 day (implementation + validation), separate from later full-scale runs.
- **Compute requirements:** CPU only, negligible.
- **Dependencies:** E1, E2. **Critical path note:** this spike must run in Phase 0, not deferred to Phase 4 — a late failure here would force a costly redesign of Contribution 2.

---

## E4 — Statistical Power Analysis (Gate 1)

- **Objective:** Determine whether coverage can be estimated with useful precision, marginally and per candidate group, given the scarcity of high-risk events — the project's primary go/no-go checkpoint.
- **Hypothesis:** Marginal coverage on high-risk test events is estimable within a pre-declared CI half-width; group-conditional coverage may or may not be, depending on per-group counts.
- **Dataset split:** Simulated calibration-set fractions (10%, 20%, 30%) of the training events; evaluated against the full official test set.
- **Inputs:** `data/processed/events.parquet` (counts/labels only — no models required).
- **Outputs:** Power analysis report; group-merging threshold recommendation (feeds Q-CONF-02).
- **Metrics:** Bootstrap-estimated CI half-width on empirical coverage of a nominal interval, for each calibration fraction, marginally and per mission/group.
- **Statistical tests:** None beyond the bootstrap itself (this experiment *is* a Monte Carlo statistical simulation).
- **Confidence intervals:** Bootstrap, ≥2,000 resamples, event-level, per configuration.
- **Figures produced:** CI half-width vs. calibration-set size, marginal and per group (small-multiples or faceted plot).
- **Tables produced:** **The Gate 1 decision table** — precision achievable per group, with groups below the viability threshold flagged for merging.
- **Failure criteria:** Even marginal coverage cannot be estimated within a useful margin at any feasible calibration size → NO-GO on the conformal approach as designed (would trigger a fundamental project reassessment, not merely a pivot).
- **Success criteria:** Marginal coverage estimable with useful precision (minimum bar); group-conditional analysis estimable for at least 2–3 groups (stretch bar) — determines whether Contribution 1's per-group claims proceed as planned or are scoped down.
- **Expected runtime:** 2–4 hours (simulation-heavy but embarrassingly parallel).
- **Compute requirements:** CPU only, multi-core beneficial.
- **Dependencies:** E1.

---

## E5 — Baseline Validation Against Published Scores

- **Objective:** Validate the evaluation harness (challenge metric implementation) by reproducing the two documented naive baselines' published performance.
- **Hypothesis:** Our implementation of the official challenge loss (F2-based, high-risk-only MSE) applied to the persistence and constant baselines matches the challenge paper's reported baseline scores within reasonable tolerance.
- **Dataset split:** Train (fit, trivially, for the constant baseline's constant) / official test (scoring).
- **Inputs:** `data/processed/events.parquet`, feature dictionary (E2) for cutoff logic.
- **Outputs:** Baseline score table; validated `metrics.py` module (unit-tested).
- **Metrics:** Official challenge score (F2-based composite), MSE on high-risk events, F2 alone, precision/recall at the high-risk threshold.
- **Statistical tests:** None required for validation itself; bootstrap CI reported for use as the comparison baseline in later experiments.
- **Confidence intervals:** Bootstrap, event-level, 2,000 resamples, on each baseline's score.
- **Figures produced:** None required (optional bar chart of baseline scores with CIs).
- **Tables produced:** Baseline score table (ours vs. published).
- **Failure criteria:** Scores do not match published values within tolerance → metric implementation bug, must be fixed before any further experiment is trusted.
- **Success criteria:** Match within tolerance on both baselines — this is the credibility gate for every subsequent metric.
- **Expected runtime:** 1–2 hours.
- **Compute requirements:** CPU only, negligible.
- **Dependencies:** E1, E2. **Runs alongside E4 to jointly inform the Gate 1 decision.**

---

**— GATE 1 DECISION POINT (supervisor review of E1–E5) —**
No further modeling proceeds without explicit sign-off. Outcomes: GO (proceed as planned) / PIVOT (scope group-conditional claims down per E4) / NO-GO (fundamental redesign).

---

## E6 — Point-Prediction Baseline (Gradient Boosting)

- **Objective:** Establish a competent, modern point/quantile predictor as the workhorse model beneath the conformal layer.
- **Hypothesis:** A gradient-boosted model on engineered last-k-CDM features outperforms the persistence baseline on the official challenge metric, though not necessarily by a large margin (consistent with prior literature's finding that this task resists strong point-prediction gains).
- **Dataset split:** Train (fit) / held-out validation carved from train (early stopping/hyperparameter selection) / official test (final scoring only, touched once).
- **Inputs:** Feature-built dataset (per E2 dictionary), cutoff rules (per Q-METH-02 resolution).
- **Outputs:** Trained model artifact(s), per-event point and quantile predictions on calibration and test sets (for later conformal wrapping).
- **Metrics:** Official challenge score, MSE_HR, F2, quantile (pinball) loss for the quantile heads.
- **Statistical tests:** Paired comparison vs. persistence baseline (E5) — e.g., paired bootstrap test on per-event squared error.
- **Confidence intervals:** Bootstrap CI (event-level, 2,000 resamples) on all metrics, ≥3 seeds aggregated.
- **Figures produced:** Predicted vs. actual risk scatter (test set); feature importance plot.
- **Tables produced:** Model performance table (vs. E5 baselines) with CIs.
- **Failure criteria:** Model performs materially worse than persistence (would itself be a reportable, if surprising, finding — but triggers a feature/hyperparameter review first).
- **Success criteria:** Matches or modestly exceeds persistence baseline; quantile heads well-formed (monotonic, sane pinball loss) for downstream CQR use.
- **Expected runtime:** 1–3 hours (hyperparameter search + multi-seed training), CPU.
- **Compute requirements:** CPU only, <8 GB RAM.
- **Dependencies:** Gate 1 pass, E2.

---

## E7 — Sequence-Model Baseline (Recurrent Point Prediction)

- **Objective:** Provide a sequence-aware point predictor (matching prior-art architecture family) for fair later comparison against the Bayesian baseline (E8) and as an alternative base learner for conformal wrapping.
- **Hypothesis:** A recurrent model (GRU/LSTM) over the full CDM sequence performs comparably to, not necessarily better than, the tabular gradient-boosting model (E6), consistent with recent literature noting strong recency bias in this data favoring simpler recency-weighted approaches.
- **Dataset split:** Same as E6.
- **Inputs:** Padded/masked CDM sequence tensors (per event, up to cutoff).
- **Outputs:** Trained model artifact(s); per-event predictions on calibration and test sets.
- **Metrics:** Same as E6 (official score, MSE_HR, F2).
- **Statistical tests:** Paired comparison vs. E6 (paired bootstrap on per-event error) and vs. E5 persistence.
- **Confidence intervals:** Bootstrap CI, event-level, ≥3 seeds.
- **Figures produced:** Training/validation loss curves; predicted vs. actual scatter.
- **Tables produced:** Model comparison table (persistence vs. LightGBM vs. LSTM), all with CIs.
- **Failure criteria:** Training instability/non-convergence across seeds (would require architecture simplification).
- **Success criteria:** Stable training; performance in the same range as E6 (large gaps in either direction warrant investigation before proceeding).
- **Expected runtime:** 2–6 hours on CPU; <1 hour if GPU available (contingent on Q-COMP-01).
- **Compute requirements:** GPU beneficial, not required; <8 GB RAM/VRAM.
- **Dependencies:** Gate 1 pass, E2.

---

## E8 — Bayesian Uncertainty Baseline (MC-Dropout / Ensemble, Steelmanned)

- **Objective:** Faithfully reproduce the closest prior-art uncertainty method (MC-dropout Bayesian deep learning) as the comparison point our conformal results must outperform on *coverage*, not merely point accuracy.
- **Hypothesis:** MC-dropout-derived predictive intervals, even when tuned generously for their own coverage performance (steelmanned per Q-BASE-02), fail to achieve nominal coverage, particularly on the selection-biased official test set — motivating the entire project.
- **Dataset split:** Same base split as E7; interval evaluation on official test set (and self-split, per Q-SEL-02, once E9 exists).
- **Inputs:** E7's architecture family, extended with dropout-at-inference and/or a small deep ensemble.
- **Outputs:** Per-event predictive distributions (samples or moments); derived intervals at each nominal level (per Q-STAT-01).
- **Metrics:** Empirical coverage at each nominal level; interval width; reliability diagram deviation; PIT histogram uniformity (e.g., via KS test against uniform).
- **Statistical tests:** Binomial/Clopper–Pearson test of observed vs. nominal coverage; KS test on PIT values.
- **Confidence intervals:** Bootstrap CI on coverage (event-level, 2,000 resamples).
- **Figures produced:** Reliability diagram; PIT histogram; interval-width distribution.
- **Tables produced:** Coverage table across nominal levels — **this table is the paper's motivating evidence** for why heuristic Bayesian uncertainty is insufficient.
- **Failure criteria:** N/A in the usual sense — poor coverage is the *expected and hypothesis-confirming* outcome; failure would instead be if MC-dropout achieves excellent, well-calibrated coverage (which would undercut the project's motivation and require re-framing around a narrower gap).
- **Success criteria (for the paper's narrative, not the baseline's performance):** A clear, quantified coverage deficiency is documented, especially under selection bias.
- **Expected runtime:** 2–4 hours (multiple dropout forward passes at inference, ≥3 seeds).
- **Compute requirements:** Same as E7.
- **Dependencies:** E7.

---

## E9 — Split Conformal on Exchangeable Self-Split (Machinery Validation)

- **Objective:** Validate that our split-conformal implementation achieves nominal coverage under conditions where its assumptions actually hold, before applying it to the biased official test set.
- **Hypothesis:** On a self-constructed, randomly sampled (exchangeable) held-out split from the training pool, standard split conformal achieves coverage statistically indistinguishable from nominal.
- **Dataset split:** Training pool randomly partitioned into fit / calibration / self-test (event-level, seeded); official test set untouched in this experiment.
- **Inputs:** Candidate base predictors, retrained or reused on the fit portion. **Base-learner set (Gate-1 amendment, 2026-09-01):** GBM (E6), GRU (E7), MC-dropout (E8), **and persistence (the E5 LRP predictor)** — four candidates, not three. Persistence is added because E6's point estimate is poorly determined (its L bootstrap CI spans ~2 orders of magnitude); Contribution 1 is a coverage-VALIDITY demonstration that needs a well-defined, not accurate, predictor, and persistence is the most stable one on this dataset with predictions already available from E5 at zero cost. See DECISIONS.md, 2026-09-01. This is independent of the E6/E7 point-accuracy outcome.
- **Outputs:** Prediction intervals on the self-test split; coverage validation report.
- **Metrics:** Empirical coverage vs. nominal (per level from Q-STAT-01); interval width.
- **Statistical tests:** Binomial/Clopper–Pearson test of coverage vs. nominal; per Q-STAT-02's pre-declared success margin.
- **Confidence intervals:** Bootstrap CI, event-level.
- **Figures produced:** Coverage-vs-nominal plot (calibration curve) with CI bands.
- **Tables produced:** Machinery-validation coverage table.
- **Failure criteria:** Coverage deviates from nominal beyond the pre-declared margin under exchangeable conditions → implementation bug in the conformal core; must be fixed before proceeding to E10–E13 (a bug here would invalidate everything downstream).
- **Success criteria:** Coverage matches nominal within margin — proof the conformal implementation is correct before it is asked to handle the harder, biased case.
- **Expected runtime:** 1–2 hours.
- **Compute requirements:** CPU only.
- **Dependencies:** E6, E7, E8, and E5 persistence (the four candidate base learners per the 2026-09-01 amendment; persistence needs no retraining).

---

## E10 — Naive Split Conformal on Official (Biased) Test Set

- **Objective:** Quantify the coverage failure caused by ignoring the dataset's documented selection bias — establishing the problem that Contribution 1 solves.
- **Hypothesis:** Standard (unweighted) split conformal, calibrated on exchangeable training data but evaluated on the selection-biased official test set, exhibits coverage below nominal, particularly for high-risk events.
- **Dataset split:** Calibration from training pool (as in E9); evaluation on the full official test set.
- **Inputs:** Same predictors as E9.
- **Outputs:** Prediction intervals on official test set; coverage report (naive method).
- **Metrics:** Empirical coverage (marginal and, where powered, per group) vs. nominal; interval width; under-coverage magnitude specifically on high-risk events.
- **Statistical tests:** Binomial/Clopper–Pearson coverage test; two-sample comparison of coverage (E9 self-split vs. E10 official test) to quantify the bias-induced gap.
- **Confidence intervals:** Bootstrap CI, event-level, per Q-STAT-03's chosen method(s).
- **Figures produced:** Coverage-vs-nominal comparison, self-split (E9) vs. official test (E10), side by side — **candidate manuscript figure demonstrating the problem**.
- **Tables produced:** Naive-method coverage table on official test.
- **Failure criteria:** No meaningful coverage gap observed between E9 and E10 (would weaken the selection-bias narrative — not fatal, since Contributions 2–3 stand independently, but requires honest reframing).
- **Success criteria:** A clear, statistically supported coverage deficit on the official test set relative to the self-split — the empirical justification for Contribution 1.
- **Expected runtime:** 1–2 hours.
- **Compute requirements:** CPU only.
- **Dependencies:** E9.

---

## E11 — Weighted Conformal Prediction (Selection-Bias Correction) — Gate 2

- **Objective:** Deliver Contribution 1: coverage-valid intervals on the official test set via weighted conformal prediction correcting for the documented selection mechanism.
- **Hypothesis:** Weighted conformal prediction, using weights derived from the documented test-set construction rule (per Q-SEL-01's resolved choice), restores coverage on the official test set to statistically indistinguishable-from-nominal, closing the gap observed in E10.
- **Dataset split:** Same calibration/official-test structure as E10.
- **Inputs:** E10's predictors and nonconformity scores; selection-mechanism weight function.
- **Outputs:** Weighted prediction intervals on official test set; weight diagnostics (effective sample size, positivity/overlap checks per Q-SEL-03).
- **Metrics:** Empirical coverage vs. nominal (marginal + per-group where powered); interval width vs. E10; effective sample size after weighting.
- **Statistical tests:** Binomial/Clopper–Pearson coverage test; formal comparison of E10 vs. E11 coverage (the headline contrast); positivity-violation rate reporting.
- **Confidence intervals:** Bootstrap CI, event-level; sensitivity variant with mission-level cluster bootstrap (per Q-STAT-03c).
- **Figures produced:** **Headline figure** — naive (E10) vs. weighted (E11) coverage, side by side, with nominal line and CI bands; weight distribution plot with positivity diagnostics.
- **Tables produced:** Naive-vs-weighted coverage comparison table (the paper's central result table).
- **Failure criteria:** Weighting fails to close the E10 gap, or introduces instability (exploding weights, vacuous intervals) beyond the pre-registered clipping policy → triggers design review of the weight construction (Q-SEL-01 alternative b/c) before proceeding.
- **Success criteria:** Coverage on official test set statistically restored to nominal (or materially closer than E10) with interval widths remaining operationally useful (not vacuous) — **this is Gate 2**: supervisor review before proceeding to Phase 4.
- **Expected runtime:** 2–4 hours (weight estimation/validation + multi-seed evaluation).
- **Compute requirements:** CPU only.
- **Dependencies:** E10, resolution of Q-SEL-01/Q-SEL-03.

---

**— GATE 2 DECISION POINT (supervisor review of E9–E11) —**
Confirms Contribution 1 is real and correctly implemented before Contribution 2 work begins. Also the recommended checkpoint for the arXiv preprint (per project plan).

---

## E12 — Conformalized Quantile Regression (CQR)

- **Objective:** Provide heteroskedastic (event-adaptive) intervals as a methodological complement to split conformal, testing whether adaptivity improves efficiency (narrower intervals at equal coverage) over the fixed-width split-conformal approach.
- **Hypothesis:** CQR achieves comparable coverage to weighted split conformal (E11) while producing tighter intervals for low-uncertainty events and wider ones for genuinely uncertain events, improving overall interval efficiency.
- **Dataset split:** Same structure as E11, using E6's quantile-regression heads.
- **Inputs:** Quantile predictions from E6 (or a quantile-adapted E7); selection-mechanism weights from E11 (weighted CQR variant).
- **Outputs:** CQR intervals on official test set (naive and weighted variants).
- **Metrics:** Coverage (as above); interval width distribution (mean and variance, to assess adaptivity); efficiency comparison vs. E11.
- **Statistical tests:** Coverage test as in E11; paired comparison of interval widths (CQR vs. split conformal) via paired bootstrap.
- **Confidence intervals:** Bootstrap CI, event-level.
- **Figures produced:** Interval width vs. predicted risk level (adaptivity plot); CQR vs. split-conformal width comparison.
- **Tables produced:** Method comparison table (split conformal vs. CQR): coverage and mean width.
- **Failure criteria:** CQR fails to achieve valid coverage even after weighting (points to quantile-head miscalibration in E6, requiring revisit). **[UPDATE 2026-09-16, post-run: this failure criterion WAS met — CQR under-covers on the official test set, naive and weighted — but its hypothesised cause is REFUTED. The E12 self-test diagnostic validated the GBM quantile heads and CQR machinery (coverage ≈ nominal under exchangeability at all levels), so this is NOT E6 quantile-head miscalibration. The actual, unresolved cause is a weight/CQR-score interaction: rule-derived weighting restores split-conformal coverage but not the CQR score's. A future reader should NOT chase an E6-head fix. See DECISIONS.md 2026-09-16 (E12 disposition).]**
- **Success criteria:** Valid coverage with measurable width improvement over split conformal for at least a subset of events.
- **Expected runtime:** 1–3 hours.
- **Compute requirements:** CPU only.
- **Dependencies:** E11, E6.

---

## E13 — Group-Conditional Calibration — **SKIPPED (Gate 1 PIVOT, 2026-08-01)**

> **STATUS: SKIPPED — not run, not scoped down, dropped.** At Gate 1, E4's power analysis derived a
> minimum group size of **200 high-risk events** for a coverage estimate to meet the pre-registered
> 5 pp precision bar. The entire official test set contains **150** high-risk events, and the
> largest single mission contains **32** — so no merging threshold rescues this experiment with the
> available data. This is precisely the failure criterion written into this experiment below ("No
> groups meet the minimum-size threshold → this experiment is skipped/scoped down entirely,
> consistent with the pre-agreed PIVOT"), so the outcome was anticipated by the plan rather than
> improvised. Q-CONF-02 (group merging rule) is closed as moot. Contributions 1, 2 and 3 are
> unaffected. Decided by Sidh; see `DECISIONS.md`, Gate Outcomes.
>
> The full specification is retained below, unedited, so the record of what was planned and why it
> was dropped survives (CLAUDE.md §6: append, do not rewrite).

- **Objective:** Assess and, where powered, deliver per-mission/orbit-group coverage guarantees, addressing the documented cross-mission distribution shift.
- **Hypothesis:** Marginal coverage (E11) can mask meaningful per-group under-coverage; group-conditional calibration improves worst-group coverage relative to the marginally-calibrated method, for groups meeting the Gate-1/Q-CONF-02 minimum-size threshold.
- **Dataset split:** Same as E11, partitioned by mission/group per Q-DATA-01's resolution and Q-CONF-02's merging rule.
- **Inputs:** E11's weighted conformal machinery, applied per group.
- **Outputs:** Per-group prediction intervals; worst-group coverage statistic.
- **Metrics:** Per-group coverage; worst-group coverage (marginal-only vs. group-conditional method); group sample sizes.
- **Statistical tests:** Per-group binomial/Clopper–Pearson coverage tests (only for groups meeting the power threshold); comparison of worst-group coverage across methods.
- **Confidence intervals:** Bootstrap CI, per group, event-level.
- **Figures produced:** Per-group coverage plot (forest-plot style, one row per group, CI whiskers, nominal line).
- **Tables produced:** Per-group coverage table (marginal method vs. group-conditional method).
- **Failure criteria:** No groups meet the minimum-size threshold (per Gate-1 outcome) → this experiment is skipped/scoped down entirely, consistent with the pre-agreed PIVOT.
- **Success criteria:** For groups meeting threshold, group-conditional calibration measurably improves worst-group coverage over marginal-only calibration.
- **Expected runtime:** 1–2 hours (contingent on group count).
- **Compute requirements:** CPU only.
- **Dependencies:** E11, Gate 1 output (group viability), Q-DATA-01 resolution.

---

## E14 — Label-Noise Sensitivity Analysis — Gate 3

- **Objective:** Deliver Contribution 2: quantify how known covariance miscalibration in the risk labels propagates into coverage validity.
- **Hypothesis:** As the covariance-scaling factor departs further from 1.0 (per the pre-declared grid, Q-LBL-02), the achieved coverage of methods calibrated on original labels degrades in a measurable, ideally monotone, pattern relative to the rescaled "true" labels.
- **Dataset split:** Same official test structure as E11, with labels regenerated under each scaling factor via E3's validated Pc computation (scope limited to the complete-covariance-field subset per Q-DATA-05). *[UPDATE 2026-09-16, post-run: "the complete-covariance-field subset" turns out to be **all 2,167 official-test events** — the target-defining CDMs have 0% missingness — so the scoped-M7 restriction bites only through the high-risk **focus stratum**, not through field availability. Two label arms are reported (direct / anchored), both declared in advance, because A4 is a PARTIAL HOLD and the direct arm's level confounds rescaling with recomputation error; see the E14 pre-registration + amendment in DECISIONS.md.]*
- **Inputs:** E11/E12's calibrated intervals; E3's Pc recomputation engine; scaling grid (e.g., 0.8×–2.0×, per Q-LBL-02).
- **Outputs:** Coverage-vs-scaling-factor curves; rescaled-label dataset for the M7-eligible subset.
- **Metrics:** Coverage at each scaling factor; degradation rate; representativeness check (M7 subset vs. full test set label distribution, addressing Q-DATA-05's caveat).
- **Statistical tests:** Trend test (e.g., regression of coverage on scaling factor) for monotonicity; representativeness test (subset vs. full-set distribution comparison, KS test). *[UPDATE 2026-09-16, pre-run: this line CONFLICTS with the Q-STAT-04 resolution, which spends the project's single formal confirmatory contrast on E10-vs-E11 and requires every other comparison to be descriptive. Resolved by computing exactly the named quantities and reporting them with CIs, **labelled exploratory** — no E14 p-value is presented as a confirmatory test. Flagged rather than silently resolved; see the E14 pre-registration in DECISIONS.md §9.]*
- **Confidence intervals:** Bootstrap CI at each grid point, event-level.
- **Figures produced:** **Headline figure** — coverage vs. covariance-scaling factor curve, with CI bands, nominal-coverage reference line.
- **Tables produced:** Scaling-factor sensitivity table; M7-subset representativeness table.
- **Failure criteria:** M7 subset is too small or unrepresentative to support any claim (ties back to E3/Q-LBL-01 outcome — if E3 failed, this experiment runs the reduced/abstract version instead, per the pre-agreed fallback).
- **Success criteria:** A clear, quantified, defensible relationship between label miscalibration and coverage reliability — this result, together with Gate 2's outcome, determines the **Gate 3 venue-tier decision** (Q2 vs. Q1 stretch).
- **Expected runtime:** 3–6 hours (recomputation across grid × methods).
- **Compute requirements:** CPU only.
- **Dependencies:** E3, E11, E12.

---

**— GATE 3 DECISION POINT (supervisor review of E11–E14) —**
Determines target venue tier based on the combined strength of Contributions 1 and 2.

---

## E15 — Decision-Cost Evaluation

*Spec amended 2026-09-18 to match the E15 design review (DECISIONS.md, "E15 design review (Gate 3 binding requirement)"). The four resolutions are marked (D1)–(D4) below; the pre-amendment text is in git history.*

*Expansion 2026-09-18 — per Sidh's instruction to prioritise thoroughness given confirmed schedule slack. E15 now also contains a threshold-based decision analysis that absorbs E16's lead-time dimension. This **supersedes the earlier narrower single-threshold addendum and the separate E16 design**. The matched-budget spec below is unchanged and its results stand. The full protocol is in DECISIONS.md, "PRE-REGISTRATION: expanded threshold-based decision analysis"; in summary:*
- **Rank invariance.** The matched-budget finding is formally grounded by Proposition 1: alerts are identical at every budget if and only if two scores are order-isomorphic. Every method is classified against it, and the classification is empirically confirmed (`reports/05b_rank_invariance.html`).
- **Added decision rule:** alert iff score ≥ t. The grid T is the sorted, deduplicated **union** of the 5th–95th percentiles of pooled point predictions, the 5th–95th percentiles of the pooled values of every validated bound (all methods, both sidednesses), and the fixed operational threshold −6 — all percentiles on the training pool's **internal validation split** (`val_inner`). It is built per horizon, and the official test set is never used to select it (Sidh, 2026-09-19; grid extended by Sidh, 2026-09-20, to fix the ceiling artifact — see the DECISIONS.md pre-registration of that date).
- **Added methods:** point prediction; split and weighted conformal, each as a one-sided upper bound and a two-sided upper edge; CQR in both sidednesses; the E8 Bayesian bound in both. Persistence's one-sided bounds are excluded with disclosure (degenerate quantile, Gate 2).
- **Added outputs.**
  - Per horizon, level, method and threshold: alerts issued, missed high-risk events (primary), and unnecessary maneuvers and rate (secondary), all with bootstrap CIs.
  - Missed-vs-unnecessary operating curves per method, with point-vs-bound shift markers at every grid threshold.
  - Cost-minimizing thresholds per cost ratio: selected on the self-test split and evaluated on the official test set (primary). In-sample oracle optima are reported separately and labelled as not achievable.
- **Lead times (Q-METH-04, resolved by Sidh 2026-09-19): horizons {2-day, 3-day}, both on the official test set.**
  - The originally specified {2-day, 1-day} pair was infeasible: the official test set has no CDMs between 1 and 2 days before TCA.
  - Each horizon gets its own fresh 24-trial hyperparameter search (E6/E7/E8); no reuse across cutoffs.
  - The lead-time comparison uses the official-test events predictable at **both** horizons (2,045 of 2,167). Each horizon's full set is also reported (pre-registration amendment, 2026-09-19).
- **Pre-registered prediction.** Calibration changes alert sets under the threshold rule, with the shift tracking interval half-width. The pre-registration makes this precise as P1a (fixed-threshold operating point shifts by exactly Q), P1b (the translation class's operating locus is unchanged) and P1c (cost optima).
- **Runtime:** estimated from the smoke runs. The full run was launched on Sidh's instruction (2026-09-19), after a real-data smoke run covering both horizons.

- **Objective:** Translate calibrated intervals into operational terms: maneuver/no-maneuver outcomes under explicit cost assumptions, judged first on the events that matter operationally — the true high-risk events (D1, per the Gate 3 binding requirement).
- **Hypothesis:** Decisions informed by calibrated one-sided upper bounds (weighted conformal / CQR) miss fewer high-risk events, and achieve a better missed-high-risk-event vs. unnecessary-maneuver tradeoff, than decisions based on uncalibrated point predictions or the naive Bayesian baseline (E8), at matched alert budgets (D3).
- **Dataset split:** Official test set, using outputs from E8, E11, E12. **Primary reporting population:** the true high-risk events (n = 150). **Secondary:** the whole official test set (D1).
- **Inputs:** Point predictions and **one-sided upper bounds** from E10/E11 (split and rule-weighted conformal), E12 (CQR), and E8 (MC-dropout). The one-sided upper bound is used directly; the two-sided interval's upper edge is **not** substituted (D2). Pre-registered cost ratios **{5:1, 10:1, 20:1}** (missed-high-risk-event cost : unnecessary-maneuver cost) (D3).
- **Decision rule — matched alert budget (D3):** at each evaluation point, every compared method raises the **same total number of maneuver alerts**, so methods are compared at equal operator burden rather than at equal threshold value.
- **Outputs:** Decision outcomes (maneuver/no-maneuver) per event per method per alert budget; cost per cost ratio.
- **Metrics:** **PRIMARY — high-risk events (D1):** missed high-risk events (**the lead number**) and miss rate / recall on high-risk events. **SECONDARY — whole population (D1):** unnecessary maneuvers (false positives) and false-positive rate; F2-style decision score; cost-weighted total at each cost ratio.
- **Mandatory caveat (D2):** every E15 table and figure states that the one-sided upper bound under-covers on the official test set. Per the E11 diagnostic, the one-sided machinery is validated under exchangeability (E9), but rule-derived weighting does not restore one-sided validity. The bound's realised one-sided coverage is reported alongside the decision metrics.
- **Statistical tests:** **None (D4).** E15 is descriptive. Q-STAT-04's single confirmatory contrast (Gate 2's naive-vs-weighted two-sided coverage) stands alone; the previously listed McNemar comparison is withdrawn.
- **Confidence intervals:** Bootstrap CI, event-level, on every reported decision metric.
- **Figures produced:** Tradeoff curves — missed high-risk events vs. unnecessary maneuvers — across methods, swept over the alert budget, with the D2 caveat in the caption.
- **Tables produced:** Decision-cost summary table across methods, alert budgets and cost ratios, with the high-risk (primary) block first and the whole-population (secondary) block after, each carrying the D2 caveat.
- **Failure criteria:** Calibrated methods provide no decision-relevant advantage over point predictions — no reduction in missed high-risk events at matched alert budgets — at any tested cost ratio. This is a reportable, honest negative result, not a project failure; it ties to the pre-agreed "intervals too wide to matter" outcome.
- **Success criteria:** A clear decision-relevant advantage (fewer missed high-risk events at a matched alert budget) in at least one realistic cost regime, or an honestly characterized absence thereof.
- **Expected runtime:** 1–2 hours.
- **Compute requirements:** CPU only.
- **Dependencies:** E8, E11, E12; the E15 design review (DECISIONS.md, 2026-09-18).

---

## E16 — MERGED INTO E15 (entry retained, not deleted, per standing convention)

**Original objective:** characterize how forecast quality and calibration validity change with decision lead time.

**Disposition:** absorbed into E15's expanded design. The {2-day, 3-day} horizon comparison (itself a pre-registered revision of the original {2-day, 1-day} pair — see the Q-METH-04 revision decision) was built directly into E15's threshold-based analysis rather than run as a separate experiment, because doing so let the lead-time comparison and the decision-cost comparison share one coherent, cross-validated pipeline instead of two disconnected ones. E15's report already contains the lead-time results (cost rising and unnecessary maneuvers roughly doubling from 2→3 days; persistence remains cheapest at both horizons). No further E16 work is needed. This entry stays in the plan, marked merged, so nobody re-derives it as if it were still outstanding.

---

## E17 — Robustness, Consistency & Gap-Closure Consolidation (EXPANDED)

- **Objective:** (a) confirm the project's headline results are stable under reasonable alternative statistical choices, as originally scoped; (b) close one specific, identified, unclosed scientific question left open by E15's own findings; (c) consolidate the cross-experiment "train/test imbalance" narrative into a single, checkable artifact rather than leaving it scattered across dated log entries.
- **Hypothesis:** H1 (original scope): headline results (Gate 2's naive-vs-weighted coverage restoration, E14's label-noise sensitivity curve) are robust to reasonable variation in (i) the bootstrap's clustering assumption (Q-STAT-03c), (ii) the weight-clipping cap — noting clipping was never actually triggered (rule k̂ = −2.34, classifier k̂ = 0.17, both comfortably stable), so this sub-check becomes "confirm clipping remains untriggered under a stricter cap, and report why" rather than a live sensitivity sweep — and (iii) the declared multiple-comparison policy (Q-STAT-04). H2 (new): one-sided CQR, whose machinery is now built and validated on the exchangeable self-test split (via E15), also fails to have its coverage restored by rule-derived weighting on the official test set — consistent with the pattern already established for split-conformal one-sided (E11) and CQR two-sided (E12). H3 (new): the "five manifestations of train/test high-risk imbalance" pattern (Phase 2 point-prediction collapse → E14 conditional-coverage collapse → E15 matched-budget ranking collapse → E15's grid-instrument distortion → the grid-extension's asymmetric, partial fix) holds together as a single coherent phenomenon rather than five coincidentally similar but structurally unrelated findings — testable by checking whether a common diagnostic (e.g., per-event high-risk-vs-low-risk prediction residual) predicts which of the five effects an event contributes to.
- **Dataset split:** reuses E11/E12/E14/E15 outputs and cached predictions; the one new computation (H2, one-sided CQR coverage restoration) uses the existing calibration/official-test split structure, no new split needed.
- **Inputs:** E11, E12, E14, E15 outputs; the already-built and self-test-validated one-sided CQR machinery from E15.
- **Outputs:**
  - Robustness supplement (cluster-bootstrap comparison, clipping-cap sensitivity, multiple-comparison policy check) — as originally scoped.
  - The completed {split, CQR} × {two-sided, one-sided} coverage-restoration matrix (currently 3 of 4 cells filled: split two-sided restored, split one-sided not restored, CQR two-sided not restored; this closes the fourth cell for CQR one-sided).
  - A single consolidated cross-experiment synthesis table/figure for the five-manifestation narrative, with the shared diagnostic from H3 if it holds, or an honest statement that the five findings are related in effect but not reducible to one shared per-event mechanism if it doesn't.
  - The stale caveat-string display defect (flagged and deferred at the E15 grid-extension checkpoint) is fixed in this phase's natural re-render — not via a dedicated isolated re-run.
- **Metrics:** coverage and its CIs (for H2, matching E11/E12's existing convention exactly, so the new cell is directly comparable to the other three); qualitative robustness (do headline conclusions reverse under alternative specifications, yes/no, with the CI overlap shown); for H3, correlation/association strength between the candidate shared diagnostic and manifestation membership, reported descriptively (no new formal hypothesis test, consistent with Q-STAT-04's single-primary-contrast policy).
- **Statistical tests:** none beyond what's inherited from E11/E12's existing coverage-test convention for the new CQR one-sided cell. No new formal comparisons introduced.
- **Confidence intervals:** bootstrap, event-level, matching prior convention, for the new CQR one-sided coverage result.
- **Figures produced:** headline-result robustness comparison plot (as originally scoped); the completed 2×2 coverage-restoration matrix, rendered as a single clean table/heatmap — likely the clearest single figure in the paper for stating exactly where the selection-bias correction does and doesn't work; the cross-experiment synthesis figure for the five-manifestation narrative.
- **Tables produced:** robustness supplement table (original scope); completed coverage-restoration matrix table; cross-experiment synthesis summary table.
- **Failure criteria:** headline conclusions reverse under a robustness variant (must be disclosed prominently if so, not buried — unchanged from original scope); H2 comes back ambiguous (neither clearly restored nor clearly not) — report honestly with full CIs rather than forcing a binary call; H3's shared-diagnostic search comes back null — report as "five related but mechanistically distinct findings" rather than overclaiming a single root cause that the data doesn't actually support.
- **Success criteria:** robustness confirmed for headline results (original scope); the coverage-restoration matrix is complete and internally consistent with each cell's own prior finding; the synthesis artifact is honest about what is and isn't shown to be a single mechanism.
- **Expected runtime:** H1 (robustness checks): 1–2 hours, reuses existing outputs. H2 (CQR one-sided backfill): small — reuses already-fitted quantile heads and already-validated bound construction; primarily a scoring pass against the official test set, likely under 30 minutes given no new model fitting is required. H3 (synthesis): analysis/writing time, not compute-heavy.
- **Compute requirements:** CPU only throughout.
- **Dependencies:** E11, E12, E14, E15 (all complete).

---

## E18 — Final Manuscript Figure/Table Consolidation + Reviewer-Checklist Dry Run (EXPANDED)

- **Objective:** produce the final, publication-ready set of figures and tables from the full, now much larger, experiment suite, with consistent styling, self-contained captions, and provenance stamps — and, new to this revision, perform an explicit walkthrough of `REVIEWER_CHECKLIST.md` against the assembled artifact set as a structured final gate before manuscript drafting begins.
- **Hypothesis:** N/A (production/verification step).
- **Inputs:** all figures/tables from E1–E17 (updated from the original E1–E17 scope, which predates E15's expansion and E17's revision above).
- **Outputs:** `reports/manuscript_figures/`, `reports/manuscript_tables/`, each traceable to its generating experiment and commit hash; an updated `REVIEWER_CHECKLIST.md` walkthrough record (see below).
- **Figures produced (revised full list):** selection-bias evidence (E1); Bayesian-baseline coverage failure (E8); naive-vs-weighted two-sided coverage restoration — the Gate 2 headline (E11); E9/E11 one-sided coverage validation and the one-sided non-restoration finding; CQR adaptivity and its coverage caveat (E12); label-noise sensitivity curve with the width-driven-flatness caveat stated in the caption itself (E14); high-risk-conditional coverage with CIs (E14 addendum); the rank-invariance proof's empirical confirmation (E15); the threshold-sweep operating curves, both original and extended grid, with the ceiling-artifact episode noted (E15); the completed coverage-restoration matrix (E17); the cross-experiment synthesis figure (E17). (E13's group-conditional forest plot is removed — skipped per the Gate 1 PIVOT; E16's lead-time figure is subsumed into E15's threshold-sweep figures, not separately listed.)
- **Tables produced:** final versions of all tables listed above, formatted for manuscript submission, each with sample sizes and CIs shown per `REVIEWER_CHECKLIST.md`'s T1/T2 requirements.
- **Failure criteria:** any figure/table cannot be traced to a specific experiment run and commit hash (unchanged from original scope — regenerate, never manually adjust); the reviewer-checklist walkthrough (below) surfaces a top-tier risk with no completed supporting evidence.
- **Success criteria:** every manuscript figure/table is regenerable by one command from a tagged release; the reviewer-checklist walkthrough is complete and every item in its "Pre-Submission Triage: Five Most Likely Rejection Reasons" section has a stated, evidenced disposition (not necessarily resolved in the paper's favor — an honestly reported limitation counts as a disposition).
- **New sub-step — reviewer-checklist dry run:** walk every criticism in `REVIEWER_CHECKLIST.md` (all nine categories) against the now-final artifact set. For each, confirm the cited "supporting experiment" actually produced what the checklist claims it would, and update the checklist itself where new findings from Phases 3–5 (the one-sided/CQR pattern, the five-manifestation imbalance narrative, persistence's dominance under decision-cost analysis) supply a stronger or different defense than what was drafted before those results existed. This is a document-maintenance task, not new experimentation — but it is binding: the manuscript should not go to drafting with a checklist that's stale relative to the actual evidence base.
- **Expected runtime:** 3–5 hours (styling/formatting pass, revised from the original 2–4 hour estimate given the larger figure/table set, plus the reviewer-checklist walkthrough itself).
- **Compute requirements:** CPU only.
- **Dependencies:** E1–E17 (all, including the revised E17 above).

---

## Notes on Scope Discipline

- No experiment above introduces a new project goal beyond PROJECT_KNOWLEDGE.md §5; each maps to Contribution 1 (E9–E13), Contribution 2 (E3, E14), or Contribution 3 (E15–E16), or is infrastructure/validation (E0–E2, E5–E8, E17–E18).
- Several experiments (E9, E13, portions of E14) have pre-agreed reduced-scope fallbacks tied to Gate outcomes (E4, E3) rather than open-ended improvisation, per OPEN_QUESTIONS.md Q-RISK-02.
- Runtimes assume CPU-only execution as the conservative case; all are compatible with PROJECT_KNOWLEDGE's zero-budget, consumer-hardware constraint.
