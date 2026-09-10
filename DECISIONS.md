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
- **Q-DATA-05 / Q-LBL-01** (missing-field policy; Pc recomputation feasibility) — resolved by the Phase 0 spike (E3); blocks labelnoise scope.
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
