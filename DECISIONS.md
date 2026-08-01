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
- **Q-CONF-01** (calibration unit: per event vs. per event-horizon) — must be fixed before Phase 3 conformal module design.
- **Q-SEL-01** (weight construction: rule-derived vs. estimated propensity vs. hybrid) — deferred to the Phase 3 design review with Sidh (per SOFTWARE_ARCHITECTURE.md Appendix B).
- **Q-STAT-01, Q-STAT-02, Q-CONF-02, Q-DATA-02** — resolved as outputs of Gate 1 (E4/E5).
- **Q-COMP-01** (hardware inventory) — resolved before Phase 2 planning.
- **Q-STAT-04, Q-SEL-03, Q-PUB-04** — resolved before Phase 3 runs (pre-registration).
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

## Observations Log

*(Per CLAUDE.md §2: interesting things noticed outside current scope get logged here, not acted on.)*

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

## Gate Outcomes

*(Populated at each gate: date, gate number, decision — GO / PIVOT / NO-GO, summary evidence, decided by.)*
