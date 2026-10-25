# DECISIONS.md

**Purpose:** Append-only project decision log. Every gate outcome, every resolution of an OPEN_QUESTIONS.md item, every deviation from plan, and every "surprising result" investigation gets an entry here — this file is the reproducibility appendix and the project's memory (per CLAUDE.md §6, §11).
**Convention:** Newest entries at the bottom. Entries are never deleted; corrections are new entries referencing the one being corrected. Each entry: date, ID (if resolving an OPEN_QUESTIONS.md item), decision, one-paragraph rationale, who decided.

---

## PENDING — Must resolve before Phase 0 begins

Per IMPLEMENTATION_PLAYBOOK.md, these four are cheap to decide now and expensive to retrofit later. Nothing in Phase 0 should start until this section is empty.

*(All four resolved — see RESOLVED section below. This gate is now clear.)*

## DEFERRED — Resolved empirically during Phase 0, or at a later named checkpoint

These don't block the start of Phase 0 but must be resolved before the module/phase noted, per OPEN_QUESTIONS.md's blocking summary.

- **Q-DATA-01** (group identifier availability) — resolved by the Phase 0 audit (E1); blocks conformal/grouped.py.
- **Q-DATA-03** (feature leakage dictionary) — resolved during Phase 0 (E2); blocks features.py.
- **Q-STAT-01, Q-STAT-02, Q-CONF-02, Q-DATA-02** — resolved as outputs of Gate 1 (E4/E5).
- **Q-COMP-01** (hardware inventory) — resolved before Phase 2 planning.
- **Q-PUB-01, Q-PUB-02** — resolved before the Phase 3 arXiv preprint.
- **Q-REPO-02, Q-REPO-03** — resolved before first public repository push.

## RESOLVED

<!--
### YYYY-MM-DD — [Q-ID or topic]
**Decision:** [what was decided]
**Rationale:** [why, one paragraph — do not reference any result this decision could affect]
**Decided by:** Sidh [/ with guide / at Gate N]
**Supersedes:** [none, or reference to prior entry]
-->

### 2026-08-01 — Q-METH-01: Prediction target definition
**Decision:** Regress raw log-risk, including floor/sentinel values, as the primary target. No censoring/two-part model at this stage.
**Rationale:** Matches every prior paper on this dataset, which is required for E5 baseline validation (our metric implementation is only trusted once it reproduces published challenge scores). Revisit only if the Phase 0 audit (E1) shows floor mass is large enough to distort near-threshold interval semantics — that check happens regardless, per E1's specified deliverables.
**Decided by:** Sidh.
**Supersedes:** none.

### 2026-08-01 — Q-METH-02: Prediction cutoff / lead-time rules
**Decision:** Replicate the original challenge's cutoff rules exactly as primary; custom cutoffs may be added later as a secondary, clearly labeled analysis, never as a substitute for the primary replication.
**Rationale:** Direct prerequisite for E5's baseline validation and the standard defense against REVIEWER_CHECKLIST EV1 ("why these thresholds?") — the answer is "these are the challenge's own definitions, and we prove we implemented them correctly by matching published scores."
**Decided by:** Sidh.
**Supersedes:** none.

### 2026-08-01 — Q-METH-03: Interval sidedness
**Decision:** Support both one-sided (upper bound) and two-sided intervals from the start of the conformal module's design. Two-sided is the default descriptive/coverage-table presentation (comparability with the CQR/conformal literature); one-sided upper bounds feed the decision-cost evaluation (E15), since underestimating risk is the operationally dangerous error.
**Rationale:** Dropping either mode weakens a different part of the paper — two-sided for comparability (REVIEWER_CHECKLIST M4), one-sided for the operational decision story (X4). Cost is low since the conformal API was already designed to accommodate both (SOFTWARE_ARCHITECTURE.md Appendix B).
**Decided by:** Sidh.
**Supersedes:** none.

### 2026-08-01 — Q-SEL-02: Evaluation split(s) used
**Decision:** Use both a self-made, randomly sampled exchangeable split (E9) AND the official biased test set (E10, E11), with pre-declared, distinct roles: the self-split validates that the conformal implementation is correct where its assumptions hold; the official test set demonstrates the selection-bias problem and the weighted correction.
**Rationale:** This is the single highest-leverage decision of the four for defensibility. Without E9, any coverage failure observed on the official test set (E10) is indistinguishable from an implementation bug rather than evidence of selection bias — this is REVIEWER_CHECKLIST's X2, flagged as one of the sharpest available attacks on the paper's headline contribution. Both splits were already budgeted as separate experiments in EXPERIMENT_PLAN.md, so this adds no new scope, only the explicit commitment to run and report both.
**Decided by:** Sidh.
**Supersedes:** none.

---

### 2026-09-15 — Phase 3 Design Review: Q-CONF-01 (calibration unit)

**Decision (part i — exchangeability unit):** One nonconformity score per event, with calibration performed separately for each prediction horizon. Scores from the same event at different horizons are NEVER pooled into a single calibration set.

**Decision (part ii — calibration population):** Calibration draws from the full eligible training pool, NOT a high-risk-only subset. This is recorded explicitly so that the n_cal collapse scenario flagged in the Phase 1 (E4) report — where restricting calibration to the high-risk stratum would reduce n_cal from ~2,600 to ~73 and make the calibration variance term non-negligible — is documented as deliberately avoided, not merely unencountered.

**Rationale:** Our multi-horizon structure is not classical multi-horizon forecasting (where each horizon targets a different future value); both horizons target the same quantity — the event's final risk — from different information sets. It is therefore structurally a clustered/hierarchical problem (multiple correlated views of one unit), not a streaming time-series problem. Two independent literatures converge on the same answer for this structure: (a) the hierarchical conformal literature identifies "subsampling once" (one score per unit) as the construction with exact finite-sample validity, holding without requiring intra-unit exchangeability, and explicitly warns that naive pooling of correlated within-unit scores breaks the uniform-rank property and produces systematic under- or over-coverage; (b) in genuine online multi-horizon forecasting, multi-step Conformal PID calibrates separately per horizon as its baseline valid design, with cross-horizon information sharing offered only as an efficiency improvement, never as a validity requirement. The acknowledged cost of subsampling-once — discarded data and higher variance — is accepted, and is precisely why part (ii) preserves the full calibration pool rather than shrinking it further.

**Explicitly NOT adopted, with reasons:** (1) Full Conformal PID online-control machinery — built for streaming non-stationary forecasting; this is a static historical benchmark, so it is the wrong tool. (2) Bonferroni or joint multi-horizon coverage corrections — inapplicable, because this project reports per-horizon coverage separately (E16) and never claims a joint simultaneous guarantee across horizons; correcting for a claim we do not make would be inappropriate. (3) Repeated subsampling / double conformal (quantile-of-quantiles) with mission as the clustering unit — legitimate and literature-grounded, but adopting it as the primary method would further reduce effective calibration size against the same precision constraint that already forced the Gate 1 PIVOT dropping E13. Logged instead as the specific method to use for the Q-STAT-03(c) cluster-robustness sensitivity check in E17.

**Decided by:** Sidh, at the Phase 3 design review.
**Supersedes:** none (first resolution of Q-CONF-01).

---

### 2026-09-15 — Phase 3 Design Review: Q-SEL-01 (weight construction)

**Decision:** Rule-derived deterministic weights are the PRIMARY method, constructed directly from the two selection criteria empirically confirmed in Phase 0 (the latest-CDM-within-1-day recency filter, and the measured high-risk enrichment ratio). Classifier-estimated propensity weights are implemented as a SECONDARY robustness comparison only, following the standard construction ŵ(x) = p̂(x)/(1 − p̂(x)) where p̂ is a probabilistic classifier (logistic regression and/or random forest) trained to discriminate calibration-pool events from official-test events on safe covariates.

**Agreement between the two specifications is quantified by the maximum multiplicative divergence** γ̂ = sup_x max{ ŵ(x)/w(x), w(x)/ŵ(x) }, treating the rule-derived weight as the oracle. γ̂ → 1 indicates the estimated weight is well specified and corroborates the rule-derived construction; large γ̂ indicates classifier misspecification or overfitting. Both the γ̂ value and a side-by-side coverage comparison under each weight specification are reported.

**Manuscript language requirement (binding):** the exact finite-sample coverage claim is entitled to be made ONLY for the rule-derived weights. Results under classifier-estimated weights must be explicitly labeled as carrying a weaker, non-exact guarantee. The two must never be presented as interchangeable or reported under a single blanket validity claim.

**Rationale:** The known-versus-estimated distinction is not a technicality but a difference in guarantee class. With an exactly known likelihood ratio, weighted conformal prediction attains exact finite-sample marginal coverage for any n, with no parametric or asymptotic assumptions. Once the ratio must be estimated, that exactness is lost: coverage degrades in proportion to weight-estimation error (bounded by the L1 error of ŵ against w*), and parts of the literature relax the criterion to asymptotic/PAC validity precisely because finite-sample guarantees are unavailable in that regime. This project's selection mechanism was documented by the dataset's creators and independently confirmed empirically in Phase 0 (2.49× high-risk enrichment; 100% vs. 71.9% on the recency axis), placing it in the strongest available regime. There is direct precedent for treating a known selection mechanism this way: in settings where the analyst knows the test input distribution in closed form, the literature states this "absolves the need for density estimation" and permits computing the weights exactly, without density-ratio estimation error. The oracle-versus-classifier comparison adopted here as the robustness check is itself the validation procedure used in the foundational weighted-conformal paper.

**Decided by:** Sidh, at the Phase 3 design review.
**Supersedes:** none (first resolution of Q-SEL-01).

---

### 2026-09-15 — Phase 3 Design Review: Q-SEL-03 (weight diagnostics, clipping, and positivity)

**Decision (A — mandatory diagnostics).** Every weighted result in E11 (and E12's weighted variant) reports, without exception:
1. Raw calibration size n AND effective sample size n̂ = (Σ wᵢ)² / Σ wᵢ², side by side.
2. Pareto k̂ tail-shape diagnostic, fitted to the upper tail of the weight distribution, interpreted on the standard bands: k̂ < 0.5 stable (finite variance); 0.5 ≤ k̂ < 0.7 usable but flagged; k̂ > 0.7 unreliable, clipping required; k̂ > 1 weight mean does not exist, importance weighting invalid.
3. Weight distribution summary (five-number summary) plus a weight histogram/density figure.
4. Absolute Standardized Mean Difference (ASMD), post-weighting, computed specifically on the two covariates Phase 0 (E1) identified as divergent between splits — risk level and time-to-TCA of the latest CDM — with the conventional < 0.1 threshold indicating adequate post-weighting balance.

Reporting n̂ alongside n is required because the Gate 1 finding that precision is capped by test-set size rather than calibration size was established for UNWEIGHTED calibration; a skewed weight distribution could reduce effective calibration size enough to revive calibration-side precision as a binding constraint. This must be visible in the results, not discovered afterward.

**Decision (B — clipping, conditional).** Clipping is NOT applied prophylactically. It is triggered only when the Pareto k̂ diagnostic indicates instability (k̂ > 0.7). If triggered: clip at a pre-registered bound B, compute the induced clipping bias directly as Δ_B = 1 − mean(min(w, B)) over the calibration sample, and evaluate at an inflated target coverage level incorporating Δ̂_B, reporting the clipped fraction, B, and Δ̂_B alongside the result. If k̂ falls in the ambiguous 0.5–0.7 band, the maximum weight ratio Q_S = max wᵢ / Σ wᵢ is computed as a secondary tiebreaker (a value exceeding roughly 0.01 flags severe concentration).

**Explicitly NOT adopted:** the full CLISF/CWCP apparatus (clipped function class, structural risk minimization over B, Rademacher complexity penalty). That machinery exists to control damage from *learning* an unbounded density ratio via least-squares importance fitting. The primary weights here are not learned — they are a deterministic function of two documented, low-dimensional criteria — so there is no function class to bound and no estimator overfitting to guard against. Only the bias-correction *idea* (Δ_B and coverage inflation) is borrowed, which is arithmetic on already-known weights. Full CLISF remains a documented fallback if the secondary classifier-estimated weights prove unstable, and is noted as such in the limitations rather than built.

**Decision (C — positivity / low-support test events).** Test events are partitioned into a supported region (adequate calibration support) and an unsupported region (effectively zero weight support), using a pre-registered operational threshold fixed before results are inspected. The coverage guarantee is reported as holding on the supported region, and the manuscript must SAY SO explicitly rather than implying a whole-population claim. The unsupported subpopulation is reported with its count and characteristics (mission and risk-band composition), never silently dropped. Rationale: exclusion without disclosure silently redefines the target population — the causal-inference literature is explicit that trimming shifts the estimand to the trimmed subpopulation — so the scope narrowing must be stated in the claim itself. This mirrors the selective/rejection-CP construction of guaranteeing coverage on the supported domain while formally flagging the unsupported one.

**Decided by:** Sidh, at the Phase 3 design review.
**Supersedes:** none (first resolution of Q-SEL-03).

---

### 2026-09-15 — Phase 3 Design Review: Q-STAT-04 (multiple-comparison policy)

**Decision:** Hierarchical policy. Exactly ONE primary confirmatory contrast is formally tested: naive versus selection-bias-weighted marginal coverage on the official test set (the E10 vs. E11 comparison). Every other comparison — across nominal levels, across base learners, across methods (split conformal vs. CQR), across horizons — is reported descriptively with confidence intervals and is NOT subjected to formal hypothesis testing. This policy is fixed before Phase 3 results are inspected and is stated as such in the manuscript's methods section.

**Rationale:** The evaluation grid produces dozens of possible comparisons; without a declared primary, any "significant" finding is attackable as multiplicity-driven. Declaring a single confirmatory contrast, pre-registered, is the standard defense and matches how rigorous applied papers handle this. Should a secondary formal comparison later prove necessary (e.g., interval-width efficiency across methods), applying a Bonferroni correction to paired tests has direct precedent in the recent conformal-prediction evaluation literature — but this is a documented fallback, not part of the current plan.

**Decided by:** Sidh, at the Phase 3 design review.
**Supersedes:** none (first resolution of Q-STAT-04).

---

### 2026-09-15 — Phase 3 Design Review: Q-PUB-04 (pre-registration mechanism)

**Decision:** Two-track. (1) BLOCKING and satisfied now: pre-registration of primary endpoints, success margins, thresholds, and analysis choices via dated, git-timestamped entries in this file (`DECISIONS.md`), which is sufficient to unblock Phase 3 execution. (2) NON-BLOCKING, assigned to Sidh as a parallel task: public OSF pre-registration citing the relevant git commit SHA, to be completed before the Gate 2 arXiv preprint. Phase 3 execution does NOT wait on the OSF registration, and no Claude Code loop invocation may treat its absence as a blocker.

**Rationale:** The git-timestamped internal record is auditable and sufficient for the target venues. A public registration is a genuine differentiator against forking-paths criticism and unusual in this subfield, but it requires an external account and human action, so it must not gate automated execution. Note for the record: a literature check found no source connecting pre-registration practice specifically to conformal prediction — this decision rests on general scientific-practice grounding, not a CP-specific precedent, and the manuscript should not imply otherwise.

**Decided by:** Sidh, at the Phase 3 design review.
**Supersedes:** none (first resolution of Q-PUB-04).

---

### 2026-09-15 — Phase 3 blocking gate cleared

All five items flagged by the CLAUDE.md §13 loop as blocking Phase 3 (Q-CONF-01, Q-SEL-01, Q-SEL-03, Q-STAT-04, Q-PUB-04) are now RESOLVED above. E9–E11 may proceed. The batch boundary at E11 (Gate 2) remains in force: execution stops there for review regardless of outcome.

**Decided by:** Sidh.

---

### 2026-09-16 — GATE 2 DECISION: Contribution 1 (weighted conformal correction)

**Decision: GO**, scoped precisely as follows.

**What is confirmed and publication-ready:** Two-sided marginal coverage validity is restored by rule-derived weighted conformal prediction on the official (selection-biased) test set. This is the project's primary, pre-registered contrast (Q-STAT-04) and it passed cleanly:

- E9 (self-split, exchangeable, two-sided): coverage ≈ nominal for all four base learners (|gap| ≤ 1.1pp) — the conformal machinery is validated as correct where its assumptions hold, before it is asked to handle the harder case.
- E10 (naive, official biased test, two-sided): under-covers by 4.2–6.4pp across all four learners — the selection-bias problem, empirically demonstrated, not merely asserted from the challenge paper's documentation.
- E11 (rule-derived weighted correction, two-sided): restores coverage to within ~0.5pp of nominal for GBM, GRU, and MC-dropout; persistence lands at +2.6pp (conservative but valid).
- Primary formal test (McNemar, persistence, 90%, two-sided, pre-registered per Q-STAT-04): E10 0.858 → E11 0.926, p = 5.6e-45, 148 events flipped uncovered→covered, 0 the reverse.
- Weight diagnostics clean throughout: rule weights k̂ = −2.34 (stable), n̂ = 1530 of n = 2391 (no calibration-precision collapse — the Gate 1 concern did not materialize), zero clipping triggered, zero unsupported (positivity-violating) test events. Classifier (secondary) weights independently confirmed stable (k̂ = 0.17); γ̂ ≈ 1.04e6 reflects genuine substantive disagreement between the two weight specifications, not numerical instability in either, corroborating that the exact finite-sample claim rests on the rule-derived weights alone (per the Q-SEL-01 resolution).

> **[ANNOTATION 2026-10-01 — exact E9 figures]** "|gap| ≤ 1.1pp" above: the exact largest two-sided
> |gap| on the E9 self-split is **1.18 pp** (GBM at 80%, gap −1.1753 pp; `e9_machinery_validation`,
> F03). "≤ 1.1pp" understates it by 0.08 pp. No verdict changes: E9 is an exactness check and the
> 95% CP interval still contains nominal in that cell. (Found while annotating, recorded but not
> annotated in place: the one-sided "gaps ≤0.8pp" in the next paragraph is **0.82 pp** (GBM at 90%)
> per F03.) See the 2026-10-01 record-annotation entry, item 5.

**Manuscript scoping (binding):** the paper's exact-coverage claim for Contribution 1 is stated for TWO-SIDED intervals only. This was always the design of the pre-registered primary contrast; this entry makes it explicit given the one-sided finding below, so the two are never conflated in writing.

**Second, honest finding — not a blocker, a secondary result:** the weighted correction does NOT restore one-sided (upper-bound) coverage for GBM, GRU, or MC-dropout, despite the one-sided conformal code path being independently validated as correct under exchangeability (E9 one-sided: PASS for all three, gaps ≤0.8pp). This is therefore a real, shift-driven phenomenon, not an implementation bug, and is reported in the manuscript as a secondary finding: selection-bias-corrected weighted conformal prediction restores two-sided marginal validity but not one-sided upper-bound validity under this dataset's selection mechanism. Persistence's one-sided numbers are excluded from this finding and carry a separate, distinct caveat (below) — the two must not be reported together as if they share a cause.

> **[ANNOTATION 2026-10-02 — exact E9 one-sided figure]** "gaps ≤0.8pp" above: the exact largest
> one-sided |gap| on the E9 self-split (learned models) is **0.82 pp** (GBM at 90%: coverage
> 0.8918, gap −0.8180 pp; `e9e11_coverage`, `E9_selftest`, upper; F03). "≤0.8pp" understates it by
> 0.02 pp. No verdict changes: the 95% CP interval [0.8787, 0.9040] contains nominal, and all 9
> one-sided cells pass. This closes the item the 2026-10-01 annotation above recorded but did not
> annotate in place.

**Persistence one-sided caveat (distinct issue, diagnosed, not a shift effect):** persistence's one-sided coverage is degenerate under exchangeability itself (E9 one-sided: FAILS at 80%/90%, identical coverage 0.9376 at both). Root cause verified directly: 65.9% of persistence's signed nonconformity scores equal exactly zero (final risk equals the last pre-cutoff risk, typically both at the risk floor), producing a point mass that makes the 80th and 90th score percentiles coincide. This is a property of the persistence predictor's residual distribution, not of the conformal machinery or the selection-bias correction. No fix was applied (out of scope for Phase 3); a randomized/smoothed conformal quantile is the standard remedy if persistence one-sided intervals are needed later. Persistence's one-sided results are excluded from any coverage claim in the manuscript pending that fix, if pursued.

> **[ANNOTATION 2026-10-01 — one-sided finding, per level, under the final criterion]** The
> "second, honest finding" above states that weighting does NOT restore one-sided coverage for GBM,
> GRU and MC-dropout, without a per-level breakdown. Under the final H1 criterion (coverage ≥
> nominal, tested on the CI upper bound; 2026-09-21), applied per level to the committed
> `e15_bound_coverage_table` (all-supported population, n = 2,167, 3 seeds):
> - at **90% and 95%**, 6 of 6 cells are **not restored** — the statement above is correct there;
> - at **80%** the naive arm has **no deficit to restore**, and the rule-weighted arm's CI lies
>   **wholly below nominal**: GBM 0.8210 → 0.7590 (−6.20 pp; weighted 95% CP [0.7404, 0.7768]),
>   GRU 0.8210 → 0.7631 (−5.78 pp; [0.7446, 0.7809]), MC-dropout 0.8091 → 0.7623 (−4.68 pp;
>   [0.7438, 0.7801]). Weighting **creates** a one-sided deficit there. The verdicts are the same
>   under the table's bootstrap intervals.
>
> This is the same pattern as one-sided CQR (E17 close-out, item 2). The unified framing is recorded
> in the 2026-10-01 record-annotation entry, item 1. The Gate 2 decision itself is unaffected: its
> exact-coverage claim was always two-sided.

**Consequence flagged forward to Phase 5 (not resolved here):** E15's decision-cost evaluation was designed to consume the one-sided upper bound specifically, since underestimating risk is the operationally dangerous direction. Given the one-sided finding above, E15 must either (a) use the two-sided interval's upper edge in place of a dedicated one-sided bound, or (b) explicitly incorporate the one-sided under-coverage as a stated caveat on any decision-cost result that relies on it. This decision is deferred to the Phase 4/5 design review, not made now — logged here so it is not rediscovered late.

**Rationale for GO despite the one-sided gap:** the pre-registered primary contrast was always two-sided; it passed decisively, with validated machinery, clean diagnostics, and no leakage or bias-source ambiguity. The one-sided result is a genuine, interesting, non-obvious finding about the boundary of when selection-bias correction works — arguably a bonus result for the paper, provided it is framed as a discovered scope limitation rather than smoothed over. Holding Gate 2 open pending a full resolution of the one-sided asymmetry would block a clean, publishable, already-validated result over a question that belongs to Phase 5's decision-cost design, not to Contribution 1's core validity claim.

**Phase 4 (E14, label-noise sensitivity) may proceed.** E12 (CQR) and E13 (already skipped per Gate 1) may also proceed per the existing execution order.

**Decided by:** Sidh, at Gate 2.
**Supersedes:** none (first Gate 2 decision).

---

### 2026-09-16 — E12 (CQR) manuscript disposition + cross-experiment synthesis of the weighting correction

**Decision (E12 disposition):** CQR is reported in the manuscript as a **secondary result with two
separated claims**:
1. **Efficiency finding** — CQR produces ~4x narrower, adaptive intervals at equal nominal coverage
   versus split conformal (width tracks predicted risk; machinery validated via the exchangeable
   self-test diagnostic, which hits nominal at all levels).
2. **Coverage-validity caveat (honest)** — CQR, both naive and weighted, fails to achieve valid
   coverage on the official test set; weighting does not restore it and shows a small,
   directionally consistent (weighted <= naive at all three nominal levels) but **not
   formally-significance-tested** negative effect. Reported as a caveat, not a fixed method.

**No further engineering** is spent trying to fix weighted-CQR's coverage in Phase 3 or 4. It is
logged as an **open methodological question for the manuscript's discussion/limitations** section.

**Cross-experiment synthesis (scope of Contribution 1's claim).** Rule-derived weighting is now:
- **CONFIRMED to restore validity** for **two-sided split-conformal marginal coverage** (Gate 2, E11);
- **CONFIRMED NOT to restore validity** for two independently-tested variants —
  (i) **one-sided split-conformal upper bounds** (E11 diagnostic: shift-driven, machinery validated),
  and (ii) **CQR of either sidedness** (E12: shift-driven, machinery validated on self-test).

The manuscript's **Contribution 1 claim is scoped precisely to two-sided split-conformal marginal
coverage**. The one-sided and CQR results are reported as honest secondary findings about the
**boundary conditions** of the selection-bias correction — NOT folded into the primary claim.

**Rationale:** each of the three settings shares validated machinery (self-test/exchangeable
coverage ~ nominal), so the differences are real properties of the correction, not artifacts. A
tightly-scoped primary claim plus transparent boundary findings is more defensible against a hostile
reviewer than an over-broad claim.

**Decided by:** Sidh.
**Supersedes:** none (first E12 disposition; refines the Gate 2 scoping to add the CQR boundary case).

> **[ANNOTATION 2026-09-18 — scope correction]** Item (ii) above says weighting fails for "CQR of
> **either sidedness**". The E12 run (`run_e12`) computed **two-sided CQR only**; one-sided CQR was
> never computed or validated at E12. The supported claim is therefore for two-sided CQR. One-sided
> CQR is first built and validated in E15 (E15 pre-registration §5), and whatever it shows is
> recorded there, not back-filled here. No number changes.

> **[ANNOTATION 2026-10-01 — superseded wording]** Claim 2's "a small, directionally consistent …
> negative effect" is **superseded** by the E17 item-2 wording, confirmed by Sidh on 2026-09-21
> ("E17 item 2 confirmed", Part A): weighting lowers CQR coverage in **both** sidedness arms at
> **every** level (two-sided −1.62 / −0.60 / −1.37 pp; one-sided −5.55 / −1.43 / −2.06 pp at
> 80 / 90 / 95%); the one-sided decreases are larger at every level; and only one-sided CQR gains a
> deficit it did not have (at 80%). "Small" does not describe −5.55 pp. Synthesis item (i) above
> ("one-sided split-conformal upper bounds … NOT restore") is likewise refined by the per-level
> annotation on the Gate 2 entry: at 80% weighting creates a one-sided deficit. See the 2026-10-01
> record-annotation entry, items 1 and 3.

### 2026-09-16 — Q-LBL-02: covariance-rescaling grid semantics (label-noise, E14)
**Decision:** The **primary** covariance-rescaling grid uses a **single scalar factor applied to the
combined/total covariance** (option (a)), matching the grid already scoped in EXPERIMENT_PLAN.md E14
(≈0.8x–2.0x). A **debris(secondary)-object-only variant (option (c)) is an explicit stretch goal**,
not required for Gate 3.
**Rationale:** keeps E14 tractable within the remaining project timeline while still delivering the
primary sensitivity-curve result Contribution 2 needs; the per-object 2-D grid (option (b)) is not
pursued.
**Decided by:** Sidh.
**Supersedes:** none. **Note:** Q-LBL-02 was `Blocks implementation: No` and was not in the DEFERRED
list (only Q-LBL-01 was, bundled with Q-DATA-05); this entry resolves it for the record ahead of E14.

### 2026-09-16 — Q-LBL-03: rescaled labels used for evaluation only (label-noise, E14)
**Decision:** **Evaluation-only** (option (a)). Rescaled labels are used **solely to re-evaluate the
already-fit E9–E12 conformal machinery's coverage** under label noise; models are **never retrained**
on rescaled labels in this project.
**Rationale:** this directly answers Contribution 2's actual question — does known label noise
threaten an already-computed validity claim — at far lower cost than retraining, and avoids
conflating it with the broader question of how label noise affects *what models learn*, which is
logged as **explicit future work**, not in scope.
**Decided by:** Sidh.
**Supersedes:** none. **Note:** Q-LBL-03 was `Blocks implementation: No` and was not in the DEFERRED
list; resolved here for the record ahead of E14.

### 2026-09-16 — Assumption A4 / Q-LBL-01: PARTIAL HOLD → scoped M7; Q-DATA-05 resolved with it

**Status of this gap:** Assumption A4 was flagged at the Phase 0 checkpoint and its disposition was
explicitly reserved for Sidh; the E3 spike ran but no hold/partial/fail call was ever recorded. The
DEFERRED list's "resolved by the Phase 0 spike (E3)" was therefore inaccurate — the spike produced
*evidence*, not a *decision*. The §13 loop correctly halted at E14 on this. This entry closes it.

**DECISION (A4):** Assumption A4 (Pc recomputability from public CDM fields) is resolved as
**PARTIAL HOLD**.

**Evidence on record (from the E3 Phase 0 findings, not re-derived here):**
- **65.0%** of the stratified E3 sample fell within the pre-registered ±0.5 log10-risk tolerance
  (**56.8%** excluding floor-to-floor comparisons) — **below** the pre-registered 80% bar, **above**
  the 50% floor that would constitute an outright fail. This is squarely the pre-registration's
  named "partial hold" band.
- The Pc computation engine itself was **independently validated**: toy-geometry tests agree to
  ~1e-3, and the reported `miss_distance` is reproduced at Pearson **r ≈ 1.0**. The partial hold is
  therefore about *input-field fidelity under anonymisation*, not about a broken implementation.
- Required fields are **essentially complete**: 0.0068% of training CDMs are missing any required
  field.
- Agreement is **strongly stratum-dependent**, and critically is **best in the operationally
  relevant high-risk band** (median |Δ| ≈ 0.06 in the (−6, 0] risk stratum) and **worst in the
  deep-safe tail** — the opposite of the pattern that would make this finding disqualifying.

**DECISION (Q-LBL-01):** resolved as **option (b), SCOPED M7**. Contribution 2's label-noise
sensitivity analysis (E14) is conducted on the **complete-covariance-field subset**, with **primary
analytical focus on the operationally relevant risk stratum** where Pc recomputation is empirically
most reliable.

**Rationale:** this is not a retreat from full-dataset generality — it is a scope match to where the
evidence actually supports the claim. The stratum-dependence itself becomes a **reported finding**
(label-noise sensitivity is characterizable specifically in the regime that matters for
collision-avoidance decisions), not merely a limitation. Scoping the claim to where the label
reconstruction is demonstrably faithful is the same discipline applied at Gate 2, where
Contribution 1's exact-coverage claim was scoped to two-sided split-conformal marginal coverage
rather than asserted broadly.

**DECISION (E3 pre-registered tolerance):** **CONFIRMED as-is, unrevised** (±0.5 log10-risk
per-CDM criterion; 80% sample-level bar). It correctly and honestly discriminated a real partial-hold
result. There is **no basis to loosen it now that its output is known** — doing so would be exactly
the forking-paths problem pre-registration exists to prevent (CLAUDE.md §3: never adjust a procedure
after seeing its result, and never justify a change by reference to the result it would change).
The PROPOSED pre-registration entry dated 2026-08-01 is annotated as confirmed by this entry.

**DECISION (Q-DATA-05, missing-field policy):** resolved **concurrently and consistently**: the
**M7-eligible complete-field subset defines the labelnoise scope directly**. No imputation, no
fabrication, no smoothing over missingness (CLAUDE.md §10) — events lacking required covariance
fields are out of E14's scope by construction, and the 0.0068% missingness rate means this excludes
almost nothing.

**BINDING REQUIREMENT ON E14:** E14 **must** include an explicit **representativeness check**
comparing the M7-eligible subset's label/risk distribution against the **full official test set**,
reported as a **named table and figure**, not merely asserted in prose. A scope restriction that is
not quantified is an undisclosed change of estimand (the same reasoning already recorded for the
positivity partition in Q-SEL-03(C)).

**Decided by:** Sidh.
**Supersedes:** none (first resolution of A4/Q-LBL-01/Q-DATA-05). Removes the
`Q-DATA-05 / Q-LBL-01` line from the DEFERRED section.

---

### 2026-09-18 — GATE 3 DECISION: Contribution 2 (label-noise sensitivity) + Venue Tier

**Decision: GO on Contribution 2. Venue tier: Q2, confirmed as the firm target — *Advances in Space Research* primary, *Journal of Space Safety Engineering* secondary (its operational/decision-cost framing fits E15 well). This is a locked decision, not contingent on Phase 5 results, made explicitly to prevent E15 from being shaped toward a "Q1-worthy" narrative rather than executed and reported honestly.**

**What is confirmed and strengthens Contribution 2:**
- Assumption A4's stratum-dependent structure (best agreement in the operationally relevant (−6,0] risk band, worst in the deep-safe tail) replicated closely at 20× the original sample size (E3: n=100; E14: n=2,167), confirming this is a real, stable property of the recomputation approach rather than small-sample noise.
- The scoped-M7 restriction bites only through the risk-focus stratum and (for the anchored arm) label censoring — NOT through field availability, since all 2,167 official-test events proved M7-eligible (0% missingness). The pre-registered representativeness check therefore passes trivially (KS p = 1.0) and does not fire the fallback.
- A genuine implementation flaw (the anchored label arm producing a mathematically impossible median label, log10 Pc > 1) was caught and fixed BEFORE any coverage number was computed, via a dated amendment to the pre-registration — the fix is on record as made without reference to any result it could change.
- The narrow-interval methods (E11/GBM, E12/CQR) show a clean, monotone degradation in coverage as covariance miscalibration increases (Spearman ρ = −1.00 across the grid) — a real, physically sensible dose-response finding.

**Binding manuscript scoping — the flat primary curve (persistence, 0.9667 at all seven grid points):** this MUST be reported with its diagnosed cause, not as evidence of noise-robustness. The induced high-risk label shift at the grid's extremes (≤1.9 log-units at p95) is small relative to persistence's 90% interval width (43.4 log-units). The correct claim is "coverage is insensitive to this label-noise range because the interval is wide enough to absorb it," not "the method is robust to label noise." These are different claims and must not be conflated in writing.

**New finding, logged and flagged forward to Phase 5 (not resolved here) — high-risk-conditional coverage:** at nominal 90%, conditional coverage on TRUE high-risk events is markedly poor for the narrow/informative methods (GBM ≈ 0.47, CQR ≈ 0.20–0.27) despite good marginal coverage, while persistence's wide, uninformative intervals achieve conditional coverage ≈ 0.96. This is not a Contribution 1 failure (conformal guarantees are marginal by construction, and group/conditional claims were already dropped at Gate 1 for power reasons) but it is a real, citable, uncomfortable finding: the only method with good coverage on the events that matter most operationally is the one whose intervals are too wide to usefully inform a decision. Bootstrap confidence intervals must be computed and reported for these three conditional-coverage figures (currently point estimates only) before they are treated as final.

**Consequence for E15 (binding requirement, not optional):** the decision-cost evaluation must report high-risk-conditional performance as a primary analytical lens, not an afterthought, given what E14 surfaced. E15's design should be reviewed against this requirement before execution, not retrofitted after.

**Rationale for locking Q2 now:** the paper's actual strength is methodological honesty across multiple validated boundary conditions (where selection-bias correction works, and precisely where and why it doesn't), which is exactly what a rigorous Q2 aerospace/space-safety venue values. Framing the venue tier as open and contingent on Phase 5 would create pressure — even unconsciously — to shape E15's design or reporting toward a more Q1-flattering outcome. Locking the target now protects the project's demonstrated discipline (pre-registration before results, no tuning after seeing numbers, honest reporting of negatives) through to the end. This does not preclude a Q1 submission being considered once the complete manuscript exists and can be judged as a finished whole — that is an end-of-project decision, not a Phase 5 design constraint.

**Decided by:** Sidh, at Gate 3.
**Supersedes:** none (first Gate 3 decision).

---

### 2026-09-18 — E15 design review (Gate 3 binding requirement): high-risk lens, one-sided bound, cost ratios, no second formal test

**Context:** Gate 3 made it binding that E15 report high-risk-conditional performance as a primary
lens, and that E15's design be reviewed before execution rather than retrofitted. The review found
four open points in the E15 spec: it had no high-risk lens; Gate 2 had deferred the choice of
interval bound; the cost ratios and "matched alert budget" were never defined; and it proposed
McNemar tests that Q-STAT-04 does not authorize. Resolved as follows.

**Decision 1 — reporting lens.** High-risk events (n = 150 on the official test set) are the
**PRIMARY** reporting lens for every E15 metric; whole-population figures are reported as
**secondary** context. **Missed high-risk events is the lead number.**

**Decision 2 — interval bound: option (b).** E15 uses the **one-sided upper bound directly**. Its
known under-coverage is stated **explicitly as a caveat on every E15 result**: per the E11
diagnostic, the one-sided machinery is validated under exchangeability (E9), but the rule-derived
weighting does not restore one-sided validity on the official test set. The two-sided interval's
upper edge is **NOT** substituted. This resolves the consequence the Gate 2 decision flagged forward
to the Phase 4/5 design review.

**Decision 3 — cost ratios and matched alert budget.** Pre-registered now, before any E15 number
exists: cost ratios (missed-high-risk-event cost : unnecessary-maneuver cost) of **{5:1, 10:1,
20:1}**. **"Matched alert budget"** is defined as: the total number of predicted-maneuver alerts is
held equal across compared methods at a given evaluation point, so methods are compared at **equal
operator burden, not equal threshold value**.

**Decision 4 — no second formal test.** E15 stays **descriptive with event-level bootstrap CIs
throughout**. Q-STAT-04's single confirmatory claim (Gate 2's naive-vs-weighted two-sided coverage
contrast) stands alone; E15's decision-cost analysis gets **no hypothesis test of its own**, and the
spec's McNemar line is withdrawn.

**Rationale:**
1. Follows directly from Gate 3's binding requirement and from E14's finding that good marginal
   coverage can coexist with poor coverage on the events that matter most operationally.
2. Keeps E15 on the operationally relevant object, since underestimating risk is the dangerous
   error, and carries that object's known limitation openly as a caveat instead of swapping in a
   bound with a cleaner coverage claim.
3. Fixes the cost regimes before results exist. Comparing at equal operator burden stops a method
   from looking better simply by alerting more often.
4. Preserves the multiplicity discipline the paper's primary claim rests on.

**Decided by:** Sidh, at the E15 design review following Gate 3.
**Supersedes:** resolves the E15 interval-bound choice deferred in the Gate 2 decision entry; amends
EXPERIMENT_PLAN.md E15 (updated to match in the following commit).

---

### 2026-09-19 — Expanded E15 design decisions: Q-METH-04 revised to {2-day, 3-day} on the official test set; fresh 3-day search; two-sided arms retained; grid built on the internal validation split

**Context:** The expanded threshold-analysis pre-registration (2026-09-18) left three points open:
§0 (lead times), §1 (two-sided arms) and §2 (the grid's source split). They are resolved below
**before any full-grid result exists**. The only threshold numbers produced so far come from smoke
runs, which pre-registration §9 declares not to be findings.

**Decision 1 — Q-METH-04, revised: horizons {2-day, 3-day}, both on the OFFICIAL TEST SET.**
Both horizons are evaluated on the official test set. This replaces any design with one horizon on
the official test set and the other on the self-test split.
- *Rationale:* the originally specified {2-day, 1-day} pair is infeasible. The official test set has
  **zero** CDMs between 1 and 2 days before TCA — a data-availability fact discovered during the
  E15 threshold-analysis smoke test, not a code defect. Keeping both horizons on the same
  evaluation population preserves the comparability of the lead-time effect, without confounding
  it with a different underlying event population.
- This is the **first recorded resolution of Q-METH-04**. It supersedes every reference to a
  {2-day, 1-day} pair, and to Q-METH-04 as pending, in this file (annotated in place) and in
  EXPERIMENT_PLAN.md (corrected there).

**Decision 2 — fresh 24-trial search for the 3-day horizon.** The 3-day horizon does **not** reuse
the 2-day horizon's cached hyperparameters. A fresh 24-trial search — E6 GBM, E7 GRU and E8
MC-dropout, with the equal Phase-2 budgets — runs on the 3-day feature cutoff.
- *Rationale:* reusing 2-day hyperparameters for a different cutoff would be an unjustified
  shortcut. Given confirmed schedule availability, the cost of a proper search (up to about 3.5 h
  on the established timing range) is accepted.

**Decision 3 — two-sided arms retained; grid built on the internal validation split; −6 always
included.**
- **Two-sided arms stay** in the threshold-based analysis alongside the one-sided arms, for every
  method where both are already validated.
- **The grid's structure** (its percentile boundaries) is chosen using the training pool's
  **internal validation split only**. The official test set is never used to select the grid, only
  to score against it once built. This preserves the project's standing single-use rule for the
  official test set.
- **The fixed operational threshold −6** is included in the grid regardless of where it falls
  percentile-wise.

**Decided by:** Sidh.
**Supersedes:**
- the expanded pre-registration's §0 (lead times blocked) and its §1 flag on the two-sided arms;
- §2's grid source (calibration split → internal validation split);
- the open status of Q-METH-04.

**Unchanged:** §4's split for selecting cost-minimizing thresholds (self-test) and every other
pre-registered choice.

---

## PRE-REGISTRATION (PROPOSED — awaiting Sidh's confirmation)

<!--
These entries are written BEFORE the experiment they govern is interpreted
(CLAUDE.md §3). They are proposals, not resolutions: Claude Code does not adopt
them unilaterally. Sidh confirms (or revises) each in a RESOLVED entry before the
dependent result is trusted.
-->

### 2026-08-01 — E3 Pc-agreement tolerance (Assumption A4 / Q-LBL-01) — PROPOSED, awaiting Sidh's confirmation
**Status:** PROPOSED. Written before the recompute-vs-reported comparison was run,
as required by CLAUDE.md §3/§10 (pre-registration; no picking a flattering
tolerance after seeing results). Encoded in `config/default.yaml` under
`pc_spike.tolerance` so the spike reads it rather than hardcoding.

**Proposed tolerance for "recomputed risk agrees with reported risk":**
- Per-CDM agreement criterion: `|log10(Pc_recomputed) − risk_reported| ≤ 0.5` log10 units.
- Sample-level success criterion: at least **80%** of the stratified sample of
  ~100 CDMs must satisfy the per-CDM criterion for A4 to be considered to *hold*.
  (A "partial hold" band — 50–80% within tolerance, or agreement concentrated in a
  characterizable subpopulation — is reported descriptively; the hold/partial/fail
  call itself is Sidh's, not Claude Code's.)

**Reasoning (written before seeing the comparison):**
1. *Why 0.5 log10 units.* The prediction target is base-10 log risk and the
   challenge's own high-risk band spans several log-units (threshold at −6, floor
   at −30). Half a log-unit is ~3.2× in linear Pc — tight enough that agreement at
   this level means the public fields reconstruct the risk's *order of magnitude*
   (which is what the label-noise/covariance-scaling analysis in E14 needs), yet
   loose enough to absorb the known, unavoidable spike-level approximations:
   anonymisation of the fields, summing each object's covariance without an
   inter-object frame rotation, and HBR taken as `(t_span+c_span)/2`.
2. *Why 80%.* The recomputation cannot be expected to hold where required fields
   are absent or where the reported risk sits at the −30 sentinel (an atom, not a
   computed value). Requiring a supermajority — rather than near-unanimity —
   pre-commits to a bar that tolerates a minority of these known failure modes
   while still being strong enough that clearing it is evidence A4 is usable.
3. *Why pre-register at all.* A4 is the project's #1 technical unknown (R2). Fixing
   the bar first is the only defence against unconsciously tuning it to whatever
   the data happens to deliver.

**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh at the Phase 0 checkpoint.**
**Supersedes:** none.

> **[ANNOTATION 2026-09-16 — CONFIRMED]** This tolerance was **confirmed as-is, unrevised** by the
> RESOLVED entry *"2026-09-16 — Assumption A4 / Q-LBL-01: PARTIAL HOLD → scoped M7"*. The observed
> outcome (65.0% within tolerance) landed in the pre-registered **partial-hold** band, and Sidh
> resolved A4 as a partial hold with Q-LBL-01 option (b) (scoped M7). The bar was **not** moved
> after seeing the result.

### 2026-08-01 — E5 baseline-agreement tolerance — PROPOSED, awaiting Sidh's confirmation
**Status:** PROPOSED. Written before our baseline scores were computed, per CLAUDE.md §3
(pre-registration). Encoded in `config/default.yaml` under `baseline_validation`.

**Published reference values** (extracted verbatim from Uriot et al., arXiv:2008.03069v2 —
Table 3, Table 4, and §4.4; the same content as the Astrodynamics 2022 version of record):
- LRP (Latest Risk Prediction / persistence) on the full test set: **L = 0.694, MSE_HR = 0.513, F2 = 0.739**
- LRP on the training set (Table 4): **L = 0.804, MSE_HR = 0.330, F2 = 0.411**
- CRP (Constant Risk Prediction, r̂ = −5) on the test set: **L = 2.5** (§4.4, 2 significant figures)

**Proposed agreement criterion:**
- Primary (LRP): `|ours − published| ≤ 0.001` on each of L, MSE_HR, F2 — i.e. agreement at the
  precision the paper reports. This is a deterministic recomputation on the identical data, so
  anything looser than the published rounding would be hiding a real discrepancy.
- Secondary "close but not exact" band: `≤ 0.01`. Landing here is reported as a **partial match
  requiring investigation**, not a pass.
- CRP: `|ours − published| ≤ 0.05` on L, since 2.5 is given to 2 significant figures only.
- The harness is considered validated only if the **primary** criterion is met on LRP test-set L.

**Reasoning (written before seeing our numbers):**
1. E5 is the credibility gate for every later number (IMPLEMENTATION_PLAYBOOK: "if they do not
   match, the metric implementation is wrong and nothing downstream is trustworthy"). A tolerance
   loose enough to absorb a genuine bug would defeat the entire purpose of the experiment.
2. Unlike E3 — where approximation error was expected and physical — E5 has no legitimate source
   of disagreement: same data, same deterministic formula. Exact agreement is the correct
   expectation, so the bar is set at the published precision.
3. Fixing the bar first is the only defence against relaxing it to whatever we happen to produce.

**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh at Gate 1.**
**Supersedes:** none.

### 2026-08-01 — E4 coverage-precision bar and group-merging rule (Q-STAT-01/02, Q-CONF-02) — PROPOSED, awaiting Sidh's confirmation
**Status:** PROPOSED. Written before the power simulation was run, per CLAUDE.md §3. Encoded in
`config/default.yaml` under `power`.

**Proposed pre-registered values:**
- **Nominal coverage level (Q-STAT-01):** **90%** as primary (α = 0.10). Reported alongside 80% and
  95% as secondary levels, per Q-STAT-01's recommended option (c) with 90% primary.
- **"Useful precision" bar (Q-STAT-02):** a coverage estimate is *useful* iff the **95% bootstrap CI
  half-width on empirical coverage is ≤ 5 percentage points**. Secondary, looser bar reported at
  **10 pp** for context.
- **Group-merging threshold (Q-CONF-02):** adopt option (b) — the floor is the smallest high-risk
  event count whose simulated 95% CI half-width meets the 5 pp bar. Groups below the resulting
  floor are flagged for merging into an "other" bucket rather than reported individually.

**Reasoning (written before seeing the simulation):**
1. *Why 5 pp.* The claims this project makes are of the form "nominal 90% intervals achieve
   ~90% coverage". A ±5 pp half-width is the coarsest precision at which 90% is still
   distinguishable from a materially miscalibrated 85% or 95%. Anything wider cannot support the
   claim, and anything much tighter is not attainable at this dataset's high-risk counts.
2. *Why the floor is derived, not fixed at 30.* Q-CONF-02 offers a fixed floor of 30 high-risk
   events (option (a)) or a power-derived floor (option (b)). A derived floor is self-documenting
   and defensible against "why 30?"; the fixed value is recorded in OPEN_QUESTIONS as the *likely
   numeric outcome* of the derivation, which is a prediction to be checked, not an input.
3. *Why pre-register.* The whole point of Gate 1 is to decide scope from precision. Choosing the
   precision bar after seeing which groups happen to clear it would make the gate meaningless.

**Explicitly not pre-registered here:** the GO/PIVOT/NO-GO call itself, and the final merge
threshold. E4 produces the table; Sidh decides.

**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh at Gate 1.**
**Supersedes:** none.

---

## Phase 0 Empirical Findings (E0–E3) — REPORTED, no decision taken

<!--
These are measurements, not decisions. They are recorded here because several
OPEN_QUESTIONS.md items were designated "resolved empirically during Phase 0"
(see the DEFERRED section above), and the reproducibility appendix needs the
finding and its provenance in one place. Every number below is regenerable via
`kc audit` and is written to reports/tables/*.csv by the notebooks.
Claude Code makes NO go/no-go, scope, or tolerance call in this entry.
-->

### 2026-08-01 — Phase 0 audit + Pc spike: measurements
**Reports:** `reports/00_data_audit.html` (E1+E2), `reports/00b_pc_spike.html` (E3).
**Provenance:** config hash recorded in each report's sidecar JSON; seed 42; raw store md5-verified
(`d19dc8875229f2f6893253c38adddc87`) and frozen read-only. Re-running `kc audit` reproduces the E3
comparison byte-for-byte (determinism verified by diff).

**Findings:**
1. **Published statistics (E1 H1): match exactly** — 13,154 train / 2,167 test events, 103 features.
2. **Challenge cutoff rules (Q-METH-02): reproduce on the data.** Test input CDMs all satisfy
   `time_to_tca >= 2` d (min 2.0002); all test events' final CDM lies within 1 d of TCA (max 0.977).
   Note: the release's own README documents the 103 columns but states *neither* rule, so both were
   verified against the data rather than asserted. Both config keys stay `[verify]` until E5.
3. **Selection bias (E1 H2): confirmed and quantified on both axes.** High-risk prevalence
   2.77% train vs 6.92% test (2.49× enrichment; bootstrap 95% CIs in `e1_high_risk_prevalence.csv`);
   71.9% of train events' final CDM falls within 1 d of TCA vs 100% of test. KS/Mann-Whitney p ≈ 0
   on both. Candidate manuscript Figure 1 is `e1b_time_to_tca_latest_cdm_train_vs_test`.
4. **Q-DATA-01 (mission identifier): USABLE** — answer (a). Complete integer `mission_id`, no
   missing values, 19 distinct missions, 18 present in both splits. Whether any single mission has
   enough high-risk *test* events for a group-conditional coverage claim is a power question for
   Gate 1 (E4), not answered here.
5. **Q-DATA-02 (floor mass): answer (b), "substantial but confined to low-risk events."**
   65.4% of event targets sit exactly at the −30 sentinel (63.5% train, 77.2% test). The mass is
   far above the "<5% negligible" case, but sits 24 log units below the −6 high-risk threshold.
   *This is the revisit condition named in the Q-METH-01 entry above — Sidh's call whether "large
   mass, far from threshold" triggers a target-definition revisit. Not decided here.*
6. **Q-DATA-05 (field availability half): fields are essentially complete.** Only 0.0068% of
   training CDMs lack any field the Foster computation requires, so an M7 subset would be nearly
   the whole dataset. The *policy* choice among Q-DATA-05's options (a)/(b)/(c) remains open.
7. **E2 feature dictionary:** 99 safe / 2 unsafe (`event_id`, `risk`) / 2 ambiguous
   (`max_risk_estimate`, `max_risk_scaling`), covering all 103 columns with a per-column rationale.
   Two ambiguous is within "a handful", so the blanket conservative-exclusion fallback was not
   triggered; the conservative option is recorded per-column instead.
8. **E3 / Assumption A4 — measurement against the PROPOSED tolerance (±0.5 log10, 80% bar):**
   - Engine validated first: reproduces its analytic toy geometries to ≤ ~1e-3 relative error, and
     reproduces the reported `miss_distance` from the state vectors (Pearson r ≈ 1.0), so the
     geometry half is independently confirmed.
   - 100/100 sampled CDMs computed without error or missing fields.
   - **65.0%** of the full stratified sample within tolerance (bootstrap 95% CI [0.560, 0.740]);
     **56.8%** excluding floor-to-floor matches (CI [0.457, 0.679]). Both are **below the
     pre-registered 80% bar and above 50%** — i.e. the pre-registration's *partial hold* band.
   - No systematic bias (Wilcoxon p = 0.91); the disagreement is dispersion, not offset.
     Pearson r = 0.92 (full), 0.80 (excl. floor).
   - **Agreement is strongly stratum-dependent — a characterisable subpopulation**, which is
     exactly the condition the pre-registration named for a partial hold. Median |Δ| by stratum:
     floor 0.000 (100% within tol), (−30,−15] 0.659 (40%), (−15,−10] 0.684 (45%),
     (−10,−6] 0.338 (65%), **(−6, 0] 0.060 (75%)**. Accuracy is best in the operationally
     relevant high-risk band and worst in the deep tail, where log-Pc is extremely sensitive to
     covariance detail. MAE is inflated by tail outliers (max |Δ| = 22.5 log units).
   - The spike-level approximations that could explain the tail were declared before the run in
     `pc_foster.py`: covariances summed without inter-object frame rotation, HBR = (t_span+c_span)/2,
     position block only.

**Explicitly NOT decided here (Sidh's, at the Phase 0 checkpoint):** whether A4 holds / partially
holds / fails; whether to confirm or revise the proposed tolerance; the resulting M7 scope; the
Q-DATA-05 policy; and whether finding 5 triggers the Q-METH-01 revisit.
**Reported by:** Claude Code (Phase 0 implementation).

---

## Phase 1 Empirical Findings (E4, E5) — REPORTED, no decision taken

<!--
Measurements, not decisions. Gate 1's GO/PIVOT/NO-GO call and the confirmation of
the pre-registered bars belong to Sidh. Every number is regenerable via
`kc baselines` and `kc power`.
-->

### 2026-08-01 — E5 baseline validation: the metric implementation reproduces the published scores
**Reports:** `reports/01b_baseline_validation.html`. **Provenance:** git SHA + config hash in the
sidecar JSON; seed 42. Re-running reproduces the table byte-for-byte.

**Finding: PASS on the pre-registered primary criterion — all 7 published quantities match.**

| baseline | split | quantity | published | ours | \|diff\| |
|---|---|---|---|---|---|
| LRP | official test | L | 0.694 | 0.693961 | 3.9e-05 |
| LRP | official test | MSE_HR | 0.513 | 0.512889 | 1.1e-04 |
| LRP | official test | F2 | 0.739 | 0.739075 | 7.5e-05 |
| CRP | official test | L | 2.5 | 2.504140 | 4.1e-03 |
| LRP | train (eligibility-filtered) | L | 0.804 | 0.803753 | 2.5e-04 |
| LRP | train (eligibility-filtered) | MSE_HR | 0.330 | 0.330213 | 2.1e-04 |
| LRP | train (eligibility-filtered) | F2 | 0.411 | 0.410839 | 1.6e-04 |

Three independent corroborations that do **not** involve the scoring code: the test split contains
exactly 150 high-risk / 2017 low-risk events (matching the paper's Figure 10(b) caption); the
eligibility-filtered training set retains exactly 66 high-risk events (matching §4.2's statement);
and both counts fall out of the paper's stated rules without anything being fitted to them.

**Anomaly, diagnosed and resolved (not tuned):** the *unfiltered* training split does not reproduce
Table 4 (we get L = 0.096 vs 0.804). Cause: the training split was never subjected to the §4.2
eligibility rules, so for 42.6% of training events `r_{-2}` *is* the target CDM and the baseline is
exact by construction, deflating MSE_HR. Applying the paper's own documented rules recovers the
published row to 4 d.p. This was one stated hypothesis tested once, corroborated by the independent
n_HR = 66 count — not a parameter search.

**Consequence — Q-METH-02 cutoff rules are now CONFIRMED.** The `[verify]` markers carried on
`cutoff.cutoff_days_before_tca` and `cutoff.test_recency_filter_days` through Phase 0 are lifted:
both values are stated verbatim in arXiv:2008.03069v2 §4.2 *and* confirmed by exact reproduction of
two independent published score rows. `cutoff.min_cdms_per_event: 2` was added from §4.2 i.

**Reported by:** Claude Code. **Tolerance confirmation remains Sidh's** (entry still PROPOSED).

### 2026-08-01 — E4 power analysis: the Gate 1 decision table
**Reports:** `reports/01_power_analysis.html`. Deterministic across re-runs (verified by diff).

**Findings against the pre-registered (PROPOSED) 5 pp bar at nominal 90%:**

| scope | n_HR | best CI half-width | meets 5 pp | meets 10 pp |
|---|---|---|---|---|
| Marginal (all high-risk test events) | 150 | **5.13 pp** | **NO (near miss)** | yes |
| Best single mission (mission 1) | 32 | 11.52 pp | no | no |
| All 18 shared missions | ≤32 | ≥11.52 pp | **0 of 18** | **0 of 18** |

- **Marginal is a near miss: 5.13 pp against a 5.00 pp bar.** At nominal 95% it *does* clear the bar
  (3.74 pp); at nominal 80% it does not (6.69 pp). EXPERIMENT_PLAN's E4 *minimum* bar is therefore
  NOT MET as pre-registered, but by 0.13 pp.
- **Precision is limited by the evaluation set, not the calibration set.** The test-set term
  (2.45 pp) dominates the calibration term (0.58–0.82 pp) at every fraction, so moving from 10% to
  30% calibration changes the half-width by <0.01 pp. Spending more data on calibration is not a
  lever here.
- **Derived merging floor (Q-CONF-02 option (b)): 200 high-risk events per group.** The entire test
  set contains only 150, so **no group — and not even the marginal set — reaches the floor at the
  5 pp bar.** EXPERIMENT_PLAN's E4 *stretch* bar (2–3 groups estimable) is NOT MET. For reference,
  Q-CONF-02 option (a) guessed a fixed floor of 30; the power curve puts it far higher.
- Three missions (20, 23, 24) have zero high-risk test events and are unscorable at any bar.

**Methodological finding — a real bug, found and fixed mid-experiment.** The first run reported a
merging floor of 5 high-risk events and identical group counts at the 5 pp and 10 pp bars. Both were
artifacts: a percentile bootstrap of a proportion has *exactly zero width* when every event is
covered, which at nominal 90% happens with probability 0.9^n — 59% at n = 5. The median bootstrap
half-width therefore collapses to 0 for small groups, making tiny missions look infinitely precise.
The **pre-registered bar was not changed**; the estimator was. Precision is now judged on the exact
Clopper–Pearson interval (non-degenerate at k = n), with the bootstrap and its degeneracy rate
reported alongside, per Q-STAT-03's option (c) which already recommended reporting both.
`tests/test_power.py` pins the failure mode so it cannot silently return.

**Carried forward:** if Phase 3's calibration unit (Q-CONF-01) is the high-risk stratum rather than
the full training pool, n_cal collapses from ~2,600 to ~73 and the calibration term stops being
negligible. Quantified in §4 of the report; flagged for the Phase 3 design review.

**Explicitly NOT decided here (Sidh's, at Gate 1):** the GO / PIVOT / NO-GO call; confirmation or
revision of the 5 pp bar and the 90% nominal level (Q-STAT-01/02); the final group-merging threshold
(Q-CONF-02); and whether a 0.13 pp marginal shortfall counts as meeting the minimum bar.
**Reported by:** Claude Code.

---

## Phase 2 Pre-registration (PROPOSED — awaiting Sidh's confirmation)

### 2026-08-01 — Q-COMP-01: compute inventory (factual record, not a judgement)
**Inventory measured on the development machine:** Windows 11, Intel 12-logical-core CPU,
15.7 GB RAM, **no CUDA GPU** (`torch.cuda.is_available() == False`; torch installed as
`2.13.0+cpu`, 8 compute threads).
**Consequence:** Phase 2 runs CPU-only. This is the R11 fallback contemplated in
`PROJECT_KNOWLEDGE.md` §14 ("dataset is small; tree-based models carry the paper if deep models are
cut") and is adequate here — the training pool is ~13k events and the sequence model is small.
Multi-seed budgets stay at the Q-STAT-05 (a) freeze already in config (3 seeds, 2,000 resamples);
no upgrade to (5, 5,000) is proposed, since the binding constraint at Gate 1 was the *evaluation*
set size, not compute.
**Decided by:** factual inventory recorded by Claude Code; **no judgement call is being made** — the
only decision this enables (whether to cut deep models) is not needed, since the sequence model
trains acceptably on CPU.

### 2026-08-01 — CONFLICT FLAGGED: `feature_dictionary.yaml`'s `risk` verdict vs. E6/E7 as specified
**Status:** PROPOSED. Written **before** any model was trained, per CLAUDE.md §3. This is a
documented conflict between two project artifacts, surfaced rather than silently resolved
(CLAUDE.md §6: "If code and a planning document diverge, that is a bug in one of them — flag the
conflict explicitly").

**The conflict.** `feature_dictionary.yaml` classifies the `risk` column **unsafe**, with the
rationale: *"Only strictly pre-cutoff observed risk values may be used, and only as the explicit
persistence baseline input (E5), **not as a generic feature**."* Read literally, no model in E6/E7
may use any historical risk value. But:
- `EXPERIMENT_PLAN.md` E6 specifies "last-k-CDM features" and hypothesises that the model
  *outperforms the persistence baseline*. Persistence **is** the last pre-cutoff risk value, so a
  model forbidden from seeing risk history is being asked to beat a baseline built from exactly the
  information it is denied. The hypothesis is untestable under the literal reading.
- Using strictly pre-cutoff risk is **not leakage**: those CDMs are, by the challenge's own §4.2
  cutoff rule, available to a forecaster at prediction time. E5 already scored persistence on the
  official test set on precisely this basis, and that pass reproduced the published figure exactly.
- Prior art does the same. Uriot et al. §5.1 report that 65% of teams "framed the learning problem
  as a static one, summarizing the information contained in the time series as an aggregation of
  attributes (e.g. using summary statistics, or simply the latest available CDM)".

**Proposed resolution (requires Sidh's confirmation):** treat the dictionary's carve-out as scoped
to *concurrent/final-CDM* risk, and permit **strictly pre-cutoff** risk history as a feature in
E6/E7. Concretely, the feature builder enforces:
1. the final-CDM risk (the target) can never enter — asserted in `tests/test_features.py`;
2. `event_id` never enters (dictionary: unsafe, and it would memorise events);
3. only CDMs satisfying `time_to_tca >= cutoff_days_before_tca` contribute anything;
4. the two **ambiguous** columns (`max_risk_estimate`, `max_risk_scaling`) are **EXCLUDED**, taking
   the dictionary's own stated conservative option. These are not re-litigated.

**Both variants are built and compared on the INTERNAL VALIDATION split only**, so the cost of the
strict reading is quantified without spending a second pass on the official test set. The single
final test-set pass per baseline uses the primary (pre-cutoff-risk-permitted) variant.

**If Sidh rejects this resolution**, the strict variant is already implemented and its validation
numbers are reported alongside; re-running the final pass under the strict feature set is a
one-command change (`features.risk_history: false` in config).
**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh.**
**Supersedes:** none — it interprets, and does not modify, `feature_dictionary.yaml`.

### 2026-08-01 — E6/E7 decision rule: a validation-selected promotion threshold — PROPOSED
**Status:** PROPOSED, awaiting Sidh. Written **before** the promoted variant was scored on the
official test set (the raw variant had been scored and is reported alongside).

**The problem, measured.** The regression target is dominated by the risk floor: **62.9%** of
training events sit at −30 and only **2.6%** are high-risk (≥ −6). An L2-trained regressor
therefore shrinks its predictions toward that mass — the plain LightGBM point model puts only
**1 of 2167** test predictions above −6, so TP ≈ 0, **F2 = 0**, and the challenge loss
`L = MSE_HR / F2` is **undefined (+inf)**. This is not a code defect: it is METRICS.md §1's
documented `F2 = 0` edge case firing on real data, and it is the same pathology the challenge
paper describes — *"the F2 score puts emphasis on ... promoting borderline low-risk events to
high-risk events, thus improving recall (at the cost of penalizing precision)"* (Uriot et al.
§5.3.1). The winning team's first three submitted steps were exactly such promotions
("raise to −5.95", "raise to −5.60", "raise to −5.00", Table 4).

**Proposed rule.** On top of the regressor, apply a promotion threshold `tau`:

    y_hat_final = max(y_hat, threshold + margin)   where y_hat >= tau
    y_hat_final = y_hat                            otherwise

`tau` is selected **on `val_inner` only**, by minimising the validation challenge loss over a
fixed grid; `margin` is a small positive constant so a promoted event lands just above −6. The
official test set is not consulted in the selection.

**Both variants are reported.** The raw L2 model (L = +inf, F2 = 0) and the promoted model appear
side by side in the E6/E7 tables. Reporting only the promoted one would hide the metric pathology;
reporting only the raw one would produce a strawman baseline that no challenge participant would
have submitted. The same rule and the same grid apply to E6, E7 and E8's point predictions, so the
three stay comparable.

**Why pre-register.** `tau` is a threshold, and CLAUDE.md §10 forbids choosing a threshold after
inspecting the results it will be judged against. Fixing the grid and the selection split in
advance, in config (`gbm.promotion_thresholds`), is what makes the later number admissible.
**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh.**

---

## Phase 2 Empirical Findings (E6, E7, E8) — REPORTED, no decision taken

<!--
Measurements only. Every number is regenerable via `kc baselines-phase2` and is
written to reports/tables/*.csv. Claude Code makes no scope or gate call here.
-->

### 2026-08-01 — E6/E7: both learned point predictors are MUCH WORSE than persistence
**Report:** `reports/02_baselines.html`. Deterministic; 3 seeds each; official test set read
exactly once per experiment, after all selection was made on `val_inner`.

| model | L (mean ± sd) | MSE_HR | F2 |
|---|---|---|---|
| E5 persistence (LRP) | **0.694** | **0.513** | **0.739** |
| E5 constant (CRP) | 2.504 | 0.679 | 0.271 |
| E6 GBM | 53.46 ± 17.60 | 1.751 | 0.035 |
| E7 GRU | 6.39 ± 0.82 | 1.748 | 0.276 |

**This triggers EXPERIMENT_PLAN.md E6's documented failure criterion** ("Model performs materially
worse than persistence ... triggers a feature/hyperparameter review first"). The review was
performed *before* reporting and is recorded here:
- 24-trial hyperparameter search per model on `val_inner` (equal budget, see the E8 entry);
- a target-parameterisation sweep (absolute vs residual-on-persistence) — **residual won on
  validation** (val L 1.631 vs 1.804) and was selected;
- a promotion-threshold sweep over tau, selected on validation (**tau = −7.5**, val L 1.631).

After all of that, E6's *validation* L is 1.631 but its *test* L is 53.5. The gap is not a bug in
the harness: E5's persistence baseline scores 0.694 on the identical pipeline and reproduces the
published figure exactly, so the metric and the test-set plumbing are known-good.

**Diagnosis (stated as a hypothesis, not a settled cause).** 63% of training targets sit at the −30
floor but only 2.6% of training events are high-risk, versus **6.9% in the official test set**
(E1's documented 2.49× enrichment). An MSE-trained residual model therefore learns a
predominantly *downward* correction to persistence, which is precisely wrong for the high-risk
events the metric scores. F2 collapses (E6 flags 3–6 of 150 true high-risk events) and MSE_HR
roughly triples. This is the selection bias the project exists to study, showing up in the
baselines rather than in the conformal layer.

**Not acted on.** No further tuning was performed after seeing the test numbers — doing so would be
exactly the post-hoc threshold-fitting CLAUDE.md §10 forbids. Whether E6/E7 should be rebuilt
around a persistence-anchored formulation is Sidh's call.

### 2026-08-01 — E8: the expected coverage deficiency is CONFIRMED
**Steelman is auditable, not asserted:** all three baselines received an identical 24-trial random
search on `val_inner`; only the objective differed, which is the point — E6/E7 were tuned for
validation MSE, E8 for **its own coverage error**, reaching 2.04 pp mean |empirical − nominal| on
validation before being audited on test.

Marginal coverage on the official test set (2,167 events; 3 MC-dropout seeds + a 5-member ensemble):

| nominal | empirical (mean) | gap | mean width (log10) | binomial p |
|---|---|---|---|---|
| 80% | 79.59% | −0.41 pp | 16.12 | 0.727 (n.s.) |
| 90% | 84.49% | **−5.51 pp** | 20.70 | ~1e−16 |
| 95% | 88.03% | **−6.97 pp** | 24.66 | ~1e−37 |

PIT uniformity is rejected decisively for every seed and for the deep ensemble
(KS ≈ 0.16–0.18, p ≈ 1e−48 to 1e−64).

**Verdict: the hypothesis holds.** The deficiency is *level-dependent* — MC-dropout is essentially
calibrated at 80% and degrades as the nominal level rises, i.e. its tails are too thin. It is also
simultaneously **very wide and under-covering** (~21 log-units at nominal 90%, on a target spanning
about 30 log units), which is the strongest form of the project's motivating claim: the intervals
are both operationally useless *and* not trustworthy. Reported honestly as level-dependent rather
than as a blanket failure.

**Explicitly NOT decided here:** whether E6/E7 are rebuilt around a persistence anchor; whether the
`features.risk_history` conflict (flagged above, still PROPOSED) is resolved as proposed; and any
Phase-3 scope consequence of E6/E7 underperforming. **Reported by:** Claude Code.

---

## Observations Log

*(Per CLAUDE.md §2: interesting things noticed outside current scope get logged here, not acted on.)*

### 2026-10-14 — INCIDENT: the D: project folder was found emptied; recovered from GitHub; cause unknown

**Status:** OBSERVATION, recorded by Claude Code per Sidh's 2026-10-14 instruction. **Only verified facts
are stated.** The cause is **unknown** and was not investigated beyond the read-only checks below.

**1. What was found (on 2026-10-14, system clock, before the 23:34 IST clone).**
- `D:\College\Sem 3\EDI 1` contains only `Project\data`, which is **empty**: 3 directory entries in
  total, 0 bytes.
- The repository, every source file, `data/raw` and the off-repo bundle folder
  `D:\College\Sem 3\EDI 1\repo-backups` are all gone.
- **Last-modified times of the remaining folders:**
  - `EDI 1`: 2026-10-10 05:39 IST;
  - `Project`: 2026-10-10 05:39 IST;
  - `data`: 2026-10-10 11:52 IST.

  These record the last change to each folder's contents, not necessarily the time of deletion.
- The Claude Code session scratchpad on C: was also found empty. It had held pre-run CSV snapshots, the
  downloaded NASA license PDFs, and copies of the two removed EXPERIMENT_PLAN revision drafts.
- A read-only search found **no moved copy**. It searched for `DECISIONS.md` and `*.bundle` (to depth 6)
  under D:\ and the user's Desktop, Documents, Downloads and OneDrive folders. The two `DECISIONS.md`
  files it found belong to unrelated projects.
- The Recycle Bin and File History were **not** checked.

**2. What survives on GitHub (`origin`, verified by `git ls-remote` and a fresh clone).**
- **Branches:**
  - `main` `640fda6`;
  - `phase2/e6-e8-baselines` `c94fe4c`;
  - `phase3/e12-cqr` `87a48bf`;
  - `phase4/e14-labelnoise` `f931aac`;
  - **`phase5/e15-decision-cost` `152cbb2`**, the last commit pushed before the loss.
- **Tags:** `gate1-power-analysis` → `1d364bc`, `gate2-weighted-conformal` → `7ccf97f`,
  `gate3-label-noise` → `ff6b972`.

**3. What was lost.**
- **Four commits, made locally and never pushed.** Their hashes and subjects are as recorded in the
  session transcript; their absence from `origin` is verified.
  - `c9132b9` "E18: state what RESTORED means wherever a learned-model cell is called restored";
  - `32ecbb2` "E18: record the manuscript manifest rebuilt on a clean tree at c9132b9";
  - `2379c27` "docs: annotate date provenance; git commit dates are authoritative";
  - `6ae60cf` "docs: align CLAUDE.md §10's license rule with PROJECT_KNOWLEDGE §10".
- **Two uncommitted items:** the Pc validation pre-registration entry and
  `config/experiments/pc_validation.yaml`.
- **Everything gitignored, by design never in git** (`.gitignore`):
  - `/data/raw/` and `/data/processed/`;
  - `/artifacts/`, which held the hyperparameter search caches and progress logs;
  - `/reports/*.html`, `/reports/figures/` and `/reports/tables/`. The tables were **every computed
    result table**, so no experiment's numbers exist on disk any more; only their committed provenance
    sidecars, captions and manifest remain;
  - `/reports/manuscript_figures/` and `/reports/manuscript_tables/`.
- **The local git bundles** in `D:\College\Sem 3\EDI 1\repo-backups`.

**4. What was recovered (2026-10-14).**
- A fresh clone of `origin` at `C:\EDI-1-restored`, with every branch tracked and all tags fetched; its
  `.git` was created at 23:34 IST.
- A verified all-refs bundle in `C:\EDI-1-backups`.
- Branch `recover/2026-10-14` from `152cbb2`, replaying the lost **documentation** only:
  - the Pc pre-registration and YAML are reconstructed (`8d322fd`);
  - this entry;
  - the date-provenance annotation;
  - the CLAUDE.md §10 wording;
  - the pending-implementation record.

  **The RESTORED wording (`c9132b9`/`32ecbb2`) is not re-applied.** It changes generated artifacts
  whose source tables no longer exist; it is recorded as pending instead.
- **Not recovered:**
  - every computed result, which needs a full pipeline re-run after `kc ingest` re-downloads and
    checksum-verifies the raw data;
  - the search caches.

**5. Consequence.** The project's numbers now exist only as values quoted in this log, the committed
captions and manifest, and `REVIEWER_CHECKLIST.md`. They cannot be re-derived until the pipeline is
re-run. Whether and when to run it is Sidh's decision.

**Recorded by:** Claude Code.


### 2026-09-21 — pandas' default CSV float parser is not round-trip exact; it caused two false "not bit-identical" findings

**The observation.** `write_table_atomic` writes every float with the full 17 significant digits
needed to round-trip. `pd.read_csv` with its default `float_precision=None` uses a fast parser
that can read such a value back as a double **one ULP away** from the one written. The loss
happens on **reading**, not writing. Every notebook in this project reads tables with the default
parser.

**Where it bit.**
- **E15 grid (2026-09-20).** The verification reported component (a) as reproducing "within
  1 ULP, not bit-for-bit" and attributed that to multithreaded reductions. Both parts were wrong:
  it reproduced exactly (corrected in place, 2026-09-21).
- **E17 re-render (2026-09-21).** A matrix cell appeared 1 ULP off the computing run. The same
  cause, traced this time. `load_e17` now reads with `float_precision="round_trip"`, and a
  regression test fails without it.

**Impact.** No reported number is affected: results are reported to at most 4 decimal places,
far above 1e-16. What it corrupts is any **bit-level** comparison of values that went through a
CSV, which is exactly the kind of determinism check CLAUDE.md §4 asks for. A check that reads
through the default parser can report non-determinism that is not there. This makes it a
reproducibility-verification hazard, not a results hazard.

**Status: logged, acted on only inside E17.** The project-wide fix is to use
`float_precision="round_trip"` wherever a table is read for an exactness check. It would touch
every notebook's reads, which is outside E17's scope; noted as a candidate for E18's
consolidation pass. Separately: the E15 error was a cause **stated without being tested**, and the
discipline point is to trace a discrepancy before naming its cause.

**Noticed by:** Claude Code, while tracing a 1-ULP matrix discrepancy in E17. **Flagged for:** Sidh.

### 2026-09-20 — SYNTHESIS: the Phase-2 train/test high-risk imbalance surfaces five times over, most recently in the instrument itself
*(updated 2026-09-21 with the fifth manifestation, per Sidh's decision of that date.)*

**The observation.** One property of the dataset — the train/test high-risk imbalance identified in
Phase 2 (high-risk prevalence is far higher in the official test set than in the training pool, by
the challenge organisers' deliberate construction) — has now produced five independently-measured
failures, in five different parts of the project:

1. **Point-prediction collapse (E6/E7, Phase 2).** Both learned models regress toward the low-risk
   mass and are much worse than persistence on the official test metric.
2. **Conditional-coverage collapse (E14, Phase 4).** Coverage conditional on the true high-risk
   stratum falls far below nominal (GBM ≈0.47, CQR ≈0.20–0.27 at nominal 90%) while marginal
   coverage holds; persistence ≈0.96.
3. **Ranking-quality collapse (E15, Phase 5).** At matched alert budgets the ranking score decides
   everything, and the learned models' ranking of high-risk events is poor enough that persistence
   is cheapest at every cost ratio.
4. **Instrument distortion (E15 expanded, 2026-09-19/20).** Because the learned point predictions
   sit below −6, a threshold grid built from them has no resolution where the conformal bounds
   live, and 62.3% of bound threshold selections pinned to the grid ceiling. Here the imbalance did
   not degrade a method — it degraded the *measuring device*, and was only visible because the
   pinning fraction was computed and reported.
5. **The fix is only partly available (E15 expanded, 2026-09-20/21).** Extending the grid with the
   bounds' own percentiles repaired the primary deployable read-out (bound pinning 62.7% → 26.9%)
   but pushed the rule-weighted read-out the other way, to 69.4%: its cost optimum sits at or
   beyond even the extended grid's maximum, where the median pinned arm alerts on 0.26% (2 d) and
   0.03% (3 d) of events and misses essentially every high-risk event. The imbalance does not just
   distort the instrument — it drives one reasonable selection criterion toward "never alert",
   which no amount of grid resolution can make informative.

**Why it is worth stating as one thing.** These read as five separate limitations scattered across
three contributions. They are five consequences of one dataset property, and the last two are the
sharpest version of the point: a selection-biased benchmark biases not only what is learned, but how
it can be evaluated — and, at the limit, whether a sensible decision criterion has any non-degenerate
operating point to choose at all. That unifies the project's three contributions under a single mechanism
instead of leaving each with its own caveat.

**Status: logged, not acted on beyond the grid fix.** Per CLAUDE.md §2 this is an observation, not a
new goal or contribution. It is flagged as a strong candidate for the **manuscript's discussion
section** as a unifying theme. Nothing about the pre-registered protocol changes because of it, and
whether it is used that way is Sidh's decision.

**Noticed by:** Claude Code, while diagnosing the grid ceiling. **Flagged for:** Sidh.

### 2026-09-10 — DEFERRED (do not run): the `risk_history=false` counterfactual ablation
**What it would test.** Whether removing pre-cutoff risk-history access from E6 — while E7 retains
equivalent information implicitly through the raw per-timestep CDM sequence — explains any part of
the observed E6-vs-E7 performance gap (E6 L = 53.46 ± 17.60 vs E7 L = 6.39 ± 0.82).

**Status: deliberately deferred. NOT run now, and NOT blocking Phase 3.** The 2026-09-01 amendment
audit already established that neither model was handicapped in the reported run (both had risk
history; E6 was additionally persistence-anchored via residual mode), so this ablation is not
needed to defend the Phase-2 conclusion. It would only quantify a counterfactual.

**Candidate timing.** As a supplementary ablation during **Phase 5 manuscript writing**, and only if
the paper's narrative ends up needing it (e.g. a reviewer asks whether the architecture comparison
was confounded by feature access).

**Standing instruction from Sidh:** do **not** execute this ablation as part of this or any future
CLAUDE.md §13 loop invocation unless explicitly instructed. A §13 loop must treat this entry as a
closed, non-eligible item — it is logged here precisely so the loop does not rediscover it and
schedule it on its own authority.
**Logged by:** Claude Code at Sidh's instruction.

### 2026-08-31 — Two Phase-2 runs overlapped; results were identical, but the write path is not atomic
Session teardown orphaned a Phase-2 run without killing it, so a relaunch executed concurrently
with it (run A: 16:52-19:04; run B: 19:02-19:40). Both wrote the same `reports/tables/*.csv`.

**No result was affected.** Every Phase-2 number was verified byte-identical between the two runs
(E6 per-seed L 71.09206335711703 / 35.89428553288039 / 53.40577127185363; E7 6.071024147441799 /
5.7761317468555475 / 7.326659950521958; E8 coverage 0.7959 / 0.8449 / 0.8803; all three search
budgets). That is the determinism guarantee working as intended, with the cached searches returning
the same selections.

**But the hazard was real.** `save_table` in the reporting notebooks writes with a plain
`df.to_csv`, not the temp -> fsync -> rename sequence SOFTWARE_ARCHITECTURE.md §6 mandates and that
`data.write_events_parquet` already implements. Two concurrent writers could have produced a torn
or mixed set of tables that still looked plausible. The committed provenance sidecar also briefly
carried run A's `executed_utc` while the artifacts on disk were run B's — corrected in a follow-up
commit.

**Not acted on beyond the provenance fix** (Phase 2 is closed): making `save_table` atomic, and
adding a lockfile or run-id guard so two runs cannot target the same output directory, is a small
reporting-layer change for Sidh to schedule. Logged, not implemented.


### 2026-08-01 — E3 tail behaviour suggests a frame-rotation refinement (not acted on)
The E3 disagreement concentrates in the deep-tail strata while the high-risk band agrees well. The
most likely single cause is the documented spike simplification of summing both objects' RTN
covariances without an inter-object frame rotation, which matters most when the two covariances are
large and differently oriented. If Sidh directs a refinement of the Pc engine, that is the first
thing to try. Logged, not implemented — E3 is a feasibility spike and the full `pc_foster` build is
governed by the Phase-4 scope decision (SOFTWARE_ARCHITECTURE.md Appendix A, step 6).

### 2026-08-01 — Repository is not yet under version control
The working tree is not a git repository, so the provenance stamps in both Phase-0 reports honestly
record `git_commit_sha: "UNAVAILABLE (working tree is not a git repository)"` rather than a
fabricated value. Invariant I4 and CLAUDE.md §5 (protected `main`, `phase{N}/{id}` branches, PR
workflow, gate tags) cannot be satisfied until `git init` plus the first commit happen. Flagged for
Sidh; not done unilaterally, since the initial commit and branch/remote layout are the owner's call.

---

## Phase 2 Amendment — risk_history conflict resolution (2026-09-01)

### 2026-09-01 — PRE-REGISTRATION (written BEFORE any re-run): risk_history audit outcome
**Status:** This entry is written and committed BEFORE Step 3 of the Phase-2 amendment executes any
re-run, per the amendment's Step 2 and CLAUDE.md §3. It records what the audit found and pre-commits
the discipline for anything that follows.

**Nature of the conflict (recap of the 2026-08-01 CONFLICT FLAGGED entry above).**
`feature_dictionary.yaml` marks `risk` unsafe with a carve-out: usable "only as the explicit
persistence baseline input (E5), not as a generic feature." The E6 spec ("last-k-CDM features",
hypothesis that the model beats persistence) needs pre-cutoff risk history to be a fair test. The
2026-08-01 entry proposed permitting strictly-pre-cutoff risk history (`features.risk_history:
true`) and ran Phase 2 under that permissive policy.

**Which model(s) are actually affected by the STRICT interpretation (Step 1 finding — VERIFIED by
reading the code, the committed config, the run provenance, and an empirical rebuild):**
- The reported Phase-2 numbers were produced with `risk_history: true` (permissive). Confirmed by
  `config/default.yaml`, by `reports/02_baselines_provenance.json` (`risk_history_enabled: true`),
  and by rebuilding the feature matrices.
- Under that policy BOTH models already had the pre-cutoff risk signal:
  * E6 tabular carried 6 risk-derived features (`risk_last/mean/min/max/std/delta`); `risk_last`
    is the persistence input r_last.
  * E6 additionally SELECTED residual mode, so its prediction is persistence-anchored:
    pred = model(y − r_last) + r_last.
  * E7 sequence carried raw per-timestep `risk` across up to 10 CDMs.
- Therefore the amendment's premise — "E6 denied the signal, E7 has it implicitly" — does NOT
  describe the reported run. NEITHER model was handicapped; the strict variant (`risk_history:
  false`) was never run. The reported E6 result (L=53.5) is not a feature-handicap artifact: E6 had
  the persistence anchor and still failed.

**Corrected feature policy being adopted (this RESOLVES the 2026-08-01 PROPOSED conflict).**
The permissive policy — strictly-pre-cutoff risk history permitted as a model feature, final-CDM
(target) risk never — is ADOPTED as the standing policy. It is already the policy the reported
numbers reflect, so no result changes. The dictionary's literal carve-out is read as scoped to the
concurrent/final-CDM value; `event_id` and the target remain hard-excluded and asserted.

**The one-re-run discipline (recorded per Step 2, binding on anything that follows):**
"Exactly one clean re-run is permitted per affected model, using the identical search protocol as
the original run (same 24-trial count, same objective, same val_inner split, no expanded search
budget). Whatever the outcome — better, worse, or unchanged — it will be reported as-is. No further
adjustment follows this single re-run."

**Consequence for Step 3.** Because zero models were run under the strict policy, there is no
handicapped result to correct: re-running under the (already-in-force) permissive policy would
reproduce the reported numbers bit-for-bit (determinism verified at the prior checkpoint). No
corrective re-run is therefore performed. Adopting the permissive policy is a no-op on the numbers
and is recorded as such — NOT re-run to manufacture a fresh figure. Measuring the counterfactual
STRICT variant (to quantify whether the hypothesised E6-vs-E7 asymmetry is real) is a distinct,
optional experiment left for Sidh to authorise; it is not "the correction" and is not run here.
**Decided by:** Sidh (amendment) for the policy adoption; Step-1 finding reported by Claude Code.
**Supersedes:** the PROPOSED status of the 2026-08-01 CONFLICT FLAGGED entry (now RESOLVED:
permissive adopted). The underlying analysis in that entry stands.

### 2026-09-01 — Phase 3 scope addition: persistence (E5 LRP) as a fourth conformal base learner
**Decision:** In Phase 3 (E9–E12), wrap the conformal machinery around FOUR candidate base learners
— GBM (E6), GRU (E7), MC-dropout (E8), and **persistence (the E5 LRP predictor)** — rather than
three.
**Rationale (independent of the amendment's Step 3–5 outcome, and logged as such):** E6's point
estimate is poorly determined — its own event-level bootstrap CI on L spans roughly two orders of
magnitude ([24.7, 220.3] on the median seed) and its across-seed L ranges 35.9–71.1. Contribution 1
is a coverage-VALIDITY demonstration, which does not need an accurate point predictor, only a
well-defined one; persistence is the most stable, best-understood predictor on this dataset (it
reproduces the published baseline exactly) and its predictions already exist from E5 at zero
additional cost. Hedging the core coverage demonstration against a single unreliable predictor
family is ordinary good experimental design. This decision would stand regardless of how the
risk_history audit landed; it is not a reaction to E6/E7's numbers.
**Decided by:** Sidh (amendment). **No implementation now** — recorded for Phase 3; E9 is not begun.
**Supersedes:** none (extends EXPERIMENT_PLAN.md E9–E12 candidate-learner set).


---

## Phase 3 Empirical Findings (E9, E10, E11) — REPORTED, no Gate 2 decision taken

<!--
Measurements only. The Gate 2 GO/PIVOT/NO-GO call is Sidh's. Every number is
regenerable via `kc conformal`; report reports/03_conformal.html. 3 seeds
(42/43/44), event-level bootstrap + Clopper-Pearson CIs, 3 nominal levels
{80,90,95}%, two-sided + one-sided-upper, four base learners.
-->

### 2026-09-11 — E9/E10/E11 conformal batch: Contribution 1 machinery, problem, and correction
**Report:** `reports/03_conformal.html`. Seed-42 numbers reproduce the earlier 1-seed smoke exactly
(persistence E11-rule = 0.9262 both times), confirming determinism.

**E9 (machinery validation, exchangeable self-split) — PASSES.** Coverage tracks nominal for every
learner at every level; largest |gap| ~1.1 pp (nominal 90%: persistence 0.898, GBM 0.908, GRU
0.903, MC-dropout 0.900). No implementation bug: the conformal core is correct where its
assumptions hold, so any official-test deviation is attributable to the shift, not to code.

**E10 (naive split conformal, official biased test) — under-covers, as hypothesised.** At nominal
90%: persistence 0.858 (−4.2 pp), GBM 0.836 (−6.4), GRU 0.859 (−4.1), MC-dropout 0.853 (−4.7).
The self-split-vs-official gap is the selection-bias problem, quantified (figure
`e10_problem_selfsplit_vs_official`).

> **[ANNOTATION 2026-10-01 — exact E9 figure]** "largest |gap| ~1.1 pp" in the E9 paragraph above
> is **1.18 pp** exactly (GBM, two-sided, 80%: gap −1.1753 pp; `e9_machinery_validation`, F03), as
> the E9 report itself prints. See the 2026-10-01 record-annotation entry, item 5.

**E11 (weighted conformal, rule-derived primary) — restores coverage.** At nominal 90%: persistence
0.926 (+2.6 pp), GBM 0.896 (−0.4), GRU 0.903 (+0.3), MC-dropout 0.896 (−0.4). Gap closed vs E10:
4.4–6.8 pp. Headline figure `e11_headline_naive_vs_weighted` (naive below the diagonal, weighted on
it). Interval widths widen (the expected cost of weighting; e.g. GBM 18.8→23.6 log-units at 90%).

**Pre-registered primary contrast (Q-STAT-04), persistence, nominal 90%, two-sided, supported
region:** E10 0.858 → E11 0.926; McNemar exact two-sided p = 5.6e-45 (148 events moved
uncovered→covered, 0 the other way). The single formally-tested comparison; everything else
descriptive with CIs.

**Weight diagnostics (Q-SEL-03) — clean for the primary construction.** Rule-derived weights:
Pareto k̂ = −2.34 ("stable"), n = 2391, n̂ = 1530 (so weighting did NOT revive the calibration-side
precision constraint Gate 1 flagged — n̂ stayed well above the danger zone), 1673/2391 positive
(718 zeroed by the hard recency filter, consistent with E1's 71.9% train recency). No clipping
triggered (k̂ < 0.7). Positivity: all 2167 official-test events supported, 0 unsupported.

**Anomalies flagged honestly:**
1. **γ̂ = 1.04e6** — the rule-vs-classifier weight divergence is enormous. This is the Q-SEL-01
   diagnostic working: the classifier assigns near-zero weight to some calibration events the rule
   keeps (and vice versa), so the two constructions disagree violently in the tail. It corroborates
   resting the EXACT finite-sample claim on the rule-derived weights only (as pre-registered); the
   classifier weights (k̂ = 0.17, discriminator AUC 0.72) are a robustness check, not
   interchangeable. Worth Sidh's eye at Gate 2.
2. **Persistence E11 over-covers** (+2.6 pp at 90%, +3.2 pp at 95% → 0.982). Valid but conservative;
   persistence intervals are much wider (43.4 vs GBM 23.6 log-units at 90%) because persistence
   residuals are large. Over-coverage is not a validity failure, but the width cost is real and the
   "operationally useful, not vacuous" success criterion should be weighed per learner.
3. The result is strong but NOT suspicious-good in the leakage sense: E9 independently validates the
   machinery, weights use only observable pre-cutoff covariates (never test labels), and restored
   coverage is the pre-registered hypothesis. Checked per CLAUDE.md §3/§10.

**Implementation deviation (recorded):** Pareto k̂ is the GPD shape parameter via scipy's MLE fit,
not the Zhang-Stephens PSIS estimator the Q-SEL-03 resolution names; same shape parameter, same
0.5/0.7/1.0 bands, vetted estimator chosen over a hand-rolled one for a correctness-critical
quantity.

**Explicitly NOT decided here (Sidh's, at Gate 2):** the GO/PIVOT/NO-GO call; whether Contribution 1
is "validated"; confirmation that persistence is the right base learner for THE primary contrast;
whether persistence's over-coverage / width tradeoff is acceptable; and anything in E12/E13 or later
— execution stops at this batch boundary (CLAUDE.md §13.4).
**Reported by:** Claude Code.


---

## Phase 3 Empirical Findings (E12 — CQR) — REPORTED, no decision taken

<!--
Measurement only; regenerable via `kc conformal --only cqr`. Report:
reports/03b_cqr.html. 3 seeds (42/43/44), nominal {80,90,95}%, two-sided,
event-level bootstrap + Clopper-Pearson CIs. E13 SKIPPED (Gate 1 PIVOT), so the
E12-E13 batch reduced to E12 alone; execution stops before E14 (Gate 3).
-->

### 2026-09-16 — E12 CQR: large efficiency gain, but a genuine coverage negative (failure criterion met)
**Report:** `reports/03b_cqr.html`. CQR runs on the GBM quantile heads (the E6 quantile capability;
point-only learners are out of E12 scope). Q-CONF-03 resolved (b) for CQR: score in-house (reuses
the tested conformal quantile), not MAPIE/crepes, since the weighted arm must combine it with the
in-house likelihood-ratio weights.

**Efficiency — the clear win.** CQR intervals are ~0.24x the width of weighted split conformal at
equal nominal (~4x narrower): median width at 90% is 5.5 (CQR) vs 23.6 (split); ratios 0.26/0.23/0.24
at 80/90/95%. CQR is adaptive — width tracks the predicted risk level (corr ~0.96), whereas split
conformal is constant-width.

**Coverage — a genuine negative, reported exactly as observed (CLAUDE.md §3, §9; not tuned).**
- CQR machinery VALIDATED on the exchangeable self-split (the E9 analog): 0.797/0.896/0.949 at
  80/90/95%, CP CI contains nominal at every level. So the GBM quantile heads are sound and the CQR
  code path is correct.
- On the official (biased) test set CQR UNDER-COVERS: naive 0.774/0.865/0.922, weighted
  0.757/0.859/0.908 at 80/90/95%. The Clopper-Pearson CI EXCLUDES nominal at every level, naive and
  weighted. This meets E12's documented failure criterion ("CQR fails to achieve valid coverage even
  after weighting").
- Weighting does NOT restore CQR coverage (weighted <= naive at every level), whereas the SAME rule
  weights DID restore split conformal on the identical events (E11 ref: 0.896 at 90%, valid). The
  selection-bias correction is effective for the absolute-residual (split) score but not for the CQR
  score on this dataset.

**Diagnostic reading (for Sidh, not a decision made here).** E12's failure criterion attributes
invalid coverage to "quantile-head miscalibration in E6." The self-test arm REFUTES that cause: the
heads and machinery hit nominal under exchangeability. The official-test under-coverage is therefore
shift-driven, and the effective issue is the weight-vs-CQR-score interaction — the likelihood-ratio
weighting that corrects the split score does not correct the CQR score here. So the "revisit" the
failure criterion calls for should target that interaction (or the CQR-score/weight construction),
not the E6 quantile heads.

**Explicitly NOT decided here:** whether CQR enters the manuscript as an efficiency result with a
stated coverage caveat, or is held pending a weighting fix; and anything in E14/Phase 4. Per §9 the
failure was reported exactly, not retried for a better number; per §13 execution stops at the
E12-E13 batch boundary (E13 SKIPPED). **Reported by:** Claude Code.


---

## Phase 4 Pre-registration (PROPOSED — written BEFORE E14 executes)

### 2026-09-16 — PRE-REGISTRATION: E14 label-noise sensitivity protocol

**Status:** PROPOSED. Written and committed **before** any E14 code reads the official test set,
per CLAUDE.md §3 (no procedure may be adjusted after seeing its result) and §9. It instantiates
every choice E14 needs that `EXPERIMENT_PLAN.md` leaves open, so none of them can later be accused
of being selected to flatter the curve. Claude Code proposes; Sidh confirms or revises at Gate 3.

**Binding scope (from the 2026-09-16 A4 / Q-LBL-01 resolution): SCOPED M7.** Complete-field subset;
primary interpretive focus on the operationally relevant risk stratum; representativeness check
mandatory.

**1. Label source and M7 eligibility.** The label of an official-test event is the reported risk of
its **target-defining CDM** (the `true_risk` row in `test_data_private.csv`, per the Q-METH-01
target definition already implemented in `data.py`). E14 regenerates exactly that quantity. An
event is **M7-eligible** iff that target CDM carries all 20 fields in
`labelnoise.pc_foster.REQUIRED_FIELDS` as finite values. No imputation (CLAUDE.md §10); ineligible
events are excluded by construction and counted.

**2. Covariance-scaling semantics (makes Q-LBL-02(a) unambiguous).** The scalar `s` multiplies the
**combined position covariance** `C = C_target + C_chaser → s·C`, i.e. the *variance* scale;
each sigma therefore scales by `sqrt(s)`. Stated explicitly so "2.0x" cannot be read two ways.
Because the B-plane projection is linear, scaling the 3x3 before projection and scaling the 2x2
after are identical — no ambiguity there either.

**3. Grid.** `s in {0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0}` — evenly spaced across the ≈0.8x–2.0x range
EXPERIMENT_PLAN E14 names, including the `s = 1.0` anchor. Declared in `config/default.yaml` under
`labelnoise.scaling_grid`; not a literal in code.

**4. Two label definitions, both reported; neither presented as "the truth".**
- **(P) Direct** (the spec's own wording — "labels regenerated ... via E3's validated Pc
  computation"): `y_s = max(log10 Pc_s, -30)`.
- **(A) Anchored / differential**: `y_s^anch = max(y_reported + [log10 Pc_s − log10 Pc_1.0], -30)`,
  using unfloored log-Pc for the delta.
Arm (A) is declared **now, in advance, and specifically because A4 is only a PARTIAL HOLD**: the
level of curve (P) at `s = 1.0` confounds the rescaling effect with E3's recomputation discrepancy,
whereas (A) isolates the perturbation that covariance rescaling alone induces. Declaring both
before seeing either forecloses picking whichever curve looks better afterwards.

**5. What is held fixed (Q-LBL-03, evaluation-only).** Models are never retrained, and conformal
**calibration stays on the original reported labels**. Only official-test labels are regenerated.
**Stated limitation:** a genuinely global covariance miscalibration would perturb calibration
scores too; holding calibration fixed answers the deployment-relevant question ("an already-
calibrated system meets differently-calibrated truth"), not the global one. The both-sides variant
is logged as future work, deliberately out of scope, not overlooked.

**6. Methods re-evaluated** (two-sided throughout, matching Gate 2's scoping of the coverage claim):
`E10_naive_official` (split conformal, unweighted), **`E11_weighted_rule` (PRIMARY)**, and
`E12_cqr_weighted_rule` (secondary). Base learners: **persistence** — the learner carrying the
pre-registered Q-STAT-04 primary contrast — and **GBM** (also the only learner with quantile heads,
so the only one CQR can use). **GRU and MC-dropout are excluded for runtime**, declared here in
advance rather than chosen once results exist. Nominal levels {0.80, 0.90, 0.95}, primary 0.90;
seeds 42/43/44.

**7. Analysis populations, fixed in advance.** (i) **All M7-eligible supported** official-test
events. (ii) **PRIMARY interpretive focus** — the **high-risk stratum**, defined by the **ORIGINAL
reported label > −6**, so the event set is *identical at every grid point* and the curve compares
like with like. Defining the stratum by the rescaled label instead would let the population drift
with `s` and is rejected here, before results.

**8. Representativeness check (binding, per the A4 resolution).** M7-eligible subset vs. the FULL
official test set: n, high-risk prevalence, floor mass, quantiles of `target_log_risk`, and a
two-sample KS test. Named outputs: table `e14_m7_representativeness`, figure
`e14_m7_representativeness`.

**9. Trend analysis — DESCRIPTIVE, not confirmatory.** OLS slope of coverage on `s` with CI, plus
Spearman rho for monotonicity. **Conflict flagged rather than silently resolved:** EXPERIMENT_PLAN
E14 lists a "trend test", while the Q-STAT-04 resolution spends the project's *single* formal
confirmatory contrast on E10-vs-E11 and requires every other comparison to be descriptive. E14
therefore **computes exactly the quantities the spec names and reports them with CIs, labelled
exploratory** — no p-value from E14 is presented as a confirmatory test. Sidh may revise this at
Gate 3.

**10. Confidence intervals.** Event-level bootstrap (`bootstrap.n_resamples`) plus Clopper-Pearson
at **every** grid point, method, level and population — the same machinery E9–E12 used.

**11. The spec's failure criterion, instantiated BEFORE seeing results.** E14 fails if the M7
subset is "too small or unrepresentative to support any claim". Concretely, declared now:
- **Too small** if `n_eligible < 0.80 × n_official_test`, **or** fewer than **100** M7-eligible
  high-risk events remain (below ~100 the Clopper-Pearson half-width at 90% coverage exceeds the
  Gate-1 `useful_half_width_pp = 5.0` bar, so the focus stratum could not support a claim).
- **Unrepresentative** if the KS test rejects at α = 0.05 **AND** high-risk prevalence differs from
  the full test set by more than **1.5 pp** absolute. Both are required deliberately: KS alone
  rejects on trivially small differences at n ≈ 2,000, which would be a meaningless failure.
If either fires, Claude Code **reports the failure and surfaces** Q-LBL-01's pre-agreed fallback
(option (c), the reduced/abstract version) — it does **not** switch to the fallback on its own
authority (CLAUDE.md §9, §10).

**12. Determinism.** The Pc integrator is deterministic (fixed polar grid, resolution declared in
`labelnoise.integration`); the only randomness is the seeded bootstrap. Same config + seeds ⇒ same
numbers.

**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh at Gate 3.**
**Supersedes:** none.

### 2026-09-16 — AMENDMENT to the E14 pre-registration: the anchored arm is undefined at the censoring sentinel

**Status:** PROPOSED amendment, written **after the label regeneration ran but BEFORE any coverage
number was computed**. It is justified entirely by a physical-validity violation visible in the
labels themselves, with **no reference to any coverage result** — the test CLAUDE.md §3 sets for a
mid-experiment procedure change. Nothing here was chosen to move a curve, because no curve existed.

**What went wrong.** Arm (A) as originally specified was
`y_s = max(y_reported + [log10 Pc_s − log10 Pc_1], −30)`. Applied to the real target CDMs, its
median label reached **+348 at s = 2.0** — i.e. `log10 Pc > 0`, a probability above 1. The cause is a
category error, not a bug: for the ~78% of official-test events whose **reported label sits at the
−30 sentinel**, that label is *censored* ("at most 1e-30") and carries no magnitude, while the
recomputation for the same event can sit thousands of log-units lower. Differencing an uncensored
recomputation and adding it to a censored label is not an operation on comparable quantities.

**Amendment (two parts).**
1. **Arm (A) is DEFINED ONLY WHERE `y_reported > −30`** (uncensored reported label), in addition to
   the finite-anchor condition already declared. Censored events are flagged undefined and dropped
   from the anchored population **uniformly across all scales**, never patched (CLAUDE.md §10).
   Note this leaves the **PRIMARY focus stratum fully intact**: every high-risk event
   (reported label > −6) is uncensored by construction, so the primary curve loses nothing.
2. **Arm (A) is clipped from above at 0** (`Pc ≤ 1`), for the same reason — a label above 0 is not a
   large value, it is an impossible one.
Arm (P), the direct arm, is **unchanged**: it floors at −30 exactly as the reported-label convention
does, and never exceeds 0 because the integrator returns `log10 Pc ≤ 0`.

**Related implementation fix, same reasoning.** `pc_on_disk` underflows to exactly `0.0` for deep-tail
conjunctions (Pc below ~1e-308), which silently destroys the magnitude arm (A) must difference. A
log-space integral `log10_pc_on_disk` (log-sum-exp stabilisation, identical quadrature) was added and
is used **only** for the new unfloored quantity; `pc_on_disk` and E3's `log10_pc` expression are left
byte-identical, so **no E3 number changes**. Validated against the first-order point-mass form in the
underflow regime (`tests/test_labelnoise_rescale.py`).

**Decided by:** PROPOSED by Claude Code; **to be confirmed or revised by Sidh at Gate 3.**
**Supersedes:** amends §4 of the 2026-09-16 E14 pre-registration entry above; that entry stands
otherwise unchanged.


---

## Phase 4 Empirical Findings (E14) — REPORTED, no Gate 3 decision taken

<!--
Measurements only. The Gate 3 venue-tier call is Sidh's. Every number is
regenerable via `kc labelnoise`; report reports/04_labelnoise.html. 3 seeds
(42/43/44), nominal {80,90,95}%, two-sided, event-level bootstrap +
Clopper-Pearson CIs, scaling grid {0.8 … 2.0}, two label arms, two populations.
-->

### 2026-09-16 — E14 label-noise sensitivity: Contribution 1's claim is robust, but for a reason that is itself a limitation

**Report:** `reports/04_labelnoise.html`. Protocol exactly as pre-registered above (plus the one
dated amendment); nothing was tuned after a coverage number was seen.

**Determinism / integrity checks, done first.** (i) Adding the `labelnoise` config block changed the
config hash and invalidated the E6 GBM search cache, so the 24-trial search re-ran: it reproduced the
cached `best_params` **and** `best_objective_value` **bit-for-bit** (23.801101479171347). (ii) E14's
direct arm at `s = 1.0` reproduces the E9–E11 record to within recomputation error — E11 weighted at
90%: **persistence 0.9239 vs 0.926 recorded, GBM 0.8920 vs 0.896 recorded** — confirming E14 is
re-evaluating the same machinery. (iii) The private file's labels were checked against the events
table before any label was regenerated (max |Δ| ≤ 1e-9).

**1. The scoped-M7 restriction turns out not to bite on field availability.** **2,167 / 2,167**
official-test events are M7-eligible — the target-defining CDMs have **0% missingness**. The
subset therefore *is* the full test set, and the representativeness check is exact by construction
(KS statistic 0.0, p = 1.0; high-risk prevalence gap 0.000 pp). **The pre-registered failure
criterion is NOT met.** Scoped M7 bites only through the high-risk **focus stratum** (n = 150) and,
for the anchored arm, through label censoring: only **494** events carry an uncensored reported
label, the other 1,673 sitting at the −30 sentinel. The focus stratum is unaffected by that — every
high-risk event is uncensored by construction.

**2. A4's stratum pattern is confirmed on 2,167 events, not 100.** Agreement at `s = 1.0`,
recomputed vs reported, within the pre-registered ±0.5 tolerance: **89.8% overall — but that is
carried by floor-to-floor matches** (99.1% of the 1,673 floored events). By non-floor band:
(−30,−15] **25.0%**, (−15,−10] **58.0%**, (−10,−6] **63.3%**, **(−6,0] 79.3%**. This independently
reproduces the E3 100-CDM finding (75% in the high-risk band) at 20× the sample size and
corroborates the reasoning behind the PARTIAL HOLD decision: recomputation is most faithful exactly
where operations care, worst in the deep-safe tail.

**3. PRIMARY CURVE — flat, and the flatness is explained, not hand-waved.** E11 weighted conformal
on persistence, nominal 90%, high-risk focus stratum (n = 150): coverage is **0.9667 at every one of
the seven grid points, in both label arms** — slope exactly 0.00, range 0.00 pp. Per CLAUDE.md §3 a
result this clean was treated as suspect and diagnosed rather than reported: the label shift that
0.8×–2.0× rescaling actually induces in the high-risk stratum is **tiny** (median |Δ| ≤ 0.12
log-units; 95th percentile ≤ 1.9), while persistence's 90% interval is **43.4 log-units wide**. The
perturbation is one to two orders of magnitude smaller than the interval, so no coverage flip is
arithmetically possible. **The insensitivity is real and correctly computed, but it is partly a
property of very wide intervals rather than evidence of an intrinsically noise-proof method.**
Reporting it without that caveat would be misleading.

**4. Where intervals are narrower, degradation IS measurable and monotone — the hypothesised
pattern.** Whole M7 set (direct arm, n = 2,167, nominal 90%), coverage at s = 0.8 → 2.0:
- `E11_weighted_rule` / GBM: **0.8965 → 0.8597**, slope **−0.031** per unit s (95% CI
  [−0.034, −0.028]), Spearman ρ = **−1.00** (perfectly monotone).
- `E12_cqr_weighted_rule` / GBM: **0.8696 → 0.8043**, slope **−0.056** (CI [−0.066, −0.046]), ρ = −1.00.
- `E10_naive_official` / GBM: **0.8369 → 0.7933**, slope −0.037, ρ = −1.00.
- `E11_weighted_rule` / persistence: **0.9197 → 0.9368** — a slight *increase*, ρ = +1.00.
All descriptive with CIs, no confirmatory test (Q-STAT-04). The anchored arm on the 494 uncensored
events is far steeper for the learned models (E11/GBM **0.7335 → 0.5189**), which is expected: that
population excludes the floor mass, so the same rescaling moves labels that are free to move.

**5. ANOMALY, flagged prominently — high-risk CONDITIONAL coverage is very low for the learned
models.** At `s = 1.0`, nominal 90%, high-risk stratum: `E11_weighted_rule`/GBM ≈ **0.47**,
`E12_cqr_weighted_rule`/GBM ≈ **0.20–0.27**, `E10_naive_official`/GBM ≈ **0.27–0.28**; persistence
≈ **0.96**. Read carefully before alarm: this is **conditional coverage on a subgroup**, which
conformal prediction never promises — the Gate 2 claim is explicitly **marginal**, and Gate 1
already PIVOTed away from group-conditional claims (E13 skipped) on power grounds. So this is
**not** a new failure of Contribution 1. It is, however, the first time this project has looked at
high-risk conditional coverage, it is a number any reviewer will ask about, and the operational
reading is uncomfortable: the learned models' intervals miss the true risk for roughly half the
high-risk events they are supposed to protect. Surfaced for Sidh; **not** acted on, and no method
was retried to improve it (CLAUDE.md §9).

> **[ANNOTATION 2026-09-15 — bootstrap CIs added, per the Gate 3 requirement]** The three figures
> above were point estimates only; Gate 3 required event-level bootstrap CIs before treating them as
> final. They are now reported in `reports/04_labelnoise.html` §10 and
> `reports/tables/e14_conditional_coverage_anomaly_ci.csv` (+ figure
> `e14_conditional_coverage_anomaly_ci`). High-risk stratum, n = 150, s = 1.0, nominal 90%,
> 3 seeds, 2,000 resamples, seed-averaged percentile-bootstrap bounds (same convention as E9–E14):
> - `E11_weighted_rule` / GBM: **0.467 [0.387, 0.544]** (anchored); **0.500 [0.420, 0.580]** (direct)
> - `E12_cqr_weighted_rule` / GBM: **0.200 [0.138, 0.262]** (anchored); **0.269 [0.200, 0.340]** (direct)
> - `E11_weighted_rule` / persistence: **0.967 [0.933, 0.993]** (both arms)
>
> No new computation: `coverage_with_ci` had already produced these bounds in `e14_coverage.csv`;
> the addendum only surfaces them. A re-render reproduced every previously recorded E14 coverage
> value exactly. Descriptive only — conditional coverage is not tested against nominal (Q-STAT-04;
> conformal's guarantee is marginal). The GBM and CQR bootstrap intervals exclude nominal 90% by a
> wide margin, and both lie entirely below persistence's interval.

**6. Seed behaviour is sane.** Persistence is seed-invariant (sd = 0.000, expected — it fits
nothing). GBM sd across 3 seeds is 0.001–0.003 for split conformal and ~0.027 for CQR, so the CQR
arm carries visibly more seed variance than the split arms.

**Explicitly NOT decided here (Sidh's, at Gate 3):** the venue-tier call; whether Contribution 2 is
established; how to frame a flat primary curve whose flatness is partly interval-width-driven;
whether the high-risk conditional-coverage anomaly (finding 5) warrants any scope or framing change;
and whether to confirm or revise the E14 pre-registration and its amendment. Execution stops at the
Gate 3 boundary — no Phase 5 (E15–E18) work was started (CLAUDE.md §13.4, §13.7).
**Reported by:** Claude Code.


---

## Phase 5 Pre-registration (PROPOSED — written BEFORE E15 executes)

### 2026-09-18 — PRE-REGISTRATION: E15 decision-cost protocol (turning the E15 design review into a protocol)

**Status:** PROPOSED by Claude Code. Written before any E15 code read the official test set. It
turns Sidh's four E15 decisions (RESOLVED, 2026-09-18) into an executable protocol. Where those
decisions leave a choice open, the choice is made here, before results, and flagged (§3, §4).

**§1 Methods.** Decision scores on the official test set, 3 seeds (42/43/44):

| method | learners | decision score |
|---|---|---|
| `point` | persistence, GBM, GRU, MC-dropout (MC mean) | uncalibrated point prediction |
| `E10_naive_upper` | same four | one-sided split-conformal upper bound (signed residual score) |
| `E11_weighted_rule_upper` | same four | rule-weighted one-sided upper bound (the Gate 2 weights) |
| `E12_cqr_weighted_rule_upper` | GBM | rule-weighted one-sided CQR bound on the level-ℓ quantile head (§5) |
| `E8_bayes_upper` | MC-dropout | uncalibrated Gaussian predictive bound μ + Φ⁻¹(ℓ)·σ |

- Nominal ℓ ∈ {0.80, 0.90, 0.95}; primary 0.90.
- Hyperparameters come from the Phase-2 searches.
- Events outside the Q-SEL-03 supported region get a bound of +∞ (always alerted), and they are
  counted. E11 found none.

**§2 Matched alert budget (D3).**
- The K highest-scoring events are alerted.
- Events tied at the boundary share the remaining alerts equally (the expected value under uniform
  random tie-breaking). This is deterministic, and no method gains from an arbitrary tie order.
- **Primary evaluation point:** K = round(p_test × N), the prevalence-matched budget. At this
  burden a perfect ranking misses nothing and raises no false alarm. p_test is the same test
  high-risk prevalence the rule weights already use.
- **Secondary evaluation points:** K = 5%, 10% and 20% of N.
- The tradeoff figure sweeps every K from 1 to N.

**§3 The high-risk lens (D1) in practice — flagged for Sidh.** High-risk means true final risk ≥
−6 (the challenge definition; n = 150).
- **High-risk block (primary).** Missed high-risk events (the lead number), miss rate, recall, and
  the bound's realised one-sided coverage on high-risk events. These are computed on the high-risk
  events.
- **Whole-population block (secondary).** Unnecessary maneuvers, false-positive rate, precision, F2
  and cost all count non-high-risk events by definition, so they **cannot** be computed on the 150
  high-risk events alone.
- Every table puts the high-risk block first.

**§4 Two identities, stated before results — flagged for Sidh.**

(i) *Rank invariance.* Alerts depend on a score only through its order.
- The split and weighted one-sided bounds are pred + Q with one shared Q (the rule weights use one
  representative test weight).
- One-sided CQR is q_hi(x) + Q.
- So at every matched budget, `E10_naive_upper` and `E11_weighted_rule_upper` raise **the same
  alerts as their own learner's `point`**. `E12_cqr_weighted_rule_upper` raises the same alerts as
  the GBM upper quantile head.
- Only three things can change which events are alerted: the choice of learner, CQR's quantile
  head, and MC-dropout's per-event σ.
- **Consequence:** under D3, split/weighted conformal cannot beat its own point prediction, by
  construction. For those methods the E15 failure criterion is met by construction.
- The runner reports the largest alert difference against the matching point score. It is expected
  to be exactly 0, except where float rounding in pred + Q creates a new tie. Any non-zero value is
  reported, not hidden.

(ii) *Cost at a matched budget.* C_r = r·FN + FP = (r+1)·FN + K − n_HR.
- At a fixed K, ordering methods by cost is the same for 5:1, 10:1 and 20:1.
- That ordering is the same as ordering by missed high-risk events.
- The ratios scale cost differences but cannot reorder methods.

Together, (i) and (ii) mean the D2 caveat (one-sided under-coverage) cannot change any matched-budget
decision. The caveat bears on the bound's value, which is reported as realised coverage (§3). It
would also bear on a threshold rule (alert if the bound is ≥ −6), but D3 excludes that rule and E15
does not run it.

**§5 New construction — one-sided CQR.**
- E12 computed two-sided CQR only (see the annotation on the 2026-09-16 E12 disposition entry), so
  one-sided CQR is new here.
- It is implemented in `conformal/cqr.py` with analytic tests.
- It is validated on the exchangeable self-test split (the E9 analog) before its official-test
  numbers are read.
- If self-test coverage misses nominal (the Clopper–Pearson CI excludes it), that is reported and
  the CQR arm is marked unvalidated.

**§6 Uncertainty.**
- 2,000 event-level resamples per seed, using the same draws `coverage_with_ci` uses.
- Decisions stay fixed at their full-sample values; the events are resampled.
- 95% percentile intervals, averaged over seeds (project convention).
- Resamples where a metric is undefined are excluded and counted.
- **"Advantage"** in the success/failure criteria is read from a **paired** bootstrap interval of
  the difference in missed high-risk events. Each calibrated method is compared with (a) its own
  learner's point prediction and (b) `E8_bayes_upper`, at the primary budget and level.
- That interval is descriptive: no p-values, no significance language (D4).

**§7 Caveat text.** Every E15 table and figure carries: *"One-sided upper bounds under-cover on the
official test set (E11 diagnostic: the one-sided machinery is validated under exchangeability, but
rule-derived weighting does not restore one-sided validity); persistence's one-sided bound is
additionally degenerate (a 65.9% zero-atom in its signed scores, Gate 2)."*

**§8 Runtime and integrity.**
- Adding the `decision_cost` config block changes the config hash, so all three searches (GBM, GRU,
  MC-dropout) re-run.
- The searches are seeded; their `best_params` must match the existing caches (E6 `30b803eb…`;
  E7/E8 `eb89df79…`).
- A mismatch is reported, not silently accepted.

**Decided by:** PROPOSED by Claude Code; to be confirmed or revised by Sidh at the E15 checkpoint.
**Supersedes:** none.

### 2026-09-18 — PRE-REGISTRATION: expanded threshold-based decision analysis (E15 expansion, absorbs E16)

**Status:** PROPOSED by Claude Code, written before any threshold-analysis code exists. Sidh's
instruction: expand Phase 5 properly, given confirmed schedule slack and no shortcuts. This
**supersedes the earlier narrower single-threshold addendum and the separate E16 design**. The
matched-budget E15 results above stand unchanged; this adds the threshold-based view that D3
excluded from the matched-budget comparison. Nothing past a smoke test runs until Sidh has seen and
approved the runtime estimate.

**§0 BLOCKED — the lead-time set (flagged; not decided here).**
- **Q-METH-04 has no resolution in this file.** `OPEN_QUESTIONS.md` *recommends* option (b),
  horizons {2d, 1d}, and says it "must be fixed before Phase 3 evaluation runs". E16's spec defers
  to "Q-METH-04's resolved horizon set" without naming one. There is therefore no recorded
  {2d, 1d} specification to reuse.
- **A 1-day horizon cannot be built on the official test set.** All 24,484 official-test input CDMs
  are at least 2 days before TCA: **0** fall in [1, 2) days and 0 below 1 day (measured on
  `data/processed/events.parquet`; consistent with Phase 0 finding 2). A 1-day prediction would see
  exactly the inputs the 2-day one sees. The training pool does contain them: 24,681 CDMs in
  [1, 2) days across 9,231 events, so 1-day horizons exist only there.
- **Options for Sidh:**
  1. 2d on the official test set, plus 1d on the exchangeable self-split only — disclosed, not
     comparable to official-test numbers, and the selection-bias correction has nothing to correct
     there;
  2. longer horizons on the official test set, e.g. {2d, 3d} or {2d, 3d, 5d} (test CDMs reach
     about 7 d), each needing recut features, refit learners and per-horizon calibration (Q-CONF-01);
  3. a single 2d horizon, with the lead-time analysis dropped and disclosed;
  4. (1) combined with (2).
- Until this is resolved, everything below is written for a generic horizon set H, and the smoke
  test runs H = {2d} only.

> **[RESOLVED 2026-09-19 — Sidh]** Q-METH-04 is revised to horizons **{2-day, 3-day}, both on the
> official test set** (option 2 above, with the pair {2d, 3d}). The {2d, 1d} pair is infeasible, as
> recorded above, and no longer describes the design. See the RESOLVED entry "Expanded E15 design
> decisions" (2026-09-19).

**§1 Methods (decision scores).**
- **All four learners** (persistence, GBM, GRU, MC-dropout):
  - `point`;
  - split conformal (E10 naive): one-sided upper bound, and two-sided upper edge;
  - weighted conformal (E11 rule): one-sided upper bound, and two-sided upper edge.
- **GBM only:** rule-weighted CQR, one-sided upper bound (validated at E15 §5) and two-sided upper
  edge (validated at E12).
- **MC-dropout only:** the E8 Bayesian bound, one-sided and two-sided upper edge.
- **Exclusion with disclosure:** persistence's one-sided bounds (E10/E11 upper) are excluded,
  because of the degenerate 65.9% zero-atom in its signed scores (Gate 2). The exclusion is listed
  in every table, with its reason. Persistence's point prediction and two-sided arms are included.
- **Two-sided arms and D2 — flagged for Sidh.** D2 forbids *substituting* the two-sided upper edge
  for the one-sided bound. Here the two-sided arms are separately labelled methods reported
  *alongside* the one-sided ones, never in their place. If D2 is meant to exclude two-sided upper
  edges from decision analysis altogether, these arms are dropped.

> **[RESOLVED 2026-09-19 — Sidh]** Two-sided arms are **retained** alongside the one-sided arms,
> for every method where both are already validated.
- Nominal levels {0.80, 0.90, 0.95}, primary 0.90; seeds 42/43/44; hyperparameters from the Phase-2
  searches.

**§2 Decision rule and threshold grid.**
- Rule: alert on an event iff its score ≥ t.
- **Grid T:** the 5th, 10th, …, 95th percentiles (19 values) of the point predictions of all four
  learners, pooled over all seeds, on the **calibration split**. The grid is fixed without reading
  official-test inputs or labels. Duplicates are removed (the −30 floor atom makes several low
  percentiles coincide) and the number removed is reported.
- The fixed operational threshold **−6** is added regardless of where it falls.
- One grid per horizon, applied unchanged to every method's score. A bound therefore alerts on a
  different set than its point prediction at the same t — that is the effect under study.
- **Operating curves:** each method's full missed-vs-unnecessary locus is swept over every distinct
  threshold (with no ties this equals the budget sweep of E15), with markers at each t ∈ T. The
  same t is linked between a point prediction and its bounds, so the shift is visible across the
  whole range, not at one point.

> **[REVISED 2026-09-19 — Sidh]** The grid's percentile boundaries are computed on the training
> pool's **internal validation split** (`val_inner`), not the calibration split. The official test
> set is never used to select the grid, and −6 is always included. Everything else in §2 stands.

**§3 Metrics, per horizon, level, method, learner and threshold.**
- **PRIMARY — high-risk events (D1):** missed high-risk events (the lead number), miss rate, recall,
  high-risk events alerted.
- **SECONDARY — whole population:** alerts issued, unnecessary maneuvers, false-positive rate,
  precision, F2, cost at 5:1 / 10:1 / 20:1.
- **Uncertainty:** 2,000 event-level resamples per seed (the same draws as `coverage_with_ci`),
  decisions fixed, seed-averaged bounds.
- Paired bootstrap differences, bound minus point, in missed high-risk events and in unnecessary
  maneuvers at each t. Descriptive only (D4).

**§4 Cost-minimizing thresholds, per ratio, per method against its own point prediction, per horizon.**
Choosing the cost-minimizing threshold *on the official test set* would be tuning on it
(CLAUDE.md §3). Hence four read-outs:
- **Primary (deployable).** The cost minimizer over T is selected on the **self-test split**
  (exchangeable, labelled, disjoint from calibration and official test), separately for the point
  prediction and for each bound. It is then **evaluated on the official test set** with bootstrap
  CIs. Disclosed caveat: self-test has the training high-risk prevalence (2.77% vs 6.92% on test),
  so the selected operating points carry the documented shift. That is the realistic deployment
  condition.
- **Secondary (deployable, shift-aware).** The same selection, with each self-test event's cost
  weighted by the rule-derived likelihood-ratio weights (the Gate 2 weights), so selection targets
  the test distribution.
- **Oracle (not deployable).** The in-sample cost minimizer over T on the official test set.
  Labelled "oracle" everywhere and never presented as achievable.
- **Unrestricted oracle.** The in-sample minimum over *all* thresholds, reported to separate
  calibration effects from grid discretisation.
- **Reported for each:** optimal t, cost, missed, unnecessary and alerts; the threshold shift
  (bound − point) and cost change (bound − point), the latter with a paired bootstrap CI.

**§5 Pre-registered predictions (written before any threshold result).**
- **P1 (Sidh's prediction, verbatim in substance).** Calibration changes alert sets under the
  threshold rule, unlike the matched-budget policy, with the size of the divergence from the
  point-based curve tracking each method's interval half-width.
- **P1 made precise by Corollary 4 of Proposition 1**, so it cannot be read two ways afterwards:
  - **P1a — operating point at a fixed threshold.** For the translation class (split/weighted
    conformal), alerts(bound, t) = alerts(point, t − Q) exactly. The change in alert set at a fixed
    t grows with Q: the one-sided quantile, or the two-sided half-width. Expected to hold exactly;
    verified numerically per method.
  - **P1b — the operating locus.** For the translation class, the missed-vs-unnecessary locus over
    all thresholds is **identical** to the point prediction's; it does **not** diverge, whatever Q
    is. Only CQR and the E8 bound can trace a different locus. So "divergence tracking half-width"
    is predicted for the operating point at a fixed t (P1a), **not** for the locus (P1b).
  - **P1c — cost optima.** For the translation class, the unrestricted-oracle optimal cost equals
    the point prediction's exactly, with the optimal threshold shifted by Q. Grid-restricted and
    self-test-selected optima can differ from the point prediction's only through grid
    discretisation and the selection-split/test mismatch.
- **Descriptive association.** Spearman correlation, across method × learner × level, between Q and
  the fixed-t alert-set change. No test (D4).

**§6 Per-horizon handling (applies once §0 is resolved).** For each horizon h:
- features are recut at cutoff h, and learners refit with the E6–E8 hyperparameters (re-searching
  per horizon is an option, flagged, at about 45 min per horizon);
- calibration is done separately per horizon (Q-CONF-01);
- bounds are recomputed, CQR is self-test validated, and the positivity partition is recomputed
  per horizon.

> **[RESOLVED 2026-09-19 — Sidh]** No hyperparameter reuse across horizons: the 3-day horizon gets a
> **fresh 24-trial search** (E6/E7/E8, equal budgets). The 2-day search also re-runs, because the
> config hash changes; being seeded, it must reproduce the earlier 2-day caches, and that is checked.

**§7 Caveats carried.** The E15 one-sided caveat; the persistence one-sided exclusion; and a
threshold-rule note that bounds and point predictions share one grid defined in point space.

**§8 Execution discipline.**
1. A smoke run (1 seed, reduced grid) validates the pipeline end to end.
2. A runtime estimate is reported to Sidh.
3. After approval, the full run goes to the background with a progress log, a monitor, and
   30-minute checkpoints.

**§9 Protocol details, fixed before the smoke run.**
- **Tie rule.** Among thresholds with equal minimal cost, the highest one (fewest alerts) is chosen.
- **Shift-aware selection weights (§4 secondary).** The rule-derived weights are evaluated on the
  self-test events with the same construction and prevalences as the Gate 2 calibration weights.
  Events failing the recency filter get weight 0, exactly as in calibration.
- **Unrestricted oracle.** The candidate thresholds are every distinct finite score value (alerting
  at or above it), plus +∞ (no alerts).
- **P1a check.** For each bound, Q = median(bound − point) over supported events. P1a holds when the
  counts of `bound ≥ t` equal the counts of `point ≥ t − Q` at every t ∈ T. Float rounding can move
  an event sitting exactly on a boundary, so any non-zero difference is reported, not hidden.
- **P1b check.** The largest absolute difference between the budget-sweep loci of bound and point
  (missed high-risk events at every K).
- **The smoke run and the official test set.** The smoke run (1 seed, reduced percentile grid) reads
  the official test set only to validate the pipeline end to end and to time it. Its decision
  numbers are **not** interpreted, **not** recorded as findings, and **not** used to change any
  choice here. The full run re-scores the test set once.
- **Search cache.** Adding the `threshold_analysis` config block changes the config hash, so the
  smoke run re-runs the three searches once (about 45 min); the full run then reuses them.

**Decided by:** PROPOSED by Claude Code under Sidh's instruction; to be confirmed or revised by Sidh
(including §0, the §1 two-sided arms, and §4's selection split) before the full run.
**Supersedes:** the earlier narrower single-threshold addendum; EXPERIMENT_PLAN.md E16 as a
separate experiment (merged into E15).

### 2026-09-19 — AMENDMENT to the expanded threshold pre-registration: implementing the {2-day, 3-day} resolution

**Status:** PROPOSED by Claude Code. Written after Sidh's 2026-09-19 decisions and **before any
full-grid result exists**. It records what implementing those decisions requires; item 1 is a
consequence of Decision 1's own rationale and is flagged for Sidh.

**1. Event populations — flagged.**
- At the 3-day cutoff, **122 of the 2,167 official-test events** have no input CDM at least 3 days
  before TCA, so they cannot be predicted. 12 of them are high-risk.
- The 3-day set (2,045 events, 138 high-risk) is a strict subset of the 2-day set. Measured on the
  real data before any threshold result.
- Evaluating each horizon on its own set would confound the lead-time effect with a change of
  population — exactly what Decision 1's rationale rules out. Therefore:
  - **Primary lead-time comparison:** both horizons are scored on the **common set**, the 2,045
    official-test events predictable at both horizons.
  - **Also reported:** each horizon on its own full set. For 2-day that is all 2,167 events,
    matching E15; for 3-day it is identical to the common set. The 122 excluded events are
    disclosed with their high-risk count.
  - Calibration, weights, self-test threshold selection and the grid all stay per horizon, on that
    horizon's own training-pool splits. Only the official-test scoring population is harmonised.

**2. Per-horizon configuration.**
- Each horizon runs from a derived configuration. It is identical to the base except that
  `cutoff.cutoff_days_before_tca` equals the horizon and the horizon list is reduced to it.
- Features, splits, calibration and the search cache are therefore horizon-specific, and each
  horizon's searches get their own cache key.
- The search-integrity check compares a cache only with earlier caches for the same cutoff. Every
  cache written before horizon support existed is a 2-day cache.

**3. Grid source (Decision 3).** The grid uses the pooled point predictions of the four learners,
over all seeds, on each horizon's `val_inner`. `val_inner` is also the learners' early-stopping
split; here it only places the percentile boundaries and is never scored.

**4. Real-data smoke before the full run.** The horizon machinery is new code, so per standing
practice a real-data smoke run comes first: 1 seed, reduced grid, both horizons, numbers not
findings. Smoke and full run share one configuration, so the searches the smoke run performs are
cached and reused by the full run, with no double search cost.

**Decided by:** PROPOSED by Claude Code, implementing Sidh's 2026-09-19 decisions. Sidh may revise
item 1 before the full run's results are read.


### 2026-09-20 — PRE-REGISTRATION: extended threshold grid (point + bound percentiles), fixing the ceiling artifact

**Status:** PROPOSED by Claude Code, implementing Sidh's 2026-09-20 decision. Written **before any
number produced under the extended grid exists**, and before the code that builds it was run
(CLAUDE.md §3). It fixes the limitation flagged — not silently corrected — in §4 of the
2026-09-19 expanded-threshold findings entry.

**1. The diagnosed cause (measured, already on record).**
- The original grid is the 5th–95th percentiles of the pooled **point predictions** on the internal
  validation split, plus the fixed operational −6. Every one of those percentiles lies below −6, so
  the grid's maximum is exactly −6 at both horizons: 18 thresholds at 2 d (max −6, next −7.167),
  19 at 3 d (max −6, next −7.097).
- GBM and GRU point predictions sit systematically below −6 — the same train/test high-risk
  imbalance identified in Phase 2, where the learned models collapse toward the low-risk mass.
  Their conformal bounds sit **above** their own points by Q, frequently above −6 itself.
- Consequence, measured: the self-test-selected threshold lands on the grid maximum for **62.3% of
  bound selections** across the two deployable read-outs (62.7% / 62.0%), against 54.2% of point
  selections. The bound arms were being scored on a grid with **no resolution in the range they
  actually occupy**, so §4's "threshold shift vs point" largely measured the distance to the
  ceiling rather than Q. The direct point-vs-bound P1c contrast is unaffected: it optimises over
  every distinct score value, not over the grid.

> **[ANNOTATION 2026-10-01 — historical, not regenerable]** The 62.3% / 54.2% ceiling fractions
> above were computed by the original-grid E15 run at `c9f423f` (2026-09-19). The extended-grid run
> (`6e8debd`) overwrote `e15c_selection`, so **they cannot be regenerated from the current tables**;
> reproducing them requires re-running E15 at `c9f423f`. `05c_threshold_analysis.ipynb` §7b (added
> at `6e8debd`) prints them as hardcoded literals ("was 62.3% … was 54.2%"), so the rendered
> `05c_threshold_analysis.html` carries two historical numbers that no current table supports. The
> notebook and report are **not** changed by this annotation. See the 2026-10-01 record-annotation
> entry, item 6.

**2. The fix.** The threshold grid T, per horizon, becomes the sorted, deduplicated union of:
- **(a)** percentiles of the pooled **point-prediction** distribution — the original design,
  unchanged: four learners × all seeds, on `val_inner`;
- **(b)** percentiles of the pooled distribution of **every validated bound's values**, across all
  methods and both sidednesses, at the same percentile list, on `val_inner`;
- **(c)** the fixed operational threshold **−6**.

All percentiles are computed on the training pool's **internal validation split only**. The
official test set is never used to select the grid — it is only scored on the grid once built.
This is the standing rule of Sidh's 2026-09-19 Decision 3, unchanged.

**3. Why this targets the diagnosed mechanism directly.** The artifact is a resolution failure, not
a selection failure: the grid had no candidate thresholds where the bounds live, so bound selection
had nowhere to go but the ceiling. Pooling the bounds' own values into the percentile computation
puts grid points exactly where the bounds are dense, at the same percentile resolution the point
predictions already got. Nothing else about the procedure changes. **This was decided before seeing
what it would do to any reported number**; §5 below records, in advance, what it must and must not
move.

**4. Scope of the re-run — what is and is not redone.**
- **Not redone:** every hyperparameter search. All searches are cached, keyed by the per-horizon
  config hash, and the extended grid does not change that hash's search inputs. The run records
  `searches_cached_at_start` per horizon in its metadata and provenance; that record is checked
  after the run, and a cache miss (a search actually executing) is reported as an anomaly, not
  absorbed silently.
- **Redone:** grid construction and the whole analysis-over-grid stage, for both horizons, both
  populations, all three seeds, all nominal levels.
- **Honest statement of cost:** the pipeline holds **no prediction cache** — `base_predictions` and
  the quantile heads refit on every invocation. They are pure seeded functions of (config, seed,
  code version), so they reproduce the completed run's predictions exactly; they cost roughly
  57 minutes of the run's ~61. Nothing upstream is *re-decided*, but it is re-*computed*.
  Verification that it reproduced: component (a) of the extended grid must be **bit-identical** to
  the original grid's percentile thresholds. If it is not, the run is a loud failure and stops.
  *(ANNOTATION 2026-09-20, after the run: this wording was too strong. Component (a) came back
  within 1 ULP (3.55e-15 absolute, 1.9e-16 relative), not bit-for-bit, because the learned fits
  use multithreaded reductions whose summation order is not bitwise reproducible. CLAUDE.md §4's
  standard is "byte-identical **or** numerically-identical-within-tolerance"; this meets the
  latter. Recorded as a deviation in the findings entry of the same date, not waved through.)*
  *(CORRECTION 2026-09-21: the annotation above is WRONG, and so was its stated cause. Component
  (a) reproduced **bit-for-bit**. The apparent 1-ULP gap was produced by the verification script,
  which read the grid table back with pandas' default fast float parser; that parser can return a
  double one ULP away from the 17-digit value written. Re-read with `float_precision="round_trip"`,
  both horizons' component (a) is exactly equal to the original grid. The "multithreaded
  reductions" explanation was never tested — an unverified guess recorded as fact. The
  pre-registration's "bit-identical" wording was correct and was met. Found during E17, when the
  same parser artifact reappeared and was traced. See the Observations Log, 2026-09-21.)*
- **Implementation consequence:** the GBM quantile heads must also predict on `val_inner` (they
  previously predicted calibration / self-test / official-test only), so that component (b) can be
  computed on the same split as (a). Adding a split changes no existing split's values.
- Bound values that are `+inf` outside the Q-SEL-03 supported region are excluded from the
  percentile computation; so are persistence's one-sided bounds, which are excluded from the
  analysis itself (degenerate quantile, Gate 2) and are therefore not "validated bounds".

**5. Stated in advance — what the fix must and must not change.** These are falsifiable checks, not
expectations to be reinterpreted afterwards:
- **Must be unchanged (exactly):** every quantity read at the fixed operational threshold −6 — the
  §4 primary high-risk table, the §5 secondary table, the lead-time comparison — because −6 is in
  both grids and those tables are read at a fixed threshold, not at a selected one.
- **Must remain exactly 0:** P1a, P1b and P1c. P1c is grid-independent by construction; P1a and
  P1b are computed over T and must hold on any grid. A non-zero value is a defect, not a finding.
- **Expected to change:** the four threshold-selection read-outs, the ceiling-pinned fraction, the
  grid-restricted oracle, and the density of the operating curves. Whether the corrected read-outs
  alter the lead-time or persistence-dominance story is **the open question this re-run answers**;
  no direction is predicted here.
- **Unchanged by construction:** populations (common 2,045 / horizon-full), arms and exclusions,
  cost ratios, nominal levels, the highest-threshold tie rule, 2,000-resample event-level
  bootstrap, the selection split, and the standing caveat that one-sided bounds under-cover.

**6. Cross-experiment synthesis.** This is the fourth independent manifestation of the Phase-2
train/test high-risk imbalance — this time distorting the evaluation instrument itself. Logged in
full in the Observations Log (2026-09-20) and flagged there as a manuscript discussion-section
candidate.

**Decided by:** Sidh (2026-09-20), recorded by Claude Code before execution.


---

## Phase 5 Empirical Findings (E15) — REPORTED, no decision taken

<!--
Measurements only. Every number is regenerable via `kc decision`; report
reports/05_decision_cost.html; tables reports/tables/e15_*.csv. 3 seeds
(42/43/44), 2,000 event-level resamples, seed-averaged values and bounds.
-->

### 2026-09-18 — E15 decision cost: conformal calibration changes no matched-budget decision; the ranking score decides, and persistence ranks best

**Report:** `reports/05_decision_cost.html`, run at commit `94ed187`, 3,839 s. The protocol is
exactly as pre-registered above; nothing was tuned after a decision number was seen.

**Every stated caveat applies:** one-sided upper bounds under-cover on the official test set (E11
diagnostic: machinery validated under exchangeability, but rule-derived weighting does not restore
one-sided validity), and persistence's one-sided bound is additionally degenerate (a 65.9%
zero-atom, Gate 2). Finding 5 quantifies this.

**Integrity checks, all passed.**
- **Searches.** The config-hash change re-ran the GBM, GRU and MC-dropout searches. All three
  reproduced every earlier cache bit-for-bit, `best_params` and objective alike (§8).
- **Alert identity (§4(i)).** At every level and budget, the largest alert difference between each
  E10/E11 bound and its own point prediction, and between one-sided CQR and its GBM quantile head,
  is **exactly 0**.
- **One-sided CQR (§5).** It is validated on the exchangeable self-split, with the CP interval
  containing nominal at every level: 0.788 at 80%, 0.893 at 90%, 0.943 at 95%.
- **Cost ordering (§4(ii)).** Method ordering is identical across missed high-risk events and all
  three cost ratios.
- **Positivity.** All 2,167 test events are supported.

**1. PRIMARY — missed high-risk events.** Prevalence-matched budget K = 150 (n_HR = 150), nominal
90%, mean [95% CI]:
- persistence (point, and its E10/E11 bounds): **50.0 [36.7, 63.7]**, miss rate 33.3%
- GBM one-sided CQR bound (rule-weighted): **71.3 [55.3, 88.0]**, 47.6%
- GRU (point, and its bounds): 101.0 [82.3, 120.7], 67.3%
- MC-dropout E8 Bayesian bound: 101.3 [83.0, 120.7]; MC-dropout point and its bounds: 101.7 [83.0, 121.0]
- GBM (point, and its E10/E11 bounds): **113.0 [92.7, 133.3]**, 75.3%

The ordering is the same at every other pre-registered budget. Missed high-risk events at
5% / 10% / 20% of N:

| method | K = 108 | K = 217 | K = 433 |
|---|---|---|---|
| persistence | 80.0 | 26.0 | 13.0 |
| CQR | 83.7 | 49.3 | 15.0 |
| GBM | 119.7 | 95.0 | 41.3 |

**2. SECONDARY — whole population, same budget.** At K = n_HR, unnecessary maneuvers equal missed
high-risk events by arithmetic (FP = K − TP = FN), so the unnecessary counts repeat finding 1, and F2
equals recall.
- Persistence: FPR 2.48%, F2 0.667, cost 300 / 550 / 1,050 at 5:1 / 10:1 / 20:1.
- CQR: FPR 3.54%, F2 0.524.
- GBM: FPR 5.60%, F2 0.247.
- The cost ratios scale these differences but never reorder methods (§4(ii), confirmed).

**3. Paired differences in missed high-risk events** (primary budget and level; positive = misses
more; descriptive):
- **E10 and E11 bounds vs their own point prediction: +0.0 [+0.0, +0.0] for all four learners**, by
  construction (§4(i)). Split or weighted conformal calibration changed **no** alert.
- **E12 one-sided CQR vs GBM point: −41.7 [−56.0, −27.3].** Because CQR raises exactly the alerts of
  its 0.90 quantile head, this advantage comes from the quantile-regression ranking, not from the
  conformal step.
- CQR vs the E8 Bayesian bound: −30.0 [−43.7, −17.7].
- Persistence bounds vs E8: −51.3 [−69.7, −33.7]. GBM bounds vs E8: +11.7 [+1.7, +22.3]. GRU and
  MC-dropout bounds vs E8: intervals include 0.
- The E8 Bayesian bound vs MC-dropout's own point prediction differs by under one event (101.3 vs
  101.7).

**4. What the pre-registered identities turned into.** Under the matched-budget definition (D3),
every decision difference in E15 comes from the **ranking score**. Conformal calibration adds a
constant and changes nothing. The best-ranking score is the **uncalibrated persistence point
prediction**, which misses fewer high-risk events than every calibrated bound at every budget. The
only bound that beats its own learner's point prediction is CQR, through its quantile head, and it
still misses more than persistence.

**5. The D2 caveat, quantified — realised one-sided coverage at nominal 90%.**

| bound | whole population | high-risk events only |
|---|---|---|
| E8 Bayesian | 0.882 | 0.264 |
| GBM E11 | 0.854 | 0.107 |
| GBM CQR | 0.849 | 0.131 |
| GRU E11 | 0.870 | 0.244 |
| MC-dropout E11 | 0.866 | 0.191 |
| persistence (E10/E11, degenerate) | 0.897 | 0.407 |

- Across the whole population the learned-model bounds range 0.849–0.882. Persistence's degenerate
  bound is 0.897.
- **On true high-risk events the one-sided bounds sit below the true risk for 59–92% of them** —
  underestimating risk exactly where it is dangerous. This is the one-sided counterpart of the E14
  two-sided conditional-coverage anomaly, and it is sharper.

**Mechanical reading of the spec criteria — not a judgement.**
- For split and weighted conformal, "no reduction in missed high-risk events at matched budgets at
  any cost ratio" holds exactly, by construction.
- For one-sided CQR, there is a reduction against its own learner (GBM) and against E8, but not
  against the best point prediction (persistence).

**Explicitly NOT decided here (Sidh's):**
- whether the E15 failure or success criterion is met;
- whether pre-registration §3 (which metrics form the high-risk block) and §4 (the identities) are
  confirmed;
- whether the matched-budget comparison should be complemented by a threshold-based view, where
  calibration would matter (D3 excludes one; E15 did not run it);
- how finding 4 and finding 5 are framed;
- anything in E16–E18.

Execution stopped at this checkpoint.
**Reported by:** Claude Code.

> **[EXTENDED 2026-09-18]** The formal grounding for finding 4 and the complete method
> classification are in the next entry, "EXTENSION of the E15 matched-budget finding". This entry
> is unchanged.

### 2026-09-18 — EXTENSION of the E15 matched-budget finding: rank invariance (Proposition 1), complete method classification, empirical confirmation

**Extends, does not replace,** the E15 findings entry directly above; that finding stands as
recorded. This entry adds the formal result behind it and the complete classification it lacked.
**Report:** `reports/05b_rank_invariance.html`, run at `ab4c5d1` (1,084 s, 3 seeds). The learners
were refit with the cached hyperparameters — no search, no model selection. The official test set
was scored only.

**Setting.** Events i = 1…n carry scores s_i, and s₍K₎ is the K-th largest. The matched-budget rule
(D3) alerts a_i(K; s) = 1 if s_i > s₍K₎; (K − #{j : s_j > s₍K₎}) / #{j : s_j = s₍K₎} if s_i = s₍K₎;
and 0 otherwise.

**Proposition 1 (rank invariance).** For scores s and s′ on the same events, **a(K; s′) = a(K; s)
for every K ∈ {0,…,n} if and only if s and s′ are order-isomorphic**: for all i, j, s_i < s_j ⇔
s′_i < s′_j, and s_i = s_j ⇔ s′_i = s′_j. In particular, s′ = g(s) with g strictly increasing gives
identical alerts at every budget.

**Proof.**
- **(⇐)** Order isomorphism preserves the descending order and the tie classes. The K-th largest
  s′ therefore sits in the tie class matching the K-th largest s, so {s′ > s′₍K₎} = {s > s₍K₎} and
  {s′ = s′₍K₎} = {s = s₍K₎}, hence a(K; s′) = a(K; s). A strictly increasing g is injective and
  order-preserving, which is order isomorphism.
- **(⇒)** Define u_i = min{K : a_i(K) > 0} and v_i = min{K : a_i(K) = 1}. Under the rule,
  u_i = #{j : s_j > s_i} + 1 and v_i = #{j : s_j ≥ s_i}. Then s_i = s_j ⇔ (u_i, v_i) = (u_j, v_j),
  and s_i < s_j ⇔ v_j ≤ u_i − 1. So the alert family determines the weak order up to isomorphism.
  Identical alerts at every K give identical (u, v), hence isomorphic orders. ∎

**Remark (strictness matters).** A weakly increasing g can merge two scores into a tie and change
the fractional alerts (three-event example in `tests/test_rank_invariance.py`).

**Corollaries.**
1. **Split and weighted conformal bounds are translations of the point prediction.** p(x) + Q and
   p(x) + Q_w use one shared Q, both for the one-sided upper bound (signed score) and for the
   two-sided upper edge (absolute score). They are therefore rank-identical to the point
   prediction.
   - For weighted conformal this rests on the implementation's single representative test weight.
     A per-event w(x) would void it.
   - Unsupported (+∞) events would also void it; there are none.
2. **CQR is a translation of its quantile head.** The one-sided bound is q₁₋α(x) + Q; the two-sided
   upper edge is max(q_α/2, q₁₋α/2)(x) + Q. Each is rank-identical to its head, which is a separately
   fitted pinball-loss model with no structural relation to p(x).
3. **The Bayesian bound μ + zσ(x)** is rank-identical to μ only if σ is constant or order-preserving
   in μ. Otherwise any agreement is empirical.
4. **Threshold rule.** alerts(g(p), t) = alerts(p, g⁻¹(t)). A translation keeps the operating locus
   and shifts only the operating point at a fixed t, by Q. This is the basis of P1a/P1b/P1c in the
   expanded pre-registration.

**Classification and empirical confirmation.** 20 method × learner × sidedness combinations, each
checked at 3 nominal levels × 3 seeds:

| structural class | arms | prediction | observed |
|---|---|---|---|
| translation of the point prediction | E10 split and E11 weighted; one-sided upper bound and two-sided upper edge; all 4 learners (16 arms) | rank-identical to own point prediction | **16/16 confirmed.** 0 order violations, 0 tie violations, Kendall τ = 1.000, offset spread ≤ 7.1e-15 (float), alert difference **exactly 0** at every budget |
| translation of the quantile head | GBM CQR: one-sided (head q_ℓ) and two-sided upper edge (repaired q_{1−α/2}) | rank-identical to its head, not to the GBM point | **2/2 confirmed.** Order-isomorphic to its head in every level and seed; not to the point (≈1,100 order violations, τ ≥ 0.65). Alert overlap with the point at K = 150 as low as 0.41 (one-sided) and 0.27 (two-sided) |
| event-specific dispersion | E8 Bayesian: one-sided and two-sided upper edge | no structural relation | **Not rank-identical** (≈1,000 order violations among 2,166 adjacent pairs, τ ≥ 0.965), yet alert overlap with the MC mean ≥ 0.98 at every budget |

Structural predictions contradicted: **0 of 20**.

**Why E8 matched its point prediction (~101.5 missed) — an empirical fact, not a structural one.**
- **Its dispersion is not monotone in μ.** Spearman(μ, σ) = −0.87: σ falls as μ rises.
- **Yet it barely reorders events.** σ hardly varies relative to μ. The constant aleatoric term is
  80% of mean predictive variance (σ_ale ≈ 5.6; total σ spans only ≈5.7–6.8), so z·σ ranges over
  ≈1.4 log-units while μ spans ≈30.5.
- **Only near-ties swap.** Events whose μ differ by less than about 1.4 can swap. That reorders
  many adjacent pairs but moves ≤2% of alerts at any budget. Missed high-risk events at K = 150:
  101.3 for the bound vs 101.7 for the mean.
- **Not guaranteed.** A different aleatoric/epistemic balance would not guarantee this agreement.

**Reproduction.** The recomputed missed high-risk events match all 168 rows of the E15 table
(largest |difference| 1.4e-14).

**Observation, flagged — not an E15 finding.** The two-sided CQR upper edge misses 49.7 high-risk
events at K = 150, versus 71.3 for the one-sided CQR bound and 50.0 for persistence. D2 excluded
two-sided upper edges from E15's decision comparison, so this is recorded only as a by-product of
the classification. It bears on the open §1 question in the expanded pre-registration (whether
two-sided arms enter decision analysis). No conclusion is drawn here.

**Explicitly NOT decided here (Sidh's):** the use of Proposition 1 in the manuscript; anything in
the expanded threshold analysis.
**Reported by:** Claude Code.

### 2026-09-19 — Expanded E15 threshold analysis over lead times (E16 merged): P1 holds exactly; calibration moves operating points; persistence stays cheapest; the grid ceiling censors the deployable read-out

**Report:** `reports/05c_threshold_analysis.html`, run at `c9f423f`. It took 3,648 s (61 min) with no
system sleep, no unexpected search and no stage over its flag limit.
- **Setup:** 3 seeds; nominal {80, 90, 95}%; horizons {2 d, 3 d}, both on the official test set.
- **Protocol:** exactly as pre-registered — the 2026-09-18 pre-registration, Sidh's 2026-09-19
  decisions, and the 2026-09-19 amendment.
- A real-data smoke run covering both horizons (not findings) preceded it. That smoke run was paused
  by a 2 h 36 min laptop sleep, which the Windows System log confirms; seeded results are unaffected.
- All numbers are **measurement only**. Every E15 caveat applies, including one-sided under-coverage
  and the persistence one-sided exclusion.

**Integrity, all passed.**
- **Searches.** The fresh 2-day searches reproduce all 10 earlier 2-day caches bit-for-bit. The
  fresh 3-day searches have no earlier cache at that cutoff, as expected.
- **Populations as pre-registered.** 2-day full set: 2,167 events (150 high-risk). Common set:
  2,045 (138); 122 excluded, 12 of them high-risk. The 3-day full set equals the common set.
- **Tables.** 4,884 decision rows, as expected, with 0 NaN or infinite values. Every count identity,
  rate bound, CI bracket and threshold monotonicity check holds.
- **Grids,** from `val_inner` with −6 added: 2-day, 18 thresholds (2 duplicates removed) from −30.96
  to −6.00; 3-day, 19 thresholds (1 removed) from −30.22 to −6.00.

**1. Prediction P1, as made precise before the run: holds exactly.** Across both horizons, both
populations and all levels (168 translation-class rows):
- **P1a:** 0 count difference between `bound ≥ t` and `point ≥ t − Q`;
- **P1b:** 0 operating-locus difference;
- **P1c:** 0 unrestricted-optimal-cost difference.

The fixed-threshold alert-set change tracks Q: Spearman ρ = 0.951 over the 84 translation-class
arms in the common population (descriptive). Calibration **does** change alert sets under the
threshold rule, by exactly a Q-shift along an unchanged operating locus.

**2. At the operational threshold −6, nominal 90%, common population.** Values are mean over 3 seeds,
with 95% CIs.
- **Learned-model point predictions almost never alert.** Both horizons: GBM 1.3 alerts, missing
  137.3 of 138 high-risk events. GRU: 10.7 / 6.0 alerts, missing 133.0 / 136.3. MC-dropout: 2.0 / 6.3
  alerts, missing 138.0 / 137.3.
- **Persistence point** (2 d / 3 d): missed 30.0 [19.7, 41.0] / 28.0 [18.0, 38.7], unnecessary maneuvers
  58 / 112.
- **The bounds are what make the learned models alert at −6.** 2-day GBM, missed / unnecessary:
  - split one-sided 123.3 / 30.7; weighted one-sided 122.3 / 35.3;
  - split two-sided 93.3 / 143.7; weighted two-sided 62.0 [48.0, 77.7] / 217.3;
  - CQR one-sided 91.7 / 20.0; **CQR two-sided 45.7 [33.0, 59.0] / 44.3**.
- **Persistence two-sided bounds** alert on 839–1,250 events: missed 4–8, unnecessary 706–1,120.

**3. Lead time: 2-day → 3-day, same 2,045 events, at −6.**
- Persistence point: missed 30.0 → 28.0, but unnecessary 58 → 112 (alerts 166 → 222).
- CQR two-sided (GBM): missed **45.7 → 109.7**. CQR one-sided: 91.7 → 114.0.
- Conformal arms on the learned models: unnecessary maneuvers generally rise at 3 d (e.g. GBM
  weighted two-sided 217 → 254), with missed roughly unchanged (62.0 → 67.0).
- **Best achievable cost** (unrestricted oracle; point predictions; 5:1 / 10:1 / 20:1; not
  deployable):
  - persistence: 178 / 283 / 409 at 2 d, and 246 / 361 / 572 at 3 d;
  - learned models: at least 476 / 560 / 660 at 2 d, and at least 558 / 706 / 831 at 3 d.
  Persistence is cheapest at both horizons, and every cost is higher at 3 days.

**4. Cost-minimizing thresholds — FLAGGED: the grid ceiling censors the deployable read-out.**
- **Why:** both grids top out at exactly **−6**. Every point-prediction percentile on `val_inner`
  lies below −6, and bounds sit above their points by Q.
- **How often:** the threshold selected on the self-test split lands **on the grid maximum for 63%
  of bound selections**, against 29% of point selections. The rule-weighted variant: 62% of bound
  selections and 79% of point selections. The grid-restricted test oracle: 13%. 14% of unrestricted
  bound optima lie above −6.
- **Consequence:** the deployable "threshold shift vs point" largely measures the distance from the
  point's choice to the ceiling, not Q. For example, every 2-day GBM bound selects −6 against the
  point's −8.562, a shift of +2.562 for all of them. This is a consequence of the pre-registered
  design (grid built from point predictions and applied to bounds), not a code defect, and nothing
  was changed after the fact. **P1c remains the clean calibration comparison.**
- **Read with that caveat — the deployable cost change vs own point prediction** (10:1, 90%, common,
  paired CIs):
  - Learned-model bounds **lower** cost against their own point prediction. 2-day GBM: CQR two-sided
    −829 [−1014, −647], weighted two-sided −493 [−660, −337]. 3-day GBM: CQR one-sided −359
    [−496, −233]. Some 3-day one-sided intervals include 0 (e.g. GBM weighted one-sided −10
    [−45, +21]).
  - Persistence two-sided bounds **raise** cost: +398 [+283, +502] at 2 d, +764 [+655, +859] at 3 d.
  - **Lowest deployable cost** at 10:1: persistence point, 358 [255, 472] at 2 d and 392 [292, 500]
    at 3 d. Best learned arm: GBM CQR two-sided, 501 [373, 633] at 2 d; GBM weighted two-sided,
    924 [771, 1086] at 3 d.

**Explicitly NOT decided here (Sidh's):**
- whether P1 counts as confirmed;
- how to handle the grid-ceiling censoring of §4 — for example reading P1c only, or a grid extension
  that would need a new pre-registration;
  *(ANNOTATION 2026-09-20: RESOLVED by Sidh — the grid extension, pre-registered that day before any
  new number existed. §4's selection read-outs above are superseded by the extended-grid re-run; every
  quantity read at the fixed threshold −6 in §1–§3 stands.)*
- the framing of the lead-time effect and of persistence's dominance;
- whether the two-sided CQR result enters the manuscript;
- anything in E17–E18.

Execution stops at this checkpoint.
**Reported by:** Claude Code.


### 2026-09-20 — Extended-grid re-run: the instrument is fixed for the primary read-out, the ceiling moved for the rule-weighted one, and every conclusion at −6 is unchanged

**Status:** REPORTED by Claude Code. Measurement only, under the 2026-09-20 pre-registration,
written before any of these numbers existed. Run: `kc decision --only threshold`, git
`6e8debd`, config hash `00d1cb2d…`, 3 seeds, 2,000 event-level resamples, 3,404.6 s, no sleep.
Report `reports/05c_threshold_analysis.html`; tables `reports/tables/e15c_*.csv`.

**0. The pre-registered checks, answered.**
- **Component (a) reproduced — to round-off, NOT bit-for-bit.** The pre-registration said the
  point-prediction percentiles must come back *bit-identical*; they came back within **1 ULP**
  (max |difference| 3.55e-15, max relative 1.9e-16, at both horizons). The claim was too strong:
  the learned fits use multithreaded reductions, whose summation order is not bitwise
  reproducible. This meets CLAUDE.md §4's determinism standard ("byte-identical **or**
  numerically-identical-within-tolerance") but not the wording of the pre-registration, and is
  recorded as a deviation rather than passed over. Every original threshold is present in the
  extended grid at that tolerance, and −6.0 is present exactly.
  *(CORRECTION 2026-09-21: this bullet is WRONG, and so was its stated cause. Component
  (a) reproduced **bit-for-bit**. The apparent 1-ULP gap was produced by the verification script,
  which read the grid table back with pandas' default fast float parser; that parser can return a
  double one ULP away from the 17-digit value written. Re-read with `float_precision="round_trip"`,
  both horizons' component (a) is exactly equal to the original grid. The "multithreaded
  reductions" explanation was never tested — an unverified guess recorded as fact. The
  pre-registration's "bit-identical" wording was correct and was met. Found during E17, when the
  same parser artifact reappeared and was traced. See the Observations Log, 2026-09-21.)*
- **Everything read at the fixed threshold −6 is unchanged** — matching the 2026-09-19 entry
  digit for digit: 2-day GBM point 137.3 missed of 138 with 1.3 alerts; 2-day GBM two-sided CQR
  45.7 [33.0, 59.0] missed with 44.3 unnecessary; 3-day the same arm 109.7; persistence point
  30.0 [19.7, 41.0] at 2 d and 28.0 [18.0, 38.7] at 3 d, unnecessary 58 → 112; GBM weighted
  two-sided 62.0 → 67.0 missed, 217.3 → 254.0 unnecessary. §1–§3 of that entry therefore stand
  in full.
- **P1a = P1b = P1c = 0 exactly**, across 168 translation-class rows, on the new grid. (The
  offset spread is 7.1e-15, the same round-off as above.)
- **No search ran.** All 13 integrity rows compare cached searches at the same cutoff with
  `best_params_equal` and `objective_equal` True; the run took 3,405 s against a single 24-trial
  search's ~3.5 h.
- **Populations unchanged:** common 2,045 events, 138 high-risk, at both horizons.
- **Integrity:** 9,900 decision rows (4,884 × 75/37 thresholds, exactly as the grid growth
  predicts), 0 NaN, 0 inf, alert counts consistent everywhere.

**1. The grid.**

| | 2-day | 3-day |
|---|---|---|
| thresholds | 37 (was 18) | 38 (was 19) |
| range | [−30.957, **+2.866**] (was [−30.957, −6.000]) | [−30.221, **+6.882**] (was [−30.221, −6.000]) |
| contributed by bound percentiles only | 19 | 19 |
| above −6 | 3 (was 0) | 4 (was 0) |

The grid now has resolution above −6, but **sparsely**: the pooled bounds' 5th–95th percentile
range still lies mostly below −6, so only 3–4 grid points sit above it.

**2. Ceiling pinning — fixed for the primary read-out, worse for the rule-weighted one.**

| read-out | arm | now | was |
|---|---|---|---|
| `selected_on_self_test` | bound | **26.9%** | 62.7% |
| `selected_on_self_test` | point | **0.0%** | 29% |
| `selected_on_self_test_rule_weighted` | bound | **69.4%** | 62.0% |
| `selected_on_self_test_rule_weighted` | point | **66.7%** | 79% |
| `oracle_on_official_test_grid` | bound | 10.2% | 13% |
| `unrestricted_oracle_on_official_test` | any | 0.0% | 0% (grid-independent) |

- The **primary deployable read-out is repaired**: bound pinning fell from 62.7% to 26.9% and
  point pinning to zero.
- The **rule-weighted variant is not**. Its optimum wants a threshold *above* the extended grid's
  maximum, so the censoring moved from −6 up to the new ceiling rather than disappearing. Bound
  selections now land above −6 in 70.1% of 2-day and 83.3% of 3-day cases, with median selected
  threshold −0.960 (2 d) and +6.882 (3 d — the grid maximum itself). **This is a real residual
  limitation, not a fixed one**, and it is disclosed rather than corrected post hoc.

**3. The quantity the ceiling was destroying now measures something.** "Threshold shift vs point",
deployable, 10:1: originally *every* 2-day GBM bound reported exactly +2.562 — one
ceiling-determined value. Now the shifts are dispersed: 14 distinct values spanning
[+1.930, +13.356] at 2 d (median +7.103) and 15 spanning [+4.552, +13.841] at 3 d (median
+9.570). The GBM bounds alone span +1.93 to +11.25 at 2 d. The instrument now reflects Q.

**4. What did NOT change in the substantive story.**
- **Best achievable cost (unrestricted oracle, point arms, 5:1/10:1/20:1) is identical** to the
  2026-09-19 entry, as P1c requires: persistence 178/283/409 at 2 d and 246/361/572 at 3 d;
  learned models at least 476/560/660 at 2 d and at least 558/706/831 at 3 d.
- **Persistence still dominates.** It is the cheapest arm at both horizons, every cost ratio, on
  both the deployable and the unrestricted-oracle read-outs (the sole variation: at 2 d, 20:1 the
  cheapest deployable arm is persistence's *two-sided split-conformal bound*, 611, rather than its
  point prediction).
- **Every cost is still higher at 3 days.**
- **Lowest deployable cost at 10:1 is unchanged**: persistence point, 358 [255, 472] at 2 d and
  392 [292, 500] at 3 d — both select −6, which was in both grids.

**5. What DID change.**
- **The best learned arm at 3 days changed identity**: previously GBM weighted two-sided,
  924 [771, 1086]; now **GBM CQR one-sided, 938 [763, 1120]** at t = −6.731. At 2 days it is
  unchanged (GBM CQR two-sided, 501 [373, 633], t = −6.000).
- **Deployable cost change vs own point prediction** shifts slightly where the point arm's own
  selection un-pinned: 2-day GBM CQR two-sided −834 [−1020, −652] (was −829 [−1014, −647]);
  2-day GBM CQR one-sided −528 [−681, −382]. The 3-day GBM CQR one-sided figure is unchanged at
  −359 [−496, −233].
- Persistence's two-sided bounds now select the grid maximum and buy very low misses at extreme
  burden (2 d: 7.0 missed for 471 unnecessary; 3 d: 11.0 for 719) — behaviour the old grid could
  not express.

**6. Known defect in the rendered artifacts.** The caveat sentence stamped on this run's tables
and figures still reads "compared on ONE grid defined in point-prediction space", which the
extension made untrue. The string was corrected in code after the run; **the currently rendered
`05c_threshold_analysis.html` and both figures carry the stale wording**. No number is affected —
only that sentence. Re-rendering costs a full re-run (~57 min of refitting) and was not done
unilaterally.

**Explicitly NOT decided here (Sidh's):**
- whether the residual rule-weighted censoring (69.4%) warrants a further grid extension, and if
  so under what new pre-registration — noting that a grid reaching high enough for that read-out
  approaches "never alert";
- whether the 3-day best-learned-arm change alters any intended manuscript claim;
- whether to spend a re-run correcting the stale caveat on the rendered artifacts;
- the framing of the lead-time effect and of persistence's dominance;
- anything in E17–E18.

Execution stops at this checkpoint.
**Reported by:** Claude Code.


### 2026-09-21 — Grid-extension outcome accepted: the asymmetric fix stands, residual censoring is a finding, the caveat fix rides along

**Status:** RESOLVED by Sidh (2026-09-21), recorded by Claude Code. Closes the four items left open
by the 2026-09-20 extended-grid findings entry. No new run, no new experiment, no change to any
number.

**1. The residual rule-weighted censoring is a FINDING, not a defect to be engineered away.**
The extended grid repaired the primary deployable read-out (bound pinning 62.7% → 26.9%) but the
rule-weighted variant rose to 69.4%. **Decision: no further grid extension.** This is recorded as
an honest result about that selection criterion, not as an instrument fault.

What the data supports, stated precisely:
- Of the 108 rule-weighted bound-selection rows (common population, nominal 90%), **69.4% select
  the grid maximum** (+2.866 at 2 d, +6.882 at 3 d).
- At that pinned threshold the **median** pinned arm issues **5.3 alerts of 2,045 events (0.26%)**
  at 2 d and **0.7 of 2,045 (0.03%)** at 3 d, missing **137 of 138** and **138 of 138** high-risk
  events respectively. For the majority of pinned arms, this criterion's cost-minimizing threshold
  therefore sits at or beyond the point where the rule effectively **stops alerting at all**.
- **The exact optimum is not located and is not claimed.** It lies at or beyond the extended grid's
  maximum; where beyond, if anywhere, this grid cannot say. The statement on record is a direction
  and a bound, not a value.
- **The behaviour is not uniform across arms.** Persistence's two-sided bounds are the exception:
  at the same pinned threshold they still alert 602–771 times at 2 d and 846–992 at 3 d, because
  their conformal quantile is large enough that many bounds exceed even +6.882. (This is not a
  positivity artifact — `n_unsupported` is 0 at both horizons, so no arm is forced to alert by the
  Q-SEL-03 `+inf` convention.)

**Rationale.** Extending the grid until this criterion's optimum falls strictly inside it would mean
extending toward "never alert", at which point the grid would be chasing a degenerate optimum rather
than measuring a decision rule. The informative result is that the rule-weighted criterion *wants*
that corner on this population — which is itself a statement about how poorly the bounds rank
high-risk events — not that the grid is too short.

**2. The 3-day best-learned-arm identity change is a second-order detail.**
At the original grid the cheapest deployable learned arm at 3 days was GBM weighted two-sided,
924 [771, 1086]; at the extended grid it is GBM CQR one-sided, 938 [763, 1120] (t = −6.731). Their
intervals overlap almost entirely. **Decision: logged as a narrow factual note, reported as such in
the manuscript, and not opened as its own investigation.** It does not touch the headline claim —
persistence remains the cheapest arm at both horizons, at every cost ratio, on both the deployable
and unrestricted-oracle read-outs — and the 2-day best learned arm is unchanged.

**3. The stale caveat string is display-only and its fix rides along.**
The sentence "compared on ONE grid defined in point-prediction space" became untrue when the grid
was extended. It is stamped on the tables and figures rendered by the 2026-09-20 run. **Confirmed:
it affects no computed quantity — it is presentation text only.** It was corrected in code in
`cd01ffe`. **Decision: no dedicated re-render.** The correction propagates into the rendered
artifacts at the next re-render this project performs for its own reasons. Until then the rendered
`reports/05c_threshold_analysis.html` and both `e15c_operating_curves_h*d` figures carry the stale
wording, and that is known and accepted rather than overlooked.

**4. Cross-experiment synthesis extended to a fifth manifestation.**
The whole grid-ceiling episode — diagnosis, pre-registered fix, and the partial, asymmetric outcome —
is logged as the **fifth** manifestation of the Phase-2 train/test high-risk imbalance, joining
point-prediction collapse (E6/E7), conditional-coverage collapse (E14), matched-budget ranking
collapse (E15), and the original grid-instrument distortion. Recorded in full in the Observations
Log entry of 2026-09-20, updated on this date. **Flagged explicitly as strong material for the
manuscript's discussion section.**

**Explicitly still NOT decided:** the framing of the lead-time effect and of persistence's
dominance; whether the two-sided CQR result enters the manuscript; anything in E17–E18, which remain
unstarted and unscoped.

**Decided by:** Sidh (2026-09-21), recorded by Claude Code.


### 2026-09-21 — E17 H1 scoped to persistence / GBM / GRU; MC-dropout (E8) excluded, disclosed

**Status:** RESOLVED by Sidh (2026-09-21), recorded by Claude Code **before E17 is re-launched and
before any E17 number exists**. Surfaced by the §13 loop when the first E17 launch blocked.

**1. What surfaced.** E17's first launch stalled for ~30 minutes on "seed 42: fitting base
learners". Process evidence (PID alive, 0.99 cores busy) showed it was computing, not hung: the
base configuration's MC-dropout search cache
(`e8_mcdropout_00d1cb2ddd3bf10c_seed42.json`) **does not exist**, so `base_predictions` had begun
a full 24-trial hyperparameter search (~3.5 h). The run was stopped rather than allowed to
complete. The pre-launch check that should have caught this verified the two **horizon-derived**
configs E15 used (`02b75edb…`, `347d68f9…`), not the **base** config (`00d1cb2d…`) E17 runs on.
That was a checking error, recorded here rather than quietly fixed.

**2. Why the missing cache is not merely a cost problem.** E8's published results were produced
under an **older config hash**; the configuration has since gained the `decision_cost` and
`threshold_analysis` blocks, which changes the hash. Re-searching under the current hash would
select MC-dropout hyperparameters **that E8 never used**, so E17's "E8 Bayesian" arm would be a
different fitted model from the one E8 reported. Every cross-reference between E17's robustness
result and E8's own findings would then be comparing two different models while appearing to
compare one. The 3.5 hours is the visible cost; the silent loss of like-for-like comparison is
the real one.

> **[ANNOTATION 2026-10-01 — item 2's rationale was unsupported]** Item 2's claim that a search
> under the current hash "would select MC-dropout hyperparameters that E8 never used" was asserted
> by Claude Code without evidence, and the project's own record contradicts it for this very arm:
> the 2026-09-18 E15 findings entry records that a config-hash change re-ran the GBM, GRU **and
> MC-dropout** searches and "all three reproduced every earlier cache bit-for-bit, `best_params`
> and objective alike". The defensible fact is only that **no MC-dropout cache exists under the base
> hash `00d1cb2d…`**, so including the arm would have required a fresh ~3.5 h search, which was not
> run. The exclusion decision (item 3) is Sidh's and is not changed by this annotation; the same
> unsupported sentence remains in `robustness_runner.H1_EXCLUSION_REASON`,
> `e17_h1_excluded_learners.csv` and the E17 report §2a. See the 2026-10-01 record-annotation entry,
> item 2.

**3. Decision.** H1's robustness checks — the mission-level cluster bootstrap (Q-STAT-03c), the
clipping-cap confirmation (Q-SEL-03) and the multiple-comparison policy check (Q-STAT-04) — are
scoped to **persistence, GBM and GRU only**. **MC-dropout / E8 is excluded from E17's H1.**

**4. This is a disclosed scope boundary, not a silent gap.** The exclusion and this reason must be
stated explicitly in the E17 report itself, not only here. A reader of the robustness supplement
must be able to see that the Bayesian arm was not checked, and why, without consulting this log.

**5. What is unaffected.**
- **H2** (one-sided CQR coverage backfill) needs the GBM quantile heads only — no E8 dependency.
- **H3** (five-manifestation shared-mechanism test) uses the GBM point residual — no E8 dependency.
- **Nothing already published changes.** E8's own results stand exactly as reported; this decision
  governs only which arms E17's robustness checks cover.
- The Gate-2 headline contrast, the project's only formally tested result, is **persistence**,
  which has no hyperparameters and requires no search at all. It is inside the retained scope.

**6. Verification required before re-launch.** The cached hyperparameters for every **included**
learner must be verified against the current config hash explicitly — the check that was skipped
for E8 — and the verification reported in the E17 checkpoint. "Included learner" means GBM
(`e6_gbm`) and GRU (`e7_sequence`); persistence has no search to verify, which is itself to be
stated rather than glossed.

**7. Implementation consequence.** Reporting only three learners is not sufficient: the shared
`base_predictions` fits all four regardless of what is reported, so it would still trigger the E8
search. The included-learner set must be pushed down into the fitting call so the E8 search is
never reached. Anything less would re-run the search and merely hide it from the output.

**Decided by:** Sidh (2026-09-21), recorded by Claude Code before execution.


### 2026-09-21 — CORRECTION: E17's coverage-restoration criterion is the one-sided guarantee (coverage ≥ nominal), not CI-containment

**Status:** RESOLVED by Sidh (2026-09-21), recorded by Claude Code **before the E17 report is
rendered**. A specification correction, made after the E17 computation had run.

**1. The bug.** E17's implementation labelled a cell "restored" when the rule-weighted arm's
confidence interval **contained** the nominal level and the naive arm's did not. That was a
**specification bug, not a legitimate alternative reading.** Conformal prediction's guarantee is
**coverage ≥ 1 − α — a one-sided bound.** An arm that over-covers is conservative and *satisfies*
the guarantee; only under-coverage violates it. CI-containment treats an interval lying entirely
above nominal as a failure, which the guarantee never does. A conservative result must never be
marked a restoration failure.

**2. The corrected criterion, stated operationally.** A cell is **RESTORED** when:
- the **naive** arm's CI upper bound lies **below** nominal — under-coverage is statistically
  established; **and**
- the **rule-weighted** arm's CI upper bound lies **at or above** nominal — under-coverage can no
  longer be established.

If the naive arm's CI upper bound is already at or above nominal, the cell is **"no deficit to
restore"**, which is a different statement and is never reported as a success.

The test is made on the CI's upper bound, not the point estimate, deliberately. Both bootstrap
schemes share one point estimate, so a point-estimate criterion would make H1's
iid-versus-cluster comparison vacuous: it would agree 9/9 by construction and test nothing.

**3. What changed and what did not.** **No result computation changed.** The coverage estimates
and CI bounds were computed once, by the 2026-09-21 E17 run (2,873.2 s), and are reused unchanged.
Only the rule for which pre-existing quantity defines "restored" changed. The E17 report is
rendered from those already-computed tables; the analysis is not re-run.

**4. The Gate-2 headline under each criterion.** Persistence, two-sided, nominal 90%:
naive 0.8579; rule-weighted **0.9262**.

| scheme | naive CI | weighted CI | CI-containment (original) | coverage ≥ nominal (corrected) |
|---|---|---|---|---|
| iid | [0.8426, 0.8736] | [0.9151, 0.9372] | not restored | **RESTORED** |
| cluster | [0.8332, 0.8776] | [0.9087, 0.9397] | not restored | **RESTORED** |

- The original implementation reported the headline as **failing**, under both schemes, purely
  because the weighted arm over-covers.
- Under the corrected criterion, H1's cluster-bootstrap robustness check for the Gate-2 headline
  **PASSES**. The verdict is the same under both resampling schemes.
- This is **strong restoration, not a width artifact.** The weighted CI lies entirely above
  nominal under both schemes (lower bounds 0.9151 and 0.9087), and the naive CI entirely below it.

**5. Scheme agreement across all nine learner × level cells** (persistence, GBM and GRU at 80, 90
and 95%, two-sided). Both criteria are applied and compared:
- **Corrected criterion: 8/9 agree.** The only disagreement is GBM at 80%.
- **Original CI-containment criterion: 6/9 agree.** It disagrees at GBM 80%, GRU 95% and
  persistence 80%.

**6. The remaining disagreement is a genuine fragility, reported as-is.** At **GBM, two-sided,
80%**, the verdict depends on the bootstrap scheme:

| scheme | naive CI upper | weighted coverage | weighted CI | verdict |
|---|---|---|---|---|
| iid | 0.7387 | 0.7828 | [0.7657, **0.7997**] | not restored |
| cluster | 0.7556 | 0.7828 | [0.7520, **0.8092**] | RESTORED |

**It is not rounded into either column.** Its mechanism needs stating, because it bears on how the
8/9 figure should be read:
- The weighted **point estimate, 0.7828, is below nominal under both schemes**.
- The cluster verdict flips to RESTORED only because its **wider** interval can no longer reject
  under-coverage — not because coverage improved.
- Under a criterion of the form "under-coverage cannot be established", a less precise interval
  makes RESTORED easier to reach. The cluster bootstrap is wider in 34 of 36 arms, so it leans
  toward RESTORED under this criterion.

The 8/9 agreement is therefore evidence that the conclusions do not *reverse* under clustering. It
is not evidence that every cell is strongly restored. The headline (item 4) is strong; GBM at 80%
is not.

**7. Reporting.** Both criteria appear in the manuscript-facing E17 output, side by side:
- the **corrected criterion is primary**;
- the **original CI-containment criterion is a labelled secondary comparison**, kept because it
  shows concretely why the distinction matters — the headline passes or fails depending on it.

**8. The H2 coverage-restoration matrix is unaffected.** Its four verdicts are identical under both
criteria, because every weighted arm there that fails still under-covers:
- split conformal two-sided: RESTORED (weighted CI upper 0.908 ≥ 0.90);
- split one-sided: not restored (0.869);
- CQR two-sided: not restored (0.874);
- CQR one-sided: not restored (0.863).

**H3 does not use the criterion at all.**

**9. Post-hoc discipline.** Two facts are recorded so a reader can weigh them.
- **Timing — disclosed, not hidden.** The correction was made **only after seeing** that the two
  criteria disagreed on the headline result. Before that, the containment criterion had been
  implemented without anyone noticing it contradicted the guarantee.
- **Justification — independent of the answer.** The criterion is fixed by the mathematical
  definition of the conformal guarantee, coverage ≥ 1 − α. That definition dictates this criterion
  whichever answer it produces, so the choice cannot have been reverse-engineered from the result.
  CLAUDE.md §3's prohibition on adjusting a procedure after seeing its result is upheld: this
  corrects a procedure that did not compute the quantity it was specified to compute.
- **Supporting check, from the data.** The correction changed **6 verdicts**. **All 6 are arms
  whose weighted coverage exceeds nominal** — exactly the class the containment bug mishandles:
  GRU 95% cluster; persistence 80% iid; persistence 90% iid and cluster; persistence 95% iid and
  cluster. **No under-covering arm's verdict changed.** A correction chosen for its answer would
  have no reason to respect that boundary; a correction of this specific bug must.

**Decided by:** Sidh (2026-09-21), recorded by Claude Code before rendering.


### 2026-09-21 — E17 robustness, consistency & gap-closure: the Gate-2 headline is robust; weighting restores 1 of 4 cells; H3 is circular and falls back to the honest null

**Status:** REPORTED by Claude Code. Measurement only, under the revised E17 specification, the
2026-09-21 H1 scope decision and the 2026-09-21 criterion correction.
- **Computation:** one run, launched 13:04 at `f53d27a`, 2,873.2 s total, 3 seeds (42/43/44),
  2,000 event-level resamples. Seed fits took 966.2 / 876.3 / 941.1 s. H1 took 28.0 s, H2 2.4 s,
  H3 1.3 s.
- **Report:** `reports/06_robustness.html` rendered with `kc robustness --from-tables` at
  `33440cd` plus the H3 disclosure. It **recomputes nothing**: it re-derives verdicts from the
  computed tables.
- **Tables:** `reports/tables/e17_*.csv`.

**0. Integrity.**
- **No search ran.** The GBM and GRU caches were verified against the **full** config hash, not
  the filename prefix — both match `00d1cb2d…`, cutoff 2.0, seed 42, 24 trials, selected on
  `val_inner`. Persistence has no search. Seed 42's learners fitted in 5 min 10 s, with no `.tmp`
  cache write at any point.
- **The re-render changed no computed table.** All 7 computed tables are byte-identical (SHA-256)
  to the computing run's output.
- **The H2 matrix is bit-identical** to the computing run in every cell.
- **The render is clean:** zero error outputs.

**1. H1 scope.** H1 covers persistence, GBM and GRU. **MC-dropout / E8 is excluded** (2026-09-21
decision), and the report states the exclusion and its reason in its own §2a.

**2. H1 (i) — clustering assumption.** A mission-level cluster bootstrap over **18 missions** and
2,167 supported events; the largest mission holds 16.1% of events.
- The cluster CI is wider than the iid CI in **34 of 36 arms**; median width ratio **1.49**,
  range [0.77, 2.71].
- **Gate-2 headline (persistence, two-sided, 90%): RESTORED under both schemes.** Naive 0.8579,
  weighted 0.9262.
  - iid: naive [0.8426, 0.8736], weighted [0.9151, 0.9372].
  - cluster: naive [0.8332, 0.8776], weighted [0.9087, 0.9397].
  - **The weighted CI lies wholly above nominal under both schemes**, and the naive CI wholly below
    it. **H1's failure criterion — a headline conclusion reversing — is not met.**
- **Scheme agreement:** primary criterion **8/9** learner × level cells; secondary
  (CI-containment) criterion 6/9.
- **Fragility, reported as-is — GBM, two-sided, 80%:**
  - iid: weighted CI [0.7657, 0.7997] → not restored;
  - cluster: weighted CI [0.7520, 0.8092] → RESTORED.
  - The weighted point estimate, **0.7828, is below nominal under both schemes.** The verdict
    changes only because the cluster interval is wider and can no longer reject under-coverage.
- **What 8/9 means.** Because the cluster bootstrap is the wider scheme, it leans toward RESTORED
  under this criterion. So 8/9 shows conclusions do not *reverse* under clustering. It does not
  show every cell is strongly restored: the headline is strong, GBM at 80% is not.
- **The criterion correction changed 6 of 18 verdicts.** All 6 are over-covering arms, and all
  moved toward RESTORED. No under-covering arm changed.

**3. H1 (ii) — clipping cap.** Clipping **never triggers**, at k̂ triggers 0.7, 0.5 or 0.3. The
induced bias is zero. This confirms, rather than sweeps: k̂ never approached any trigger.

**4. H1 (iii) — multiple comparison.** Every committed table was swept for p-values: the family
has **exactly one member**, E11's McNemar p = 5.61e-45. **Holm is therefore the identity** and the
contrast is still rejected. The check confirms Q-STAT-04's policy was *adhered to*.

**5. H2 — the completed matrix** (GBM, nominal 90%; both criteria agree in all four cells):

| | two-sided | one-sided |
|---|---|---|
| **split conformal** | 0.836 → 0.896 **RESTORED** | 0.850 → 0.854 not restored |
| **CQR** | 0.865 → 0.859 not restored | **0.863 → 0.849 not restored** (new) |

- **Rule-weighting restores coverage in 1 of 4 cells:** two-sided split conformal only. **H2's
  hypothesis is confirmed.** The new cell is unambiguous: its weighted CI [0.833, 0.863] lies
  wholly below 0.90.
- **The machinery is valid; the failure is the shift.** On the exchangeable self-test split,
  one-sided CQR covers at every level, and each CI contains nominal:
  - 80%: 0.7881 [0.7712, 0.8043];
  - 90%: 0.8925 [0.8794, 0.9047];
  - 95%: 0.9433 [0.9333, 0.9523].
  So the official-test shortfall is attributable to selection bias, not to a miscalibrated
  quantile head.
- **Weighting moves one-sided CQR coverage *down* at every level:** 0.8159 → 0.7603 at 80%,
  0.8629 → 0.8486 at 90%, 0.9085 → 0.8879 at 95%. At 80% the naive arm had **no deficit** (CI
  [0.7989, 0.8320]); weighting **creates** one (CI [0.7418, 0.7782], wholly below). This matches
  the two-sided CQR cell, where weighting also lowers coverage.

**6. H3 — CIRCULAR by construction; the honest-null fallback applies.**
- **What was measured.** The candidate diagnostic is the per-event GBM residual d = y − ŷ.
  |point-biserial r| across M1–M3 runs 0.102 to 0.699, and pairwise overlap lifts 5.04× to 7.77×.
- **Why those numbers are not evidence.** Every event-level membership is **defined from d
  itself**:
  - **M1** is `d ≥ 90th percentile of d`, a threshold on d;
  - **M3** is `high-risk and ŷ < −6`, so every member has d > 0 by definition (its high-risk share
    is exactly 1.000);
  - **M2** is "uncovered by ŷ ± Q", i.e. |d| > Q.
- **The consequence.** The associations are consequences of these definitions, not evidence of a
  shared mechanism. As built, the test **cannot distinguish a shared mechanism from a shared
  definition**. M4 and M5 are instrument-level and have no per-event membership at all.
- **The outcome.** Per E17's failure criterion, this is reported as **"related in effect, not
  shown to reduce to one per-event mechanism"** — not as a unification. The report's §6 states
  the construction caveat before the numbers and repeats it in the summary.
- **Where the flaw originates.** The specification's own example diagnostic ("per-event prediction
  residual") is the one that produces the circularity, so the flaw is in H3's framing as much as
  in its implementation. It was caught at write-up, not by a test.

**7. Incidents in this batch, in order.**
1. The first launch began an unplanned E8 search, stopped at 30 min: the pre-launch check verified
   the wrong config hashes.
2. The notebook aborted with `StopIteration`: a duplicated p-value-column lookup.
3. The restoration criterion was mis-specified as CI-containment; corrected 2026-09-21.
4. H3's circularity was found at write-up.

Each is recorded where it happened. Items 3 and 4 were caught by reading results with suspicion,
not by tests.

**8. The deferred caveat-string fix is not propagated by E17.** E17 renders only
`06_robustness.html`, not `05c_threshold_analysis`, so this phase performs no natural re-render of
the stale artifacts. The code fix (`cd01ffe`) stands; propagation falls to E18's regeneration.

**Explicitly NOT decided here (Sidh's):**
- whether H3 should be redesigned around a diagnostic not used to define membership, or closed as
  the honest null;
- whether the completed matrix, and weighting's *adverse* effect on CQR, change any manuscript
  claim;
- how GBM at 80% is presented;
- anything in E18.

Execution stops at the E17 batch boundary.
**Reported by:** Claude Code.


### 2026-09-21 — E17 CLOSED: H3 honest null, one-sided CQR adverse effect confirmed, GBM@80% framing fixed, H1 criterion final

**Status:** RESOLVED by Sidh (2026-09-21), recorded by Claude Code. Closes the four items left open
by the 2026-09-21 E17 findings entry. No run, no new number.

**1. H3 is CLOSED as the honest null. No redesign.**
- The manuscript states the five-manifestation pattern (Phases 2–5) as a **qualitative,
  independently evidenced narrative**. Each manifestation was measured by a different experiment
  with its own method. The pattern is **explicitly not reduced to one shared quantitative per-event
  mechanism.**
- **Why the attempt failed: it was circular by construction.** The candidate diagnostic, the GBM
  residual d = y − ŷ, was definitionally bound to the memberships it was meant to predict:
  - **M1** is a threshold on d itself. Its association (r = 0.699) is tautological.
  - **Every M3 member has d > 0 by construction.** The high-risk condition gives y ≥ −6 and the
    membership condition gives ŷ < −6. So its association (r = 0.529) is a sign constraint, not a
    finding.
  - **M2** is defined by the per-seed magnitude |y − ŷ| exceeding Q. Its weak association with
    signed d (r = 0.102) is uninformative, not contrary evidence.

  So two of the three associations are definitional artifacts, and the third measures the wrong
  functional of the same residual.
- **Precision on "determined".** Signed d fully determines only M1. It constrains M3's sign
  without determining M3 membership, which also needs y and ŷ separately. The 2026-09-21 findings
  entry's "every event-level membership is defined from d itself" is tightened accordingly.
- **Disclosure rule.** The circularity is disclosed. The correlation and lift figures are **never**
  reported at face value as evidence of shared mechanism.

**2. Weighting's adverse effect on one-sided CQR coverage is CONFIRMED as a manuscript-bound
finding.**

The finding, stated specifically:
- Rule-derived weighting **does not merely fail to restore** one-sided CQR coverage. It **actively
  lowers** it at every nominal level:
  - 80%: 0.8159 → 0.7603 (−5.55 pp);
  - 90%: 0.8629 → 0.8486 (−1.43 pp);
  - 95%: 0.9085 → 0.8879 (−2.06 pp).
- **It creates a new deficit at 80%.** The naive arm had none there (CI [0.7989, 0.8320], upper
  bound at or above nominal). The weighted arm's CI [0.7418, 0.7782] lies wholly below nominal.
- **Robust to seed.** Weighting lowers coverage in **9 of 9** (level, seed) cells.
- **Structural, not sampling noise.** Both arms share one quantile head and differ only in the
  calibration quantile Q, and coverage is monotone in Q. Lower coverage in every cell therefore
  implies a lower weighted quantile in every cell. This is a logical consequence of the
  construction; *why* the rule weights pull Q down is not claimed.

**Correction to the framing as given.** The decision as dictated contrasted this with a "no
effect" characterisation of two-sided CQR. **The record does not support that contrast.**
- Weighting lowers **two-sided** CQR coverage at every level as well:
  - 80%: 0.7736 → 0.7574 (−1.62 pp);
  - 90%: 0.8653 → 0.8593 (−0.60 pp);
  - 95%: 0.9220 → 0.9083 (−1.37 pp).
- E12's own entry already recorded "weighted <= naive at every level".

The distinction that does hold, and is recorded in its place:
- **the one-sided decreases are larger at every level;** and
- **only in one-sided CQR does weighting create a deficit where the naive arm had none.** At 80%,
  two-sided naive already under-covers (CI upper bound 0.7910 < 0.80), so there weighting deepens
  an existing deficit rather than creating one.

The one-sided finding is therefore sharper in degree and in kind than the two-sided one — but not
"adverse versus no effect". **This contrast is recorded as the data show, pending Sidh's
confirmation of the corrected wording.**

**3. GBM @ 80%: the cluster-bootstrap flip is framed as a wider interval failing to reject
under-coverage.**
- **Not "coverage improved".** The weighted point estimate, **0.7828, is below nominal under both
  bootstrap schemes.**
- The cluster verdict reads RESTORED only because the cluster interval is wider:
  - cluster: weighted CI upper bound 0.8092;
  - iid: weighted CI upper bound 0.7997.
- The manuscript **preserves this distinction.** It must not collapse the cell to a pass/fail
  verdict.

**4. The corrected H1 restoration criterion is FINAL.**
- The criterion is coverage ≥ nominal, tested on the CI upper bound. It stands.
- **Gate 2's headline is confirmed robust to the clustering assumption:** persistence, two-sided,
  90% is RESTORED under both the iid and the mission-level cluster bootstrap, with the weighted CI
  wholly above nominal under both.

**E17 is closed.**

**Decided by:** Sidh (2026-09-21), recorded by Claude Code. Item 2's two-sided contrast is recorded
as corrected against the data, and awaits Sidh's confirmation.


### 2026-09-21 — E17 item 2 confirmed; METHODOLOGICAL NOTE: validity under shift vs exactness on exchangeable data

**Status:** RESOLVED by Sidh (2026-09-21), recorded by Claude Code.
- **Part A** confirms the corrected wording of E17 item 2.
- **Part B** is a **standing methodological note**, written for future work to consult before
  writing any check that turns a coverage estimate into a verdict. It records the pre-E18 audit in
  full.

---

**Part A — E17 item 2: the corrected wording is CONFIRMED as the manuscript-bound framing.**

1. **Weighting lowers CQR coverage in both arms, at every level.**
   - Two-sided: −1.62 / −0.60 / −1.37 pp at 80 / 90 / 95%.
   - One-sided: −5.55 / −1.43 / −2.06 pp.
2. **One-sided CQR is hurt more, at every level.**
3. **Only one-sided CQR gains a deficit it did not have.** At 80% its naive CI [0.7989, 0.8320]
   shows no deficit, and its weighted CI [0.7418, 0.7782] lies wholly below nominal. Two-sided
   naive already under-covers there, so weighting deepens an existing deficit.
4. **The shared-quantile-head implication is stated; no untested cause is asserted.** Both arms
   share one quantile head and differ only in the calibration quantile Q, and coverage is monotone
   in Q. So lower coverage in a cell implies a lower weighted quantile in that cell. The effect
   holds in 9/9 (level, seed) cells. Why the rule weights lower Q is not claimed.

---

**Part B — METHODOLOGICAL NOTE: which form a coverage check must take.**

**B1. The distinction.** A check that turns a coverage estimate into a verdict answers one of two
different questions. They need different mathematical forms.

| question | where it arises | what theory guarantees | correct form of the check |
|---|---|---|---|
| **Validity under shift** — does the method meet its guarantee? | official (selection-biased) test set | coverage **≥ 1 − α** — a **one-sided** bound | CI **upper bound ≥ nominal**: under-coverage not established. Over-coverage passes. |
| **Exactness on exchangeable data** — is the implementation right? | exchangeable self-split, unweighted | coverage ∈ **[1 − α, 1 − α + 1/(n+1)]** — a **two-sided** band | CI **contains nominal**. A deviation *either* way indicates a defect. |

**Sources for the two guarantees.**
- **The one-sided bound** (a lower bound on coverage) is the finite-sample guarantee of split
  conformal (Vovk, Gammerman & Shafer 2005; Lei et al. 2018). It carries over to weighted conformal
  under covariate shift (Tibshirani, Barber, Candès & Ramdas 2019).
- **The upper edge of the band** requires exchangeability and almost-surely distinct (continuous)
  scores. It is stated for split conformal in Lei et al. 2018 and for CQR in Romano, Patterson &
  Candès 2019.
- **Citation precision.** The papers are cited without theorem numbers, matching the project's own
  code; numbers that could not be verified are not stated.

**The upper edge is negligible here.** With n = 2,391 calibration events it is 1/(n+1) = 0.042 pp,
below the resolution of any CI in this project. "CI contains nominal" is therefore the exact band
test up to that slack.

**Three consequences that are easy to get wrong:**
1. **An interval's sidedness is not its guarantee's sidedness.** A *two-sided* interval
   [ŷ − Q, ŷ + Q] still carries a *one-sided* coverage guarantee, coverage ≥ 1 − α. Validity
   checks are one-sided **for two-sided intervals too.**
2. **Containment is the right tool for exactness, not for validity.** Applied to a validity
   question, it marks a conservative, over-covering method as a failure. The guarantee never does.
3. **The two forms can disagree only on the lower side.** Both compare the CI's upper bound with
   nominal in the same way, so they differ only when the CI lies wholly *above* nominal. A knife-edge
   at the upper bound can never separate them.

**B2. The case that exposed the confusion (E17 H1, 2026-09-21).**
- **The error.** H1 defined "restored" by CI containment. That is the exactness form applied to a
  validity question.
- **Its effect.** It reported the Gate-2 headline as failing. Persistence, two-sided, 90% is
  0.8579 → 0.9262; the weighted CI [0.9151, 0.9372] lies wholly above nominal, so the containment
  form rejected it purely because the method is conservative.
- **The correction.** The one-sided form restores the headline under both bootstrap schemes. It
  changed 6 of 18 verdicts, all of them over-covering arms, and no under-covering arm.

**B3. The pre-E18 audit (read-only, 2026-09-21).** Every verdict-producing comparison in `src/` and
in the notebooks was inventoried and classified.

| check | location | question asked | form used | correct? | why |
|---|---|---|---|---|---|
| E17 H1 `restoration_verdict` | `robustness.py` | validity under shift | one-sided (since the correction) | ✓ | the case in B2, now fixed |
| E17 H2 matrix verdicts | `robustness_runner.py` | validity under shift | one-sided, same function | ✓ | shares H1's definition |
| E9 self-split "largest \|gap\|" | `03_conformal.ipynb` cell 8 | exactness | two-sided (abs) | ✓ | exchangeable, unweighted: the band applies |
| E12 self-test `ok`, `self_valid` | `03b_cqr.ipynb` cells 5, 13 | exactness | containment | ✓ | exchangeable, unweighted CQR: the band holds for CQR (Romano et al. 2019) |
| E15 `CQR_VALIDATED` | `05_decision_cost.ipynb` cell 7 | exactness | containment | ✓ | exchangeable, unweighted one-sided CQR; continuous scores, so the band applies |
| **E12 official-test `valid=`** | **`03b_cqr.ipynb` cells 7, 13** | **validity under shift** | **containment** | **✗ wrong form** | **the latent finding — see B4** |
| E9 / E10 / E11 / Gate 2 | `03_conformal.ipynb` cell 17 | — | no programmatic verdict | ✓ | signed gaps keep direction; the GO was a human reading |
| Gate 2 McNemar | `03_conformal.ipynb` cell 15 | change in coverage | two-sided exact binomial | ✓ | conservative for a directional claim; direction (148 vs 0) recorded separately |
| E8 `well_calibrated` | `02_baselines.ipynb` cell 23 | calibration of a Bayesian predictive | two-sided (±2 pp, PIT KS) | ✓ | MC-dropout carries no conformal guarantee; calibration is symmetric. All gaps are negative, so the verdict is the same under either form. |
| E14 representativeness | `labelnoise_runner.py` | does the M7 subset resemble the full set? | two-sided (\|Δprevalence\|, KS) | ✓ | representativeness is symmetric |
| E14 coverage | `labelnoise_runner.py`, `04_labelnoise.ipynb` | — | no coverage verdict | ✓ | signed gaps and trend slopes only |
| E3 Pc agreement | `00b_pc_spike.ipynb` cell 11 | reproduction | two-sided (±0.5 log10) | ✓ | reproduction error in either direction is error |
| E5 baseline match | `01b_baseline_validation.ipynb` cell 10 | reproduction | two-sided tolerance | ✓ | as above |
| E4 `meets(bar_pp)` | `power.py` | precision | CI half-width ≤ bar | ✓ | a magnitude; no direction |
| E15 P1a/b/c, rank classes | `threshold_runner.py`, `05b_rank_invariance.ipynb` | structural identity | equality / tolerance | ✓ | identities are symmetric |
| E1 recency rules | `00_data_audit.ipynb` cell 8 | data facts | equality / inequality | ✓ | no coverage guarantee involved |

**B4. The one latent finding.** `03b_cqr.ipynb` cells 7 and 13 label the E12 **official-test**
arms `valid=` by CI containment. That is the B2 error class. The arms concerned are naive CQR,
weighted CQR and the E11 split-conformal reference.
- **It is inert.** **0 of 9** official-test E12 verdicts differ under the correct one-sided form,
  at 80, 90 and 95%.
- **Why.** No official-test E12 arm has a CI wholly above nominal, and that is the only case
  (B1, consequence 3) in which the forms can disagree.
- **The rendered E12 report is correct in value.** Every printed `valid=` label is right. Only its
  code has the wrong form.
- **One apparent anomaly is not a discrepancy.** The E11 reference at 80% displays as
  [0.7648, 0.8000] yet reads "containment False". Its exact upper bound is 0.79999968 < 0.80, so
  both forms agree.
- **Fix:** 2026-09-21, commit `2355f8e`; see the entry directly below.

**B5. Rule for future checks.** Before turning a coverage estimate into a verdict, name the
question.
- **Validity under shift** → **one-sided**: CI upper bound ≥ nominal.
- **Exactness on exchangeable, unweighted data** → **two-sided**: CI contains nominal.
- **Calibration of a non-conformal predictive** → **two-sided**.
- **Reproduction or agreement** → **two-sided tolerance**.

Name the question in the code, not only in the prose. A check whose question is implicit is how
the B2 error went unnoticed until a result looked wrong.

**Decided by:** Sidh (2026-09-21), recorded by Claude Code.


### 2026-09-21 — E12 latent validity-form bug FIXED (`2355f8e`); E17 CLOSED

**Status:** DONE by Claude Code per Sidh's 2026-09-21 instruction. Closes the latent finding in
the methodological note above (B4). **No reported number or verdict changed.**

**1. The fix.** `03b_cqr.ipynb` cells 7 and 13 labelled E12's **official-test** arms `valid=` by
CI containment. That is the wrong form for a validity question.
- **Official-test arms** now answer **validity under shift**, one-sided:
  `robustness.meets_coverage_guarantee`, which checks CI upper bound ≥ nominal.
- **The self-test arm** keeps **exactness on exchangeable data**, two-sided:
  `robustness.consistent_with_exact_coverage`, which checks that the CI contains nominal. This was
  already correct and is unchanged in form.
- Both come from `conformal_runner.e12_coverage_checks`, which tags every label with its question
  and its form — B5's rule, applied in code. No inline containment test remains in the notebook.

**2. Reuse.** `restoration_verdict` answers a *two-arm* question (naive versus weighted); E12's
label is a *single-arm* one. Reusing it directly would have been misuse. Instead:
- the single-arm primitives it rests on were extracted;
- `restoration_verdict` and E12 now both call them.

So "valid" and "exact" each have exactly one definition in the project. The refactor preserves
behaviour: every E17 verdict re-derives identically from the committed tables.

**3. Verified against the committed E12 table** (read-only, at 80, 90 and 95%):
- **0 of 9** official-test labels changed;
- **0 of 3** self-test labels changed;
- the published 90% labels are reproduced exactly: naive invalid, weighted invalid, split valid,
  self-test exact.

This matches the audit.

**4. Regression test.** The test is built on the one case where the two forms differ, a CI lying
wholly above nominal. **It fails with the bug reintroduced and passes with the fix.** Under the
bug, only that test fails; the published-labels test still passes. That is the inertness made
concrete: the real data never over-covers, so only the synthetic case can catch this bug. A
companion test pins that the self-test arm stays two-sided.

**5. Re-render: NOT done — it is not cheap, and is left to Sidh.**
- `03b_cqr.ipynb` **recomputes E12** (`run_e12`, 3 seeds, GBM quantile heads and point model);
  it has no from-tables path. Its cells also need per-event width and adaptivity data that are not
  all persisted.
- **Estimated cost: ~20–35 min**, from the quantile-head fits measured this week and allowing for
  the established ~2× machine-speed variance. No search would run: the `e6_gbm` cache exists
  under the current hash.
- **It would re-run a published experiment under a newer config hash.** E12 ran under `eb89df79…`
  on 2026-09-11; a re-render would run under `00d1cb2d…`, overwriting the E12 tables that E17's H2
  matrix reads.
- **Reproduction is likely but unverified.** The GBM best parameters and objective are identical
  across the two hashes, and E15 showed the fits reproduce bit-for-bit. A re-run should still be
  checked against a pre-run snapshot, not assumed.
- **What it would change in the artifact: no value.** Only the wording of two printed headers
  would change, to name the one-sided and two-sided forms. Every `valid=` value in the current
  `03b_cqr.html` is already correct.

**6. E17 is closed.** H1, H2 and H3 are recorded; the four decisions and item 2's wording are
confirmed; the audit is logged as a standing note; the latent finding is fixed. Two stale rendered
artifacts remain, **both correct in every value**, and both are candidates for E18's regeneration:
- the E15 `05c` caveat sentence;
- the E12 `03b_cqr` header wording.

**Recorded by:** Claude Code.


### 2026-09-22 — E18 (final manuscript consolidation): deferred fixes verified, artifact set built, checklist revised, audit findings reported

**Status:** REPORTED by Claude Code, under the revised E18 specification (merged `bbbd8c7`). Parts A–D
executed in full. **No decision is taken here.** Part D's findings are reported, not fixed.

---

**Part A — the two deferred display fixes, both verified before anything was reused.**

**A.1 — E15's stale grid caveat (`e5501f2`).** No from-tables path existed, so one was built:
`threshold_runner.load_threshold_analysis` loads the 10 computed `e15c_*` tables exactly
(`float_precision="round_trip"`), checks them against the config (horizons, levels, populations,
extended grid) and refuses the original pre-extension grid; `kc decision --only threshold
--from-tables` re-renders displays only. Verified:
- all **10 computed tables byte-identical** before and after (SHA-256);
- the 8 derived display tables that changed differ **only** in the caveat — restoring the old caveat
  text into the new files reproduces each pre-render SHA-256 **exactly**;
- the stale sentence is absent from every non-smoke table and from the rendered report.
Recompute cost: zero. The `e15c_smoke_*` tables still carry the old caveat; they are a smoke run whose
numbers are explicitly not findings, and are not manuscript-bound.

**A.2 — E12's stale header, with snapshot verification first (`993f44a`).** `03b_cqr.ipynb` recomputes
E12, so it was re-run (~21 min) under config `00d1cb2d` where E12 originally ran under `eb89df79` at
`5422ccd`. **Before any number from the re-run was reused**, it was checked against a pre-run snapshot:
- `e12_coverage`, `e12_coverage_all`, `e12_cqr_selftest`, `e12_width_efficiency`, `e12_widths`:
  **byte-identical** (SHA-256) and **0 differing cells** under exact round-trip parsing;
- PNG figures byte-identical; PDFs identical apart from `/CreationDate`;
- the report's text differs only in the provenance stamp, the committed code, the new
  `e12_adaptivity` save (`dfb48a9`), and the two corrected header wordings.
E12 therefore reproduces bit-for-bit across a config-hash change, which is also the strongest
determinism evidence the project has (RP3).

---

**Part B — the manuscript artifact set (`e9ffc4e`, manifest `018465d`).**

`kc manuscript` builds **13 figures and 1 table** from the experiments' committed tables (plus the
frozen processed events, for E1's two histograms only), writing `reports/manuscript_figures/`,
`reports/manuscript_tables/`, `reports/manuscript_captions.md` and `reports/manuscript_manifest.json`.
Properties that are enforced in code rather than asserted:

- **Captions are generated from the data, and checked before they are written.** Every directional
  claim a caption makes passes a `_require` check against the source tables first, so a caption cannot
  state what the data does not show. Seven caption claims were tightened during review after reading
  them against the tables (e.g. "the rule-weighted version does not under-cover" → "its under-coverage
  is not established"; the E14 width caveat restated through table-backed widths; the E8 marginal-vs-
  conditional sentence corrected, because rule-weighted CQR fails the marginal guarantee too).
- **One definition per criterion.** All verdicts come from `robustness.meets_coverage_guarantee`,
  `consistent_with_exact_coverage` and `restoration_verdict`, so the manuscript cannot state a
  criterion differently from the experiment that computed it. E17's matrix verdicts are re-derived at
  build time and must match the committed table.
- **Exact reads.** Every table is read with `float_precision="round_trip"`.
- **The circular H3 statistics cannot be reached.** `Builder.table` refuses any `e17_h3_*` table; the
  five-manifestation table (T13) is qualitative, and a test asserts the prefix appears exactly once in
  the module (the guard itself).
- **Traceability or failure.** The build fails loud on any artifact without an experiment, a source
  table, an output file or a caption, and on any experiment whose computing commit cannot be
  established. E1 predates the repository, so its commit is traced to the initial commit `5a309ac` by
  checking at build time that that commit's `config/default.yaml` hashes to E1's recorded config hash;
  E17's from-tables sidecar names only its render (`33440cd`), so the computing commit is taken from
  this log (`f53d27a`) and every E17 table's SHA-256 is checked against that sidecar.
- **Determinism.** A test builds the whole set twice and requires byte-identical output, figures
  included; figure metadata carries no timestamps.
- **Two derivations are disclosed**, in the manifest and in the captions: Clopper–Pearson intervals for
  E8 (which recorded coverage and n but no interval; every implied k verified integral), and E1's
  histograms, drawn from the processed events after checking they reproduce E1's recorded counts.
- **One artifact is not regenerable and says so:** F02b carries the E8 run's calibration-audit figure
  verbatim, because E8's per-event predictive distributions were never persisted; rebuilding it needs
  an MC-dropout refit, which under the current hash requires a fresh 24-trial search.

Per the E18 spec: the completed 2×2 restoration matrix under the final criterion (F11), the
validity-vs-exactness explanatory figure (F12), and the five-manifestation narrative as a
**qualitative** table (T13) are all built; **no statistic of any kind was computed across the five
manifestations**, and no H3 table was read.

---

**Part C — `REVIEWER_CHECKLIST.md` substantively revised (`8870ae4`).**

Revised after reading the Phase 2–5 entries of this log in full. M5, EV2, EV3, M4 and X4 were rewritten
around the evidence that now exists; M1 was confirmed and **re-framed as a weaker position than
drafted** (the two weight specifications disagree by γ̂ ≈ 1.04e6, so the planned "agreement proves
completeness" defense is unavailable and is no longer made); a new item **M8** was added for the
question the completed matrix invites ("your correction works in 1 of 4 cells, and sometimes makes
coverage worse"). Stale references were corrected throughout: E13 removed from EV3/T2/X1 (dropped at
Gate 1), X3 no longer cites E16 or claims coverage validity across lead times, M1 no longer attributes
weight-specification robustness to E17, and figure items now name the built artifacts. Two drafted
defenses were found to be rhetorical and are now marked **[OPEN]** rather than left standing: the
`kc reproduce-all` one-command path (does not exist) and cross-validation of the Pc engine against an
independent reference implementation (never performed).

**Triage re-ranked:** M8 and EV3 enter the top five on new evidence; S1 and N1 leave it (the power
analysis ran before modeling and is reported as ±5.13 pp, the only underpowered analysis was dropped
rather than reported weakly, and the venue tier is locked at Q2 with a boundary condition now reported);
M5 stays at #1 because the margin turned out far larger than "barely"; M1 rises on increased risk; M3
falls to #5. The re-ranking is an analysis offered for review, not a decision.

---

**Part D — final consistency audit (read-only).**

Swept this log, `EXPERIMENT_PLAN.md`, `README.md` and the Part B artifact set for any number or
characterization predating the final H1 criterion correction (2026-09-21) or the item-2 CQR correction.

**The manuscript-bound artifact set is clean.** No stale number reached it: every figure and table is
re-derived from the current committed tables under the final criterion, containment appears only in F12
where it is the subject, and no E13/E16 reference survives. The audit's stop condition was therefore not
triggered. The findings below are in the record, the governing documents or the code — **none is fixed
here.**

1. **Pre-correction characterization of the CQR weighting effect (not annotated).** The 2026-09-16 E12
   disposition entry describes "a small, directionally consistent … negative effect". The confirmed
   2026-09-21 wording is sharper: weighting lowers coverage in **both** arms at **every** level
   (two-sided −1.62/−0.60/−1.37 pp; one-sided −5.55/−1.43/−2.06 pp), the one-sided decreases are larger
   at every level, and only one-sided CQR gains a deficit it did not have. "Small" does not describe
   −5.55 pp.
2. **The one-sided non-restoration statement has no per-level breakdown, and at 80% the final criterion
   says something different.** The Gate 2 entry, the 2026-09-16 cross-experiment synthesis and
   `README.md`'s Gate 2 line all state that weighting "does not restore" one-sided coverage for GBM,
   GRU and MC-dropout. Under the final criterion, applied per level: at 90% and 95% that is right
   (6 of 9 cells "not restored"); **at 80% the naive arm has no deficit to restore (its CI upper bound
   is at or above nominal) and the weighted arm's CI lies wholly below nominal** — GBM 0.821 → 0.759,
   GRU 0.821 → 0.763, MC-dropout 0.809 → 0.762. That is weighting *creating* a one-sided deficit, the
   same pattern confirmed for one-sided CQR in item 2 of the E17 close-out, and it is not recorded
   anywhere. Surfaced by building F05. The figure and its table state the per-level verdicts as the data
   give them; the record was not edited.
3. **Containment-form wording survives in the governing documents for a validity question.**
   `EXPERIMENT_PLAN.md` E11 states the hypothesis as restoring coverage "to statistically
   indistinguishable-from-nominal" and the success criterion as "statistically restored to nominal";
   `PROJECT_KNOWLEDGE.md` S1 sets "within ±[margin] of nominal". These are the two-sided exactness form
   applied to validity under shift — the exact bug class corrected on 2026-09-21. Read literally, the
   project's own primary result (persistence, +2.6 pp over-coverage) would count as a failure. Gate 2's
   GO already treated over-coverage as valid ("conservative but valid"), so the substance is consistent;
   only the wording was never revisited. E9's hypothesis uses the same phrasing and is **correct** there,
   because exactness on the exchangeable self-split is genuinely two-sided.
4. **An unsupported rationale, stated by Claude Code and carried into the record and the code.** The
   MC-dropout exclusion from E17 H1 is justified as: "running a fresh search would select hyperparameters
   E8 never used" (`robustness_runner.H1_EXCLUSION_REASON`; the 2026-09-21 H1 scope entry, item 2; the
   E17 report §2a). **This project's own evidence contradicts it for this very arm:** the 2026-09-18
   E15 entry records that a config-hash change re-ran the GBM, GRU **and MC-dropout** searches and "all
   three reproduced every earlier cache bit-for-bit", and E14 recorded the same for GBM
   (`best_objective_value` 23.801101479171347). The defensible fact is narrower and is what the
   manuscript artifact states: no MC-dropout cache exists under the current config hash, so including
   the arm would have required a fresh ~3.5 h search, which was not run. The exclusion decision itself
   is Sidh's and is unaffected; only its stated reason is wrong.
5. **A rounding imprecision that predates all of the above.** E9's own report prints the largest
   two-sided |gap| on the self-split as **1.18 pp**; this log records "~1.1 pp" and the Gate 2 entry
   "≤1.1pp". F03 prints 1.18 pp, from the table.
6. **Hardcoded historical numbers in a rendered report.** `05c_threshold_analysis.ipynb` §7b prints
   "was 62.3% / 54.2%" as literals (CLAUDE.md §10 forbids hardcoding a computed number into a report).
   They are no longer regenerable: the extended-grid run overwrote `e15c_selection`, so reproducing them
   requires re-running E15 at `c9f423f`. The same figure is therefore deliberately **not** printed in
   T13 row 4, which states only what the current tables support.
7. **Documented CLI surface does not match the implemented one.** `CLAUDE.md` §12 and
   `SOFTWARE_ARCHITECTURE.md` §2 name `kc train`, `kc evaluate` and `kc reproduce-all`; the implemented
   commands are `ingest, audit, baselines, power, baselines-phase2, conformal, labelnoise, decision,
   robustness, manuscript`. `README.md` already states that `kc reproduce-all` is not implemented; the
   two governing documents do not.

Also checked and **consistent, no action**: the 62.3% / 62.7% pair (pooled across the two deployable
read-outs vs the primary read-out alone); Gate 2's "+2.6pp (conservative but valid)"; the E17 findings
entry's 6/9 containment figure (explicitly labelled as the superseded criterion); the ceiling-pinning
fractions, which recompute from `e15c_selection` + `e15c_grid` to 26.9% / 69.4% / 10.2% / 0.0% exactly as
recorded.

---

**Explicitly NOT decided here (Sidh's):** whether and how to annotate the record for Part D items 1–7;
whether the 80% one-sided finding (item 2) changes any manuscript framing, and whether it belongs with
the CQR one-sided finding as one result or stays separate; whether the governing documents' coverage
wording (item 3) is revised to the final criterion; whether to implement `kc reproduce-all`, perform the
clean-machine reproduction, build the related-work comparison table, or cross-validate the Pc engine
(the four open vulnerabilities now listed in `REVIEWER_CHECKLIST.md`); the revised triage ranking; and
anything about manuscript drafting, which has not begun. Execution stops at the E18 boundary.

**Reported by:** Claude Code.


### 2026-10-01 — Record annotations for E18 Part D items 1–7; unified one-sided framing; two vulnerabilities recorded OPEN

**Status:** RESOLVED by Sidh (2026-10-01 instruction), recorded by Claude Code. **Append-only:** no
historical text was edited or deleted. Each item below is also annotated in place, beside the text
it qualifies, as a dated `[ANNOTATION 2026-10-01]` block. **No code, table, figure or report changed.**
Every number below is read from a committed table, named in place.

**1. One-sided split conformal at 80% — the same pattern as one-sided CQR; unified framing.**
Under the final criterion (coverage ≥ nominal, tested on the CI upper bound), at 80%, the naive
one-sided arm has **no deficit to restore**, and the rule-weighted arm's CI lies **wholly below
nominal** for every learned model (`e15_bound_coverage_table`, all-supported, n = 2,167, 3 seeds,
95% CP):

| learner | naive | weighted | change | verdict |
|---|---|---|---|---|
| GBM | 0.8210 [0.8041, 0.8369] | 0.7590 [0.7404, 0.7768] | −6.20 pp | no deficit to restore; weighted wholly below |
| GRU | 0.8210 [0.8041, 0.8369] | 0.7631 [0.7446, 0.7809] | −5.78 pp | no deficit to restore; weighted wholly below |
| MC-dropout | 0.8091 [0.7919, 0.8255] | 0.7623 [0.7438, 0.7801] | −4.68 pp | no deficit to restore; weighted wholly below |

The verdicts were re-derived with `robustness.restoration_verdict` and are identical under the
table's bootstrap intervals. This is the **same pattern** as one-sided CQR (E17 close-out, item 2;
`e17_h2_coverage`: naive 0.8159 [0.7989, 0.8320] → weighted 0.7603 [0.7418, 0.7782]).

**Unified manuscript framing (Sidh):** *for one-sided bounds, rule-weighting never restores
coverage, and at 80% it creates a deficit.* The record supports both halves. Across all 12 one-sided
cells on the official test set (split conformal: GBM, GRU and MC-dropout × 80/90/95%; CQR: GBM ×
80/90/95%), **0 are restored**. At 80%, **all 4** learner × method cells move from no deficit to a
weighted CI wholly below nominal. At 90% and 95% the naive arm already under-covers and the weighted
arm still does (8 of 8 cells). The framing describes non-restoration, not uniform harm: at 90–95%
the weighted point estimate is sometimes higher than the naive one (e.g. GBM 95%, +2.12 pp), but
never high enough for under-coverage to stop being established. Persistence stays excluded from
one-sided claims (degenerate zero-atom, Gate 2). Contribution 1's exact-coverage claim stays
two-sided and is unaffected.

**2. MC-dropout exclusion rationale: the stated reason was unsupported.** The claim that "a fresh
search would select hyperparameters E8 never used" (2026-09-21 H1 scope entry, item 2;
`robustness_runner.H1_EXCLUSION_REASON`; `e17_h1_excluded_learners.csv`; E17 report §2a) is
contradicted by the 2026-09-18 E15 findings entry. That entry records that a config-hash change
re-ran the GBM, GRU **and** MC-dropout searches, and all three reproduced their caches bit-for-bit,
`best_params` and objective alike. **The defensible fact is only that no MC-dropout cache exists
under the base hash `00d1cb2d…`.** The exclusion decision is unchanged by this entry; whether it
stands is the subject of the E8 inclusion check pre-registered below.

**3. Superseded CQR wording.** The 2026-09-16 E12 disposition's "a small, directionally consistent
… negative effect" is **superseded** by the E17 item-2 wording confirmed on 2026-09-21: weighting
lowers CQR coverage in both arms at every level, the one-sided decreases are larger at every level,
and only one-sided CQR gains a deficit it did not have.

**4. Containment-style criterion wording in the governing documents.** `EXPERIMENT_PLAN.md` E11
(hypothesis "statistically indistinguishable-from-nominal"; success criterion "statistically
restored to nominal") and `PROJECT_KNOWLEDGE.md` S1 ("within ±[margin] of nominal") carry a dated
amendment, appended beside the original text, pointing to the final criteria:
- **validity under shift** — coverage ≥ nominal, tested on the CI upper bound;
- **exactness on exchangeable data** — the two-sided band, tested by CI containment of nominal
  (2026-09-21 methodological note, Part B).
The original wording is retained. E9's hypothesis is not amended; it is an exactness check, where
the two-sided form is correct.

**5. E9 exact figure.** The largest two-sided |gap| on the E9 self-split is **1.18 pp** (GBM at
80%, −1.1753 pp; `e9_machinery_validation`, F03), not "~1.1 pp" (2026-09-11 batch entry) or "≤ 1.1pp"
(Gate 2 entry). Found while annotating, not separately instructed: the Gate 2 entry's one-sided "gaps
≤0.8pp" is **0.82 pp** (GBM at 90%) per F03. It is recorded here; its in-place annotation is
combined with the 1.18 pp one.

**6. Hardcoded historical percentages in the 05c report.** `05c_threshold_analysis.ipynb` §7b prints
"was 62.3% … was 54.2%" as literals (introduced at `6e8debd`). They are **historical values from
the original-grid run at `c9f423f`**. They are **not regenerable from the current tables**, because
the extended-grid run overwrote `e15c_selection`. The notebook and rendered report are not changed;
correcting them requires a notebook edit and re-render, which is not instructed.

**7. Two vulnerabilities recorded OPEN, with no code changes.**
- **OPEN — `kc reproduce-all` is documented but not implemented.** `CLAUDE.md` §12 and
  `SOFTWARE_ARCHITECTURE.md` §2 name it; `README.md` already states it is absent.
- **OPEN — the Pc engine has never been cross-validated against an independent implementation.** Its
  validation is against analytic geometries and the challenge's own reported risk values (E3, the
  ±0.5 log10 tolerance) only.
Both are listed [OPEN] in `REVIEWER_CHECKLIST.md`. Neither is acted on here.

**Decided by:** Sidh (2026-10-01), recorded by Claude Code.


### 2026-10-01 — PRE-REGISTRATION: E8 inclusion check (MC-dropout search under the base hash), written BEFORE the search runs

**Status:** PRE-REGISTERED per Sidh's 2026-10-01 instruction, committed **before** any search runs.
No MC-dropout cache exists under the base hash at the time of writing
(`artifacts/search_cache/e8_mcdropout_00d1cb2ddd3bf10c_seed42.json` is absent).

**(i) E8's original cached search (read-only record).**
- **Path:** `artifacts/search_cache/e8_mcdropout_eb89df79f00cd6e5_seed42.json` (git-ignored;
  SHA-256 `031bde6c8373acbe13514e5f18bfc3b4682bba67ed0d41f38cd48c14320d24f2`).
- **Config hash:** `eb89df79f00cd6e557691d084469b7be37056e7869690b0f83f8b91985e24be2`. This is the hash in
  `reports/02_baselines_provenance.json`, E8's published run (commit `83df997`, 2026-08-31).
- **Search:** 24 trials, 24 configs evaluated, selection split `val_inner`, seed 42; objective
  "mean |empirical − nominal| coverage error (ITS OWN metric)"; 875.8 s wall-clock.
- **best_params:** `{"hidden_size": 128, "num_layers": 1, "dropout": 0.2, "learning_rate": 0.01,
  "batch_size": 128, "cell": "gru"}`.
- **best_objective_value:** `0.02038586703858669`.
- **Context, also read-only.** Three later MC-dropout caches at the same 2-day cutoff — `7d6ccea5…`,
  `ce0f4e21…` and the E15 2-day horizon config `02b75edb…` — hold the identical `best_params` and
  `best_objective_value`. The 3-day cache (`347d68f9…`) differs, but it ran at a different cutoff
  and is not a comparison target. Recorded wall-clocks across all five caches are 310–1,051 s.
  That is well under the "~3.5 h" figure in the 2026-09-21 H1 scope entry; the discrepancy is noted,
  not resolved, and the run is monitored either way.

**(ii) Prediction.** A search under the base hash
`00d1cb2ddd3bf10c415095aebaf67dcb863eb2a5dc4dc930744dad51566b67f5` will reproduce (i) **exactly**:
`best_params` dict-equal and `best_objective_value` float-equal after JSON parsing. This is what the
three E15 re-searches (GBM, GRU, MC-dropout) did across a config-hash change.

**How it is run and compared — no new machinery.** The search is triggered through the same call
`base_predictions` makes:
`cached_search(cfg, "e8_mcdropout", cfg.seed, lambda: search_mc_dropout(cfg, _seq_view(data), seed=cfg.seed))`,
on `prepare_conformal_data(cfg, load_events(cfg))` under the base config. The driver is a thin
script in the session scratchpad that only calls these library functions and writes nothing but the
cache file. The comparison is the project's existing `decision_runner.search_integrity(cfg)`, which
compares the new cache with every earlier cache at the same cutoff. **"Identical"** means
`best_params_equal` and `objective_equal` are both True against the `eb89df79…` reference.

**(iii) Decision rule — fixed now, applied mechanically.**
- **Identical →** E8 joins H1, and the exclusion note is retired, replaced by a statement of
  inclusion with this entry as its evidence. Then:
  1. SHA-256 snapshot of every current `e17_*` table.
  2. Extend `H1_LEARNERS` to persistence, gbm, gru and mc_dropout, and re-run E17 (`kc robustness`).
  3. Before any new row is trusted, verify that every persistence/gbm/gru row in every H1 table is
     identical to the snapshot under round-trip parsing (`float_precision="round_trip"`, 0 differing
     cells). **Expected and pre-registered:** adding a learner cannot change those rows. The Holm
     family is the single committed E11 McNemar p-value, the clipping check depends only on the
     weights, and each cluster-bootstrap row is reseeded independently. The H2 and H3 tables do not
     use MC-dropout and are expected **byte-identical**. Any difference stops the procedure and is
     reported, not explained away.
  4. Re-render, re-run `kc manuscript`, and list every artifact that changed and why. Expected: none
     beyond exclusion notes. Update any caption or note that mentions the exclusion.
- **Different →** report both parameter sets and objectives side by side. Keep the exclusion, with
  its **true** rationale: no cache existed under the base hash, and a search under it selected
  hyperparameters different from E8's. **No tuning, no second search, no E17 re-run.**

**Failure handling.** A crash or an unexplained stall is reported as observed. Process state (PID,
CPU) is inspected before anything is concluded stuck, and the run is not retried with different
settings.

**Pre-registered by:** Claude Code, per Sidh's 2026-10-01 instruction.


### 2026-10-01 — E8 inclusion check RESULT: identical → MC-dropout joins E17 H1; existing rows verified unchanged

**Status:** REPORTED by Claude Code. The pre-registered decision rule (entry above, `145b10c`) was
applied mechanically. Nothing was tuned, and no second search ran.

**1. The search — prediction confirmed exactly.** It ran under base hash `00d1cb2d…` and took 941.6 s
(989.8 s with data assembly), with no failures. It wrote
`artifacts/search_cache/e8_mcdropout_00d1cb2ddd3bf10c_seed42.json` (SHA-256 `83c0a894…`):
- `best_params`: `{"hidden_size": 128, "num_layers": 1, "dropout": 0.2, "learning_rate": 0.01,
  "batch_size": 128, "cell": "gru"}`, identical to E8's;
- `best_objective_value`: `0.02038586703858669`, identical to E8's;
- `decision_runner.search_integrity`: `best_params_equal` and `objective_equal` both **True**
  against all four same-cutoff caches (`eb89df79…` — E8's original — `7d6ccea5…`, `ce0f4e21…`,
  `02b75edb…`).

**The "~3.5 h" estimate in the 2026-09-21 H1 scope entry is not supported.** The search took about
16 minutes, consistent with the 310–1,051 s recorded in every earlier MC-dropout cache.

**2. Decision applied: E8 joins H1** (`b1a2580`). `H1_LEARNERS` adds `mc_dropout`, and the
exclusion reason is retired (the constant is removed). `H1_SCOPE_NOTE` records both the
2026-09-21 exclusion and this inclusion. The derived `e17_h1_excluded_learners` table keeps its
name and now records MC-dropout with `included=True`. Tests that pinned the three-learner scope now
pin the four-learner scope equally strictly. The wrong-run guard now refuses the superseded
three-learner tables. The full suite passes.

**3. Snapshot, re-run, verification — in that order.**
- **Snapshot:** a SHA-256 snapshot of all 10 `e17_*` tables, the E17 figures, the 06 report and
  sidecar, and all 72 manuscript artifact files was taken before the re-run.
- **Re-run:** `kc robustness` at `b1a2580`, config `00d1cb2d…`, 2,290.0 s. No search ran (the
  cache existed). The previous three-learner run took 2,873.2 s; the shorter time despite an added
  learner is machine-speed variance.
- **Verification (pre-registered), PASSED before any new row was read:**
  - `e17_h1_clipping`, `e17_h1_multiple_comparison`, `e17_h2_coverage`, `e17_h2_per_seed`,
    `e17_h3_association`, `e17_h3_overlap` and `e17_coverage_restoration_matrix` are
    **byte-identical** (SHA-256), with 0 differing cells;
  - `e17_h1_cluster_bootstrap` (36 → 48 rows) and `e17_h1_gate2_verdict` (18 → 24 rows): every
    persistence/GBM/GRU row is identical, with **0 differing cells** under `float_precision="round_trip"`;
  - the verifier was negative-controlled first: it detects a single 1-ULP float change and a single
    string change.
- **Like-for-like check (not pre-registered, added as a guard).** All 12 MC-dropout E17 coverages
  (E10/E11 × one/two-sided × 3 levels) equal the published `e9e11_coverage` values to ≤ 1.11e-16.
  That residual is seed-averaging summation order, the same 1-ULP class already documented for the
  other learners. **This is the model E8 reported.**

**4. New rows — MC-dropout, two-sided, final criterion.** RESTORED at every level, under both
schemes:

| nominal | naive → weighted | iid: naive CI upper; weighted CI | cluster: naive CI upper; weighted CI |
|---|---|---|---|
| 80% | 0.7603 → 0.7979 | 0.7774; [0.7826, 0.8133] | 0.7849; [0.7722, 0.8191] |
| 90% | 0.8528 → 0.8963 | 0.8663; [0.8845, 0.9080] | 0.8705; [0.8819, 0.9092] |
| 95% | 0.9166 → 0.9479 | 0.9272; [0.9395, 0.9562] | 0.9253; [0.9412, 0.9537] |

- **Read precisely:** the weighted **point estimate is below nominal at all three levels** (−0.21,
  −0.37 and −0.21 pp). "RESTORED" here means under-coverage is no longer established, not that
  coverage reaches nominal. This is consistent with Gate 2's "within ~0.5pp of nominal".
- **Scheme agreement:** primary criterion 8/9 → **11/12** (GBM at 80% remains the only fragile
  cell); containment criterion 6/9 → 9/12.
- **Cluster vs iid width:** the cluster interval is wider in 34/36 → **44/48** arms. For MC-dropout's
  two-sided 95% arms it is narrower (width ratios 0.889 naive, 0.752 weighted).
- **The Gate-2 headline (persistence) is untouched.**

**5. Manuscript (`kc manuscript`, final build at `c69896f`, tree clean).** Of 72 files, **8
changed**, all because of this inclusion:
- **F04 PNG and PDF:** panel (b) gains MC-dropout.
- **`F04_gate2_headline_robustness.csv`/`.md`:** six MC-dropout rows added.
- **`F04_gate2_headline.md` and `F04_gate2_headline_primary_contrast.md`:** they embed the caption
  (their CSVs are byte-identical). The caption now reads "12 learner × level cells … agree in 11",
  and "MC-dropout was not refit … absent from (b)" is removed.
- **`manuscript_captions.md` and `manuscript_manifest.json`:** the above; F06/F11/F04 "Computed by:
  E17" changes from `f53d27a` to `b1a2580` (their F06/F11 figures and tables are byte-identical);
  and the F02b note no longer claims a fresh search would be needed (it is still NOT regenerable
  from tables).

This is more than "exclusion notes only", as expected: F04(b) now carries a fourth learner.

The first build **failed loud**: "E17: computing commit not established". The E18 builder handled
E17's sidecar only as a from-tables render. A recomputing run names its commit as
`rendered_git_sha`, which the builder now accepts explicitly, still failing if it is absent
(`4dfa7d3`). `README.md` and the `REVIEWER_CHECKLIST.md` clustering item were updated to the
new scope and counts.

**Explicitly NOT decided here (Sidh's):** whether the manuscript's text or the reviewer-checklist
triage should say more about MC-dropout's restoration than F04 now shows; whether F02b should be
rebuilt now that the refit no longer needs a search; anything about manuscript drafting.

**Reported by:** Claude Code.


### 2026-10-02 — Housekeeping: retroactive gate tags; merged scratch plan files removed; E9 one-sided figure annotated

**Status:** DONE by Claude Code per Sidh's 2026-10-02 instruction. No result, table or code changed.

1. **Retroactive annotated tags** (CLAUDE.md §5 called for gate tags, and none existed). Each tag points
   at the commit that **adds** its gate decision to this log, identified from `git log` and checked by
   the commit's own diff:
   - `gate1-power-analysis` → `1d364bc` ("docs: record Gate 1 outcome …"; adds the 2026-08-01 GATE 1 entry);
   - `gate2-weighted-conformal` → `7ccf97f` ("docs: record Gate 2 decision …"; adds both 2026-09-16 Gate 2
     entries);
   - `gate3-label-noise` → `ff6b972` ("docs: record Gate 3 decision …"; adds both 2026-09-18 Gate 3 entries).

   Tag message: "retroactive tag created 2026-10-02 at the commit recording the Gate N decision".
   **Discrepancy noted, not resolved:** the Gate 2 and Gate 3 commits are timestamped 2026-09-11 and
   2026-09-15 — earlier than their entries' headings (2026-09-16, 2026-09-18). The tags mark the commits
   that record the decisions; they make no claim about the decision dates.
2. **Untracked scratch files removed:** `EXPERIMENT_PLAN_E16_E17_E18_revision.md` and
   `EXPERIMENT_PLAN_E18_revision.md` (drafts, never committed). Before deletion, their content was
   checked against `EXPERIMENT_PLAN.md`:
   - every item of the E18 revision is present verbatim, apart from its "DRAFT FOR REVIEW" preamble;
   - the E16/E17 revision's E15–E17 content is merged, and its Execution Order rows are present in
     their later-updated form;
   - its own E18 section was superseded by the E18 revision, which is merged.

   Copies are kept outside the repository (session scratchpad).
3. **E9 one-sided "≤0.8pp" annotated in place** with the exact 0.82 pp (Gate 2 entry).

**Recorded by:** Claude Code.


### 2026-10-14 — PRE-REGISTRATION (reconstructed): Pc engine independent validation (REVIEWER_CHECKLIST RP4)

**Reconstructed on 2026-10-14 from a draft lost with the D: project folder before it was ever committed.
No validation code exists and no comparison has run. Wording may differ from the lost draft; the
substantive terms are below.**

**Status:** PRE-REGISTRATION, not yet run. Committed together with
`config/experiments/pc_validation.yaml`, which holds every numeric value. Sources of the terms:
- **Sidh's Step B specification**, the brief that followed the 2026-10-02 checkpoint;
- **Claude Code's lost draft.** Every draft-only term is marked **[to be re-confirmed by Sidh]**:
  it was never reviewed by Sidh before the loss, or it rests on an input check made on data that is now
  lost.
- The CARA/MATLAB reference is skipped (Sidh).
- **Measurement only:** no recommendation follows, and no convention is adopted.

**Inputs only.** Each method reads a CDM's relative state, its two covariances and its spans. No model
output, prediction or interval is involved.

**1. Sample (seed 42).** The strata are E3's pre-specified edges (`pc_spike.risk_strata_edges`
= [−30, −15, −10, −6, 0]).
- **Primary set: the official-test target-defining CDMs** (the rows E14 recomputed):
  - **all 150** events in (−6, 0];
  - **30 each** in floor, (−30, −15], (−15, −10] and (−10, −6];
  - 270 CDMs in total.
- **Population sizes.** The E14 findings entry (introduced in commit `7c9c50d`) records floor 1,673 and (−6, 0] 150 of 2,167
  events, which leaves 344 across the three middle bands. The per-band split (108 / 138 / 98) was read
  from a table now lost [to be re-confirmed by Sidh].
- **Draw procedure:** `numpy.random.default_rng(42)`, without replacement, strata in the order above,
  uids sorted first [to be re-confirmed by Sidh].
- **Second set: E3's existing 100 training-pool CDMs** (Sidh's spec).
  - Matched to the raw training data on `(event_uid, time_to_tca)`. In the session that wrote the lost draft, all 100 matched
    uniquely, with `risk` equal to E3's recorded value, but that check ran on data now lost
    [to be re-confirmed by Sidh; re-check on re-ingested data].
  - Reported separately, not pooled [to be re-confirmed by Sidh].

**2. Methods.** None shares the engine's code (`labelnoise/pc_foster.py`).
- **Shared independent input assembly** [to be re-confirmed by Sidh]:
  - RTN covariances from sigmas and correlations;
  - HBR under convention C0;
  - its own encounter-plane basis (relative velocity, then miss direction, then cross product);
  - closed-form 2×2 principal axes instead of `eigh`.

  It implements the **same conventions** as the engine. The checks therefore validate the
  integration and the code, **not the conventions** (§6 and outcome (a)).
- **M1, deterministic 1D reduction.** The inner direction is integrated analytically (error-function
  difference via `log_ndtr`). The outer direction uses x = HBR·sin t and adaptive Gauss–Kronrod, in
  log space with the peak factored out. Valid at every depth. Its tolerances are in the YAML
  [to be re-confirmed by Sidh].
- **M3, uniform-in-disk Monte Carlo** of the 2D density, in log space. The sample size, the escalation
  rule and per-event seeds (42 + sample index) are in the YAML [to be re-confirmed by Sidh].
- **M2, plain Monte Carlo** on the encounter plane (Sidh's spec):
  - a per-event sample cap;
  - counted only where the relative standard error is ≤ 10%, otherwise "not informative" (reported, not
    counted);
  - judged within 3 standard errors.

  The chunking, the cap value, stopping at about 100 hits, and treating an event as "not informative"
  without sampling when 100/Pc_M1 exceeds the cap are all [to be re-confirmed by Sidh]. M2 cannot reach
  the deep tail.

**3. Order, each step reported before the next is read** (Sidh's spec).
1. **Engine self-convergence.** `recompute_pc_for_row` and `log10_pc_unfloored` are run at the
   configured grid of 200 × 360 and at 2× (400 × 720). For each stratum, e_s is the 95th percentile of
   |Δlog10|.
2. **M1 vs M3 gate.** The median |Δlog10| must be ≤ 0.005, else **outcome b′**.
3. **Engine vs independent.**

**4. Tolerance and agreement** (Sidh's spec).
- **Per stratum:** τ_s = max(0.01, 3·e_s) log10.
- **"Agree"** means all three hold:
  - ≥ 95% of the stratum's events lie within τ_s;
  - no event lies beyond 0.1;
  - the median |Δ| is ≤ 0.005.
- **Every** out-of-tolerance event is listed.
- **The floor stratum is judged on unfloored values.**
- **The existing ±0.5 engine-vs-reported tolerance is unchanged.**
- Requiring the engine to agree with **both** M1 and M3, and listing and excluding engine evaluation
  errors, are [to be re-confirmed by Sidh].

**5. Decision table.** Classified per stratum; a mixed outcome is reported stratum by stratum.
- The outcomes and their meanings are Sidh's spec.
- Sidh asked that the RP4/M3 consequences be stated; their wording is Claude's draft
  [to be re-confirmed by Sidh].

| outcome | condition | what it means | REVIEWER_CHECKLIST RP4 | REVIEWER_CHECKLIST M3 |
|---|---|---|---|---|
| **(a)** | M1 ≈ M3, the engine agrees with them, and both disagree with reported values | **Consistent with a label-production difference *or* a shared input-assembly error; the checks cannot separate these.** | [OPEN] narrows: "the integration is cross-validated against two independent methods (a third where informative); the shared input conventions are not." | The defense stands; the limitation gains "the disagreement is not in the numerical integration". |
| **(b)** | M1 ≈ M3, the engine disagrees | **Possible engine bug.** E14's conclusions are suspended: all of them if (−6, 0] is affected, otherwise the deep-tail anchored arm only. **Gate 3 reopens; Sidh decides.** | Becomes a disclosed, unresolved engine defect. | The quantified defense (E3 65.0%, E14 79.3%, F07) is withdrawn in the affected strata until resolved. |
| **(b′)** | M1 and M3 disagree | **Inconclusive.** Fix the checks; nothing changes. | Unchanged. | Unchanged. |

**6. Convention sensitivity** (Sidh's spec). Propose and fix a finite list from the CDM documentation
before running, report all, adopt none; a change of more than 10 pp in overall within-0.5 agreement is a
finding for Sidh. **The list itself is Claude's draft [to be re-confirmed by Sidh]:**
- **C0, baseline:** HBR = (t_span + c_span)/2, both covariances summed in one RTN frame.
- **C1:** `x_span` read as a radius, so HBR = t_span + c_span.
- **C3a / C3b:** the chaser covariance is rotated into the target's RTN frame about R by the crossing
  angle.
  - Circular-orbit approximation from `t_j2k_sma`.
  - The relative velocity is taken as chaser − target (C3a) or target − chaser (C3b).
  - The premise that each object's covariance is in its own RTN frame (the CCSDS CDM convention) is
    **not verified** against this dataset.
- **C4a / C4b, documented anchor:** Pc(k·C) vs `max_risk_estimate`, with k = `max_risk_scaling` as a
  variance factor (C4a) or a sigma factor (C4b). Rows with k ≤ 0 are excluded. This bears on E14's
  covariance-scale semantics.
- **C2, dropped:** the 2 m chaser minimum was found already applied in the data (`c_span` ≥ 2.0
  everywhere), but that check ran on data now lost [to be re-confirmed by Sidh; re-check on
  re-ingested data].

All are run with the engine by changing its inputs only. Within-0.5 agreement is reported per set and
per stratum, against `risk` (C0, C1, C3a, C3b) or against `max_risk_estimate` (C4a, C4b).

**7. Mechanics** [to be re-confirmed by Sidh].
- The independent methods get unit tests against analytic isotropic cases first.
- One `kc` subcommand writes `reports/tables/pcv_*.csv` and a provenance sidecar (commit, base config
  hash, this YAML's SHA-256, seeds, timings).
- **No existing pipeline code changes**, and the base config hash is unchanged.
- **Prerequisite:** the lost `data/raw` must be re-ingested, and E3's `e3_full_comparison` table
  regenerated, before any of this can run.

**Reconstructed by:** Claude Code, per Sidh's 2026-10-14 instruction.


### 2026-10-14 — Date provenance: git commit dates are authoritative; 35 of 67 dated headings differ from their commit dates

**Status:** ANNOTATION by Claude Code, per Sidh's 2026-10-14 instruction. It replays an annotation lost with
the D: folder (see the 2026-10-14 incident entry in the Observations Log), **recomputed from the clone**.
**No heading is edited.**

**Rule.** Where a heading's date and the git commit that introduced it disagree, **the git commit date is
authoritative**. Some headings were dated in drafts written without access to a clock.

**Method.** For each `### YYYY-MM-DD — ` heading, the introducing commit is the first commit whose
`DECISIONS.md` contains the heading's date and its first ~30 title characters (`git log -S`, author date,
IST). Matching on the full current title instead would date a retitled heading by its retitle. Computed
on branch `recover/2026-10-14` at `19ad5a4`.

**Result.** Of 67 dated headings:
- **32** match their commit date (including this branch's two entries dated 2026-10-14);
- **26** are dated **after** the commit that introduced them, by 2–5 days;
- **9** are dated **before** it.

Headings dated **after** their commit:

| heading date | introduced in | Δ days | entry |
|---|---|---|---|
| 2026-09-15 | `232a0de` 2026-09-10 23:26 | -5 | Phase 3 Design Review: Q-CONF-01 (calibration unit) |
| 2026-09-15 | `232a0de` 2026-09-10 23:26 | -5 | Phase 3 Design Review: Q-SEL-01 (weight construction) |
| 2026-09-15 | `232a0de` 2026-09-10 23:26 | -5 | Phase 3 Design Review: Q-SEL-03 (weight diagnostics, clipping, and positivity) |
| 2026-09-15 | `232a0de` 2026-09-10 23:26 | -5 | Phase 3 Design Review: Q-STAT-04 (multiple-comparison policy) |
| 2026-09-15 | `232a0de` 2026-09-10 23:26 | -5 | Phase 3 Design Review: Q-PUB-04 (pre-registration mechanism) |
| 2026-09-15 | `232a0de` 2026-09-10 23:26 | -5 | Phase 3 blocking gate cleared |
| 2026-09-16 | `7ccf97f` 2026-09-11 12:21 | -5 | GATE 2 DECISION: Contribution 1 (weighted conformal correction) |
| 2026-09-16 | `87a48bf` 2026-09-12 14:52 | -4 | E12 (CQR) manuscript disposition + cross-experiment synthesis of the weight… |
| 2026-09-16 | `87a48bf` 2026-09-12 14:52 | -4 | Q-LBL-02: covariance-rescaling grid semantics (label-noise, E14) |
| 2026-09-16 | `87a48bf` 2026-09-12 14:52 | -4 | Q-LBL-03: rescaled labels used for evaluation only (label-noise, E14) |
| 2026-09-16 | `2c21661` 2026-09-12 19:45 | -4 | Assumption A4 / Q-LBL-01: PARTIAL HOLD → scoped M7; Q-DATA-05 resolved with it |
| 2026-09-18 | `ff6b972` 2026-09-15 02:08 | -3 | GATE 3 DECISION: Contribution 2 (label-noise sensitivity) + Venue Tier |
| 2026-09-18 | `3c40917` 2026-09-15 15:47 | -3 | E15 design review (Gate 3 binding requirement): high-risk lens, one-sided b… |
| 2026-09-19 | `cc67cf8` 2026-09-17 11:15 | -2 | Expanded E15 design decisions: Q-METH-04 revised to {2-day, 3-day} on the o… |
| 2026-09-16 | `3bc9c20` 2026-09-11 13:13 | -5 | E12 CQR: large efficiency gain, but a genuine coverage negative (failure cr… |
| 2026-09-16 | `e636d34` 2026-09-12 20:08 | -4 | PRE-REGISTRATION: E14 label-noise sensitivity protocol |
| 2026-09-16 | `e636d34` 2026-09-12 20:08 | -4 | AMENDMENT to the E14 pre-registration: the anchored arm is undefined at the… |
| 2026-09-16 | `7c9c50d` 2026-09-12 20:56 | -4 | E14 label-noise sensitivity: Contribution 1's claim is robust, but for a re… |
| 2026-09-18 | `fc03e5c` 2026-09-15 16:07 | -3 | PRE-REGISTRATION: E15 decision-cost protocol (turning the E15 design review… |
| 2026-09-18 | `73b7abc` 2026-09-16 01:37 | -2 | PRE-REGISTRATION: expanded threshold-based decision analysis (E15 expansion… |
| 2026-09-19 | `d43b5fc` 2026-09-17 11:18 | -2 | AMENDMENT to the expanded threshold pre-registration: implementing the {2-d… |
| 2026-09-18 | `504dfbf` 2026-09-15 17:14 | -3 | E15 decision cost: conformal calibration changes no matched-budget decision… |
| 2026-09-18 | `b020061` 2026-09-16 01:42 | -2 | EXTENSION of the E15 matched-budget finding: rank invariance (Proposition 1… |
| 2026-09-19 | `21a9c9a` 2026-09-17 17:12 | -2 | Expanded E15 threshold analysis over lead times (E16 merged): P1 holds exac… |
| 2026-09-16 | `7ccf97f` 2026-09-11 12:21 | -5 | GATE 2 (E9–E11 review): GO, scoped to two-sided coverage |
| 2026-09-18 | `ff6b972` 2026-09-15 02:08 | -3 | GATE 3 (E11–E14 review): GO, venue tier Q2 confirmed as firm target |

Headings dated **before** their commit:

| heading date | introduced in | Δ days | entry |
|---|---|---|---|
| 2026-08-01 | `3048f19` 2026-08-02 02:58 | +1 | Q-COMP-01: compute inventory (factual record, not a judgement) |
| 2026-08-01 | `3048f19` 2026-08-02 02:58 | +1 | CONFLICT FLAGGED: `feature_dictionary.yaml`'s `risk` verdict vs. E6/E7 as s… |
| 2026-08-01 | `3048f19` 2026-08-02 02:58 | +1 | E6/E7 decision rule: a validation-selected promotion threshold — PROPOSED |
| 2026-08-01 | `08d03ca` 2026-08-31 19:09 | +30 | E6/E7: both learned point predictors are MUCH WORSE than persistence |
| 2026-08-01 | `08d03ca` 2026-08-31 19:09 | +30 | E8: the expected coverage deficiency is CONFIRMED |
| 2026-09-01 | `6f01910` 2026-09-02 03:37 | +1 | PRE-REGISTRATION (written BEFORE any re-run): risk_history audit outcome |
| 2026-09-01 | `6f01910` 2026-09-02 03:37 | +1 | Phase 3 scope addition: persistence (E5 LRP) as a fourth conformal base lea… |
| 2026-09-22 | `023f7f1` 2026-10-01 19:11 | +9 | E18 (final manuscript consolidation): deferred fixes verified, artifact set… |
| 2026-10-01 | `105cedd` 2026-10-02 00:27 | +1 | E8 inclusion check RESULT: identical → MC-dropout joins E17 H1; existing ro… |

Seven of the nine are 1-day gaps where the commit was made after midnight. Two are larger:
- the E6/E7 and E8 findings are headed 2026-08-01 but were first committed 2026-08-31 (+30 d);
- the E18 entry is headed 2026-09-22 but was first committed 2026-10-01 (+9 d).

**Pre-registration order is set by commit ancestry, not by heading dates.** Re-verified from the clone with
`git merge-base --is-ancestor`: each pre-registration commit below is an ancestor of, and earlier than,
its result commit.

| pre-registration | result | gap |
|---|---|---|
| E14 `e636d34` | `7c9c50d` | 48 min |
| E15 `fc03e5c` | `504dfbf` | 67 min |
| expanded E15 `73b7abc` | `21a9c9a` | about 40 h |
| its amendment `d43b5fc` | `21a9c9a` | about 6 h |
| extended grid `f2ef40e` | `6e8debd` | 11 min |
| E8 inclusion `145b10c` | `b1a2580` | 28 min |

**Recorded by:** Claude Code.


### 2026-10-14 — PENDING IMPLEMENTATION: the RESTORED wording, and the reproduce-all design decisions

**Status:** DECISIONS by Sidh, recorded by Claude Code on 2026-10-14 as **pending implementation**. **No
code is written by this entry.** Both items were decided in the brief that followed the 2026-10-02
checkpoint.
- Item (a) was implemented locally in commits `c9132b9` and `32ecbb2`, lost with the D: folder before
  being pushed (see the 2026-10-14 incident entry in the Observations Log).
- Item (b) was never recorded before the loss.

Every code fact cited below was verified in the clone at `1e475e5`.

---

**(a) The RESTORED wording: to be re-applied after the result tables are regenerated.**

*The decision (Sidh).*
- Wherever "restores" or "restored" describes a learned-model cell whose rule-weighted point estimate is
  below nominal, the text must say what the verdict means.
- **RESTORED means under-coverage is no longer established; it does not mean coverage reaches nominal.**
- Persistence is the only learner whose weighted interval lies wholly above nominal in the headline cells
  (two-sided, 90%).

*Where it applies.*
- **F04 caption.**
  - The first sentence says weighting removes naive split conformal's established two-sided
    under-coverage, instead of saying it "restores" coverage.
  - Panel (a) names persistence as the only learner wholly above nominal, and lists the learners whose
    weighted point estimate stays below nominal.
  - Panel (b) adds, per bootstrap scheme, the cells whose weighted interval is wholly at or above nominal
    and the cells whose point estimate is below nominal.
  - Every count and list is **computed from the verdict table at build time** and guarded by `_require`,
    including "persistence is the only learner wholly above nominal at the primary level".
- **F11 caption and figure label.**
  - The caption says "meets the restoration criterion in N of 4 cells" and qualifies the RESTORED cell
    when its weighted point estimate is below nominal.
  - The figure adds a muted label "weighted point estimate below nominal" to any such cell.
- **`REVIEWER_CHECKLIST.md`:** the N1 "strengthened since drafting" line (line 17) and the M8 "finding, stated
  plainly" line (line 127).
- **`README.md`:** the Gate 2 line and the E17 "restores 1 of the 4" line.
- **`DECISIONS.md`:** append-only annotations on the RESOLVED Gate 2 entry, the Gate 2 outcome line, the
  E17 findings entry and the E8-inclusion result entry.
  - Their numbers must be **read from the regenerated tables**, not copied from the lost commit.
- **F05 and F06 were checked and need no change:** F05 states non-restoration only, and F06 makes no
  restore claim.

*Allowed changes:* captions, figure label text, markdown tables that embed captions, and the manifest.

*Required check:* every CSV, including both verdict tables, SHA-256-identical before and after. Then
`kc manuscript` rebuilt on a clean tree, with the manifest committed.

*Why it is not re-applied now.* The captions are generated from `reports/tables/`, which was lost, so
they cannot be rebuilt or byte-checked. The wording is applied only once the tables exist again.

---

**(b) reproduce-all design decisions (Sidh).**
1. **Output hashing.** The manifest records the SHA-256 of **every output file** at a tagged release: all
   result tables and every manuscript figure and table, not only each artifact's source tables (which is
   all `reports/manuscript_manifest.json` records today).
2. **Canonical reference.** The reference is a **container run**. Windows results are compared with it
   under a tolerance that is **measured first, then decided by Sidh**.
3. **Measure before change.** Each of the following is run, diffed against the published outputs, and
   reported **before** any change is adopted:
   - torch thread pinning. `sequence.py:173` pins threads to 1 only around training;
   - the torch `warn_only` setting. `sequence.py:39` calls
     `torch.use_deterministic_algorithms(True, warn_only=True)`;
   - the `read_csv` parser change. 10 `pd.read_csv` calls in `src/kelvins_conformal` don't pass
     `float_precision="round_trip"`.
4. **Hardcoded literals** are replaced by computed or saved quantities during the full run. Known cases,
   verified in the clone:
   - the persistence 65.9% zero-atom, a constant in `decision_runner.py:71` and `threshold_runner.py:74`;
   - the original-grid 62.3% / 54.2% in `05c_threshold_analysis.ipynb` §7b, plus `decision.py:396` and
     two `manuscript.py` notes;
   - E3's 65.0% in `04_labelnoise.ipynb`;
   - E14's label-shift size, which was printed by the E14 run but never saved (`manuscript.py:937`).

   F02b also cannot be regenerated: E8's per-event predictive distributions were never saved
   (`manuscript.py:500`).
5. **HEAD-reproduction audit.** The first full run doubles as the reproduction audit for the stages whose
   reproduction at HEAD has never been checked: **E1, E3–E11, E14, E15 and E15b**.
6. **CI and Docker, as proposed.**
   - Pin Python **3.13.11** in CI and the Dockerfile: the result sidecars record 3.13.11, but CI installs
     3.11 (`ci.yaml:31`) and the Dockerfile uses `python:3.11-slim-bookworm` (`Dockerfile:5`).
   - Add `--extra models` to the Docker sync.
   - Remove the `|| uv sync` fallback from `Dockerfile:19`.
   - Set `OMP_NUM_THREADS`, `MKL_NUM_THREADS` and `OPENBLAS_NUM_THREADS` to 1 in the container.

**Consequence of the D: loss for item 3.** "The published outputs" no longer exist as files. Until the
first full run regenerates them, a measure-before-change diff can be checked only against values quoted
in this log, the committed captions and manifest, and `REVIEWER_CHECKLIST.md`. What reference that run
should be held to is Sidh's decision.

**Recorded by:** Claude Code.


### 2026-10-15 — AMENDMENT (pending Sidh's confirmation): the first reproduction audit is native Windows; the container run follows

**Status:** AMENDMENT to item (b)2 of the 2026-10-14 "PENDING IMPLEMENTATION" entry, recorded by Claude Code
per Sidh's 2026-10-15 instruction. **Pending Sidh's confirmation.** No code changes.

**The amended decision.**
- **Before:** "The canonical reference is a container run. Windows results are compared with it under a
  tolerance that is measured first, then decided by Sidh."
- **After:**
  1. **First audit, native Windows.** It runs with Python 3.13.11 and tests **byte identity** against
     every committed SHA-256.
  2. **Then the container run.** It is compared against the **regenerated Windows outputs** under a
     tolerance measured at that time.

**Why.**
- **Every committed byte-level reference was produced on Windows with Python 3.13.11.** That covers the
  manuscript manifest's `source_sha256`, the 05c sidecar, and E17's `4a35a92` sidecar.
  - All 13 committed provenance sidecars record `"python": "3.13.11"`.
  - The sidecars do not record the operating system. The only development machine in the record is
    Windows 11 (the Q-COMP-01 compute inventory).
- **The outputs those hashes describe were lost with the D: folder** (2026-10-14 incident entry). Nothing
  else is left to compare a container's outputs against.
- **A container run first could not tell two things apart:** a platform or toolchain difference, and a
  failure of the code to reproduce its own published bytes. A native Windows run on the same interpreter
  version is the only setting in which byte identity with the committed hashes is a fair test.
- **Once the Windows outputs are regenerated** and checked against those hashes, they become the
  reference the container run is measured against.

**Unchanged:** every other item of the 2026-10-14 reproduce-all record.

**Recorded by:** Claude Code. **Awaiting confirmation by:** Sidh.


### 2026-10-23 — E1–E3 regenerated natively: 3 of 3 committed hashes and 57 of 57 committed numbers reproduced

**Status:** REPORTED by Claude Code, per Sidh's 2026-10-23 instruction. This is the first stage of the
native-Windows reproduction audit (2026-10-15 amendment, pending confirmation). **No decision is taken
here.**

**Run.**
- `kc audit` (E1–E3) on 2026-10-23, at commit `2aaa0d7`, config `00d1cb2d…`.
- Python 3.13.11 (the system interpreter) on Windows 11, in a fresh clone at `E:\EDI-1\repo`, with an
  environment installed by `uv sync --locked` with the `models`, `notebooks` and `dev` extras.
- Raw data re-ingested by `kc ingest`. The zip's md5 `d19dc8875229f2f6893253c38adddc87` equals
  `config/default.yaml`.

**Per-stage wall-clock**, from timestamped CLI output (per-cell timings are not available, because the
CLI deletes the executed notebook):

| stage | duration |
|---|---|
| CLI and kernel startup | 35 s |
| `00_data_audit.ipynb` (E1 + E2, including building `events.parquet`) | 86 s |
| `00b_pc_spike.ipynb` (E3) | 35 s |
| total | 157 s |

Commit headroom never fell below 13.87 GB (limit 38.18 GB).

**Byte level — 3 of 3 reproduced.**
- Every committed SHA-256 covering E1–E3 is reproduced exactly: `e1_cutoff_rule_verification`,
  `e1_high_risk_prevalence` and `e1_two_sample_tests`, against the manuscript manifest's
  `source_sha256`, which hashes file bytes.
- No other E1–E3 output had a committed hash.
- The 20 regenerated tables, `events.parquet` and the `data/raw` files are now hashed in
  `reports/hashes/` (`c324d62`): 3 are "reproduced", every other entry is "first-recorded".

**Number level — 57 of 57 reproduced.** Every number in the Phase 0 findings entry (DECISIONS lines
586–626) and its restatements matches, compared at the precision it was written to:
- DECISIONS lines 285, 292, 295, 851, 1215, 1458, 1460 and 1729;
- the F01 caption (`reports/manuscript_captions.md` line 7).

The numbers cover event and feature counts, the cutoff rules, recency shares, high-risk prevalence and
enrichment, KS p-values, mission counts, floor mass, the E2 feature tally, field missingness, and every
E3 agreement, CI, test statistic and stratum figure.

**First recorded, not reproduced.** Two E3 quantities had no committed value:
- **MAE log10, full sample: 1.37655** (1.3765537488229966);
- **median |Δ|, full sample: 0.23074** (0.23074145341466945).

They are recorded here for the first time. A later run can reproduce them; this one could not.

**Other checks.**
- `events.parquet` holds **one row per CDM**: 187,118 = 162,634 train + 24,484 test, across 15,321
  events. That equals the CDM totals implied by `e1_cdms_per_event` (events × mean CDMs per event), a
  first-recorded table.
- The slow test `test_splits_leakage.py::test_real_train_test_events_are_disjoint` passes.
- The `data/raw` file md5s equal the values shown in this session from the `PROVENANCE.json` lost with
  the D: folder. That earlier record survives only in the session transcript; it was never committed.

**Sidecars: not committed.** `kc audit` rewrote the two tracked sidecars, and only three fields differ
in each:

| field | committed | regenerated |
|---|---|---|
| `git_commit_sha` | "UNAVAILABLE (working tree is not a git repository)" | `2aaa0d7…` |
| `config_hash` | `9c732558…` | `00d1cb2d…` |
| `executed_utc` | 2026-08-01 | 2026-10-23 |

The committed originals were restored. The regenerated copies are kept outside the repository, in
`E:\EDI-1\regenerated_sidecars\`, with SHA-256s.

**What this does not show.**
- **E4–E18 are untested.** No stage past E3 has been regenerated.
- **One machine and one OS.** The run is on the machine the D: project ran on (Windows 11), with the
  same interpreter version. Byte identity on any other machine or OS, including the container, is
  not shown.
- **E1–E3's original run predates git.** The comparison is against the committed hashes and numbers,
  not against the original files, which are lost.

**Reported by:** Claude Code.


### 2026-10-23 — E5 record mismatch: "42.6% of training events" (line 669) is not what the code measures, and cannot be reproduced

**Status:** FINDING, recorded by Claude Code from the native regeneration of E5 on 2026-10-23 (`266badf`,
config `00d1cb2d…`). Append-only: line 669 is not edited.

**The committed statement** (E5 findings entry, line 669, introduced in `4d9f38b`): "for 42.6% of
training events `r_{-2}` *is* the target CDM and the baseline is exact by construction".

**Where "42.6%" comes from.** It occurs exactly once in history: `git log --all -S"42.6%"` finds only
`4d9f38b`, which adds line 669. No notebook, `src/` file or plan document has ever contained it. The
committed notebooks store no outputs, so the original printed value is not recoverable.

**What the code prints.** `notebooks/01b_baseline_validation.ipynb` cell 12 is unchanged since
`4d9f38b`. Regenerated, it prints "training events where r_-2 IS the target CDM (zero error by
construction): 7,891 of 11,942 (66.1%)".
- **Numerator:** `np.isclose(r_minus_2, y_true)`, i.e. events whose latest pre-cutoff risk **value**
  equals the target risk value.
- **Denominator:** 11,942, the training events with an admissible pre-cutoff CDM (13,154 minus 1,212
  with none; `baselines.build_baseline_frame`).
- **The label overstates the measure.** Of the 7,891, **5,124 are both at the −30 floor** (two
  different CDMs with the same sentinel value). Only 2,767 are equal and not both at the floor.

**Candidate definitions, computed read-only. None gives 42.6%:**

| definition | share |
|---|---|
| value equality, ÷ 11,942 (the code's measure) | 66.08% |
| the same 7,891, ÷ 13,154 | 59.99% |
| identity — the final CDM itself lies at or beyond the 2-day cutoff, so the pre-cutoff CDM *is* the target CDM — ÷ 11,942 | 25.54% |
| identity, ÷ 13,154 | 23.19% |

**Conclusion:** the committed 42.6% and the regenerated 66.1% do not measure the same thing on any
reading found, and 42.6% cannot be reproduced. The E5 entry's qualitative point stands as recomputed:
LRP is exact by construction for a large share of unfiltered training events, which deflates MSE_HR.
Unfiltered L = 0.0964 (committed 0.096) reproduces. The specific percentage does not.

**Touches a Gate 1 decision input? No.** Gate 1's E5 inputs are the seven published quantities and
their tolerance, all reproduced. Line 669 is a diagnostic of the unfiltered-train anomaly, not an input.

**Reported by:** Claude Code.


### 2026-10-23 — E4 record mismatch: "calibration term (0.58–0.82 pp) at every fraction" (line 696)

**Status:** FINDING, recorded by Claude Code from the native regeneration of E4 on 2026-10-23
(`266badf`, config `00d1cb2d…`). Append-only.

**The terms, as `power.py` defines them.**
- **calibration term** = `beta_sd_pp`, the SD (pp) of Beta(n_cal + 1 − ℓ, ℓ) with ℓ = ⌊α(n_cal + 1)⌋:
  the spread of conditional coverage across calibration draws;
- **test-set term** = 100·√(p(1−p)/n_test).

Both are **standard deviations**. The reported precision is a different quantity: the **median
Clopper–Pearson half-width** of k/150, where k is the simulated number of covered high-risk events.

**Regenerated calibration terms (pp)**, from `e4_marginal_precision`:

| nominal | 10% (n_cal 1,315) | 20% (2,631) | 30% (3,946) |
|---|---|---|---|
| 80% | 1.102 | 0.779 | 0.636 |
| 90% | 0.825 | 0.584 | **0.477** |
| 95% | 0.597 | 0.424 | 0.347 |

- **"0.58–0.82" matches only the 90% values at the 10% and 20% fractions.** The 30% value, 0.477, lies
  outside it.
- No nominal level has all three fractions inside 0.58–0.82. **"At every fraction" is not reproduced.**
  The table is deterministic: two runs on this machine are byte-identical.

**Why the half-width barely moves, reconciled.**
- The calibration term adds **in quadrature** with the test-set term (2.449 pp at 90%):
  - √(0.825² + 2.449²) = 2.585 pp;
  - √(0.477² + 2.449²) = 2.496 pp;
  - a 0.09 pp change in total spread; the simulated "sd of estimate" moves 2.578 → 2.500.
- The median CP half-width does not include that spread at all. The median simulated k is 135
  (90.00%) at every fraction, so the median half-width is exactly CP(135, 150) = 5.1255 pp at all three.
  For reference, k = 134 gives 5.2613 and k = 136 gives 4.9834.
- So the E4 conclusion "<0.01 pp" (in fact 0) holds, and a falling calibration term is consistent with
  it.

**Touches a Gate 1 decision input? No.** Gate 1 rests on the marginal half-width (5.13 pp at
n_HR = 150) and the merge threshold (200 > 150), both reproduced. The calibration-term range is
supporting text for "precision is limited by the evaluation set". That statement still holds, with the
range corrected to 0.48–0.82 pp at 90%.

**Reported by:** Claude Code.


### 2026-10-23 — Gate 1 wording: the "0.001 criterion" does not cover CRP

**Status:** FINDING (wording), recorded by Claude Code. Append-only: the Gate 1 entry is not edited.

**The record.**
- **The Gate 1 entry** ("2026-08-01 — GATE 1 (E1–E5 review)", paragraph "E5 agreement tolerance
  RESOLVED") reads: "The 0.001
  absolute-difference criterion is confirmed as adequate — all 7 published quantities matched well
  within it."
- **The E5 pre-registration** (lines 514 and 519) sets ≤ 0.001 for the six LRP quantities and
  **≤ 0.05 for CRP L**, "since 2.5 is given to 2 significant figures only".
- **CRP L differs by 0.0041** (2.504140 vs 2.5; committed at line 657, and reproduced natively on
  2026-10-23). That is within its own 0.05 tolerance but not within 0.001. Six of the seven quantities
  are within 0.001.

**Reading.** Every quantity met the tolerance pre-registered for it, so the substance of the
resolution holds. The sentence's premise, that all seven were within 0.001, is imprecise for CRP.

**Touches a Gate 1 decision input? Yes.** It is the factual basis the Gate 1 entry gives for resolving
the E5 tolerance. Under the pre-registered per-quantity tolerances the outcome is unchanged. Whether
the Gate 1 entry needs an annotation is Sidh's call.

**Reported by:** Claude Code.


### 2026-10-23 — Provenance: E4/E5 ran under a sixth config hash, `59c7bedf…`, committed in `4d9f38b`

**Status:** FINDING (provenance), recorded by Claude Code. Append-only.

**The committed sidecars.** `reports/01_power_analysis_provenance.json` and
`reports/01b_baseline_validation_provenance.json` record:
- `git_commit_sha` = `5a309ac`;
- `config_hash` = `59c7bedf6a284b2097c07583fca1044aac5b9a9d508c35fd5fb3d77667728f86`;
- executed 2026-08-01 at 06:17 UTC (11:47 IST).

**Locating the config.** Hashing every historical `config/default.yaml` with `compute_config_hash`
gives:
- `59c7bedf…` is exactly the config committed in **`4d9f38b`** (11:53 IST, about 6 minutes after the
  runs);
- `5a309ac`'s own config hashes to `9c732558…`, which is E1/E3's.

So E4/E5 ran on an uncommitted working tree whose config was later committed in `4d9f38b`, while the
sidecar records HEAD as `5a309ac`. Earlier lists of historical config hashes named five
(`9c732558`, `eb89df79`, `30b803eb`, `7d6ccea5`, `00d1cb2d`), taken from the manuscript manifest, which
does not cover E4/E5. **`59c7bedf` is a sixth.**

**Touches a Gate 1 decision input? Yes — its provenance, not its values.** The E4/E5 reports are Gate 1's
evidence. The values Gate 1 rests on reproduce natively under `00d1cb2d`. The commit-level provenance
of those original runs is limited, though: their code and config entered git only after the run, in the
same commit as their results.

**Reported by:** Claude Code.


### 2026-10-23 — E4–E5 regenerated natively: deterministic on this machine; 60 of 62 committed numbers reproduced; no committed hashes existed

**Status:** REPORTED by Claude Code, per Sidh's 2026-10-23 instruction. This is the second stage of the
native-Windows reproduction audit (2026-10-15 amendment, pending confirmation). **No decision is taken
here.**

**Runs.** `kc power` (E4) and `kc baselines` (E5) ran on 2026-10-23, at `266badf` with config
`00d1cb2d…`, on Python 3.13.11 and Windows 11, in `E:\EDI-1\repo`. Wall-clock:

| command | run 1 | run 2 |
|---|---|---|
| `kc power` (E4) | 4 min 8 s (13 s startup + 3 min 55 s notebook) | 2 min 3 s |
| `kc baselines` (E5) | 13 s (4 s startup + 8 s notebook) | 20 s |

Commit headroom never fell below 12.42 GB (limit 38.18 GB).

**Byte level.** No earlier committed hash covers any E4 or E5 output: the manuscript manifest has no
E4/E5 entries, and the sidecars carry no table hashes. The 14 regenerated tables are recorded as
`first-recorded` in `reports/hashes/E4-E5.sha256.csv`.

**Determinism.** Each command ran twice, with run 1's outputs copied aside before run 2. Of 22 output
files, **16 are byte-identical**: all 14 tables and both PNG figures. The six differences are run
metadata only: `executed_utc` in the two sidecars; `/CreationDate` in the two PDFs; and in the two HTML
reports, `executed_utc`, the kernel's temp path in a warning, and one printed output split into two
output blocks.

**This shows determinism on this machine. It does not show reproduction of the original 2026-08-01
runs**, whose outputs were lost and were never hashed.

**Number level — 60 of 62 committed numbers reproduced**, compared against the E4 findings entry
(lines 681–723), the E5 findings entry (646–680), the E5 pre-registration (503–533) and the Gate 1
entry. The marginal precision, the per-mission table, the merge threshold, the bootstrap degeneracy and
all seven published E5 quantities with their stated tolerances reproduce. The two mismatches, the Gate 1
"0.001" wording and the `59c7bedf` provenance are each recorded in the four 2026-10-23 entries directly
above.

**Sidecars: not committed.** In each, only `git_commit_sha` (`5a309ac` → `266badf`), `config_hash`
(`59c7bedf…` → `00d1cb2d…`) and `executed_utc` differ. The originals were restored. The regenerated
copies are kept outside the repository, in `E:\EDI-1\regenerated_sidecars\`.

**Reported by:** Claude Code.


### 2026-10-24 — Pc pre-registration checklist items 1, 3 and 12 confirmed as facts on re-ingested data

**Status:** RECORDED by Claude Code, per Sidh's 2026-10-24 instruction. These are facts checked on inputs
only: no Pc engine run, no independent method, no validation code. They concern three
"[to be re-confirmed by Sidh]" items in the reconstructed Pc validation pre-registration (2026-10-14).
**That entry is not edited**, and the other ten items stay open.

Checked on 2026-10-23 against the data re-ingested by `kc ingest` (file hashes in
`reports/hashes/data_raw.sha256.csv`):
1. **Item 1 — per-band population split: CONFIRMED.**
   - Stratifying the 2,167 official-test target-defining CDMs (`data.official_test_target_cdms`) by
     reported log10 risk with E3's edges (`pc_spike.risk_strata_edges` = [−30, −15, −10, −6, 0]) gives:
     floor 1,673; (−30, −15] **108**; (−15, −10] **138**; (−10, −6] **98**; (−6, 0] 150.
   - The drafted split 108 / 138 / 98 holds, and the total matches.
2. **Item 3 — E3 row matching: CONFIRMED, on today's regenerated comparison table.**
   - All 100 rows of `reports/tables/e3_full_comparison.csv` are training-pool CDMs.
   - Each matches exactly one raw training row on `(event_uid, time_to_tca)`.
   - The stored `reported` value equals the raw `risk` exactly in 100 of 100.
   - **The table used is the one regenerated on 2026-10-23** (SHA-256 `4a2863cd…`, recorded as
     first-recorded in `reports/hashes/E1-E3.sha256.csv`), not the lost original. The regenerated E3
     reproduced every committed E3 number (2026-10-23 E1–E3 entry).
3. **Item 12 — `c_span` ≥ 2.0, the reason C2 was dropped: CONFIRMED.**
   - It holds for all 2,167 official-test target CDMs and all 162,634 training-pool CDMs.
   - The minimum is 2.0 in both, and no value is missing.

**Recorded by:** Claude Code.


### 2026-10-24 — Observation: E4's "half-width changes by <0.01 pp across calibration fractions" is a discrete-median artifact

**Status:** OBSERVATION by Claude Code. It is derived from the regenerated E4 numbers (2026-10-23, `266badf`,
config `00d1cb2d…`). **It is not a Gate 1 amendment.** It adds one point to the 2026-10-23 calibration-term
entry (`c4b5819`) without repeating its table.

**The point.**
- E4 reports precision as the **median** Clopper–Pearson half-width of k/150, where k is an integer.
- The `c4b5819` entry found the median simulated k is **135 at every calibration fraction**, so the
  median half-width is exactly CP(135, 150) = **5.1255 pp** at 10%, 20% and 30%.
- Because the median is a single integer outcome, this quantity **cannot respond to calibration size**
  unless the median k moves. The next values are CP(136, 150) = **4.9834 pp** (computed with
  `power.clopper_pearson_half_width_pp`) and CP(134, 150) = 5.2613 pp. The equality therefore says
  nothing about calibration size either way.

**Where the support actually lies.** The support for "precision is limited by the evaluation set, not the
calibration set" (E4 entry, lines 695–698) is the **quadrature calculation**, not the half-width
equality:
- √(cal² + test²) moves only from 2.585 to 2.496 pp as the calibration term falls from 0.825 to
  0.477 pp at nominal 90%;
- the test-set term, 2.449 pp, dominates throughout.

The `c4b5819` entry's sentence "the E4 conclusion '<0.01 pp' (in fact 0) holds" is accurate as
arithmetic, but it is not independent evidence for that conclusion.

**Recorded by:** Claude Code.


### 2026-10-24 — Observation: at exactly nominal coverage the half-width is 5.13 pp at any calibration size; near nominal, the 5 pp bar is met only above it

**Status:** OBSERVATION by Claude Code. It is derived from the regenerated E4 numbers. **It is not a Gate 1
amendment**: Gate 1 accepted 5.13 pp as sufficient and reports it as ±5.13 pp.

**The observation.**
- With n_HR = 150, an observed coverage of exactly nominal (90%, k = 135) gives a Clopper–Pearson
  half-width of **5.1255 pp**. That is a property of k and n alone, so it holds at every calibration
  size; the regenerated E4 shows it at all three fractions.
- Over all k from 0 to 150, the half-width is at most 5 pp only for **k ≥ 136** (CP(136, 150) =
  4.9834 pp; an observed coverage of **at least 90.67%, above nominal**) or for **k ≤ 14** (coverage
  ≤ 9.33%, the mirror case, irrelevant to a nominal-90% interval).
- **So at n_HR = 150, for any coverage near the nominal 90%, the pre-registered 5 pp bar could be met
  only if the observed coverage exceeded nominal.** No calibration size changes this.

**What this bears on.** It sharpens why Gate 1 found a 0.13 pp shortfall. The bar was not reachable at
nominal coverage with 150 high-risk events, whatever the calibration size. No decision follows from this
entry.

**Recorded by:** Claude Code.


### 2026-10-24 — Engine input-assembly approximation and the CDM standard

**Status:** FACTS ONLY, recorded by Claude Code per Sidh's 2026-10-24 instruction. Nothing is re-run. **E3's
and E14's conclusions stand as recorded.** No engine run, independent method or validation code was involved.

**1. What the engine does** (`src/kelvins_conformal/labelnoise/pc_foster.py`).
- **Docstring, lines 19–20:** "Each object's covariance is taken in a common RTN frame and summed directly
  (no inter-object frame rotation). This is the standard first-order treatment."
- **Lines 266–273:** `cov_t` and `cov_c` are each built as a 3×3 matrix by `position_covariance_rtn`
  (lines 49–66, "3x3 RTN position covariance from sigmas + position-position correlations").
- **Line 276:** `cov = (cov_t + cov_c) * float(covariance_scale)` — summed with no rotation between
  objects.
- **Lines 259–264:** the relative state is taken unchanged from `relative_position_{r,t,n}` and
  `relative_velocity_{r,t,n}`.
- **Line 278:** `hbr = 0.5 * (t_span + c_span)`.
- **Lines 280–282:** projection onto the plane perpendicular to the relative velocity.
- **E3 and E14 use this same assembly:**
  - E3: `00b_pc_spike.ipynb`, cell 11, `pf.recompute_pc_for_row(d, floor_sentinel=floor)`;
  - E14: `labelnoise/rescale.py`, lines 117–120, `recompute_pc_for_row(row, ..., covariance_scale=s)`.

**2. What the CDM standard specifies** (CCSDS 508.0-B-1, Blue Book, June 2013, including Technical
Corrigendum 2 of October 2021; read 2026-10-24).
- **§2.2, p. 2-1:** "Object1/Object2 covariances at TCA with respect to an object centered reference
  frame;" and "the relative position/velocity of Object2 with respect to an Object1 centered reference
  frame;"
- **p. 3-4:** "NOTE – Table 3-3 and table 3-4 will be used to define both Object1 and Object2 …"
- **Table 3-4, p. 3-9:** "Covariance Matrix in the RTN Coordinate Frame (see annex E for definition)".
- **Table 3-2, p. 3-3:** "The R component of Object2's position relative to Object1's position in the
  Radial, Transverse, and Normal (RTN) coordinate frame."
- **Annex E (informative), §E1, p. E-1** defines RTN as an "Object-centered coordinate system". It states
  the relative state "with components expressed in the Object1-centered RTN coordinate frame".
- **No sentence** in the text explicitly says that Object2's covariance is centred on Object2.

**3. What the dataset's sources say about frames — nothing.** Searched for frame, RTN, coordinate, ECI,
Object1 and CCSDS:
- **Dataset documentation** (`data/raw/raw_data/raw_data_2015-2019.txt`):
  - lines 29–30: "target refers to the ESA satellites while chaser refers to the space debris/object we
    want to avoid";
  - lines 44–49 and 60–80: components named radial, transverse (along-track) and normal (cross-track);
  - no frame and no Object1/Object2 mapping.
- **Kelvins paper** (arXiv:2008.03069v2):
  - §2, p. 3: the CDMs "are ascii files issued and distributed by the US-based Combined Space Operations
    Center (CSpOC)";
  - §3, p. 4: anonymisation transformed "position/velocity values in relative values … state with
    respect to the target";
  - no frame statement.
- **Zenodo record 10.5281/zenodo.4463683 description** (fetched 2026-10-24; the first request returned
  HTTP 403 "unusual traffic", and one retry succeeded): describes the dataset as CDMs "received by ESA
  from 2015 to 2019 … anonymised for distribution". **No frame statement and no Object1 mapping.**
- **Kelvins pages** (kelvins.esa.int/collision-avoidance-challenge/ and its data page, fetched
  2026-10-24): repeat the column documentation, including "target refers to the ESA satellites …". **No
  frame statement.**
- **kesslerlib/kessler** (FDL Europe 2020, a third-party library; README, `docs/*.rst`, `docs/index.md`
  and documentation notebooks, fetched 2026-10-24): **no frame statement.**
  - Its converter `kessler/data.py` (latest change `b80359304f`, 2025-04-24) maps `t_*` to
    `OBJECT1_C*` and `c_*` to `OBJECT2_C*`, and copies `relative_*` into CCSDS `RELATIVE_*` unchanged.
  - **This is kessler's own assumption in code, not documentation of the dataset. It does not verify
    either point.**

**4. Status.**
- **Whether the dataset's covariances and relative state follow the CCSDS conventions is unverified.**
  So is whether "target" is CCSDS Object1. None of the sources above settles either.
- If the dataset does follow the standard, line 276 adds two matrices expressed in different object-
  centred frames. **The effect of that on E3's agreement and on E14 is unmeasured.**

**5. How E3 and E14 depend on the engine**, quoted from the code.
- **E3's within-0.5 statistic** compares the engine's **absolute** floored log10 Pc with the reported
  `risk` (`00b_pc_spike.ipynb`, cell 11, lines 21–23):
  `comp["delta"] = comp["recomputed"] - comp["reported"]`, `comp["abs_delta"] = comp["delta"].abs()`,
  `comp["within_tol"] = comp["abs_delta"] <= TOL`.
  E14's `agreement_at_anchor` (`rescale.py`, lines 163–175) makes the same comparison at s = 1 over the
  eligible set.
- **E14's direct arm**, `"y_direct": np.maximum(unfloored, floor_sentinel)` (`rescale.py`, line 155),
  depends on the engine's **absolute** log10 Pc at scale s.
- **E14's anchored arm**, `y_anchored = np.where(anchored_defined, np.clip(y_reported + delta,
  floor_sentinel, 0.0), np.nan)` with `delta = unfloored - anchor` (lines 145–150), depends on the engine
  only through the **change** between scale s and s = 1. It is defined only where
  `np.isfinite(anchor) & (y_reported > floor_sentinel)` (line 140).
  - Both ends of that change are computed from the same assembled covariance and geometry. So the
    differencing cancels an offset common to both, but it does not by construction cancel an assembly
    effect that changes how log10 Pc responds to scaling.
  - That is a property of the formula, not a measured effect.

**Recorded by:** Claude Code.


### 2026-10-24 — PRE-REGISTRATION CONFIRMED (Sidh): Pc engine independent validation — checklist resolved, convention section replaced

**Status:** CONFIRMED by Sidh on 2026-10-24, recorded by Claude Code.
- **Committed before any validation code exists.**
- The reconstructed pre-registration (2026-10-14) is **not edited**. This entry resolves its
  "[to be re-confirmed by Sidh]" markers as set out below.
- `config/experiments/pc_validation.yaml`, which holds every numeric value, is updated in the same
  commit.
- No comparison has run, and none may run on any real event, real CDM or E3's sample until it is
  separately authorised.

**Checklist resolution** (numbering as in the 2026-10-23 checkpoint):

| # | term | resolution |
|---|---|---|
| 1 | per-band population split | **confirmed as fact** (2026-10-24 entry): 108 / 138 / 98 |
| 2 | draw procedure | **as drafted**: `default_rng(42)`, without replacement, strata in the listed order, uids sorted first |
| 3 | E3 row matching | **confirmed as fact**: 100 of 100 match on `(event_uid, time_to_tca)` with `reported == risk`, on the regenerated comparison table |
| 4 | E3 set reported separately | **as drafted**: a second set, not pooled |
| 5 | shared independent input assembly | **as drafted** |
| 6 | M1 tolerances | **as drafted** (`epsrel` 1e-10, `limit` 500), **plus**: non-convergence (quad `ier != 0`) is an **event-level failure** and is **never loosened afterwards** |
| 7 | M3 settings | **amended**: target relative SE **0.5%**. 1e6 samples, rerun once at 1e7 if missed. An event still above 0.5% at 1e7 is **"not informative"** for M3 |
| 8 | M2 settings | **as drafted**: chunks of 1e7, cap 1e8, stop at about 100 hits, a priori "not informative" if 100/Pc_M1 exceeds the cap; counted at relative SE ≤ 10%, judged within 3 SE |
| 9 | agreement rules | **amended**: engine evaluation errors **count as disagreements**; agreement **requires both M1 and M3** |
| 10 | RP4/M3 consequence wording | **deferred until after the result** |
| 11 | convention list | **replaced** by the convention section copied in full below, with C1 as a labelled negative control: exempt from the E3/E14 flag rule, governed by the insensitivity rule, with its per-stratum median change reported against +0.602 and **no pass/fail threshold** |
| 12 | C2 dropped | **confirmed as fact**: `c_span` ≥ 2.0 everywhere |
| 13 | mechanics | **as drafted**: unit tests on analytic cases first; one `kc` subcommand writing `pcv_*` tables; no change to the existing engine or pipeline |

**OPEN — not decided, and blocking classification only.** Item 9 requires agreement with **both** M1 and
M3. The checklist does not say how an event enters a stratum's agreement fractions when it has **no
valid independent value**: an M1 non-convergence (item 6), or an M3 "not informative" (item 7).
- `config/experiments/pc_validation.yaml` carries `missing_independent_value_policy: null`.
- The runner **refuses to classify** while it is null.
- Sidh decides this before any comparison is read. Nothing else depends on it.

**Implementation constants fixed now**, before any code or run, and recorded in the YAML:
- **M1 peak-search grid:** 2,001 points in t, used only to locate the peak that is factored out in log
  space and passed to quad as a breakpoint;
- **M3 draw chunk:** 1e6. It fixes the draw order from the per-event generator seeded 42 + sample index;
- **μ = 398600.4418 km³/s²** (WGS-84 GM), used only for C3's circular-orbit speed.

**Convention section (item 11), replacing §6 of the 2026-10-14 entry.** Copied in full from
`E:/EDI-1/scratch/proposed_convention_section.md` as confirmed. Its headings are demoted so they are not
read as log entries.

#### Convention sensitivity (§6) — as confirmed by Sidh on 2026-10-24

Drafted 2026-10-24 by Claude Code and confirmed by Sidh on 2026-10-24, with C1 set as a labelled negative
control. This section replaces §6 of the reconstructed pre-registration (2026-10-14). That entry is not
edited; this replacement is recorded in a new, dated, append-only entry, committed before any validation
code exists.

##### Disclosure

- **Where the conventions come from:** the CCSDS Conjunction Data Message standard (CCSDS 508.0-B-1,
  including Technical Corrigendum 2, October 2021), the dataset's own column documentation
  (`data/raw/raw_data/raw_data_2015-2019.txt`), and the Kelvins paper (Uriot et al., arXiv:2008.03069v2).
- **The outcome was known when the list was drafted.** E3's 65.0% within ±0.5 log10 (56.8% excluding
  floor-to-floor) was already known when C1, C3a/b and C4a/b were first drafted (2026-10-03 by that
  session's clock; that draft was lost before it was committed, so no git record of the date exists),
  and when this amendment was drafted. The list therefore cannot be called blind to the outcome it might move.
  What limits that exposure: each convention is justified only by the sources quoted below, all of them
  are run and reported, and none is adopted.

##### Sources (quoted from primary text, 2026-10-24)

| tag | source | text |
|---|---|---|
| S1 | CCSDS 508.0-B-1, §2.2, p. 2-1 | "Object1/Object2 covariances at TCA with respect to an object centered reference frame;" |
| S2 | CCSDS 508.0-B-1, §2.2, p. 2-1 | "the relative position/velocity of Object2 with respect to an Object1 centered reference frame;" |
| S3 | CCSDS 508.0-B-1, Table 3-2, p. 3-3 | "The R component of Object2's position relative to Object1's position in the Radial, Transverse, and Normal (RTN) coordinate frame. (See annex E for definition.)" (T, N and the velocity components are worded the same way) |
| S4 | CCSDS 508.0-B-1, p. 3-4 | "NOTE – Table 3-3 and table 3-4 will be used to define both Object1 and Object2 depending on the value of the keyword OBJECT which is specified in table 3-3." |
| S5 | CCSDS 508.0-B-1, Table 3-4, p. 3-9 | "Covariance Matrix in the RTN Coordinate Frame (see annex E for definition)" |
| S6 | CCSDS 508.0-B-1, Annex E (informative), §E1, p. E-1 | "RELATIVE_POSITION/RELATIVE_VELOCITY: Object2's position/velocity relative to Object1's position/velocity, calculated by taking the difference of the position and velocity vectors relative to the frame in which they are defined, with components expressed in the Object1-centered RTN coordinate frame at the time of closest approach." |
| S7 | CCSDS 508.0-B-1, Annex E, §E1, p. E-1 | "RTN Coordinate Frame: Object-centered coordinate system. The Object1-centered RTN coordinate frame: R (Radial) is the unit vector in the radial direction pointed outward from the center of the central body, T (Transverse) is the unit vector perpendicular to the R vector in the direction of the spacecraft velocity, and N (Normal) is the unit vector normal to the satellite's inertial orbit plane (in the direction of the satellite's angular momentum) that completes the right-hand coordinate frame (see figure E-1)." |
| D29–30 | dataset documentation, lines 29–30 | "Here, target refers to the ESA satellites while chaser refers to the space debris/object we want to avoid. … we replace t and c with the placeholder x." |
| D40–41 | dataset documentation, lines 40–41 | "max_risk_estimate: maximum collision probability obtained by scaling combined covariance" / "max_risk_scaling: scaling factor used to compute maximum collision probability" |
| D44–49 | dataset documentation, lines 44–49 | "relative_position_r: relative position between chaser & target: radial [m]" (likewise t, n, and relative_velocity_*) |
| D60–80 | dataset documentation, lines 60–80 | "x_sigma_r: covariance; radial position standard deviation (sigma) [m]"; "x_ct_r: covariance; correlation of transverse (along-track) position vs radial position" |
| D88 | dataset documentation, line 88 | "x_j2k_sma: semi-major axis [km]" |
| D90 | dataset documentation, line 90 | "x_span: size used by the collision risk computation algorithm (minimum 2 m diameter assumed for the chaser) [m]" |
| K3 | Kelvins paper, §3, p. 4 | "This involved transforming absolute time stamps and position/velocity values in relative values, respectively, in terms of time to TCA and state with respect to the target." |
| K3b | Kelvins paper, §3, p. 4 | "the maximum collision probability obtained by scaling combined target-chaser covariance" |
| Z | Zenodo record 10.5281/zenodo.4463683, description (fetched 2026-10-24; the first request returned HTTP 403 "unusual traffic", one retry succeeded) | "The dataset is a collection of Conjunction Data Messages (CDMs) received by ESA from 2015 to 2019. The CDMs have been anonymised for distribution." No frame statement and no Object1 mapping. |
| KP | kelvins.esa.int/collision-avoidance-challenge/ and its data page (fetched 2026-10-24) | Repeats the column documentation, including "Here, target refers to the ESA satellites while chaser refers to the space debris/object we want to avoid." No frame statement. |
| KK | kesslerlib/kessler README, `docs/*.rst`, `docs/index.md` and documentation notebooks (FDL Europe 2020, third-party; fetched 2026-10-24) | No frame statement. `docs/notebooks/basics.ipynb`: "we built a specific converter that takes care of the conversion from the Kelvins format to standard CDM format." |
| KC | kesslerlib/kessler `kessler/data.py`, `kelvins_to_event_dataset` (third-party **code**, latest change `b80359304f`, 2025-04-24) | `cdm['RELATIVE_POSITION_R'] = kelvins_cdm['relative_position_r']` (and T, N, and velocity components, copied unchanged); `cdm['OBJECT1_CR_R'] = kelvins_cdm['t_sigma_r']**2.`; `cdm['OBJECT2_CR_R'] = kelvins_cdm['c_sigma_r']**2.` This is kessler's own mapping assumption, not documentation of the dataset. |

None of the dataset documentation, the Kelvins paper, the Zenodo description, the Kelvins pages or the
kessler documentation names any reference frame or maps target or chaser to Object1/Object2. A search for
"frame", "RTN", "coordinate", "ECI", "Object1" and "CCSDS" finds nothing relevant. Only kessler's converter
code (KC) assumes a mapping: target to OBJECT1, and relative vectors carried over unchanged.

##### The conventions

All conventions run through the **engine** (`labelnoise/pc_foster.py`), changing its inputs only. C0
stays the engine baseline. Agreement is the fraction within ±0.5 log10 of `risk` (C0, C1, C3a, C3b) or
of `max_risk_estimate` (C4a, C4b), reported per set (official-test sample; E3's 100) and per stratum.

###### C0 — engine baseline (unchanged)
- **Source:** `pc_foster.py` lines 19–22 and 266–282; D90; D44–49; D60–80.
- **Premises:**
  1. Both objects' covariances and the relative vectors are in **one common frame**, and are summed
     directly (`cov = (cov_t + cov_c) * s`, line 276).
     - **Not verified, and contrary to the CCSDS convention:** S1/S4/S5 give each object's covariance in
       an object-centered RTN frame. If the Kelvins fields follow CCSDS, C0 omits the rotation between the
       target and chaser frames. This is the documented first-order approximation (lines 19–20).
  2. `x_span` is a diameter, so HBR = (t_span + c_span)/2.
     - **Partly supported:** D90 calls the chaser's 2 m floor a "diameter".
     - **Not verified for the target.**
- **Computation:** none new. This is the E3/E14 code path.
- **What its result changes:** nothing; it is the reference row.

###### C1 — NEGATIVE CONTROL: `x_span` read as a radius (HBR doubled)
- **Role:** a labelled **negative control**. It tests whether the within-0.5 agreement metric responds to a
  known, deliberate change in an input. It is **not** a candidate correction to the engine.
- **Source:** D90 ("size").
- **Premise:** "size" means radius, so HBR = t_span + c_span.
  - **Not verified, and weakly contradicted for the chaser** by D90's "minimum 2 m diameter". The target's
    "size" is unqualified.
- **Computation:** the engine with both spans doubled, which doubles HBR.
- **Stated expectation — to be checked by the run, not assumed:**
  - when the hard-body radius is small compared with the projected covariance, Pc ≈ (density at the
    origin) × πHBR²;
  - so doubling HBR multiplies Pc by about 4 and changes log10 Pc by about **+0.6** (log10 4 ≈ 0.602);
  - where HBR is not small compared with the covariance, or the miss is many sigmas out, the change can
    differ from 0.6.
  - The run reports the per-event distribution of log10 Pc(C1) − log10 Pc(C0), per stratum, and states
    how far it departs from 0.6.
- **What its result would change:** only what we know about the metric's sensitivity to HBR (see the
  decision rule, where C1 is exempt from the E3/E14 flag rule). No engine change and no E3/E14 change
  follow from it.

###### C3a / C3b — rotate the chaser covariance into the target's RTN frame
- **Source:** S1, S4, S5, S6, S7; D29–30; D44–49; D88; K3.
- **Premises:**
  1. **Each object's covariance is in its own object-centered RTN frame.**
     - **Verified from primary text** that CCSDS gives covariances "with respect to an object centered
       reference frame" (S1), "in the RTN Coordinate Frame" (S5), with one table per object (S4).
     - **Not verified:** CCSDS has no single sentence saying Object2's covariance is centred on Object2.
       S7 defines "Object-centered" RTN and gives only the Object1-centered example.
  2. **The Kelvins fields keep the CCSDS conventions after anonymisation.**
     - **Not verified.** K3 says positions and velocities became a "state with respect to the target",
       and is silent on covariance frames. Z, KP and KK are silent too.
  3. **The target is CCSDS Object1.**
     - **Not verified.** The Kelvins paper calls the target the "primary satellite" but never maps it to
       Object1. Z, KP and KK give no mapping.
     - kessler's converter (KC) **assumes** target = OBJECT1 and copies the relative vectors unchanged.
       That is a third party's coding choice, not evidence about the dataset.
  4. **Direction of the relative vectors.**
     - CCSDS gives Object2 relative to Object1 (S6). If the target is Object1, that is chaser − target,
       i.e. C3a.
     - D44–49 says only "between chaser & target", so C3b (target − chaser) is kept as the alternative.
     - **Not verified for this dataset.**
  5. **The rotation is approximated** with a circular orbit: target speed √(μ/a_t) along T, from D88
     (`t_j2k_sma`). This is an approximation, not a premise to verify.
- **Computation:**
  - estimate the crossing angle about R from the relative velocity and the circular speed;
  - rotate the chaser's 3×3 position covariance by that angle;
  - write it back as sigmas and correlations;
  - run the engine.
- **What its result would change:** whether the omitted frame rotation accounts for part of the
  recomputed-vs-reported disagreement, especially in the deep-tail strata.

###### C4a / C4b — the documented max-risk anchor
- **Source:** D40–41; K3b.
- **Premises:**
  1. `max_risk_estimate` = Pc(k·C) with k = `max_risk_scaling`, and C is the same combined covariance as
     the engine's.
     - **Verified as stated in D40–41 and K3b.**
     - **Not verified:** that ESA's combination equals the engine's direct sum.
  2. Whether k scales **variance** (C4a: covariance_scale = k) or **sigma** (C4b: covariance_scale = k²).
     - **Not stated anywhere. Not verified.**
- **Computation:** the engine with `covariance_scale` = k or k². Compared against `max_risk_estimate`.
  Rows with k ≤ 0 are excluded and counted.
- **What its result would change:**
  - which scaling semantics reproduce an ESA-computed quantity, which bears on E14's covariance-scale
    semantics (Q-LBL-02 resolved (a), variance scale);
  - an anchor for the combined-covariance assembly that does not depend on `risk`.

###### C2 — dropped
The 2 m chaser minimum is already applied in the data. `c_span` ≥ 2.0 holds in all 2,167 official-test
target CDMs and all 162,634 training CDMs (confirmed 2026-10-24).

##### Decision rule (fixed before running)

- Report every convention's within-0.5 agreement per set and per stratum, next to C0. **Adopt none.**
- **If any convention other than C1 changes overall within-0.5 agreement, in either set, by more than 10 percentage
  points relative to C0:**
  - report it as a **finding**;
  - **flag E3's partial-hold disposition** (Assumption A4: 65.0% against an 80% bar) for Sidh's review;
  - **flag E14** for Sidh's review, since its labels come from the same engine and the same C0 input
    assembly (`rescale.py:117–120`).
- **C1 (negative control) is EXEMPT from the E3/E14 flag rule above** (Sidh, 2026-10-24). It is governed
  only by these two rules:
  - **Insensitivity rule:** if C1 changes overall within-0.5 agreement, in either set, by **less than
    10 percentage points** relative to C0, report that **the within-0.5 metric is insensitive to HBR**:
    a doubling of the hard-body radius does not move it materially. A change of 10 pp or more is
    reported as measured, with no flag.
  - **Expectation report:** report the per-stratum **median** of log10 Pc(C1) − log10 Pc(C0) against the
    stated expectation of **+0.602** (log10 4), **with no pass/fail threshold**.
  - In neither case is the HBR reading changed.
- **C4a vs C4b** are reported side by side against `max_risk_estimate`. If they differ by more than
  10 pp, that is a finding on scaling semantics, flagged against E14's Q-LBL-02 resolution for Sidh's
  review.
- No convention result changes any engine code, any E3/E14 number, or any gate decision without a
  separate, recorded decision by Sidh.

**Confirmed by:** Sidh (2026-10-24). **Recorded by:** Claude Code.


### 2026-10-25 — Pc validation: YAML syntax defect and its fix; "accept 13" clarified; missing-value policy and seed streams set; the three implementation constants

**Status:** RECORDED by Claude Code on 2026-10-25 at Sidh's instruction. Insertion only; no earlier entry is edited.
- The 2026-10-14 reconstruction and the 2026-10-24 confirmation (`d181408`) stand as written, except as stated in (c).
- No validation step has run on any real event, real CDM or E3's sample. No `pcv_*` table exists.

#### (a) YAML syntax defect, 8d322fd to 002d783
- **Defect.** In `config/experiments/pc_validation.yaml`, the keys `dropped:` and `material_change_pp:` were indented as members of the `conventions:` list, which is invalid YAML.
  - The file failed to parse at both commits that carried it: `8d322fd` (reconstruction, parse error at line 73) and `d181408` (confirmation, parse error at line 105).
  - No code read the file before `002d783`, so no result depended on it.
- **Fix in `002d783`** (branch `pc-validation`): the two keys were lifted to top level and renamed `conventions_dropped:` and `conventions_material_change_pp:`. Two comment lines record the fix. The runner reads the new names.
- **Verified**, by comparing the committed blobs of `d181408` and `002d783` line by line, byte for byte:
  - blob SHA-256: `d181408` `cff62633969105dbee01e9e2b800dc2d5b77161dd38db25d3995372e009d77a1` (6,236 bytes); `002d783` `6c96025912c8fe69317b88f7423c88f46a79fc52b0cea4271a9f675a9e647c89` (6,464 bytes);
  - 106 of 108 lines unchanged and in order, including both moved C2 lines (`    - id: C2` and its `reason:` line), which are byte-identical;
  - **the two key lines are not byte-identical:** their key name and indentation changed. Every byte after each key is identical, so the value `10.0`, its alignment and its comment are unchanged, and `dropped:` still carries no inline value;
  - the only other added lines are the two comment lines;
  - **no value changed.**

#### (b) "accept 13" clarified (Sidh, 2026-10-25)
- Sidh's 2026-10-24 brief opened with "accept 13". The `d181408` entry read that as accepting **item 13** (the mechanics) as drafted.
- **Sidh's clarification: "accept 13" meant all 13 recommendations in the 2026-10-24 table.**
- Read against that table (the 13-row checklist resolution table in the 2026-10-24 confirmation entry), the clarification **changes no row.** Each row already records the resolution in the same brief, including:
  - the amendments to items 6, 7 and 9;
  - the replacement of item 11;
  - the deferral of item 10.

#### (c) Missing-value policy and seed streams (Sidh, 2026-10-25), set before any real-data run
Committed as `f71cf0d` on `pc-validation`, YAML only. The YAML's SHA-256 in git's canonical LF form (the committed blob) is `7c59124f9934cb89934e81b4cc90a3223e14f7ba9d85c4c9b2ae966260977a72`.
- **`agreement.missing_independent_value_policy: exclude`**, replacing the OPEN `null`.
  - An event with no valid M1 value (non-convergence) or no valid M3 value ("not informative") is excluded from that method's agreement fractions.
  - **Engine evaluation errors still count as disagreements.**
  - Excluded events are **listed per stratum** (`list_excluded_events_per_stratum: true`).
  - A stratum is classed **"not informative"** if more than 10% of its events lack an M1 or an M3 value (`not_informative_if_frac_missing_above: 0.10`).
- **Seed streams.** Each event's seed is `seed + seed_offset + sample index`.
  - M2 gets its own stream: `m2.seed_offset: 1000000`, which exceeds any sample index, so no M2 seed equals any M3 seed.
  - `m3.seed_offset: 0` restates M3's existing rule (42 + sample index).
- This closes the OPEN item in the 2026-10-24 confirmation entry. **Neither decision was taken after seeing any validation result.** No step had run on real data, and none has since.

#### (d) The three implementation constants fixed in d181408
- **μ = 398600.4418 km³/s²** (Earth's GM, WGS-84/EGM96 value).
  - Used only for C3a/C3b's circular-orbit target speed, √(μ/a_t).
  - **Reason:** it is the standard value for Earth-orbit work. The published alternatives differ from it by about 1e-8 relative, far below the error of the circular-orbit approximation itself, so the choice cannot move a result.
- **M1 peak-search grid: 2,001 points** (midpoints in t over (−π/2, π/2), spacing π/2001 ≈ 1.6e-3 rad).
  - Used only to locate the integrand's maximum. That maximum is factored out in log space and passed to quad as a breakpoint.
  - **Reason:** it does not set M1's accuracy, which comes from quad's `epsrel` 1e-10. It only has to land near the peak so that the scaled integrand neither overflows nor underflows. 2,001 evaluations per event is cheap.
  - A peak much narrower than the spacing could be missed. That would need a hard-body radius far larger than the covariance's scale, and none of the analytic tests reached it.
- **M3 draw chunk: 1e6.**
  - **Reason, memory:** a chunk holds about six float64 arrays of that length, roughly 50 MB at peak, well inside the commit limit whose exhaustion caused the earlier suite failures.
  - **Reason, structure:** it equals `n_samples`, so the base run is a single chunk.
  - **It is fixed, not free:** the chunk size decides how the generator's draws are split between the radius and angle variates, so changing it changes M3's numbers. Fixing it in advance makes M3 reproducible from (seed, n, chunk).

**Recorded by:** Claude Code, at Sidh's instruction (2026-10-25).


## Gate Outcomes

*(Populated at each gate: date, gate number, decision — GO / PIVOT / NO-GO, summary evidence, decided by.)*

### 2026-08-01 — GATE 1 (E1–E5 review): GO on marginal, PIVOT on group-conditional
**Decided by:** Sidh.
**Evidence reviewed:** `reports/01_power_analysis.html` (E4), `reports/01b_baseline_validation.html`
(E5), and the Phase 1 findings entry above, which remains the authoritative record of the
underlying analysis.

**GATE 1 DECISION — GO on marginal coverage analysis.**
Marginal precision (5.13 pp CI half-width at n_HR = 150) came within 0.13 pp of the pre-registered
5 pp bar. This is accepted as sufficient precision to proceed. It will be reported honestly
throughout as **±5.13 pp** rather than treated as a pass/fail cliff.

**GATE 1 DECISION — PIVOT on group-conditional coverage.**
**E13 (group-conditional calibration) is DROPPED from the project scope** — dropped outright, not
merged-and-shrunk. Rationale: the derived merge threshold (200 high-risk events per group) exceeds
the entire test set's high-risk count (150), so no threshold rescues this with the available data.
This does not affect Contributions 1, 2, or 3.

**Q-STAT-01 RESOLVED — nominal coverage levels.**
Levels tested = **{80%, 90%, 95%}**, with **90% as primary** throughout.

**Q-STAT-02 RESOLVED — success margin.**
The pre-registered 5 pp marginal precision bar is confirmed as the standing target; the achieved
5.13 pp is documented as meeting it in practice, with full reasoning preserved in the Phase 1
findings entry. *This entry supersedes only the PROPOSED status of that entry, not its underlying
analysis, which stands unaltered.*

**Q-CONF-02 RESOLVED — group merging rule.**
**Moot.** No group-conditional analysis proceeds on this dataset. The question is closed, not
merged at a threshold.

**E5 agreement tolerance RESOLVED.**
The 0.001 absolute-difference criterion is confirmed as adequate — all 7 published quantities
matched well within it. The E5 pre-registration entry's PROPOSED status is lifted.

**Consequences for the plan:** E13's row in `EXPERIMENT_PLAN.md` is marked SKIPPED (the row is
retained so the record of why it was planned and why it was dropped survives). Phase 2 (E6–E8)
proceeds.
**Supersedes:** the PROPOSED status of the E4 and E5 pre-registration entries above; neither
entry's analysis or reasoning is modified.

### 2026-09-16 — GATE 2 (E9–E11 review): GO, scoped to two-sided coverage
**Decision:** GO. Rule-derived weighted conformal restores TWO-SIDED marginal coverage on the
official test set (E10 0.858 → E11 0.926 at 90%; McNemar p = 5.6e-45; machinery validated at E9,
diagnostics clean). The exact-coverage claim is scoped to two-sided intervals. A secondary,
honest finding is logged: weighting does NOT restore one-sided (upper-bound) coverage for the
learned models (shift-driven, machinery independently validated), and persistence's one-sided
numbers are separately degenerate (a 65.9% zero-atom in its signed scores) — both excluded from
the manuscript's coverage claim. E12 (CQR) and Phase 4 (E14) may proceed; E13 remains SKIPPED
(Gate 1 PIVOT). Full entry in the RESOLVED section above.
**Decided by:** Sidh, at Gate 2.

### 2026-09-18 — GATE 3 (E11–E14 review): GO, venue tier Q2 confirmed as firm target
**Decision:** GO on Contribution 2. Venue tier locked at Q2 (*Advances in Space Research* primary,
*Journal of Space Safety Engineering* secondary), not contingent on Phase 5 results, to keep E15's
design and reporting from drifting toward a "Q1-worthy" narrative. Confirmed: A4's stratum-dependent
recomputation pattern replicated at 20× sample size (E3 n=100 → E14 n=2,167); the scoped-M7
restriction bites only via the risk-focus stratum and label censoring, not field availability
(0% missingness, KS p=1.0); narrow-interval methods show clean monotone coverage degradation under
covariance miscalibration (Spearman ρ = −1.00). Binding manuscript scoping: the flat persistence
curve (0.9667 at all seven grid points) must be reported as interval-width insensitivity, not
noise-robustness. New finding flagged forward, not resolved here: high-risk-conditional coverage is
poor for the narrow/informative methods (GBM ≈0.47, CQR ≈0.20–0.27) versus persistence's wide
intervals (≈0.96) — bootstrap CIs required on these three figures before they are final. Binding on
E15: must report high-risk-conditional performance as a primary lens. Full entry in the RESOLVED
section above.
**Decided by:** Sidh, at Gate 3.
