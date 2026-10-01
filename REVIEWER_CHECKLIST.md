# REVIEWER_CHECKLIST.md

**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Purpose:** Adversarial pre-mortem. Every criticism a hostile-but-competent Q1/Q2 reviewer is likely to raise, with the reason behind it, the defense, and the evidence (experiment, figure or table) that supplies it.
**How to use:** Before submission, walk every item. Any criticism whose evidence is missing, or whose defense is rhetorical rather than empirical, is an open vulnerability — either run the experiment or soften the claim. Open vulnerabilities are marked **[OPEN]** and are listed together at the end.
**Reviewer archetypes assumed:** (R-A) an aerospace/SSA domain expert who does not know conformal prediction; (R-B) a statistician/ML methodologist who does not care about satellites; (R-C) a generalist editor checking rigor, novelty, and fit.

**Revision status (2026-09-22, E18 Part C).** This document was drafted in Phase 0, before most of the evidence it anticipates existed. It has now been revised against the completed record (E1–E17) and the manuscript artifact set built by `kc manuscript` (`reports/manuscript_manifest.json`). Defenses that were written speculatively are replaced by what the experiments actually found, including where the finding is *worse* than anticipated. Figure/table IDs below (F01–T13) are the manuscript artifacts; every number quoted is traceable through that manifest or through the cited `DECISIONS.md` entry. Items whose evidence changed materially: **M1, M4, M5, M8 (new), EV2, EV3, X1, X3, X4, S1–S3, S5, RP1, RP3, RP4, F1–F5, T1, T2**, plus a re-ranked triage list.

---

## 1. Novelty

### N1. "Conformal prediction is a known method. Where is the methodological novelty?" — *R-B*
- **Why they ask:** Applying an existing method to a new dataset is the archetypal weak paper.
- **Defense:** The novelty is not the conformal machinery; it is (a) validity under a *documented, non-random* test-set selection mechanism — an unusually clean case of known covariate shift, specified by the dataset creators rather than estimated; (b) the label-noise sensitivity framework, where the prediction target is itself a model output with known miscalibration; (c) the domain transfer. Venue tier is locked at Q2 aerospace (*Advances in Space Research* primary; Gate 3, 2026-09-18) precisely so the contribution is judged as applied rigor, not as a methods contribution.
- **Strengthened since drafting:** the project also produced a *boundary condition* for the method — weighting restores two-sided coverage but not one-sided, and for CQR it lowers coverage in both (F11, M8). Reporting where a known method stops working is itself a contribution and is harder to dismiss as plumbing.
- **Evidence:** F04 (the correction works), F05 and F11 (where it does not), F07/F08 (label-noise framework).

### N2. "Pinto et al. already did Bayesian uncertainty on this dataset. How is this different?" — *R-A, R-C*
- **Why they ask:** Nearest prior art; reviewers check for an incremental variant.
- **Defense:** Bayesian ≠ calibrated, and this is now shown rather than asserted. The steelmanned MC-dropout baseline (hyperparameters selected on its *own* coverage error) under-covers on the official test set by −0.41 / −5.51 / −6.97 pp at 80/90/95%, and PIT uniformity is rejected for every seed and for the deep ensemble (KS p ≤ 1e-48).
- **Evidence:** F02, F02b (E8).

### N3. "The false confidence theorem paper already argued against Bayesian methods here." — *R-A*
- **Why they ask:** To test whether the authors know their field's theoretical literature.
- **Defense:** That work is purely theoretical (no data, no learned models, no CDM archive) and demands frequentist-valid uncertainty without supplying a practical method. We supply one, and we audit the Bayesian alternative empirically. Cite as motivation, not competition.
- **Evidence:** F02 (the empirical audit), F04 (the frequentist-valid alternative).

### N4. "Several recent papers already work on this dataset. Is it exhausted?" — *R-C*
- **Why they ask:** Editors screen for saturated benchmarks.
- **Defense:** Every prior work targets point-prediction accuracy or class imbalance. None reports coverage, calibration, selection-bias correction, or label-noise sensitivity. The related-work table's empty columns are the argument.
- **Evidence:** Literature review; manuscript related-work table. **[OPEN]** — the comparison table is not yet built as a manuscript artifact.

### N5. "Why should anyone care? Operators use analytic Pc, not ML." — *R-A*
- **Why they ask:** Skepticism of ML papers solving problems practitioners do not have.
- **Defense:** Lead with the agencies' own stated need (ESA, NASA CARA) rather than the method. Note also that the project's decision analysis is framed in operational terms — alerts, missed high-risk events, unnecessary maneuvers, cost ratios — not in abstract loss.
- **Evidence:** Motivation citations; F09, F10 (operational framing).

---

## 2. Statistics

### S1. "Your coverage estimates have huge uncertainty. How many high-risk events are in the test set?" — *R-B*
- **Why they ask:** Coverage is a proportion; with few high-risk events the CI may be wide enough to make claims vacuous.
- **Defense:** Answered pre-emptively and quantitatively. The power analysis ran *before* modeling (E4, Gate 1): marginal precision is a 5.13 pp CI half-width at n_HR = 150, against a pre-registered 5 pp bar; this is reported as ±5.13 pp throughout rather than treated as a pass. Group-conditional analysis was *dropped* at Gate 1 (the derived merge threshold, 200 high-risk events per group, exceeds the test set's entire high-risk count of 150), so no claim is made that the data cannot support. Marginal coverage uses the full n = 2,167, where the primary contrast is decisive (148 discordant events in one direction, 0 in the other; McNemar p = 5.6e-45).
- **Evidence:** E4 Gate 1 decision table; F04; every coverage figure carries CIs (F3).

### S2. "Events are not independent — the same objects recur. Your bootstrap is invalid." — *R-B*
- **Why they ask:** Standard bootstrap CIs assume independence; conjunction events cluster by mission.
- **Defense:** Event-level bootstrap is primary; a mission-level cluster bootstrap (18 missions, largest cluster 16.1% of events) was run as a pre-specified robustness check in E17. Clustering widens intervals, as expected — 44 of 48 arms are wider under the cluster scheme — and the Gate 2 headline survives: persistence's weighted interval lies wholly above nominal under *both* schemes. Verdicts agree in 11 of 12 learner × level cells (persistence, GBM, GRU and MC-dropout; MC-dropout added 2026-10-01 after a pre-registered check, with the other learners' rows verified unchanged); the one disagreement (GBM at 80%) is reported as a wider interval failing to establish under-coverage, not as improved coverage.
- **Evidence:** F04(b) and its robustness table; E17 H1.

### S3. "With dozens of coverage comparisons, some will look significant by chance." — *R-B*
- **Why they ask:** Multiple-comparison inflation across methods × groups × levels.
- **Defense:** Exactly one confirmatory test is declared (naive vs weighted marginal coverage, persistence, 90%, two-sided), fixed before results were seen; everything else is descriptive with CIs. E17 applied the declared Holm–Bonferroni policy and confirmed the family size is 1, so the adjustment is the identity — the single p-value stands unadjusted by construction, not by convenience.
- **Evidence:** Pre-registration in `DECISIONS.md` (Q-STAT-04); E17 H1 multiple-comparison table.

### S4. "Did you choose thresholds/splits after seeing results?" — *R-B, R-C*
- **Why they ask:** Forking paths in single-dataset papers.
- **Defense:** Timestamped pre-registration of primary endpoints, margins, seeds and bootstrap counts before each phase, in a git-auditable log. The log also records the cases where a procedure *was* corrected after the fact, with the correction and its justification stated independently of the result it changed (E17's restoration criterion; E12's validity form; the threshold-grid extension). A record that shows its own corrections is stronger evidence of discipline than one that shows none.
- **Evidence:** `DECISIONS.md`; the corrections are visible in the commit history.

### S5. "Coverage 'close to nominal' — what counts as close? Is that a test or an eyeball?" — *R-B*
- **Why they ask:** Vague success criteria are unfalsifiable.
- **Defense:** Every verdict is computed by a named function with a stated mathematical form, not by eye, and the project distinguishes two questions that need two forms: *validity under shift* (coverage ≥ 1 − α, one-sided, tested on the CI upper bound) and *exactness on exchangeable data* (coverage ∈ [1 − α, 1 − α + 1/(n+1)], two-sided, tested as CI contains nominal). Using the wrong form was a real bug here, found and corrected; the distinction is now presented to readers directly.
- **Evidence:** F12 (the explanatory figure); `robustness.meets_coverage_guarantee` / `consistent_with_exact_coverage` / `restoration_verdict`; `DECISIONS.md` 2026-09-21 methodological note.

### S6. "Single dataset, single split — how do you know this generalizes?" — *R-B, R-C*
- **Why they ask:** External validity.
- **Defense:** Honest limitation, stated explicitly: findings are about this benchmark and this era (2015–2019). Partially mitigated by the exchangeable self-split (the machinery is sound independent of the official split) and multi-seed reporting. No generalization to current orbital environments is claimed.
- **Evidence:** F03 (self-split); limitations section.

---

## 3. Methodology

### M1. "Your weights assume the documented selection mechanism is complete. What if it isn't?" — *R-B, the sharpest methodological attack*
- **Why they ask:** Weighted conformal is exact only if the likelihood ratio is correct; a partially documented mechanism leaves residual bias.
- **Defense, as the evidence actually came out — weaker than the drafted version, and stated as such.** The drafted defense was "report both specifications; agreement is evidence the mechanism is complete." The two specifications do **not** agree: the rule-derived and classifier-derived weights disagree by γ̂ ≈ 1.04e6, which E11's diagnostics attribute to genuine substantive disagreement (the classifier assigns near-zero weight to calibration events the rule keeps), not numerical instability in either. So the agreement argument is unavailable and is not made. What is claimed instead:
  - the exact finite-sample claim rests on the **rule-derived** weights alone, as pre-registered, because the rule *is* the documented mechanism rather than an estimate of it;
  - the rule weights are well-behaved: Pareto k̂ = −2.34 ("stable"), effective n̂ = 1,530 of n = 2,391, 1,673/2,391 positive, no clipping triggered, zero positivity violations;
  - the classifier weights are reported as a *disagreeing* robustness check (k̂ = 0.17, discriminator AUC 0.72), and the disagreement is itself a reported finding;
  - where weights are estimated rather than documented, the guarantee is framed as approximate.
- **Evidence:** F04 and its diagnostics; E11 weight diagnostics; E17 H1 (clipping never triggers under the stricter cap).

### M2. "Positivity/overlap: some test events may have no comparable calibration events." — *R-B*
- **Why they ask:** Weighted methods break silently when weights explode.
- **Defense:** Reported, and clean for the primary construction: all 2,167 official-test events are supported (zero positivity violations), effective sample size n̂ = 1,530, and the pre-registered clipping cap never triggered — including under E17's deliberately stricter trigger.
- **Evidence:** E11 weight diagnostics; E17 H1 clipping table.

### M3. "You're guaranteeing coverage of a *noisy label*, not of true collision probability." — *R-B and sophisticated R-A; the deepest conceptual objection*
- **Why they ask:** The target is itself a model output computed from covariances known to need rescaling.
- **Defense:** Stated as scope ("coverage with respect to the best-available operational risk estimate"), then quantified — with the quantification's own limitation disclosed. The label-noise sensitivity analysis (E14) rescales the covariance by s ∈ [0.8, 2.0] and recomputes labels. The pre-registered primary curve is flat (0.9667 at all seven scales), but **the flatness is a property of persistence's very wide intervals (median 43.4 log-units), not evidence of noise robustness** — binding manuscript scoping from Gate 3 — and the narrower methods degrade monotonically under the same perturbation (Spearman ρ = −1.00 for all three). Recomputation accuracy itself is stratum-dependent and best where it matters: within ±0.5 log10 for 75% of the (−6, 0] band in E3 (n = 100), replicated at n = 2,167 in E14 (79.3% in that band).
- **Evidence:** F07 (with the caveat in the caption), E3/E14 agreement tables; A4 resolved as PARTIAL HOLD with scoped M7 (`DECISIONS.md` 2026-09-16).

### M4. "Why conformal prediction rather than [Bayesian deep learning / quantile regression alone / confidence distributions]?" — *R-B*
- **Why they ask:** Method-choice justification.
- **Defense, now by comparison rather than assertion — including one comparison that cuts against us:**
  - *Bayesian deep learning* is audited and under-covers, increasingly at higher levels, with PIT uniformity rejected (F02).
  - *Quantile regression alone* carries no guarantee; conformalizing it (CQR) is exact on the exchangeable self-split, so the machinery is sound (F06).
  - *Conformal's distinctive property is the one the decision analysis exposes*: a conformal bound that translates its point prediction is a strictly increasing transformation of it, so at a matched alert budget it raises exactly the point prediction's alerts and **cannot** change the decision (Proposition 1; 16/16 translation-class arms confirmed empirically, 0 of 20 methods contradicting). That is a limitation of *threshold-free, budget-matched* use — and simultaneously the argument for conformal over event-specific-dispersion alternatives, which re-rank events without any guarantee (E8) and do not improve the decision either.
  - *Confidence distributions* are discussed as related theory, not as a data-driven forecasting method.
- **Evidence:** F02 (Bayesian), F06 (quantile regression vs CQR), F09 (rank invariance), F10 (threshold-based use, where calibration *does* move the operating point).

### M5. "Your models barely beat the naive baseline. Why is this publishable?" — *R-A, R-C — expect this one guaranteed*
- **Why they ask:** Reviewers pattern-match to point-prediction performance as an ML paper's worth.
- **Defense, rewritten around the evidence rather than the anticipation.** The drafted defense said "models are mediocre but honest." The record is blunter: the learned models do not barely lose, they lose by a wide margin on the official metric — GBM L = 53.46 ± 17.60 and GRU L = 6.39 ± 0.82 against persistence's L = 0.694 — and the gap is not a tuning failure, it is a property of the benchmark's construction. The paper's answer is therefore structural, not apologetic:
  1. **The loss is explained, not excused.** The official test set is enriched 2.49× for high-risk events relative to the training pool, by the organisers' documented construction (F01). Learned models fit the training distribution's low-risk mass and are then scored on an enriched set.
  2. **The same cause is observed five independent times**, by five different experiments with five different measurement methods — point-prediction collapse, conditional-coverage collapse, ranking collapse, instrument distortion, and the partial failure of the fix (T13). One dataset property, five consequences, each separately evidenced.
  3. **The contribution does not depend on winning at point prediction.** It is calibrated, selection-bias-corrected uncertainty — where the correction demonstrably works (F04) and where it does not (F05, F11).
  4. **The decision analysis is reported honestly even though it favors the baseline**: persistence is the cheapest arm at both lead times and every cost ratio (F10). A paper that says "the simplest baseline wins, and here is exactly why, and here is what calibration does and does not add" is more useful than one that manufactures a win.
- **Evidence:** F01, T13, F04, F09, F10; E6/E7 performance table.

### M6. "Are your baselines fairly implemented, or straw men?" — *R-B*
- **Why they ask:** Weak baselines are the commonest way applied papers manufacture improvement.
- **Defense:** The Bayesian baseline is steelmanned by design — its hyperparameter search optimizes its *own* coverage error, not a point metric, so it is tuned for the property it is then audited on. Search budgets are documented and equal across methods (24 trials). The baseline that wins on the official metric is the naive one, which is the opposite of straw-manning.
- **Evidence:** F02; E6/E7/E8 search-budget table.

### M7. "Why these covariance scaling factors? The grid looks arbitrary." — *R-A*
- **Why they ask:** Sensitivity grids invite suspicion of being chosen to produce a pleasing curve.
- **Defense:** The grid is fixed in versioned config and pre-registered before the run, anchored to published covariance-realism findings, and the full grid is reported regardless of which parts are favorable — including the flat curve that is flat for an unflattering reason (M3). The M7 restriction was additionally checked for representativeness and does not bite on field availability: all 2,167 official-test events are M7-eligible (0% missingness in the target-defining fields; KS p = 1.0).
- **Evidence:** F07; E14 eligibility and representativeness tables.

### M8. "Your correction works in one cell out of four. Sometimes weighting makes coverage *worse*." — *R-B — NEW, added 2026-09-22*
- **Why they ask:** This is the sharpest question the completed evidence invites, and a reviewer who reads F11 will ask it immediately. It did not exist when this checklist was drafted because the 2×2 matrix was not yet filled in.
- **The finding, stated plainly:** at nominal 90% on the official test set, rule-derived weighting restores coverage in **1 of 4** cells — two-sided split conformal (0.836 → 0.896). It does not restore one-sided split conformal (0.850 → 0.854). For CQR it *lowers* coverage in both sidednesses (two-sided 0.865 → 0.859; one-sided 0.863 → 0.849), and the one-sided decreases are larger at every level (−5.55 / −1.43 / −2.06 pp at 80/90/95%), holding in 9 of 9 level × seed cells. At 80%, one-sided CQR gains a deficit it did not have. The same pattern appears for one-sided *split* conformal at 80%, where the naive arm shows no deficit and the weighted arm's interval lies wholly below nominal (F05).
- **Defense:** Do not minimize it; scope the claim to match it.
  - The manuscript's exact-coverage claim is stated for **two-sided split conformal only** — this was binding scoping from Gate 2, decided before the matrix was completed, not a retreat after seeing it.
  - The machinery is not at fault: the same one-sided code path and the same CQR construction cover at nominal on the exchangeable self-split (F03, F06), so these are shift effects, not bugs.
  - A mechanism is stated only as far as it is supported: both CQR arms share one quantile head and differ only in the calibration quantile, and coverage is monotone in that quantile, so lower coverage implies a lower weighted quantile. *Why* the rule weights pull it down is explicitly not claimed.
  - Reporting the boundary condition is part of the contribution (N1), and the honest negative is pre-registered behaviour, not damage control.
- **Evidence:** F11 (the matrix), F05 (one-sided split), F06 (CQR, both arms), F03 (machinery exact where assumptions hold).

---

## 4. Reproducibility

### RP1. "Is code and data available?" — *R-C*
- **Why they ask:** Journal artifact policies.
- **Defense:** Public repository, permissive license, pinned environment (`pyproject.toml` + `uv.lock`), checksum-pinned ingest of already-public data, a per-stage CLI (`kc ingest|audit|power|baselines|baselines-phase2|conformal|labelnoise|decision|robustness|manuscript`), and a release tag at every gate so any historical result is reproducible from a tag. Every manuscript figure and table is rebuilt by **one command** (`kc manuscript`) from the experiments' committed tables, with a provenance manifest giving each artifact's source tables (SHA-256) and the commit and config hash of the run that computed them.
- **[OPEN]:** there is **no `kc reproduce-all` entry point**, although `CLAUDE.md` §12 and the earlier draft of this checklist both referred to one. Either implement it or state the per-stage reproduction path in the paper. A DOI-archived release and a container are also not yet produced.
- **Evidence:** `reports/manuscript_manifest.json`; `kc --help`.

### RP2. "Can your results actually be reproduced, or just downloaded?" — *R-B*
- **Why they ask:** Released code often does not run.
- **Defense:** A non-implementer reproduction from a clean machine is an explicit project success criterion, to be reported with the environment used.
- **[OPEN]:** not yet performed.
- **Evidence:** PROJECT_KNOWLEDGE success metric A1.

### RP3. "Random seeds / stochastic variation — are results stable?" — *R-B*
- **Why they ask:** Single-run results are unreliable.
- **Defense:** Three seeds for every stochastic method with variation reported, plus determinism evidence stronger than a CI assertion: E12 was re-run from scratch under a *different* config hash and reproduced all five of its published tables byte-for-byte (verified against a pre-run snapshot before any of its numbers were reused); the GBM/GRU/MC-dropout hyperparameter searches reproduced their caches bit-for-bit across config-hash changes in E14, E15 and E17; and `kc manuscript` is covered by a test that builds the entire artifact set twice and requires byte-identical output, figures included.
- **Evidence:** `tests/test_manuscript.py`; `DECISIONS.md` 2026-09-21 (E12 re-render), E14 §0, E15 §0.

### RP4. "Your Pc recomputation is homegrown. How do we know it's right?" — *R-A*
- **Why they ask:** A bespoke implementation of a standard astrodynamics computation is a credible failure point, and Contribution 2 depends on it.
- **Defense, corrected to what was actually done.** The drafted defense promised cross-validation against NASA CARA's released code; **that was never performed**. What exists instead:
  - the engine reproduces analytic toy geometries to ≤ ~1e-3 relative error, and reproduces the reported `miss_distance` from the state vectors (Pearson r ≈ 1.0), so the geometry half is independently confirmed;
  - recomputed-vs-reported agreement is reported in full, including its failure to clear the pre-registered bar: 65.0% of a stratified sample within ±0.5 log10 (95% CI [0.560, 0.740]) against an 80% bar, with no systematic bias (Wilcoxon p = 0.91) — resolved as **PARTIAL HOLD** with a scoped M7, not as a pass;
  - agreement is stratum-dependent and best in the operationally relevant band (75% within tolerance in (−6, 0] at n = 100; 79.3% at n = 2,167), and the approximations that explain the tail were declared in code before the run.
- **[OPEN]:** the independent-reference cross-validation. Either perform it or state in the paper that validation is against analytic geometries and the challenge's own reported values only.
- **Evidence:** E3 toy-geometry and agreement tables; E14 anchor-agreement table; `DECISIONS.md` 2026-09-16 (A4).

---

## 5. Experiments

### X1. "Where is the ablation study?" — *R-B, R-C*
- **Why they ask:** Standard expectation; absence reads as incompleteness.
- **Defense:** The suite is an ablation by construction, and the ablation table should be presented as such:
  - naive vs weighted conformal — isolates the selection-bias correction (F04);
  - split conformal vs CQR — isolates adaptivity (F06);
  - two-sided vs one-sided — isolates the sidedness of the guarantee (F05, F11);
  - original vs rescaled labels — isolates label noise (F07);
  - point prediction vs calibrated bound at a matched budget — isolates what calibration contributes to the decision (F09).
- **Note:** the drafted "E11 vs E13" row is removed — E13 (group-conditional) was dropped at Gate 1 on power grounds and never ran.
- **Evidence:** F04, F05, F06, F07, F09, F11.

### X2. "Did you validate the method where its assumptions hold before applying it where they don't?" — *R-B*
- **Why they ask:** Otherwise a coverage failure could be an implementation bug, and the selection-bias narrative collapses.
- **Defense:** Yes, by design and before any official-test evaluation. On the exchangeable self-split (n = 2,388), the largest two-sided |gap| is 1.18 pp and the CI contains nominal in 11 of 12 cells; one-sided, for the learned models, in 9 of 9. The one degenerate case (persistence's one-sided bound, identical coverage at 80% and 90% from a large point mass of exactly-zero residuals) is diagnosed as a property of that predictor and excluded from every coverage claim, rather than being absorbed into the shift narrative.
- **Evidence:** F03; F12 (why exactness is tested two-sided here and validity one-sided on the official set).

### X3. "You only evaluate at one lead time. Operators need earlier warning." — *R-A*
- **Why they ask:** Operational relevance; the decision deadline is the crux.
- **Defense, corrected.** The drafted defense cited "E16" and claimed "coverage validity is maintained" across horizons — E16 was merged into the expanded E15, and **no coverage claim across lead times was ever made**. What was actually run is a decision-level lead-time comparison at 2-day and 3-day horizons on a common population (2,045 events, 138 high-risk): full operating curves, a 37/38-point threshold grid per horizon, and costs under 5:1/10:1/20:1. Every learner's best achievable cost is higher at the longer lead time, and persistence remains cheapest at both. The standing caveat travels with it: one-sided upper bounds under-cover on the official test set, so the decision analysis uses the two-sided interval's upper edge and says so.
- **Evidence:** F10 and its tables.

### X4. "Does calibrated uncertainty actually change any decision, or is this a statistics exercise?" — *R-A, R-C — the "so what" question*
- **Why they ask:** Applied venues want operational consequence.
- **Defense, rewritten to lead with the proof rather than the empirics, because the answer is now sharper than "we measured it".** The honest answer is *it depends on the decision rule, and we can say exactly why*:
  1. **Under a matched alert budget: provably not.** Any bound that is a strictly increasing transformation of its point prediction — which split and weighted conformal bounds are, being the point plus one shared quantile — induces the same ranking, so at a fixed budget it raises exactly the same alerts. Calibration cannot change that decision. This is Proposition 1, proved, then confirmed empirically on all 16 translation-class arms (0 alert differences in 192 budget × level comparisons) and across a 20-method structural classification with no contradictions.
  2. **Under a threshold rule: yes.** A calibrated bound sits above its point prediction, so at a fixed operational threshold it moves the operating point along the ranking's curve — alerting more, missing fewer, at a cost in unnecessary maneuvers. The operating curves make the movement explicit at both lead times.
  3. **What the decision analysis concludes, reported as found:** persistence is the cheapest arm at both lead times and every cost ratio (lowest deployable cost at 10:1: 358 [255, 472] at 2 d, 392 [292, 500] at 3 d), and the learned models' point predictions sit so far below the operational threshold that GBM raises 1.3 alerts at t = −6 and misses 137.3 of 138 high-risk events. The negative result is the finding, not a failure to find one.
  4. **A methodological by-product:** the same analysis showed the *measuring instrument* was censored — a threshold grid built from the learned predictions had no resolution above the operational threshold — which was diagnosed, fixed by pre-registered grid extension, and only partly repaired (26.9% vs 69.4% ceiling pinning across the two read-outs). That is disclosed as a limitation of the evaluation, not hidden in it.
- **Evidence:** F09 (the proof's empirical confirmation), F10 (threshold rule, both lead times), T13 rows 3–5.

### X5. "Why not compare against the challenge winners?" — *R-A*
- **Why they ask:** Strongest-known-competitor question.
- **Defense:** Point-prediction accuracy is explicitly not the contribution, and the paper reports its own models losing badly on that axis (M5), so there is no appearance of a manufactured win. Winner methods are described at competition-report fidelity; reimplementation would introduce fidelity disputes without bearing on coverage claims.
- **Evidence:** E5 (published baselines reproduced exactly, so the metric is comparable), E6/E7.

### X6. "The dataset is 2015–2019. The orbital environment has changed dramatically." — *R-A, near-certain*
- **Why they ask:** Mega-constellation growth post-2019.
- **Defense:** Acknowledge directly; the methodological contributions (selection-bias correction, label-noise sensitivity, the rank-invariance result) are era-independent and transfer to any CDM archive; this is the only public benchmark of its kind. Do not pretend the data is current.
- **Evidence:** Limitations section.

---

## 6. Evaluation

### EV1. "Why the F2-style metric? Why that risk threshold?" — *R-A, R-B*
- **Why they ask:** Metric choices encode value judgments.
- **Defense:** These are the challenge's official definitions, adopted for comparability and validated by reproducing the published baseline scores exactly (persistence L = 0.694, matching). Conclusions are additionally reported under three decision-cost ratios so they do not hinge on one metric's implicit weighting.
- **Evidence:** E5 published-comparison table; F10.

### EV2. "Coverage alone is trivial — I can achieve it with infinitely wide intervals." — *R-B, a classic and correct objection*
- **Why they ask:** Coverage without efficiency is meaningless.
- **Defense, strengthened by a distinction the project had to make anyway.** Three parts:
  1. **Width is first-class everywhere.** Every coverage table reports median interval width beside coverage; the width cost of weighting is reported, not hidden (GBM 18.8 → 23.6 log-units at 90%), and CQR's efficiency gain is quantified (≈4.3× narrower than split conformal in the median: 5.5 vs 23.6).
  2. **The gameable case is exactly the one the project treats as a defect, not a pass.** On exchangeable data the project tests *exactness* two-sided: an interval that over-covers fails that test. That is how persistence's degenerate one-sided bound was caught (F03, F12). Conversely, on the shifted official test set the guarantee is one-sided, so a conservative method passes — and the paper says which question it is answering each time. Applying the wrong form was a real bug here; its correction is documented rather than quietly fixed.
  3. **The vacuity objection is answered operationally, not rhetorically.** Persistence's intervals *are* wide (43.4 log-units at 90%), and the paper says so and shows what that width costs: it is why its label-noise curve is flat (M3), and the decision analysis reports exactly how many high-risk events each arm misses and how many unnecessary maneuvers it buys. Width is converted into operational consequence rather than left as a number.
- **Evidence:** F04 (widths in the table), F06 (efficiency), F03 and F12 (over-coverage as a defect where exactness is the question), F07, F10.

### EV3. "Marginal coverage can hide severe group-level failures." — *R-B*
- **Why they ask:** Marginal validity is a weak guarantee; subgroup analysis is standard practice.
- **Defense, rewritten: this moved from an anticipated risk to a measured, CI-bounded finding that the paper discloses itself.** Group-conditional *calibration* (E13) was dropped at Gate 1 on power grounds — the merge threshold (200 high-risk events per group) exceeds the test set's entire high-risk count (150) — so no per-group calibration claim is made. But the high-risk stratum was examined anyway, and the result is uncomfortable and reported:
  - at nominal 90%, coverage conditional on the 150 truly high-risk events is **0.467 [0.387, 0.544]** for rule-weighted GBM and **0.200 [0.138, 0.262]** for rule-weighted CQR, against **0.967 [0.933, 0.993]** for persistence;
  - marginal coverage over all 2,167 events for the same methods is 0.892 and 0.857 — so marginal and conditional diverge by 40+ pp for the narrow methods;
  - the shortfall tracks interval width: the methods that are most informative are least reliable where it matters most, which is the operational reading and is stated as such;
  - this is a disclosed limitation of those methods, and a question distinct from whether the marginal guarantee holds (it does for rule-weighted split conformal; it does not for rule-weighted CQR — M8).
- **A reviewer raising EV3 should find the number already in the paper, with its CI, its n, and its interpretation.** That is the strongest available position given Gate 1's power constraint.
- **Evidence:** F08; E4 Gate 1 decision table (what is and is not powered); T13 row 2.

### EV4. "Did you evaluate on the official test set multiple times?" — *R-B, R-C*
- **Why they ask:** Repeated test-set use invalidates reported performance.
- **Defense:** Documented and enforced protocol: hyperparameter and model selection occur only on internal validation splits; the official test set is used once per pre-specified experiment; the exchangeable self-split exists precisely so exploration never touches it. The rule is in the project's operating rules and auditable in the commit history.
- **Evidence:** `CLAUDE.md` §3; `DECISIONS.md`; F03.

---

## 7. Writing

### W1. "The contribution statement is vague." — *R-C*
- **Defense:** Three numbered contributions, each a falsifiable claim with a pointer to the figure that establishes it — and, where the claim has a boundary, to the figure that marks it (F11).
- **Evidence:** `reports/manuscript_captions.md` (each artifact's claim is stated in its caption).

### W2. "Overclaiming: 'guaranteed' uncertainty for a safety-critical system." — *R-B, R-A*
- **Defense:** Precise language discipline: state what is guaranteed, under which assumptions, with respect to which target. The scope is two-sided split conformal on the official test set, with respect to the operational risk estimate, under the documented selection mechanism. Audit every instance of "guarantee", "ensure", "prove" and "reliable" before submission. Note that "prove" *is* warranted in exactly one place (Proposition 1, rank invariance) and should not be diluted by loose use elsewhere.
- **Evidence:** M3, M8, F12.

### W3. "The paper is written for ML people; I'm an aerospace engineer (or vice versa)." — *R-A or R-B*
- **Defense:** A one-page conformal-prediction primer for the aerospace audience and a compact CDM primer for the statistics audience; glossary in the supplement. F12 doubles as the primer for the one distinction readers most need.
- **Evidence:** PROJECT_KNOWLEDGE glossary.

### W4. "Related work is a list, not a synthesis." — *R-C*
- **Defense:** Organize by gap dimension and close with the N4 comparison table.
- **[OPEN]:** the table is not yet built.

### W5. "Limitations are buried or absent." — *R-B, R-C*
- **Defense:** A dedicated limitations section covering: data era; single benchmark; label-noise caveat and the width-driven flatness of its primary curve; anonymization limiting group analysis; marginal-vs-conditional coverage (EV3); one-sided non-restoration and CQR's adverse weighting effect (M8); the disagreement between weight specifications (M1); residual censoring in the threshold grid's rule-weighted read-out; and the E17 H3 honest null. Stating these first removes the reviewer's leverage.
- **Evidence:** F05, F07, F08, F11, T13; `DECISIONS.md` E17 entries.

---

## 8. Figures

### F1. "Figures don't support the central claim." — *R-C*
- **Defense:** The headline figure is the naive-vs-weighted coverage comparison with the nominal line and CIs explicit (**F04**), immediately followed by the figure that bounds the claim (**F11**). Each contribution has one designated figure: Contribution 1 → F04 (+ F03, F05, F11); Contribution 2 → F07, F08; Contribution 3 → F09, F10.
- **Evidence:** `reports/manuscript_manifest.json`.

### F2. "Where is the evidence the test set is actually biased?" — *R-B*
- **Defense:** Shown empirically as Figure 1 (**F01**): risk and time-to-TCA histograms, train vs official test, with prevalence 2.77% vs 6.92% (2.49×) and the recency filter visible (100% vs 71.9% within 1 day), each with its two-sample test.
- **Evidence:** F01.

### F3. "Coverage plots without confidence bands." — *R-B*
- **Defense:** Every coverage figure carries intervals; no bare coverage point appears anywhere. E8's figure is the one case where the interval had to be derived at build time (it recorded coverage and n but no interval), and that derivation is disclosed in the manifest.
- **Evidence:** F02–F08, F11, F12.

### F4. "Figures are unreadable / not colorblind-safe / unreadable in grayscale print." — *R-C*
- **Defense:** One validated palette across all figures, applied by a single style function; categorical hues assigned in fixed order; every series also carries its own marker so identity survives grayscale; status colors reserved for state and always paired with a text label; vector PDF plus PNG at 300 dpi, with TrueType fonts embedded (Type 42) as journals require; every figure ships with its table, so no reading depends on color alone.
- **Evidence:** `kelvins_conformal.manuscript` style constants; `reports/manuscript_figures/*.pdf`.

### F5. "Figure captions don't stand alone." — *R-C*
- **Defense:** Captions are **generated from the data at build time**, not typed, and every directional claim a caption makes is checked against the source tables before it is written — a caption cannot assert what the data does not show. Each states what is shown, what to conclude, what the error bars are, and n.
- **Evidence:** `reports/manuscript_captions.md`; `_require` checks in `kelvins_conformal.manuscript`.

---

## 9. Tables

### T1. "No confidence intervals in the results table." — *R-B*
- **Defense:** Every metric cell carries a CI or explicit uncertainty; no "best" value is bolded where intervals overlap. The one derived CI (E8's Clopper–Pearson, from the recorded k/n) is labeled as derived.
- **Evidence:** every `reports/manuscript_tables/*.csv`.

### T2. "Sample sizes are not reported per group." — *R-B*
- **Defense:** Every table reports n — official test 2,167, self-split 2,388, calibration 2,391, high-risk stratum 150, common lead-time population 2,045 with 138 high-risk, M7-anchored 494 — and the seed count beside it. The drafted reference to E13 is removed (dropped at Gate 1); the high-risk stratum's n is reported wherever its coverage is (EV3).
- **Evidence:** F03, F04, F08, F10 tables.

### T3. "The comparison table omits obvious competitors." — *R-A, R-C*
- **Defense:** Include the full related-work comparison table covering all identified prior work on this dataset.
- **[OPEN]:** not yet built.

### T4. "Tables report metrics not defined anywhere." — *R-C*
- **Defense:** A methods subsection defining every reported metric mathematically, with the challenge metric matched to the official source and validated by exact baseline reproduction.
- **Evidence:** E5.

---

## Pre-Submission Triage: The Five Most Likely Rejection Reasons

Re-ranked 2026-09-22 against the completed evidence base (E1–E17). Ranked by probability × severity, with the single strongest countermeasure for each.

1. **M5 — "The models lose badly to a naive baseline, and your own decision analysis prefers the baseline."** → Never frame as a point-prediction paper. Lead with the structural explanation (selection bias, F01), the five independently measured consequences (T13), and the honest decision result (F10). *Unchanged at #1: the margin turned out to be far larger than "barely", so the question is now certain to be asked — but the answer is also far better evidenced.*
2. **M8 — "Your correction works in one of four cells, and sometimes makes coverage worse."** → **NEW, entering at #2.** Scope the exact claim to two-sided split conformal (binding since Gate 2, before the matrix was completed), show the machinery is exact where its assumptions hold (F03), and present the boundary as a result (F11, F05, F06) rather than a caveat.
3. **M1 — "Your weights assume a complete selection mechanism."** → *Risk increased since drafting.* The two weight specifications disagree by γ̂ ≈ 1.04e6, so the planned "agreement proves completeness" defense is unavailable and is not used. Rest the exact claim on the rule-derived weights (which *are* the documented mechanism), report their diagnostics (k̂ = −2.34, n̂ = 1,530, no clipping, no positivity violations), and report the disagreement as a finding.
4. **EV3 — "Marginal coverage hides a severe subgroup failure."** → **NEW, entering at #4.** What was a hypothetical is now measured: high-risk-conditional coverage of 0.20–0.47 for the narrow methods against 0.97 for persistence, with CIs and n = 150. Disclose it first, with the interpretation, and connect it to the width trade-off (F08, T13).
5. **M3 — "You calibrate to a noisy label."** → *Down from #3, but still top-five.* E14 quantifies it, and the Gate 3 scoping that the primary curve's flatness is width-driven rather than noise-robustness is stated in the figure caption itself (F07). The remaining exposure is that the most reassuring curve is the least informative one.

**Moved out of the top five:**
- **S1 ("coverage estimates are underpowered")** — *out, was #2.* The power analysis ran before modeling and its result is reported as ±5.13 pp; the only underpowered analysis (group-conditional) was dropped at Gate 1 rather than reported weakly; the primary contrast is decisive (148 vs 0 discordant, p = 5.6e-45); every coverage figure carries CIs; and E17's cluster bootstrap shows the headline survives a weaker independence assumption. The residual risk is now about *subgroup* coverage, which is EV3's item, not about precision.
- **N1 ("conformal prediction isn't new")** — *out, was #4.* Venue tier is locked at Q2 aerospace (Gate 3), where applied rigor is the expected contribution, and the project now also reports a boundary condition for the method (M8), which is harder to characterize as plumbing. Still worth a crisp paragraph; no longer a top-five rejection risk.

**Open vulnerabilities (the checklist's own rule: evidence missing or defense rhetorical).** These are not ranked above, because each is work to be done rather than a finding to defend: N4/W4/T3 (the related-work comparison table is not built), RP1 (no `kc reproduce-all`; no DOI-archived release or container), RP2 (clean-machine reproduction by a non-implementer not yet performed), RP4 (no cross-validation of the Pc engine against an independent reference implementation).

If any top-five item lacks its supporting evidence at submission time, or any open vulnerability above is still open, the paper is not ready.
