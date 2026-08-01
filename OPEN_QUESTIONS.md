# OPEN_QUESTIONS.md
**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Purpose:** Every ambiguity that must be resolved before or during early implementation. No questions are answered here; recommendations are flagged only where existing evidence points somewhere. Blocking = implementation of some module cannot correctly begin until resolved.
**Convention:** IDs are stable; resolutions get logged in DECISIONS.md referencing the ID.

---

## A. Research Methodology & Task Definition

### Q-METH-01 — What exactly is the prediction target?
- **Category:** Research methodology
- **Why it matters:** Everything downstream (models, nonconformity scores, coverage semantics) depends on the target's precise definition. The challenge predicts "risk in the final CDM," but risk is reported in log space with an apparent lower floor (sentinel-like values for ~zero risk), and it is ambiguous whether we regress raw log-risk, clipped log-risk, or model the floor as a censored value.
- **Possible answers:** (a) regress log-risk as-is including floor values; (b) clip/treat floor as censored (Tobit-style or two-part model: P(above floor) × value); (c) classify high/low first, regress only above-floor.
- **Impact:** (a) is simplest and matches prior work but floor mass distorts interval semantics near the threshold; (b) is statistically cleaner but adds modeling machinery reviewers must accept; (c) changes the contribution's shape toward classification.
- **Recommended:** (a) as primary for comparability with all prior work, with the floor's effect on intervals explicitly examined in the audit; revisit at Gate 1 if floor mass dominates.
- **Blocks implementation:** YES (data.py, metrics.py cannot be finalized without it).

### Q-METH-02 — What is the operational prediction cutoff?
- **Category:** Research methodology
- **Why it matters:** "Predict final risk from early CDMs" requires defining *early*. The challenge used a cutoff (CDMs available up to ~2 days before TCA; test events filtered to have a late CDM within 1 day). Our lead-time analysis (2-day vs 1-day) presumes exact cutoff definitions consistent with the challenge, or our baseline validation against published scores will silently fail.
- **Possible answers:** (a) replicate the challenge's exact cutoff rules (extract verbatim from Uriot et al. + Kelvins scoring page); (b) define our own cleaner cutoffs and re-score baselines under both.
- **Impact:** (a) enables direct validation against published numbers (a core credibility mechanism); (b) improves interpretability but breaks comparability unless done *in addition to* (a).
- **Recommended:** (a) mandatory first, (b) as an additional analysis. Extract the rules in Phase 0 documentation before coding features.
- **Blocks implementation:** YES (features.py, all baselines).

### Q-METH-03 — One-sided or two-sided intervals?
- **Category:** Research methodology / Statistics
- **Why it matters:** Operationally, the dangerous error is *underestimating* risk; an upper confidence bound on risk may be the decision-relevant object, and one-sided conformal bounds are simpler and tighter. Two-sided intervals are the field-standard presentation. This choice shapes the headline claim.
- **Possible answers:** (a) two-sided intervals only; (b) one-sided upper bounds only; (c) both, with one-sided as the decision-cost input and two-sided as the descriptive result.
- **Impact:** (a) conventional, easier to compare with CQR literature; (b) sharper operational story but nonstandard presentation; (c) most complete, ~1.3× evaluation surface.
- **Recommended:** (c); the decision-cost module consumes upper bounds, the coverage tables report both.
- **Blocks implementation:** YES for conformal module API design (must support both sidedness modes from the start).

### Q-METH-04 — Are horizons evaluated per-event-final only, or at multiple lead times?
- **Category:** Experimental design
- **Why it matters:** The plan promises lead-time tradeoff curves; that requires defining a discrete horizon set and how an event's "prediction at horizon h" is constructed (last CDM before h). Ambiguity here multiplies experiment count.
- **Possible answers:** (a) final-prediction only; (b) horizons {2d, 1d}; (c) dense horizon grid {5d,4d,3d,2d,1d}.
- **Impact:** (a) undersells the operational story; (b) matches the challenge's structure and decision deadlines with modest cost; (c) richest curves, ~2.5× compute and analysis surface, power thins per horizon.
- **Recommended:** (b) as pre-registered primary, (c) descriptively if compute allows.
- **Blocks implementation:** No (defer to Phase 2 config), but must be fixed before Phase 3 evaluation runs.

---

## B. Statistics & Evaluation Protocol

### Q-STAT-01 — Nominal coverage level(s)?
- **Category:** Statistics
- **Why it matters:** Coverage targets (α) define the headline tables and the power analysis itself; changing them post hoc looks like p-hacking.
- **Possible answers:** (a) 90% only; (b) 95% only; (c) {80%, 90%, 95%}.
- **Impact:** Single level simplifies narrative but invites "why not X%?"; the set costs little and pre-empts the question; 95% at small high-risk counts may be underpowered (power analysis will say).
- **Recommended:** (c), with 90% pre-registered as primary; final set confirmed by Gate 1 power table.
- **Blocks implementation:** No, but must be frozen at Gate 1.

### Q-STAT-02 — What is the pre-registered success margin for "coverage achieved"?
- **Category:** Statistics / Evaluation protocol
- **Why it matters:** PROJECT_KNOWLEDGE S1 leaves the margin "power-analysis-determined." Without a pre-committed number, we can be accused of defining success after seeing results.
- **Possible answers:** (a) fixed ±5 percentage points; (b) margin = half-width of achievable 95% CI from the power analysis; (c) formal test of coverage = nominal (binomial/bootstrap) at α=0.05.
- **Impact:** (a) simple, may be tighter than data permits per-group; (b) honest but self-referential (must be justified in-text); (c) most rigorous, risks "significant deviation" headlines from trivial differences at large n.
- **Recommended:** (b) written into DECISIONS.md at Gate 1 before Phase 3 runs; (c) reported alongside as supporting inference.
- **Blocks implementation:** No; blocks Phase 3 *interpretation*.

### Q-STAT-03 — Coverage uncertainty: bootstrap, exact binomial, or both?
- **Category:** Statistics
- **Why it matters:** Coverage is a proportion over *events* that are arguably non-independent (same objects/missions recur); Clopper–Pearson assumes independence; event-level bootstrap partially respects structure but not cross-event dependence.
- **Possible answers:** (a) event-level bootstrap only; (b) Clopper–Pearson only; (c) both, plus a cluster-bootstrap sensitivity check grouping by mission (or object pair if identifiable).
- **Impact:** (a)/(b) alone invite a competent statistical reviewer's objection; (c) costs one extra analysis and defuses it.
- **Recommended:** (c).
- **Blocks implementation:** No (metrics engine should expose all three cheaply).

### Q-STAT-04 — Multiple-comparison policy across methods × groups × levels?
- **Category:** Statistics
- **Why it matters:** The evaluation grid produces dozens of coverage comparisons; without a declared policy, any "significant" finding is attackable.
- **Possible answers:** (a) no correction, descriptive framing with CIs only; (b) Holm–Bonferroni within pre-registered primary family; (c) hierarchical: one primary contrast (naive vs weighted marginal coverage on official test) formally tested, all else descriptive.
- **Impact:** (a) is defensible only with disciplined language; (b) may be over-conservative for a small-sample applied paper; (c) matches how strong applied papers handle this.
- **Recommended:** (c); primary contrast declared in DECISIONS.md before Phase 3.
- **Blocks implementation:** No.

### Q-STAT-05 — Seed count and bootstrap resample count: frozen where?
- **Category:** Reproducibility / Statistics
- **Why it matters:** "≥3 seeds, ≥2,000 resamples" appears in requirements; leaving them adjustable invites result-shopping.
- **Possible answers:** (a) freeze (3 seeds, 2,000) in default.yaml now; (b) freeze (5, 5,000) if compute audit (Q-COMP-01) permits; (c) decide per experiment.
- **Impact:** (c) is a forking-paths hazard; (a) vs (b) is purely a compute question.
- **Recommended:** (a) now, upgrade to (b) once Q-COMP-01 resolves; any change logged before, never after, a result is inspected.
- **Blocks implementation:** No.

---

## C. Dataset Assumptions

### Q-DATA-01 — Is a usable mission/group identifier actually present in the public release?
- **Category:** Dataset assumptions
- **Why it matters:** Group-conditional calibration (FR6.3) and per-mission coverage claims assume a grouping key. ESA anonymized the release; the grouping column may be absent, coarsened, or unusable — which would amputate one advertised analysis.
- **Possible answers:** (a) usable mission id exists; (b) only coarse proxies exist (orbit-regime features → constructed groups); (c) nothing usable.
- **Impact:** (a) plan unchanged; (b) groups become *derived* (must be defined pre-registration to avoid post hoc grouping accusations); (c) drop group-conditional claims, elevate label-noise contribution (pre-agreed PIVOT shape).
- **Recommended:** none yet — pure empirical question for the Phase 0 audit; pre-write the (b) grouping rule now (e.g., k-means on orbital elements with k fixed in advance).
- **Blocks implementation:** YES for conformal/grouped.py design; NO for everything else.

### Q-DATA-02 — How are risk-floor sentinel values distributed, and do they overlap the high-risk threshold machinery?
- **Category:** Dataset assumptions
- **Why it matters:** If a large mass of events sits at the floor, regression metrics, interval widths, and the F2 threshold interact with an artificial atom; ignoring it can fabricate or destroy apparent coverage.
- **Possible answers:** (a) floor mass negligible (<5%); (b) substantial but confined to low-risk events; (c) substantial and near-threshold.
- **Impact:** (a) proceed; (b) document + condition analyses; (c) forces Q-METH-01 option (b)/(c) reconsideration.
- **Recommended:** none — Phase 0 audit deliverable; the audit notebook must include this histogram explicitly.
- **Blocks implementation:** No (audit answers it), but Gate 1 cannot pass without the answer.

### Q-DATA-03 — Which of the 103 features are legitimately available at prediction time?
- **Category:** Feature engineering
- **Why it matters:** Leakage via features computed only in late CDMs (or summarizing the final state) would inflate everything and invalidate the paper. The challenge's own feature semantics are only partially documented.
- **Possible answers:** (a) all features of any CDM at or before cutoff are fair; (b) whitelist features after per-column semantic review; (c) blacklist obviously leaky columns only.
- **Impact:** (a) risks subtle leakage; (b) is slow (~103-column review) but reviewer-proof; (c) middle cost, residual risk.
- **Recommended:** (b), performed once in Phase 0 and shipped as a documented feature dictionary (also a useful community artifact).
- **Blocks implementation:** YES (features.py).

### Q-DATA-04 — Are events statistically independent (repeated object pairs / chaser reuse)?
- **Category:** Dataset assumptions / Statistics
- **Why it matters:** Bootstrap validity and exchangeability arguments weaken if many events share a chaser object or object pair; anonymization may hide this.
- **Possible answers:** (a) identifiable duplicates exist → cluster analyses by them; (b) not identifiable → acknowledge as limitation, run mission-level cluster bootstrap as sensitivity (ties to Q-STAT-03c).
- **Impact:** Determines the honesty caveat every statistical claim carries.
- **Recommended:** audit for near-duplicate state vectors in Phase 0; default to (b)'s sensitivity analysis regardless.
- **Blocks implementation:** No.

### Q-DATA-05 — Missing-field policy, especially covariance components?
- **Category:** Dataset assumptions / Label noise
- **Why it matters:** M7 (Pc recomputation) needs complete covariance/state fields; models need a missingness policy. Prevalence unknown.
- **Possible answers:** (a) drop incomplete CDMs; (b) drop incomplete events; (c) impute for modeling but never for Pc recomputation; scope M7 to the complete-field subset.
- **Impact:** (a)/(b) shrink data (power); (c) preserves power for modeling while keeping M7 honest, at the cost of an "M7 subset" representativeness question that must be checked.
- **Recommended:** (c) with an explicit representativeness comparison (M7-subset vs full-set label distributions).
- **Blocks implementation:** YES for labelnoise scope; policy must precede pc_foster spike.

---

## D. Selection Bias & Weighted Conformal

### Q-SEL-01 — How is the selection mechanism formalized into weights?
- **Category:** Selection bias / Conformal implementation
- **Why it matters:** This is the paper's headline contribution; its validity claim depends on how faithfully the documented mechanism (high-risk enrichment + latest-CDM-within-1-day filter) becomes a likelihood ratio. The enrichment *ratio* is documented qualitatively, not numerically.
- **Possible answers:** (a) deterministic-rule weights only (recency filter as hard indicator; enrichment estimated from observed class proportions train vs test); (b) estimated propensity weights (classifier: P(test | covariates)) — standard covariate-shift practice; (c) hybrid: hard rule × estimated residual density ratio.
- **Impact:** (a) cleanest theory, exact only if the documented rules are the *complete* mechanism; (b) robust to undocumented components but weights are estimated → guarantees become approximate and must be stated as such (plus overlap/positivity diagnostics required); (c) best fidelity, most machinery to defend.
- **Recommended:** (a) as primary (leveraging the rare luxury of a *documented* mechanism is the paper's elegance), (b) as robustness comparison. Final call at the Phase 3 design review with supervisor (already deferred in SOFTWARE_ARCHITECTURE Appendix B).
- **Blocks implementation:** YES for conformal/weighted.py (API must accommodate both weight sources).

### Q-SEL-02 — Is the official test set the evaluation target, an unbiased self-made split, or both?
- **Category:** Experimental design / Selection bias
- **Why it matters:** Two different scientific claims: "valid coverage on the biased official test set" (deployment-shift story) vs "valid coverage on an exchangeable held-out split" (clean-theory story). Choosing silently confuses reviewers.
- **Possible answers:** (a) official test only; (b) self-made exchangeable split only; (c) both, with roles pre-declared: self-split validates machinery, official test demonstrates the bias problem + correction.
- **Impact:** (a) alone can't show the machinery works when assumptions hold; (b) alone abandons the headline; (c) is a 2× evaluation surface but tells the complete story.
- **Recommended:** (c).
- **Blocks implementation:** YES (data.py split design must produce both from day one).

### Q-SEL-03 — Positivity/overlap failures: what if some test events have ~zero training support?
- **Category:** Selection bias / Statistics
- **Why it matters:** Weighted conformal requires overlap; test events unlike anything in calibration yield exploding weights and vacuous or invalid intervals. The recency filter makes this plausible.
- **Possible answers:** (a) weight clipping at a pre-registered cap; (b) report-and-exclude non-overlapping events as a defined subpopulation; (c) both, with the excluded set characterized in the paper.
- **Impact:** (a) trades bias for stability (must disclose); (b) narrows the claim's population honestly; (c) standard best practice.
- **Recommended:** (c), cap value fixed before Phase 3 result inspection.
- **Blocks implementation:** No, but the diagnostics must be built into weighted.py from the start.

---

## E. Label Noise (M7)

### Q-LBL-01 — Can Pc actually be recomputed from the public fields? (Assumption A4)
- **Category:** Label noise / Dataset
- **Why it matters:** Contribution 2 as designed depends on it; PROJECT_KNOWLEDGE flags it as the largest technical unknown.
- **Possible answers:** (a) yes, matches reported risk within tolerance on most events; (b) partially (subset/approximation); (c) no.
- **Impact:** (a) full M7; (b) scoped M7 with representativeness caveat (ties Q-DATA-05); (c) redesign M7 around published covariance-scaling results applied abstractly (weaker but viable contribution).
- **Recommended:** none — resolved ONLY by the Phase 0 spike (implement Foster Pc on 100 sample events, compare to reported risk). This spike must be added to the Phase 0 Claude Code brief.
- **Blocks implementation:** YES for labelnoise/*; NO for Phases 1–3.

### Q-LBL-02 — Rescaling applied to which covariances, jointly or per object?
- **Category:** Label noise
- **Why it matters:** CDMs carry covariances for both objects; ESA's realism findings may differ per object class. The scaling-grid semantics change the sensitivity curve's meaning.
- **Possible answers:** (a) single scalar on the combined covariance; (b) independent scalars per object (2-D grid); (c) scalar on secondary (debris) object only, primary held fixed.
- **Impact:** (a) simplest, one curve; (b) most informative, quadratic experiment growth; (c) mirrors the operational suspicion (debris covariances least trustworthy) with linear cost.
- **Recommended:** (a) primary + (c) secondary; (b) only if compute is free after Q-COMP-01.
- **Blocks implementation:** No (config-level), fix before Phase 4.

### Q-LBL-03 — Labels rescaled at evaluation only, or also for retraining?
- **Category:** Label noise / Experimental design
- **Why it matters:** "How does label noise affect *coverage of trained systems*" (evaluation-only) vs "…affect *what systems learn*" (retraining) are different, both interesting; the second multiplies training cost by grid size.
- **Possible answers:** (a) evaluation-only; (b) evaluation + retraining at grid extremes {0.8×, 1.5×, 2.0×}; (c) full retraining grid.
- **Impact:** (a) matches the stated contribution and budget; (b) adds a compelling robustness figure for ~3× training cost; (c) likely exceeds compute/time.
- **Recommended:** (a) as the contribution, (b) if Phase 4 is ahead of schedule.
- **Blocks implementation:** No.

---

## F. Baselines & Prior-Art Reproduction

### Q-BASE-01 — Is a challenge-winner reimplementation in scope?
- **Category:** Baselines
- **Why it matters:** Reviewers may ask why the strongest known point predictor isn't compared; but winner methods are described at competition-report fidelity, and reimplementation disputes are a known attack surface (R5).
- **Possible answers:** (a) no — persistence + LightGBM + LSTM suffice (point accuracy is explicitly not the contribution); (b) approximate reimplementation with documented deviations; (c) contact organizers/winners for code.
- **Impact:** (a) cheapest, needs one crisp sentence of justification in the paper; (b) weeks of work, residual dispute risk; (c) free if it works, unreliable timing.
- **Recommended:** (a) with (c) attempted opportunistically via the existing ESA outreach thread.
- **Blocks implementation:** No.

### Q-BASE-02 — MC-dropout reproduction: what counts as faithful?
- **Category:** Baselines / Evaluation protocol
- **Why it matters:** Demonstrating the Bayesian baseline's coverage failure is a headline; if our reproduction is weak, the comparison is unfair and attackable. Original hyperparameters are not fully published.
- **Possible answers:** (a) match published architecture description, tune honestly for *point* performance, then audit coverage; (b) grid-search to maximize its coverage (steelman); (c) both, reporting the steelman.
- **Impact:** (a) standard but "you nerfed the baseline" risk; (c) closes that attack completely for one extra tuning cycle.
- **Recommended:** (c) — audit the steelman.
- **Blocks implementation:** No.

---

## G. Conformal Implementation Details

### Q-CONF-01 — Exchangeability unit: what is "one calibration point"?
- **Category:** Conformal prediction implementation
- **Why it matters:** Options — one score per event (final-horizon prediction) vs one per (event, horizon) — change the guarantee's meaning and the effective calibration size. Mixing them silently is a correctness bug reviewers can find.
- **Possible answers:** (a) per event, separate calibrations per horizon; (b) pooled (event,horizon) scores with horizon as a feature/group.
- **Impact:** (a) clean guarantees per horizon, smaller n each; (b) larger n, but within-event score correlation across horizons breaks exchangeability *within* the pool.
- **Recommended:** (a); it is the defensible construction.
- **Blocks implementation:** YES (conformal module core design).

### Q-CONF-02 — Group merging rule for small missions?
- **Category:** Conformal prediction implementation / Statistics
- **Why it matters:** Deferred in SOFTWARE_ARCHITECTURE (Appendix B): groups below a size floor must merge or their "coverage" is noise; the floor and merge logic must be pre-registered.
- **Possible answers:** (a) floor = 30 high-risk events, merge into "other"; (b) floor from Gate-1 power table (CI half-width ≤ pre-set bound); (c) hierarchical/Mondrian taxonomy by orbit regime.
- **Impact:** (a) simple, arbitrary-looking; (b) principled, self-documenting; (c) elegant, more machinery.
- **Recommended:** (b), with (a) as its likely numeric outcome.
- **Blocks implementation:** No (Gate 1 output).

### Q-CONF-03 — Library boundary and version pinning for commodity conformal parts?
- **Category:** Conformal implementation / Reproducibility
- **Why it matters:** MAPIE/crepes APIs move; a version bump changing quantile conventions (inclusive vs exclusive) could silently shift results.
- **Possible answers:** (a) pin exact versions + add regression tests asserting library outputs on toy cases; (b) vendor the few needed routines in-house.
- **Impact:** (a) standard and cheap; (b) maximal control, more code to defend.
- **Recommended:** (a), with in-house code reserved for the contribution (weighted.py) as already decided.
- **Blocks implementation:** No.

---

## H. Repository, Licensing, Reproducibility

### Q-REPO-01 — Code license?
- **Category:** Licensing
- **Why it matters:** Must precede public repo creation; interacts with dependencies (all permissive) and journal artifact policies.
- **Possible answers:** (a) MIT; (b) Apache-2.0; (c) GPLv3.
- **Impact:** (a) simplest, maximal reuse; (b) adds explicit patent grant (irrelevant here, mildly "corporate"); (c) copyleft limits reuse (harms the toolkit-adoption goal).
- **Recommended:** (a) MIT.
- **Blocks implementation:** No, but blocks first public push.

### Q-REPO-02 — Redistribute processed data, or re-derive only?
- **Category:** Licensing / Reproducibility
- **Why it matters:** CC-BY permits redistribution with attribution; shipping processed parquet speeds reproduction but duplicates ESA data; re-derive-only depends on Zenodo availability (R9).
- **Possible answers:** (a) re-derive only (scripted from Zenodo); (b) redistribute processed artifacts with attribution; (c) re-derive default + archived processed copy in the Zenodo code deposit as fallback.
- **Impact:** (c) covers R9 at near-zero cost and keeps the canonical path honest.
- **Recommended:** (c).
- **Blocks implementation:** No.

### Q-REPO-03 — Minimum supported environment guarantee?
- **Category:** Reproducibility / Compute
- **Why it matters:** "Runs on a stranger's machine" needs a concrete floor: Python version, CPU-only guarantee, RAM ceiling.
- **Possible answers:** (a) Python 3.11+, CPU-only full reproduction guaranteed, ≤16 GB RAM; (b) GPU required for sequence models, CPU path covers tree models + all conformal/label-noise analyses.
- **Impact:** (a) strongest claim — feasible only if seq-model training fits CPU budget (unknown until Q-COMP-01); (b) honest fallback matching R11.
- **Recommended:** decide after compute audit; write the guarantee into README either way.
- **Blocks implementation:** No.

---

## I. Compute

### Q-COMP-01 — What hardware does the team actually have?
- **Category:** Compute
- **Why it matters:** Multiple deferred choices (seed counts, retraining scope Q-LBL-03, horizon grid Q-METH-04, CPU guarantee Q-REPO-03) hang on an unperformed inventory: laptops' RAM/GPU, access to free GPU tiers, CI minute budget.
- **Possible answers:** inventory outcome — (a) ≥1 usable CUDA GPU; (b) CPU-only + free notebook GPU tiers; (c) CPU-only, no reliable GPU access.
- **Impact:** (a) full plan; (b) seq models trained in free tiers with checkpoint export (reproducibility awkwardness must be documented); (c) LightGBM-centric paper (viable per R11).
- **Recommended:** none — perform the audit in week 1; record in DECISIONS.md.
- **Blocks implementation:** No for Phase 0–1; YES for Phase 2 planning.

---

## J. Publication & Paper Writing

### Q-PUB-01 — Authorship list and order?
- **Category:** Publication
- **Why it matters:** Settling authorship *after* results exist is the classic team-conflict failure; also required for the preprint at week 12. Institutional norms (guide placement, teammate contributions) apply.
- **Possible answers:** (a) Sidh first, teammates by contribution, guide last (convention); (b) alphabetical; (c) defer.
- **Impact:** (c) is the only wrong answer.
- **Recommended:** (a) discussed and recorded with the guide at project kickoff, with a contribution-statement (CRediT) draft maintained from day one.
- **Blocks implementation:** No; blocks preprint.

### Q-PUB-02 — Do target journals permit arXiv preprints, and what AI-assistance disclosure do they require?
- **Category:** Publication
- **Why it matters:** The week-12 preprint is a scoop defense; Elsevier venues (ASR, Acta, JSSE) generally permit preprints and require disclosure of AI use in manuscript preparation — but exact current policy text must be verified per journal, and the disclosure wording (AI-assisted implementation + drafting under author supervision) drafted once, honestly, and reused.
- **Possible answers:** (a) verify policies now, draft disclosure now; (b) handle at submission time.
- **Impact:** (b) risks discovering a preprint restriction *after* posting — irreversible.
- **Recommended:** (a); a 1-hour task against each journal's current author guidelines.
- **Blocks implementation:** No; blocks preprint posting.

### Q-PUB-03 — Paper genre emphasis: methods-application, benchmark/evaluation study, or toolkit paper?
- **Category:** Paper writing
- **Why it matters:** Same results, three framings with different venue fits and reviewer expectations; the intro/related-work must commit to one spine.
- **Possible answers:** (a) methods-application (conformal for conjunction risk) — fits ASR/Acta; (b) evaluation/benchmark study (auditing uncertainty on Kelvins) — fits JSSE and strengthens the toolkit claim; (c) toolkit-led — weakest for Q1/Q2 alone.
- **Impact:** Determines writing emphasis and which contribution leads the abstract.
- **Recommended:** (a) spine with (b) delivered inside it; final call at Gate 4 with results in hand.
- **Blocks implementation:** No.

### Q-PUB-04 — Pre-registration of primary endpoints: where and how formal?
- **Category:** Publication / Statistics
- **Why it matters:** Several questions above resolve to "pre-register before Phase 3" (Q-STAT-01/02/04, Q-SEL-03). The mechanism is unspecified: internal DECISIONS.md vs public timestamped registration (OSF).
- **Possible answers:** (a) DECISIONS.md entries with git timestamps; (b) OSF pre-registration (public, formal); (c) both.
- **Impact:** (a) sufficient for most applied venues; (b) unusual in aerospace (differentiator, small overhead) and immunizes against forking-paths critique.
- **Recommended:** (c) — the OSF entry is one page and cites the git SHA.
- **Blocks implementation:** No; blocks Phase 3 start.

---

## K. Risk & Process

### Q-RISK-01 — Scoop monitoring: who, how often, what trigger?
- **Category:** Risks
- **Why it matters:** R3 mitigation names monitoring but assigns no owner/cadence; an unowned mitigation is decoration.
- **Possible answers:** (a) monthly forward-citation check of Uriot et al. + arXiv keyword alert ("conformal" + conjunction/CDM), owner Sidh; (b) per-gate checks only; (c) none.
- **Impact:** (a) ~20 min/month; a hit triggers a pre-agreed response (accelerate preprint, sharpen contributions 2–3).
- **Recommended:** (a), with the response playbook written into DECISIONS.md now.
- **Blocks implementation:** No.

### Q-RISK-02 — Pre-agreed PIVOT paper shapes for each gate failure?
- **Category:** Risks / Research methodology
- **Why it matters:** Gates exist (G1 power, A4 spike, group-id absence), but the *reduced* paper each failure implies is only sketched. Deciding fallback scope under time pressure post-failure is where projects die.
- **Possible answers:** (a) write one-paragraph fallback abstracts now for: {no group power}, {A4 fails}, {both}; (b) improvise if needed.
- **Impact:** (a) costs an hour, converts every gate failure into a routing decision instead of a crisis.
- **Recommended:** (a), appended to PROJECT_KNOWLEDGE §12.
- **Blocks implementation:** No.

---

## Blocking summary (must resolve before the module in parentheses)
- **Now / Phase-0 brief:** Q-METH-01, Q-METH-02 (data, features, metrics); Q-METH-03, Q-CONF-01 (conformal API); Q-SEL-01, Q-SEL-02 (weighted.py, split design); Q-DATA-03 (features); Q-DATA-05 + Q-LBL-01 spike (labelnoise scope); Q-DATA-01 check (grouped.py).
- **Gate 1 outputs:** Q-STAT-01, Q-STAT-02, Q-CONF-02, Q-DATA-02.
- **Before Phase 2:** Q-COMP-01.
- **Before Phase 3 runs:** Q-STAT-04, Q-SEL-03 cap, Q-PUB-04.
- **Before preprint:** Q-PUB-01, Q-PUB-02.
- **Anytime, cheap, do this week:** Q-REPO-01, Q-RISK-01, Q-RISK-02.
