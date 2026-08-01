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
| E15 | Decision-cost evaluation | 5 | — |
| E16 | Lead-time / horizon tradeoff analysis | 5 | — |
| E17 | Robustness & sensitivity consolidation | 5 | — |
| E18 | Final manuscript figure/table consolidation | 5 | — |

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
- **Inputs:** E6 and/or E7 point predictors, retrained or reused on the fit portion.
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
- **Dependencies:** E6, E7 (whichever base learner(s) are carried forward).

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
- **Failure criteria:** CQR fails to achieve valid coverage even after weighting (points to quantile-head miscalibration in E6, requiring revisit).
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
- **Dataset split:** Same official test structure as E11, with labels regenerated under each scaling factor via E3's validated Pc computation (scope limited to the complete-covariance-field subset per Q-DATA-05).
- **Inputs:** E11/E12's calibrated intervals; E3's Pc recomputation engine; scaling grid (e.g., 0.8×–2.0×, per Q-LBL-02).
- **Outputs:** Coverage-vs-scaling-factor curves; rescaled-label dataset for the M7-eligible subset.
- **Metrics:** Coverage at each scaling factor; degradation rate; representativeness check (M7 subset vs. full test set label distribution, addressing Q-DATA-05's caveat).
- **Statistical tests:** Trend test (e.g., regression of coverage on scaling factor) for monotonicity; representativeness test (subset vs. full-set distribution comparison, KS test).
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

- **Objective:** Translate calibrated intervals into operational terms: maneuver/no-maneuver outcomes under explicit cost assumptions.
- **Hypothesis:** Decisions informed by calibrated (weighted conformal / CQR) intervals achieve a better missed-high-risk-event vs. unnecessary-maneuver tradeoff than decisions based on uncalibrated point predictions or the naive Bayesian baseline (E8), at matched alert budgets.
- **Dataset split:** Official test set, using outputs from E8, E11, E12.
- **Inputs:** Interval/point outputs from prior experiments; a small set of pre-declared cost ratios (missed-event cost vs. unnecessary-maneuver cost).
- **Outputs:** Decision outcomes (maneuver/no-maneuver) per event per method per cost ratio.
- **Metrics:** F2-style decision score; false-negative rate (missed high-risk events); false-positive rate (unnecessary maneuvers); cost-weighted total.
- **Statistical tests:** Paired comparison of decision outcomes across methods (e.g., McNemar's test on maneuver decisions where applicable).
- **Confidence intervals:** Bootstrap CI, event-level, on decision-cost metrics.
- **Figures produced:** Cost-tradeoff curves (false-negative vs. false-positive rate) across methods, at varying thresholds.
- **Tables produced:** Decision-cost summary table across methods and cost ratios.
- **Failure criteria:** Calibrated methods provide no decision-relevant advantage over point predictions at any tested cost ratio (a reportable, honest negative result, not a project failure — ties to the pre-agreed "intervals too wide to matter" outcome).
- **Success criteria:** A clear decision-relevant advantage in at least one realistic cost regime, or an honestly characterized absence thereof.
- **Expected runtime:** 1–2 hours.
- **Compute requirements:** CPU only.
- **Dependencies:** E8, E11, E12.

---

## E16 — Lead-Time / Horizon Tradeoff Analysis

- **Objective:** Characterize how forecast quality and calibration validity change with decision lead time (per Q-METH-04's resolved horizon set).
- **Hypothesis:** Coverage validity is maintained across horizons (a property of the conformal guarantee), but interval width increases at longer lead times, quantifying the accuracy-vs-warning-time tradeoff operators face.
- **Dataset split:** Official test set, predictions re-generated at each horizon cutoff.
- **Inputs:** Horizon-specific feature/prediction pipelines (re-run of E6/E7/E11/E12 at each horizon).
- **Outputs:** Per-horizon coverage and width tables.
- **Metrics:** Coverage and interval width at each horizon; degradation trend.
- **Statistical tests:** Trend test across horizons (regression of width/coverage on horizon).
- **Confidence intervals:** Bootstrap CI, event-level, per horizon.
- **Figures produced:** Interval width vs. lead time; coverage vs. lead time.
- **Tables produced:** Per-horizon results table.
- **Failure criteria:** Coverage breaks down materially at longer horizons (would need discussion of why the guarantee weakens — likely a positivity/support issue) rather than the expected width-only degradation.
- **Success criteria:** Coverage remains valid across horizons with the expected, interpretable width-vs-lead-time tradeoff — this is the paper's operational takeaway figure.
- **Expected runtime:** 3–5 hours (repeats core pipeline per horizon).
- **Compute requirements:** CPU only.
- **Dependencies:** E11, E12, resolution of Q-METH-04.

---

## E17 — Robustness & Sensitivity Consolidation

- **Objective:** Consolidate the robustness checks flagged throughout (cluster bootstrap, weight positivity/clipping sensitivity, multiple-comparison policy application) into one coherent supplementary analysis.
- **Hypothesis:** Headline results (E11, E14) are robust to: (a) clustering assumption in the bootstrap (Q-STAT-03c), (b) reasonable variation in the weight-clipping cap (Q-SEL-03), (c) the declared multiple-comparison policy (Q-STAT-04) not altering the primary conclusion.
- **Dataset split:** Reuses E11/E14 outputs; no new modeling.
- **Inputs:** Outputs of E11, E14; alternative bootstrap/clipping configurations.
- **Outputs:** Robustness supplement (tables/figures for the appendix).
- **Metrics:** Headline coverage/width results recomputed under each robustness variant.
- **Statistical tests:** Consistency check across variants (qualitative + CI overlap).
- **Confidence intervals:** As in E11/E14, recomputed per variant.
- **Figures produced:** Robustness comparison plot (headline result under default vs. alternative configurations).
- **Tables produced:** Robustness supplement table.
- **Failure criteria:** Headline conclusions reverse under reasonable alternative configurations — must be disclosed prominently, not buried, and would likely soften the paper's claims.
- **Success criteria:** Headline conclusions are stable across reasonable variants — supports the "not p-hacked" narrative directly.
- **Expected runtime:** 2–3 hours.
- **Compute requirements:** CPU only.
- **Dependencies:** E11, E14.

---

## E18 — Final Manuscript Figure/Table Consolidation

- **Objective:** Produce the final, publication-ready set of figures and tables from all prior experiments, with consistent styling, captions, and provenance stamps.
- **Hypothesis:** N/A (production step).
- **Dataset split:** N/A (aggregation of prior outputs).
- **Inputs:** All figures/tables from E1–E17.
- **Outputs:** `reports/manuscript_figures/`, `reports/manuscript_tables/`, each traceable to its generating experiment and commit hash.
- **Metrics:** N/A.
- **Statistical tests:** N/A.
- **Confidence intervals:** Carried through unchanged from source experiments (no re-derivation).
- **Figures produced:** Final versions of: selection-bias evidence (E1), Bayesian-baseline coverage failure (E8), naive-vs-weighted coverage (E11), CQR adaptivity (E12), group-conditional forest plot (E13), label-noise sensitivity curve (E14), decision-cost tradeoff (E15), lead-time tradeoff (E16), robustness supplement (E17).
- **Tables produced:** Final versions of all tables listed above, formatted for manuscript submission.
- **Failure criteria:** Any figure/table cannot be traced to a specific experiment run and commit hash (violates the reproducibility invariant; must be regenerated, not manually adjusted).
- **Success criteria:** Every manuscript figure/table is regenerable by one command from a tagged release, matching PROJECT_KNOWLEDGE's success metric A1.
- **Expected runtime:** 2–4 hours (formatting/styling pass).
- **Compute requirements:** CPU only.
- **Dependencies:** All prior experiments (E1–E17).

---

## Notes on Scope Discipline

- No experiment above introduces a new project goal beyond PROJECT_KNOWLEDGE.md §5; each maps to Contribution 1 (E9–E13), Contribution 2 (E3, E14), or Contribution 3 (E15–E16), or is infrastructure/validation (E0–E2, E5–E8, E17–E18).
- Several experiments (E9, E13, portions of E14) have pre-agreed reduced-scope fallbacks tied to Gate outcomes (E4, E3) rather than open-ended improvisation, per OPEN_QUESTIONS.md Q-RISK-02.
- Runtimes assume CPU-only execution as the conservative case; all are compatible with PROJECT_KNOWLEDGE's zero-budget, consumer-hardware constraint.
