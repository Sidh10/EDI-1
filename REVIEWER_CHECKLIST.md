# REVIEWER_CHECKLIST.md

**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Purpose:** Adversarial pre-mortem. Every criticism a hostile-but-competent Q1/Q2 reviewer is likely to raise, with the reason behind it, the defense, and the experiment (per EXPERIMENT_PLAN.md) that supplies evidence for that defense.
**How to use:** Before submission, walk every item. Any criticism whose "supporting experiment" column is empty or whose defense is rhetorical rather than empirical is an open vulnerability — either run the experiment or soften the claim.
**Reviewer archetypes assumed:** (R-A) an aerospace/SSA domain expert who does not know conformal prediction; (R-B) a statistician/ML methodologist who does not care about satellites; (R-C) a generalist editor checking rigor, novelty, and fit. Different criticisms come from different archetypes and are tagged accordingly.

---

## 1. Novelty

### N1. "Conformal prediction is a known method. Where is the methodological novelty?" — *R-B, most likely rejection reason at a Q1 ML-adjacent venue*
- **Why they ask:** Applying an existing method to a new dataset is the archetypal weak paper. Reviewers are trained to check whether the contribution is *method* or *plumbing*.
- **Defense:** The novelty is not the conformal machinery; it is (a) validity under a *documented, non-random* test-set selection mechanism — an unusually clean case of known covariate shift where the shift is specified by the dataset creators rather than estimated; (b) the label-noise sensitivity framework, where the prediction target is itself a model output with known miscalibration; (c) the domain transfer itself, which no prior work has performed. Frame the paper as an applied-rigor contribution at an aerospace venue, not a methods contribution at an ML venue — venue choice is itself part of the defense.
- **Supporting experiments:** E10 (demonstrates the problem exists), E11 (demonstrates the correction), E14 (label-noise framework).

### N2. "Pinto et al. already did Bayesian uncertainty on this dataset. How is this different?" — *R-A, R-C*
- **Why they ask:** Nearest prior art; reviewers check whether the new work is an incremental variant.
- **Defense:** Bayesian ≠ calibrated. Prior work produced uncertainty estimates but never verified them against observed frequencies. Our contribution is precisely the verification plus a method with distribution-free guarantees. Do not merely assert this — reproduce their method and *show* its coverage deficiency empirically.
- **Supporting experiment:** E8 (steelmanned MC-dropout reproduction with coverage audit) — this experiment exists specifically to answer N2.

### N3. "The false confidence theorem paper already argued against Bayesian methods here." — *R-A (well-read domain expert)*
- **Why they ask:** To test whether the authors know their own field's theoretical literature, and whether the contribution is redundant with it.
- **Defense:** That work is purely theoretical (no data, no learned models, no CDM archive) and demands frequentist-valid uncertainty without supplying a practical data-driven method. We supply one. Cite it prominently as motivation, not as competition — being the bridge between that critique and ML practice is a strength, not overlap.
- **Supporting experiments:** E8 + E11 (the empirical instantiation of what that literature argues for).

### N4. "A December 2025 GAN paper and several others already work on this dataset. Is the dataset exhausted?" — *R-C*
- **Why they ask:** Editors screen for saturated benchmarks.
- **Defense:** Every prior work targets point-prediction accuracy or class imbalance. None reports coverage, calibration, selection-bias correction, or label-noise sensitivity. Include an explicit related-work table with columns (point prediction / uncertainty estimate / coverage verified / selection bias handled / label noise analyzed) — the empty columns are the argument.
- **Supporting evidence:** Literature review document; related-work table in the manuscript (E18 consolidation).

### N5. "Why should anyone care? Operators use analytic Pc, not ML." — *R-A*
- **Why they ask:** Aerospace reviewers are skeptical of ML papers that solve problems practitioners don't have.
- **Defense:** Cite ESA's and NASA CARA's own published statements that ML-assisted conjunction assessment is an active open research question, and that the short decision window with few CDMs is the specific difficulty. The paper's framing must lead with the agencies' stated need, not with the method.
- **Supporting evidence:** Motivation section citations (NASA CARA 2025 compendium; ESA challenge paper's own conclusions).

---

## 2. Statistics

### S1. "Your coverage estimates have huge uncertainty. How many high-risk events are actually in the test set?" — *R-B, the single most dangerous statistical criticism*
- **Why they ask:** Coverage is a proportion; with few high-risk events, the confidence interval on coverage may be wide enough to make every claim vacuous.
- **Defense:** Pre-emptive, not reactive: the paper reports a power analysis performed *before* modeling, states the achievable precision explicitly, and confines claims to what the data supports (marginal claims if group-level is underpowered). Report CIs on coverage itself, always — never a bare coverage number.
- **Supporting experiment:** E4 (power analysis; the Gate 1 decision table goes in the paper or supplement).

### S2. "Events are not independent — the same objects recur. Your bootstrap is invalid." — *R-B*
- **Why they ask:** Standard binomial/bootstrap CIs assume independence; conjunction events plausibly cluster by object, mission, or orbital regime.
- **Defense:** Report event-level bootstrap as primary, plus a cluster-bootstrap sensitivity analysis grouping by mission (or by near-duplicate state vectors if identifiable). If clustering cannot be identified due to anonymization, say so explicitly as a limitation rather than ignoring it.
- **Supporting experiments:** E1 (duplicate/clustering audit), E17 (cluster-bootstrap robustness variant).

### S3. "With dozens of coverage comparisons, some will look significant by chance." — *R-B*
- **Why they ask:** Multiple-comparison inflation across methods × groups × nominal levels.
- **Defense:** Declare one primary contrast (naive vs. weighted marginal coverage on the official test set) as the confirmatory test; treat everything else as descriptive with CIs. State this policy in the methods section, and state that it was fixed before results were seen.
- **Supporting evidence:** Pre-registration record (DECISIONS.md / OSF entry); E17 documents that conclusions are stable under the declared policy.

### S4. "Did you choose the thresholds/splits after seeing results?" — *R-B, R-C*
- **Why they ask:** Forking paths / p-hacking suspicion, especially in single-dataset papers.
- **Defense:** Timestamped pre-registration of primary endpoints, success margins, seed counts, and bootstrap counts before Phase 3 runs; the DECISIONS.md log with git timestamps is auditable evidence. This is unusual in aerospace venues and reads as a strength.
- **Supporting evidence:** DECISIONS.md; optional public OSF pre-registration.

### S5. "Coverage 'close to nominal' — what counts as close? Is that a test or an eyeball?" — *R-B*
- **Why they ask:** Vague success criteria are unfalsifiable.
- **Defense:** Report formal coverage tests (binomial/Clopper–Pearson against nominal) alongside the pre-declared acceptance margin derived from the power analysis. Never write "approximately nominal" without an accompanying interval and test.
- **Supporting experiments:** E9, E10, E11 (all specify coverage tests, not visual comparison).

### S6. "Single dataset, single split — how do you know this generalizes?" — *R-B, R-C*
- **Why they ask:** External validity.
- **Defense:** Honest limitation, stated explicitly: findings are about this benchmark and this era (2015–2019). Partially mitigated by the self-split validation (showing the machinery is sound independent of the official split) and multi-seed reporting. Do not overclaim generalization to current orbital environments.
- **Supporting experiment:** E9 (independent exchangeable split), plus explicit limitations paragraph.

---

## 3. Methodology

### M1. "Your weights assume the documented selection mechanism is complete. What if it isn't?" — *R-B, the sharpest methodological attack*
- **Why they ask:** Weighted conformal's validity is exact only if the likelihood ratio is correct; a partially-documented mechanism yields residual bias.
- **Defense:** Two-pronged. (a) Report both the rule-derived weights and an estimated-propensity variant; agreement between them is evidence the documented mechanism is close to complete, disagreement is itself a reportable finding. (b) Explicitly frame guarantees as approximate where weights are estimated, and bound/discuss residual bias rather than claiming exactness.
- **Supporting experiments:** E11 (primary weighted method), E17 (weight-specification robustness).

### M2. "Positivity/overlap: some test events may have no comparable calibration events." — *R-B*
- **Why they ask:** Weighted methods break silently when weights explode.
- **Defense:** Report weight distributions, effective sample size after weighting, and positivity diagnostics; use a pre-registered clipping cap and characterize any excluded subpopulation explicitly rather than silently dropping it.
- **Supporting experiments:** E11 (weight diagnostics are a specified output), E17 (clipping-cap sensitivity).

### M3. "You're guaranteeing coverage of a *noisy label*, not of true collision probability. Isn't that meaningless?" — *R-B and sophisticated R-A; the deepest conceptual objection*
- **Why they ask:** The target is itself a model output computed from covariances known to need rescaling. A calibrated interval around a miscalibrated quantity is philosophically awkward.
- **Defense:** Do not hide from this — make it the paper's intellectual centerpiece. State scope precisely ("coverage with respect to the best-available operational risk estimate"), then quantify exactly how much that caveat costs via the label-noise sensitivity analysis. A reviewer who raises M3 and finds an entire section answering it becomes an ally.
- **Supporting experiments:** E3 (Pc recomputation feasibility), E14 (coverage vs. covariance-scaling curves).

### M4. "Why conformal prediction rather than [Bayesian deep learning / quantile regression alone / confidence distributions]?" — *R-B*
- **Why they ask:** Method-choice justification.
- **Defense:** Bayesian baselines are empirically audited and shown to under-cover (E8); plain quantile regression is included as the pre-conformal component of CQR and shown to lack guarantees; confidence distributions (the 2025 Entropy response to false confidence) are discussed as related theoretical work but are not data-driven forecasting methods. Justify by comparison, not assertion.
- **Supporting experiments:** E8 (Bayesian), E12 (quantile regression vs. CQR).

### M5. "Your models barely beat the naive baseline. Why is this publishable?" — *R-A, R-C — expect this one guaranteed*
- **Why they ask:** Reviewers pattern-match to point-prediction performance as the measure of an ML paper's worth.
- **Defense:** Pre-empt in the abstract and introduction: the challenge itself established that point prediction resists improvement on this data, and that is *why* calibrated uncertainty is the operationally valuable contribution. A model that is mediocre but honest about its uncertainty is more useful for a maneuver decision than one that is marginally better but silently overconfident. Never frame the paper as a point-prediction improvement paper.
- **Supporting experiments:** E5, E6, E7 (establish the point-prediction landscape honestly), E15 (shows decision-relevant value independent of point accuracy).

### M6. "Are your baselines fairly implemented, or straw men?" — *R-B*
- **Why they ask:** Weak baselines are the most common way applied papers manufacture apparent improvement.
- **Defense:** Steelman explicitly — tune the MC-dropout baseline for its *own* coverage performance before auditing it, document hyperparameter search budgets equal across methods, and use authors' released code where available. State the steelmanning procedure in the methods section.
- **Supporting experiment:** E8 (specified as steelmanned by design).

### M7. "Why these covariance scaling factors? The grid looks arbitrary." — *R-A*
- **Why they ask:** Sensitivity grids invite suspicion of being chosen to produce a pleasing curve.
- **Defense:** Anchor the grid to published ESA covariance-realism findings (cite the primary Space Debris Conference analysis with its actual reported numbers, not a secondhand characterization), and report the full grid regardless of which parts are favorable.
- **Supporting experiment:** E14; grid values fixed in config and pre-registered.

---

## 4. Reproducibility

### RP1. "Is code and data available?" — *R-C, increasingly a hard requirement*
- **Why they ask:** Journal artifact policies; reproducibility crisis norms.
- **Defense:** Public repository, permissive license, DOI-archived release, one-command reproduction (`kc reproduce-all`), pinned environment and container. Data is already public (CC-BY) with checksum-pinned ingest.
- **Supporting experiment:** E18 (consolidation verifies every figure/table is regenerable from a tag).

### RP2. "Can your results actually be reproduced, or just downloaded?" — *R-B*
- **Why they ask:** Released code often doesn't run.
- **Defense:** A non-implementer reproduces the full pipeline from a clean machine before submission (this is an explicit project success criterion, not an aspiration). Report the reproduction as performed, with the environment used.
- **Supporting evidence:** PROJECT_KNOWLEDGE success metric A1; E18.

### RP3. "Random seeds / stochastic variation — are results stable?" — *R-B*
- **Why they ask:** Single-run results are unreliable, especially for neural components.
- **Defense:** Multi-seed runs (≥3) with variation reported for every stochastic method; determinism tests in CI proving same-config-same-seed reproducibility.
- **Supporting experiments:** E6, E7, E8 (all specify multi-seed aggregation with CIs).

### RP4. "Your Pc recomputation is homegrown. How do we know it's right?" — *R-A*
- **Why they ask:** A bespoke implementation of a standard astrodynamics computation is a credible failure point, and the label-noise contribution depends entirely on it.
- **Defense:** Cross-validate against an authoritative reference implementation (NASA CARA's publicly released conjunction-assessment code) on sample cases and report the agreement quantitatively; publish the comparison as a supplementary figure.
- **Supporting experiment:** E3 (recomputed-vs-reported scatter plot and error table are specified outputs).

---

## 5. Experiments

### X1. "Where is the ablation study?" — *R-B, R-C*
- **Why they ask:** Standard expectation; absence reads as incompleteness.
- **Defense:** The experiment suite is structured as an ablation by construction: naive vs. weighted conformal (isolates the selection-bias correction), split conformal vs. CQR (isolates adaptivity), marginal vs. group-conditional (isolates grouping), original vs. rescaled labels (isolates label noise). Present this explicitly as an ablation table so reviewers recognize it.
- **Supporting experiments:** E10 vs. E11; E11 vs. E12; E11 vs. E13; E11 vs. E14.

### X2. "Did you validate the method where its assumptions hold before applying it where they don't?" — *R-B*
- **Why they ask:** Otherwise a coverage failure could be an implementation bug rather than a real phenomenon — and the entire selection-bias narrative collapses.
- **Defense:** Yes, by design: the exchangeable self-split validation runs before any official-test-set evaluation, precisely to separate "our code is wrong" from "the test set is biased."
- **Supporting experiment:** E9 (this experiment exists specifically to answer X2).

### X3. "You only evaluate at one lead time. Operators need earlier warning." — *R-A*
- **Why they ask:** Operational relevance; the decision deadline is the crux of the real problem.
- **Defense:** Lead-time tradeoff analysis across horizons, reporting how interval width degrades with earlier prediction while coverage validity is maintained.
- **Supporting experiment:** E16.

### X4. "Does calibrated uncertainty actually change any decision, or is this a statistics exercise?" — *R-A, R-C — the "so what" question*
- **Why they ask:** Applied venues want operational consequence, not just methodological correctness.
- **Defense:** Decision-cost evaluation under explicit cost ratios, comparing maneuver/no-maneuver outcomes against uncalibrated alternatives at matched alert budgets. Be prepared for the honest negative version: if intervals are too wide to change decisions, report that clearly — it is a real finding about the data's information content, and hiding it would be worse.
- **Supporting experiment:** E15.

### X5. "Why not compare against the challenge winners?" — *R-A*
- **Why they ask:** Obvious strongest-known-competitor question.
- **Defense:** Point-prediction accuracy is explicitly not the contribution; winner methods are described at competition-report fidelity and reimplementation would introduce fidelity disputes without bearing on coverage claims. State this in one crisp sentence rather than appearing to have overlooked it. If organizer/winner code becomes available, include it.
- **Supporting evidence:** Explicit scope statement; E5/E6 establish the point-prediction context.

### X6. "The dataset is 2015–2019. The orbital environment has changed dramatically." — *R-A, near-certain*
- **Why they ask:** Mega-constellation growth post-2019 makes the data era feel stale.
- **Defense:** Acknowledge directly in limitations; note that the methodological contributions (selection-bias correction, label-noise sensitivity) are era-independent and transfer to any CDM archive; note that this is the only public benchmark of its kind, and that agency outreach for newer data was attempted. Do not pretend the data is current.
- **Supporting evidence:** Limitations section; outreach correspondence record.

---

## 6. Evaluation

### EV1. "Why the F2-style metric? Why that risk threshold?" — *R-A, R-B*
- **Why they ask:** Metric choices encode value judgments and can be gamed.
- **Defense:** These are the challenge's official definitions, adopted for comparability, not chosen by us — and validated by reproducing published baseline scores exactly. Additionally report decision-cost results under multiple cost ratios so conclusions do not hinge on one metric's implicit weighting.
- **Supporting experiments:** E5 (metric validation against published scores), E15 (multiple cost ratios).

### EV2. "Coverage alone is trivial — I can achieve it with infinitely wide intervals." — *R-B, a classic and correct objection*
- **Why they ask:** Coverage without efficiency is meaningless.
- **Defense:** Always report interval width alongside coverage; include efficiency comparisons (CQR vs. split conformal) and demonstrate that intervals remain operationally useful, not vacuous. Width is a first-class reported quantity throughout, never an afterthought.
- **Supporting experiments:** E11, E12 (width reported and compared), E15 (usefulness demonstrated via decisions).

### EV3. "Marginal coverage can hide severe group-level failures." — *R-B*
- **Why they ask:** Marginal validity is a weak guarantee; fairness/subgroup analysis is now standard practice.
- **Defense:** Report per-group coverage where statistically powered, including worst-group coverage; where not powered, say so explicitly rather than reporting noisy per-group numbers as if meaningful.
- **Supporting experiments:** E13 (group-conditional), E4 (determines what is powered).

### EV4. "Did you evaluate on the official test set multiple times?" — *R-B, R-C*
- **Why they ask:** Repeated test-set use invalidates reported performance.
- **Defense:** Documented protocol: hyperparameter and model selection occur only on internal validation splits; official test set used once per pre-specified experiment; the rule is enforced in the project's operating rules and auditable in the commit history.
- **Supporting evidence:** CLAUDE.md research rules; DECISIONS.md; E9's self-split exists precisely so exploration never touches the official test set.

---

## 7. Writing

### W1. "The contribution statement is vague." — *R-C*
- **Why they ask:** Editors triage on clarity of contribution.
- **Defense:** Three numbered contributions in the abstract and introduction, each stated as a falsifiable claim with a pointer to the section and figure that establishes it.
- **Supporting evidence:** E18 (figure/table-to-claim mapping).

### W2. "Overclaiming: 'guaranteed' uncertainty for a safety-critical system." — *R-B, R-A*
- **Why they ask:** Conformal guarantees are marginal, finite-sample, and conditional on assumptions that this dataset violates in known ways. Overclaiming in a safety domain is a serious flaw.
- **Defense:** Precise language discipline throughout: state what is guaranteed, under which assumptions, with respect to which target. Prefer "coverage-valid with respect to the operational risk estimate under the documented selection mechanism" over "guaranteed safe." Audit the manuscript for every instance of "guarantee," "ensure," "prove," and "reliable" before submission.
- **Supporting evidence:** M3 defense; E14.

### W3. "The paper is written for ML people; I'm an aerospace engineer (or vice versa)." — *R-A or R-B, depending*
- **Why they ask:** Interdisciplinary submissions routinely lose one reviewer to jargon.
- **Defense:** A short "conformal prediction in one page" primer for the aerospace audience, and a compact CDM/conjunction-assessment primer for the statistics audience. Glossary in supplement. This costs one page and prevents a reviewer from being unable to assess the work.
- **Supporting evidence:** PROJECT_KNOWLEDGE glossary as the source material.

### W4. "Related work is a list, not a synthesis." — *R-C*
- **Why they ask:** Literature reviews that merely enumerate signal shallow engagement.
- **Defense:** Organize related work by *gap dimension* (point prediction / uncertainty estimation / decision layer / statistical foundations) and close with the comparison table from N4, making the unoccupied intersection visually obvious.
- **Supporting evidence:** Literature review document with per-paper gap analysis.

### W5. "Limitations are buried or absent." — *R-B, R-C*
- **Why they ask:** Reviewers trust papers that state their own weaknesses first.
- **Defense:** Dedicated limitations section covering: data era, single benchmark, label-noise caveat, anonymization limiting group analysis, marginal-vs-conditional coverage, and estimated-weight approximation. Stating M3 and X6 yourself removes the reviewer's leverage.
- **Supporting evidence:** All robustness experiments (E17).

---

## 8. Figures

### F1. "Figures don't support the central claim." — *R-C*
- **Why they ask:** Reviewers scan figures first; a mismatch between headline claim and headline figure is fatal to a first impression.
- **Defense:** The naive-vs-weighted coverage figure must be the paper's visual centerpiece, immediately legible, with the nominal line and CI bands explicit. Every contribution has one designated figure.
- **Supporting experiment:** E11 (headline figure), E14 (second headline figure).

### F2. "Where is the evidence the test set is actually biased?" — *R-B*
- **Why they ask:** The entire Contribution 1 narrative rests on this premise; asserting it from the challenge paper's text is weaker than showing it.
- **Defense:** Show the empirical distributions directly — risk histogram and time-to-TCA histogram, train vs. test, side by side. This should be Figure 1.
- **Supporting experiment:** E1 (these figures are specified deliverables).

### F3. "Coverage plots without confidence bands." — *R-B*
- **Why they ask:** A coverage point estimate without uncertainty invites exactly criticism S1.
- **Defense:** Every coverage figure carries CI bands; no bare coverage points anywhere in the paper.
- **Supporting experiments:** E9–E14 (all specify CIs on coverage).

### F4. "Figures are unreadable / not colorblind-safe / unreadable in grayscale print." — *R-C*
- **Why they ask:** Basic production quality; reviewers often print.
- **Defense:** Colorblind-safe palettes, distinguishable line styles/markers independent of color, legible font sizes at print scale, vector (PDF) output.
- **Supporting evidence:** E18 (styling pass with explicit accessibility requirement).

### F5. "Figure captions don't stand alone." — *R-C*
- **Why they ask:** Reviewers read figures out of order.
- **Defense:** Self-contained captions stating what is shown, what the reader should conclude, and what the error bars represent.
- **Supporting evidence:** E18.

---

## 9. Tables

### T1. "No confidence intervals in the results table." — *R-B*
- **Why they ask:** Point estimates alone cannot support comparative claims.
- **Defense:** Every metric cell carries a CI or explicit uncertainty; bolding of "best" values is avoided where differences are within overlapping intervals.
- **Supporting experiments:** All (bootstrap CIs are a specified output throughout).

### T2. "Sample sizes are not reported per group." — *R-B*
- **Why they ask:** Group-level results are uninterpretable without n, especially for rare high-risk events.
- **Defense:** Every group-level table reports n (total and high-risk) alongside the metric; merged/underpowered groups are labeled as such.
- **Supporting experiments:** E4, E13.

### T3. "The comparison table omits obvious competitors." — *R-A, R-C*
- **Why they ask:** Selective comparison suggests cherry-picking.
- **Defense:** Include the full related-work comparison table (N4) covering all identified prior work on this dataset, with honest columns showing what each did and did not do — including recent 2025 work.
- **Supporting evidence:** Literature review; manuscript related-work table.

### T4. "Tables report metrics not defined anywhere." — *R-C*
- **Why they ask:** Composite metrics (challenge loss, F2 variants) are venue-specific and non-obvious.
- **Defense:** A methods subsection defining every reported metric mathematically, with the challenge metric's definition matched to the official source and validated by baseline reproduction.
- **Supporting experiment:** E5.

---

## Pre-Submission Triage: The Five Most Likely Rejection Reasons

Ranked by probability × severity, with the single strongest countermeasure for each:

1. **M5 — "Models barely beat the naive baseline."** → Never frame as a point-prediction paper; lead with calibration and decision value (E15).
2. **S1 — "Coverage estimates are underpowered."** → Pre-computed power analysis in the paper, claims scoped to what it supports (E4).
3. **M3 — "You calibrate to a noisy label."** → Make it the centerpiece, quantified (E14), not a buried caveat.
4. **N1 — "Conformal prediction isn't new."** → Correct venue choice plus the selection-bias/label-noise framing (E11, E14).
5. **M1 — "Your weights assume a complete selection mechanism."** → Dual weight specifications with agreement analysis (E11, E17).

If any of these five lacks a completed supporting experiment at submission time, the paper is not ready.
