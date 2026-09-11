# CLAUDE.md

**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Audience:** Claude Code, operating under Sidh's supervision.
**Governing documents (in authority order, highest first):** PROJECT_KNOWLEDGE.md → SOFTWARE_ARCHITECTURE.md → EXPERIMENT_PLAN.md → OPEN_QUESTIONS.md → this file. If this file ever conflicts with PROJECT_KNOWLEDGE.md, PROJECT_KNOWLEDGE.md wins; flag the conflict, do not silently resolve it.

This file is read before any coding action. If a task instruction conflicts with this file, stop and ask rather than proceeding on the assumption the task instruction is more current.

---

## 1. Coding Philosophy

- **This is a scientific instrument, not a product.** The purpose of every line of code is to produce a number that will appear in a peer-reviewed paper and must survive a hostile reviewer. Correctness and provenance outrank elegance, cleverness, and speed.
- **Boring is correct.** Prefer the obvious, readable implementation over a clever one. No premature abstraction, no framework-building for hypothetical future needs.
- **Determinism over convenience.** Every stochastic process must be seeded. Every pipeline stage must be a pure function of (input data, config, seed, code version) — no hidden state, no wall-clock dependence, no unpinned dependency behavior.
- **Explicit over implicit.** No silent defaults for anything that affects a reported number (thresholds, cutoffs, seeds, tolerance bands). Every such value lives in a versioned config file, never hardcoded inline.
- **Small, reviewable units of work.** Implement one module or one experiment (per EXPERIMENT_PLAN.md's E-numbering) at a time. Do not implement ahead of the current gate.
- **Loud failure over silent degradation.** A pipeline that crashes on bad input is correct behavior. A pipeline that produces a plausible-looking wrong number is the worst possible outcome in this project.

## 2. Project Rules

- Work strictly within the scope of the current phase/gate as defined in EXPERIMENT_PLAN.md. Do not pre-build later-phase components "while you're in there."
- Do not introduce new project goals, contributions, or research questions. If you notice something interesting outside scope, log it in `DECISIONS.md` under an "Observations" heading — do not act on it.
- Do not choose between open design alternatives listed in OPEN_QUESTIONS.md on your own authority. Where a question is marked "blocks implementation," stop and surface it explicitly rather than picking a default.
- The three headline contributions (selection-bias-aware weighted conformal prediction; label-noise sensitivity analysis; decision-cost evaluation toolkit) are fixed. Any implementation choice that would reframe the project as something else (e.g., optimizing point-prediction accuracy as an end in itself) is out of scope even if it "improves the numbers."
- Treat `data/raw/` as physically and logically read-only after ingest (E0). Never write to it, never regenerate it silently, never "fix" a row in place.

## 3. Research Rules

- Every reported metric must be traceable to code, not typed in by hand into a report, table, or the manuscript.
- Never adjust a statistical procedure (threshold, calibration split, bootstrap count, multiple-comparison policy) after seeing its result on the official test set. If a procedure needs to change, that is a decision for Sidh, logged in `DECISIONS.md` with a timestamp, and it must be justified without reference to the result it would change.
- The official Kelvins test set is precious and single-use per experiment. Do not use it for exploratory analysis, hyperparameter tuning, or "just checking." Hyperparameter and model-selection decisions happen on the training pool's internal validation split only (see EXPERIMENT_PLAN.md E9 for the self-split used to validate methodology before touching the official test set).
- Any number that looks surprisingly good deserves more suspicion, not less. Check for leakage (Q-DATA-03 / feature dictionary), split contamination, and off-by-one cutoff errors before reporting it.
- Negative and null results are valid outputs. Do not iterate on a method until it "beats" a baseline; report what the pre-registered protocol actually produced.
- When implementing anything from the statistics literature (conformal prediction variants, bootstrap procedures, Pc computation), implement it against the cited paper's definition precisely, and cite the paper in a code comment at the point of implementation.

## 4. Testing Policy

- **The statistical core is mandatory-tested before it is trusted with real data.** This includes at minimum: `metrics.py` (challenge loss, coverage, PIT), `conformal/weighted.py`, `labelnoise/pc_foster.py`, and the event-level bootstrap utility. Each gets unit tests against hand-computed or analytically known toy cases before being run on the Kelvins data.
- No PR merges to `main` without: passing unit tests, a passing determinism check (same config + seed ⇒ byte-identical or numerically-identical-within-tolerance outputs), and a passing leakage check on any new feature.
- Baseline validation (EXPERIMENT_PLAN.md E5) is itself a test: the pipeline is not trusted for anything downstream until persistence/constant baselines match published challenge scores within a pre-agreed tolerance.
- Test data leakage explicitly: automated check that no event ID appears in more than one of {train, calibration, official-test, self-test}.
- CI runs a tiny-subset end-to-end smoke pipeline on every PR (not the full dataset) — this must stay fast (<10 minutes) and is a correctness check, not a performance benchmark.
- When a test fails, fix the code or the test — never suppress, skip, or loosen a tolerance to make a test pass without an explicit, logged reason.

## 5. Git Workflow

- `main` is protected. All work happens on feature branches named `phase{N}/{short-description}` or `exp/E{NN}-{short-description}` matching EXPERIMENT_PLAN.md numbering.
- One logical change per PR: one module, one experiment, or one bug fix. Do not bundle unrelated changes.
- Every PR must pass CI before merge. No direct pushes to `main`.
- Tag a release at every gate checkpoint (`gate1-power-analysis`, `gate2-weighted-conformal`, `gate3-label-noise`, `preprint-v1`, `submission-v1`) so any historical result is exactly reproducible from a tag.
- Never rewrite published/tagged history. Corrections happen as new commits, even for embarrassing mistakes — the fix and the mistake are both part of the reproducibility record.

## 6. Documentation Requirements

- Every module gets a module-level docstring stating: purpose, inputs, outputs, and which EXPERIMENT_PLAN.md experiment(s) it serves.
- Every function touching a statistical quantity (metric, interval, weight, p-value) documents its mathematical definition and cites the source (paper or PROJECT_KNOWLEDGE.md section) in its docstring, not just its parameters.
- Every notebook is paired with a rendered HTML report in `reports/`, generated headlessly (not "run once by hand and screenshotted"). A notebook that cannot execute top-to-bottom cleanly is broken, full stop.
- `DECISIONS.md` gets an entry for: every gate outcome, every resolution of an OPEN_QUESTIONS.md item, every deviation from the plan, and every "surprising result" investigation, each with a date and one-paragraph rationale.
- `README.md` stays current with: setup instructions, the one-command reproduction path, and the current phase/gate status.
- Config files are self-documenting: every key gets an inline comment explaining what it controls and why its default was chosen.

## 7. Implementation Order

Follow EXPERIMENT_PLAN.md's Execution Order Summary exactly. Do not skip ahead. Current binding order:

1. **Phase 0:** E0 (ingest) → E1 (audit) → E2 (feature dictionary) → E3 (Pc feasibility spike — do this early, not deferred; a late failure here is expensive).
2. **Phase 1 — Gate 1:** E4 (power analysis) and E5 (baseline validation) in parallel → **stop and wait for Sidh's Gate 1 decision.**
3. **Phase 2:** E6 (gradient boosting) → E7 (sequence model) → E8 (Bayesian baseline, steelmanned).
4. **Phase 3 — Gate 2:** E9 (conformal machinery validation) → E10 (naive conformal, demonstrate the bias problem) → E11 (weighted conformal, the fix) → **stop and wait for Gate 2 decision** → E12 (CQR) → E13 (group-conditional).
5. **Phase 4 — Gate 3:** E14 (label-noise sensitivity) → **stop and wait for Gate 3 (venue-tier) decision.**
6. **Phase 5:** E15 (decision-cost) → E16 (lead-time analysis) → E17 (robustness consolidation) → E18 (final figure/table consolidation).

Each phase's Claude Code brief is scoped by Sidh at the time; do not self-assign the next phase's work without an explicit brief, even if the current phase's tests all pass.

## 8. Commit Style

- Format: `<experiment-or-module-id>: <imperative summary, ≤72 chars>`, e.g. `E1: add selection-bias audit notebook`, `metrics: fix off-by-one in high-risk threshold`.
- Body (when needed): what changed, why, and what was verified (tests passing, tolerance matched, etc.). Reference the relevant EXPERIMENT_PLAN.md ID or OPEN_QUESTIONS.md ID where applicable.
- No commits with messages like "fix," "wip," or "update" alone. If a commit isn't describable in one clear line, it's probably bundling unrelated changes — split it.
- Every commit that changes a statistical procedure or a reported number's derivation must state what was true before and after, even in one sentence.

## 9. Experiment Protocol

- Before running an experiment from EXPERIMENT_PLAN.md, re-read its full specification (objective, hypothesis, split, failure/success criteria) — do not run from memory of a prior similar experiment.
- Confirm all listed dependencies (prior experiment IDs, resolved OPEN_QUESTIONS.md items) are actually satisfied before starting; if a dependency's resolution isn't recorded in `DECISIONS.md`, treat it as unresolved and stop.
- Record every run's config hash, git SHA, and seed set alongside its outputs automatically — never as a manual afterthought.
- Report results exactly as the specification's "Figures produced" / "Tables produced" fields define, with confidence intervals as specified — do not add or omit reported quantities on the fly.
- On a failure-criterion outcome, do not silently retry with different settings hoping for a better result. Stop, report the failure exactly as observed, and surface the pre-agreed fallback (if EXPERIMENT_PLAN.md specifies one) or ask.
- On a success-criterion outcome, still run the full specified diagnostic suite (coverage tests, bootstrap CIs, robustness checks) — passing the headline criterion is not a reason to skip the rest.

## 10. Forbidden Actions

- Never modify, delete, or "clean up" any file in `data/raw/`.
- Never touch the official Kelvins test set outside its designated single evaluation use per experiment (see §3).
- Never hardcode a number that should come from computation (a metric, a threshold derived from data, a p-value) directly into a report, README, or manuscript draft.
- Never loosen a test tolerance, skip a test, or comment out an assertion to make CI pass, without an explicit logged reason and Sidh's sign-off.
- Never introduce a new dependency without checking it against the license constraint (permissive licenses only, per PROJECT_KNOWLEDGE §10) and pinning its version.
- Never push directly to `main`, force-push over `main`, or rewrite tagged history.
- Never fabricate, extrapolate, or "smooth over" a missing data point — missingness is handled per the documented policy (Q-DATA-05) or the run fails loudly.
- Never make a design decision on an item flagged "blocks implementation" in OPEN_QUESTIONS.md without explicit resolution recorded in `DECISIONS.md`.
- Never claim in code comments, docstrings, or reports that a result is validated, significant, or publication-ready — that judgment belongs to Sidh and the eventual peer review, not to the implementation.
- Never proceed past a Gate (1, 2, or 3) without an explicit go/pivot decision recorded in `DECISIONS.md`.

## 11. Decision Hierarchy

When guidance conflicts or a choice is required, resolve in this order:

1. **Explicit safety/integrity invariants** (I1–I5 in SOFTWARE_ARCHITECTURE.md: immutable raw data, pure seeded functions, event-level statistics, provenance stamping, tested statistical core) — never overridden by anything below.
2. **PROJECT_KNOWLEDGE.md** — goals, non-goals, requirements, assumptions, constraints.
3. **Sidh's explicit instruction in the current session** — but only where it doesn't contradict tier 1 or 2; if it seems to, say so and ask rather than silently complying or silently refusing.
4. **SOFTWARE_ARCHITECTURE.md** — module boundaries, technology choices, folder structure.
5. **EXPERIMENT_PLAN.md** — what to run, in what order, with what criteria.
6. **OPEN_QUESTIONS.md recommendations** — used only as a tie-breaker for non-blocking questions; blocking questions always escalate to Sidh instead of defaulting to the recommendation.
7. **This file (CLAUDE.md)** — day-to-day operating procedure within all of the above.

If something is genuinely ambiguous even after checking this hierarchy, stop and ask. Guessing on a research-validity-relevant question is not acceptable even if the guess is probably right.

## 12. Repository Conventions

- Layout follows SOFTWARE_ARCHITECTURE.md §3 exactly: `data/{raw,processed}`, `src/kelvins_conformal/`, `notebooks/`, `reports/`, `tests/`, `config/`, `DECISIONS.md`.
- All configuration in `config/default.yaml` plus experiment-specific overrides in `config/experiments/*.yaml` — no scattered magic numbers in code.
- All environments pinned via `pyproject.toml` + lockfile (`uv`). No ad hoc `pip install` outside the declared dependency set.
- All CLI entry points go through the single `kc` command group (`kc ingest`, `kc audit`, `kc power`, `kc train`, `kc conformal`, `kc evaluate`, `kc reproduce-all`) — no bespoke one-off scripts living outside this structure.
- Naming: experiment-related code, configs, and reports are tagged with their EXPERIMENT_PLAN.md ID (`E11_weighted_conformal.py`, `03_conformal.ipynb`) so provenance is legible from filenames alone.
- Figures saved as both PNG and PDF to `reports/figures/`; tables as both Markdown and CSV to `reports/tables/` — human-readable and machine-readable versions of everything.
- `DECISIONS.md` is append-only in practice (entries may be annotated later but not deleted) — it is the reproducibility appendix and the project's memory.

## 13. Continuous Execution Loop Protocol

**Purpose:** allow a single stable instruction to drive execution across an entire phase (or a gate-bounded sub-phase) without a hand-written, experiment-specific prompt each time — while preserving every checkpoint and human-decision boundary defined elsewhere in this file. This section governs *what to work on next*; every other section still governs *how* that work is done.

**On every invocation of this protocol:**

1. Read, in order: this file (CLAUDE.md, in full), `DECISIONS.md` (in full — it is the authoritative record of what is actually resolved, not what a prior chat summary claimed), `EXPERIMENT_PLAN.md`'s Execution Order Summary table (including its Gate column), and `OPEN_QUESTIONS.md`'s blocking-summary section.
2. Determine the last experiment whose checkpoint is recorded complete in `DECISIONS.md`. The next candidate unit of work is the next experiment after it in `EXPERIMENT_PLAN.md`'s order.
3. Before executing anything, check whether the next candidate experiment is Gate-marked in the Execution Order Summary table, or whether reaching it requires an OPEN_QUESTIONS.md item marked "blocks implementation" that has no RESOLVED entry in `DECISIONS.md`:
   - **If yes, and no resolution is recorded** → STOP. Do not execute it, do not execute anything past it, and do not guess a default. Output only: (a) one paragraph on what was last completed, (b) exactly which gate or question is pending and why, (c) the evidence already on record relevant to that decision. Then wait — this is the same behavior already demonstrated correctly at Gate 1.
   - **If yes, and a resolution IS recorded in `DECISIONS.md`** → apply that resolution exactly as written, without re-litigating it, and proceed.
   - **If no gate or blocking question sits before it** → proceed to execute it.
4. Execute experiments in the batches `EXPERIMENT_PLAN.md` already scopes together (e.g., E0–E3, E4–E5, E6–E8, E9–E11, E12–E13, E14, E15–E18) — run the full batch in one invocation, then stop and produce a checkpoint, exactly matching the granularity used throughout this project so far. Do not execute past the end of the current batch into the next one, even if it looks unblocked, and even if a Gate-marked experiment inside the *current* batch (e.g., E11 within the E9–E11 batch) passed cleanly — stop for review at the batch boundary regardless.
5. All standing rules in §§1–12 apply without restatement or exception: seeded determinism, pre-registration before any comparison that could be adjusted by its result, suspicion of surprising results in either direction, single-use of the official test set, no scope drift beyond the current batch, multi-seed reporting with CIs, atomic writes, provenance stamping, the full test suite staying green.
6. Produce the same structured checkpoint format used in every phase so far (files created/modified, results with CIs, anomalies, explicit "what I am not deciding" section) — even when the outcome of this invocation is simply "stopped at a gate," so the human reviewer always receives a consistent, complete artifact regardless of why execution paused.
7. Never self-authorize crossing a Gate or resuming after a stop. A batch completing cleanly, or all tests passing, is never sufficient authorization on its own — only a `DECISIONS.md` entry recorded by Sidh authorizes proceeding past a gate.

**Standing invocation text (reusable verbatim, every time, in place of a bespoke prompt):**

> Continue the project per CLAUDE.md §13. Read current repo state and DECISIONS.md, execute the next eligible batch of work, and stop at the next gate, blocking question, or batch boundary — whichever comes first.

**What this changes and what it doesn't:** Sidh no longer needs a new hand-written prompt for routine, non-gated batches — Claude Code determines scope from the repo's own state. What does not change: every checkpoint this protocol produces is still reviewed (in the accompanying chat session) before the next invocation is given, gate decisions are still made by Sidh and logged in `DECISIONS.md` before the loop is allowed to cross them, and the loop confers no additional authority beyond what §§1–12 already grant.
