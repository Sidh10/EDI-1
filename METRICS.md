# METRICS.md

**Project:** Calibrated Collision Risk Forecasting for Satellite Conjunction Assessment
**Source:** Derived exclusively from PROJECT_KNOWLEDGE.md (Functional Requirements §7 module M3; Success Metrics §13; Glossary §16). No metric definitions are imported from other project documents.
**Scope note:** PROJECT_KNOWLEDGE.md specifies these evaluation quantities: the official challenge score, coverage (marginal and group-conditional), interval width, reliability/PIT calibration diagnostics, decision-cost evaluation (false-negative/false-positive under cost ratios), the label-noise sensitivity curve, and the bootstrap procedure underlying all of the above. This document expands each into a full specification.

---

## 1. Official Challenge Score (L)

- **Formula:**
  L = MSE_HR / F2
  where MSE_HR is computed only over events whose true final log-risk y ≥ τ (τ = −6, i.e., risk ≥ 1e-6), and F2 is the β=2 F-score of the high/low-risk classification induced by thresholding both true and predicted risk at τ.
- **Purpose:** The dataset's native scoring rule (per PROJECT_KNOWLEDGE §4/§7 FR3.1), reproduced to validate the evaluation harness and to provide a comparison point against every prior published result on this benchmark.
- **Interpretation:** Lower is better. It penalizes two failure modes jointly: poor recall/precision on identifying high-risk events (via F2 in the denominator — a low F2 inflates the loss) and poor regression accuracy specifically where it matters most, on events that are actually dangerous (via MSE_HR in the numerator).
- **Edge cases:** If F2 = 0 (model never correctly flags a true high-risk event, or flags none), L is undefined (division by zero) — must be handled explicitly (report as ∞ or excluded with a flag, never silently dropped). If there are zero true high-risk events in a subset (e.g., a small group), MSE_HR is undefined over an empty set — this subset cannot be scored with L at all.
- **Confidence intervals:** Bootstrap, event-level resampling (PROJECT_KNOWLEDGE §7 FR3.4), ≥2,000 resamples, reported as a percentile interval on L itself (recomputing both MSE_HR and F2 within each resample before dividing, not resampling the ratio directly).
- **Statistical meaning:** A composite, non-standard loss specific to this benchmark; it is not a probabilistic or calibration quantity and carries no coverage interpretation. It measures point-prediction quality only.
- **Expected direction:** Per PROJECT_KNOWLEDGE's stated context (the project's motivation notes that ML models on this benchmark struggle to clearly outperform a naive persistence baseline), L for our point predictors is expected to be close to, and not dramatically better than, the persistence baseline's L. A large, unexplained improvement is a signal to re-check for leakage before being reported as a finding.
- **Failure cases:** Denominator instability near F2 = 0 on small or heavily imbalanced subsets; the metric rewarding a model that is aggressive about flagging high-risk events (inflating F2) even if its risk-value regression is otherwise poor, since the two components are not independently weighted.

---

## 2. F2 Score

- **Formula:**
  F2 = (1 + β²) · (P · R) / (β² · P + R), with β = 2
  where P (precision) and R (recall) are computed from the binary high/low-risk classification obtained by thresholding true risk and predicted risk at τ = −6.
- **Purpose:** Isolates the classification (is-this-event-dangerous) component of the official score; used both as part of L and as a standalone diagnostic of high-risk detection quality (PROJECT_KNOWLEDGE §7 FR3.1).
- **Interpretation:** Ranges [0, 1], higher is better. The β=2 weighting deliberately values recall over precision — reflecting that missing a real high-risk event (false negative) is operationally worse than flagging a safe event as risky (false positive), consistent with the project's decision-cost framing (§7 FR3.3).
- **Edge cases:** Undefined when both P and R are zero (no positive predictions and no true positives) — must be handled as a defined convention (typically 0) rather than a silent NaN. Extremely small positive-class counts (few true high-risk events) make F2 highly discrete and unstable — a single misclassified event can swing F2 substantially.
- **Confidence intervals:** Bootstrap, event-level, ≥2,000 resamples, reported as a percentile interval; given the point above, this interval is expected to be wide in absolute terms whenever the high-risk count is small.
- **Statistical meaning:** A weighted harmonic mean of precision and recall; a threshold-dependent classification metric, not a probabilistic calibration statistic.
- **Expected direction:** Should exceed the naive persistence baseline's F2 by at least a modest margin if any model has learned real signal about which events are dangerous; per PROJECT_KNOWLEDGE's framing, large gains here are possible even when overall risk-value regression (MSE_HR) does not improve much.
- **Failure cases:** A model that predicts "high risk" for nearly everything can inflate recall (and thus F2) while being operationally useless (too many false alarms); F2 alone, without inspecting precision and the raw confusion counts, can be misleading.

---

## 3. MSE_HR (High-Risk Mean Squared Error)

- **Formula:**
  MSE_HR = (1 / n_HR) · Σ_{i : y_i ≥ τ} (ŷ_i − y_i)²
  computed in log-risk space, over the n_HR events whose true final risk is high-risk (y_i ≥ τ = −6).
- **Purpose:** Measures regression accuracy specifically where accuracy matters operationally — on events that are actually dangerous — rather than diluting error across the overwhelming majority of low-risk events (PROJECT_KNOWLEDGE §7 FR3.1).
- **Interpretation:** Lower is better; in squared log-risk units, so a value should be interpreted relative to the baseline's MSE_HR, not in isolation.
- **Edge cases:** Undefined if n_HR = 0 for the subset being scored (a real risk given the project's documented scarcity of high-risk events — PROJECT_KNOWLEDGE §12). Sensitive to outliers, since squaring amplifies large individual errors; a single badly mispredicted extreme event can dominate the statistic when n_HR is small.
- **Confidence intervals:** Bootstrap, event-level, restricted to resampling within the high-risk subset; PROJECT_KNOWLEDGE's stated power concern (§9 Assumption 5, §12) means this interval should be reported and inspected carefully, not assumed to be tight.
- **Statistical meaning:** A conditional mean squared error — conditional on class membership (true high-risk), not a marginal error statistic. It is a point-estimation quality measure with no calibration/coverage content.
- **Expected direction:** Expected to be difficult to improve substantially over the persistence baseline, per PROJECT_KNOWLEDGE's framing of this benchmark's known resistance to strong gains in point-prediction accuracy — the project's stated rationale for pursuing calibrated uncertainty rather than chasing this metric.
- **Failure cases:** With very few high-risk events, MSE_HR can be dominated by one or two hard cases, making model comparisons on this metric alone unreliable without accompanying confidence intervals; conflating "low MSE_HR" with "reliable risk estimates" is a category error the project explicitly avoids (PROJECT_KNOWLEDGE §2).

---

## 4. Empirical Coverage (Marginal)

- **Formula:**
  Ĉ(α) = (1 / n) · Σ_{i=1}^{n} 1{ y_i ∈ [lo_i, hi_i] }
  where [lo_i, hi_i] is the prediction interval for event i at nominal level (1 − α), and the target is Ĉ(α) ≈ 1 − α.
- **Purpose:** The project's central evaluation quantity — verifying whether stated uncertainty intervals actually contain the truth at the claimed rate (PROJECT_KNOWLEDGE §2's core problem statement, §7 FR3.2, §13 S1).
- **Interpretation:** A proportion in [0, 1]. Values close to the nominal level (1 − α) indicate valid, trustworthy intervals; values well below nominal indicate overconfident (too-narrow) intervals; values well above nominal indicate overly conservative (too-wide, operationally uninformative) intervals.
- **Edge cases:** With small n (e.g., a small evaluation subset), Ĉ(α) can only take a limited set of discrete values (multiples of 1/n), making fine-grained coverage claims meaningless below a certain sample size — precisely the concern behind the project's mandatory power-analysis gate (PROJECT_KNOWLEDGE §9 Assumption 5, §11).
- **Confidence intervals:** Bootstrap, event-level, ≥2,000 resamples (PROJECT_KNOWLEDGE §8, §7 FR3.4); this CI is itself the deliverable of the power-analysis gate and must accompany every reported coverage value — a bare coverage number is not an acceptable output per this project's standards.
- **Statistical meaning:** An estimate of a marginal probability under whatever data-generating process the evaluation set represents. Its validity as an estimate of the *conformal guarantee's* true coverage depends on the exchangeability assumption holding between calibration and evaluation data — which PROJECT_KNOWLEDGE explicitly flags as violated for the dataset's official test split (§2, §9 Assumption 2, §11 Technical Challenge 2), motivating the selection-bias correction that is the project's first contribution.
- **Expected direction:** Success metric S1 (PROJECT_KNOWLEDGE §13) sets the target explicitly: coverage of nominal 90% intervals within a power-analysis-determined margin of nominal, marginally and per group where statistically supported.
- **Failure cases:** Coverage estimated with insufficient precision (wide bootstrap CI) renders any pass/fail judgment uninterpretable — this is the project's single largest identified risk (PROJECT_KNOWLEDGE §14 R1) and the reason a dedicated feasibility gate exists before further investment.

---

## 5. Group-Conditional Coverage

- **Formula:**
  Ĉ_g(α) = (1 / n_g) · Σ_{i ∈ g} 1{ y_i ∈ [lo_i, hi_i] }
  computed identically to marginal coverage but restricted to events in group g (e.g., mission or merged orbit-regime group), subject to a minimum group-size threshold determined by the power analysis.
- **Purpose:** Marginal coverage can mask severe under-coverage within specific subpopulations; this metric addresses the documented fact that CDMs from different missions come from different distributions (PROJECT_KNOWLEDGE §4, §7 FR3.3/FR6.3, §5 goal 1).
- **Interpretation:** Same scale and target as marginal coverage, but interpreted per group; a group whose Ĉ_g(α) deviates substantially from nominal while the marginal Ĉ(α) looks fine is exactly the failure mode this metric is designed to expose.
- **Edge cases:** Groups with too few events (particularly too few high-risk events) yield uninterpretable, high-variance estimates; PROJECT_KNOWLEDGE (§7 FR6.3, §11 Technical Challenge 6) requires merging small groups or excluding them from group-conditional claims rather than reporting noise as signal. Anonymization of the dataset may leave no usable grouping key at all (§9 Assumption 5 risk, §14 R1's underlying concern extended to grouping).
- **Confidence intervals:** Bootstrap, event-level, computed independently per group, ≥2,000 resamples where group size allows a meaningful bootstrap distribution at all.
- **Statistical meaning:** A collection of conditional coverage estimates; achieving good marginal coverage does not imply good conditional coverage for any given subgroup — this is a known limitation of standard (non-group-aware) conformal methods that the project's group-conditional calibration (§7 FR6.3) is designed to address.
- **Expected direction:** Same target as marginal coverage, evaluated per eligible group; per PROJECT_KNOWLEDGE §13 S1, only reported "where statistically supported" — i.e., this metric is conditionally in scope, not unconditionally required.
- **Failure cases:** Reporting group-conditional coverage for underpowered groups gives false precision; PROJECT_KNOWLEDGE explicitly plans for the possibility that this metric may be reportable for zero groups, in which case the project's Assumption 5 / Gate decision scopes it out entirely rather than reporting misleading numbers.

---

## 6. Naive-vs-Weighted Coverage Gap (ΔCoverage)

- **Formula:**
  ΔC(α) = | Ĉ_naive(α) − (1 − α) | − | Ĉ_weighted(α) − (1 − α) |
  the reduction in absolute deviation from nominal coverage achieved by the selection-bias-aware (weighted conformal) method relative to the naive (unweighted) method, both evaluated on the official test set.
- **Purpose:** The direct, quantified evidence for the project's first headline contribution (PROJECT_KNOWLEDGE §5 goal 2, §13 S2): demonstrating that ignoring the dataset's documented selection bias produces invalid coverage, and that the correction restores it.
- **Interpretation:** A positive ΔC(α) indicates the weighted method's coverage is closer to nominal than the naive method's — the hypothesized and hoped-for outcome. A value near zero indicates the correction made little difference (would weaken, though not eliminate, the first contribution's evidentiary basis). A negative value would indicate the correction made coverage worse, which would require investigating the weighting implementation before proceeding.
- **Edge cases:** Both terms inherit all edge cases of empirical coverage (§4 above); ΔC is only meaningful when both Ĉ_naive and Ĉ_weighted are themselves estimated with adequate precision — an imprecise difference of two imprecise quantities compounds uncertainty.
- **Confidence intervals:** Must be computed via a joint or paired bootstrap over the same resampled events for both methods (not two independently bootstrapped intervals subtracted), so that the comparison correctly accounts for correlation between the two methods' errors on the same events.
- **Statistical meaning:** A differential estimate of estimator quality under known covariate shift; it directly operationalizes PROJECT_KNOWLEDGE's stated selection-bias problem (§2, §4) as a measurable quantity rather than a qualitative claim.
- **Expected direction:** PROJECT_KNOWLEDGE's success metric S2 (§13) explicitly expects and requires a "demonstrated, quantified coverage gap between naive and selection-bias-weighted conformal on the official test set" — i.e., ΔC(α) > 0 is the target result, and its magnitude is the headline finding.
- **Failure cases:** If the documented selection mechanism (§9 Assumption 2) does not fully describe the actual bias present, the weighting correction may only partially close the gap — PROJECT_KNOWLEDGE frames this as a residual-bias risk to be bounded and discussed (§9 Assumption 2's caveat), not assumed away.

---

## 7. Interval Width

- **Formula:**
  W = (1 / n) · Σ_{i=1}^{n} (hi_i − lo_i)
  the mean width of prediction intervals across evaluated events (also reported as a distribution, not only a mean).
- **Purpose:** Coverage alone is not sufficient to judge an uncertainty method — an interval that always spans the entire possible range trivially achieves any coverage target. Width measures whether achieved coverage is operationally useful (PROJECT_KNOWLEDGE §5 goal 1's "operationally meaningful" framing, §7 FR3.2).
- **Interpretation:** Narrower is better *at fixed coverage*; width and coverage must always be reported and interpreted together, never width alone.
- **Edge cases:** Degenerate methods can trivially minimize width by sacrificing coverage (always predicting a near-zero-width interval) or trivially maximize coverage by sacrificing width (predicting the full possible range) — PROJECT_KNOWLEDGE's requirement that intervals remain "operationally useful" (implicit in the decision-cost framing, §7 FR3.3) is the check against both failure modes.
- **Confidence intervals:** Bootstrap, event-level, ≥2,000 resamples, on the mean width statistic; the width distribution's shape (not only its mean) matters for judging heteroskedastic methods (e.g., CQR-style adaptivity) and should be reported alongside summary statistics.
- **Statistical meaning:** A measure of estimator efficiency/precision, complementary to but statistically independent of coverage validity; a method can be simultaneously valid (correct coverage) and inefficient (wide intervals), or invalid and falsely appear efficient (narrow but wrong).
- **Expected direction:** No absolute target is specified in PROJECT_KNOWLEDGE; the expectation is a meaningful width-vs-coverage tradeoff comparison across methods, with the project's decision-cost evaluation (§7 FR3.3) serving as the ultimate arbiter of whether achieved widths are useful.
- **Failure cases:** Reporting coverage improvements without simultaneously reporting whether width remained reasonable would overstate the practical value of the selection-bias correction — PROJECT_KNOWLEDGE's decision-cost requirement exists precisely to prevent this kind of incomplete claim.

---

## 8. Reliability Diagram Deviation

- **Formula:**
  RD = (1 / K) · Σ_{k=1}^{K} | Ĉ(α_k) − (1 − α_k) |
  the mean absolute deviation between empirical and nominal coverage across a grid of K nominal levels α_k (e.g., testing 80%, 90%, 95% intervals), visualized as a reliability diagram (empirical vs. nominal coverage plot) per PROJECT_KNOWLEDGE §7 FR3.2.
- **Purpose:** Summarizes calibration quality across the full range of confidence levels rather than at a single nominal level, giving a fuller picture of whether a method's uncertainty is trustworthy generally or only at one specific setting.
- **Interpretation:** RD near zero indicates good calibration across levels; systematic deviation in one direction (e.g., always under-covering) indicates a consistent miscalibration pattern rather than noise at a single level.
- **Edge cases:** Requires evaluating coverage at multiple α values on the same (necessarily limited) high-risk event pool, further dividing an already scarce resource (PROJECT_KNOWLEDGE §9 Assumption 5, §12) — the grid must be chosen with this scarcity in mind.
- **Confidence intervals:** Each point on the reliability diagram carries its own bootstrap CI (per §4 above); RD as a summary statistic should itself be bootstrapped rather than treated as a fixed value.
- **Statistical meaning:** An aggregate calibration-error measure, conceptually related to expected calibration error (ECE) used for classifier probability calibration, adapted here to interval coverage across confidence levels rather than binned predicted probabilities.
- **Expected direction:** Lower RD for conformal/weighted-conformal methods than for the heuristic Bayesian (MC-dropout) baseline is the qualitative expectation implied by PROJECT_KNOWLEDGE's motivating claim (§2, §4) that prior uncertainty methods on this task are "never verified" and, per the cited false-confidence literature, may be systematically miscalibrated.
- **Failure cases:** A reliability diagram built from too few high-risk events per α-level produces a noisy, uninterpretable curve rather than a genuine calibration signal — the same power concern (§11, §12) applies here as for single-level coverage, compounded across the grid.

---

## 9. PIT (Probability Integral Transform) Uniformity

- **Formula:**
  u_i = F̂_i(y_i)
  where F̂_i is the model's predicted cumulative distribution function for event i, evaluated at the true observed value y_i. Under perfect calibration, the set {u_i} is distributed Uniform(0, 1); deviation is typically tested via a Kolmogorov–Smirnov statistic comparing the empirical distribution of {u_i} to the uniform CDF.
- **Purpose:** A finer-grained calibration diagnostic than coverage at a few discrete nominal levels — checks calibration across the entire predictive distribution at once (PROJECT_KNOWLEDGE §7 FR3.2).
- **Interpretation:** A PIT histogram close to flat/uniform indicates good probabilistic calibration; a U-shaped histogram indicates underdispersed (overconfident) predictive distributions; an inverted-U (hump) shape indicates overdispersed (underconfident) predictions; skew indicates directional bias.
- **Edge cases:** Requires a full predictive distribution (not just a point prediction or a single interval), so it is only computable for methods that produce one (e.g., the Bayesian/MC-dropout baseline, or quantile-based methods interpolated into a distribution) — not directly applicable to bare point predictors.
- **Confidence intervals:** The KS test statistic has a known reference distribution under the null (uniformity) for sufficiently large samples; for the project's likely sample sizes, a bootstrap or permutation-based p-value is more appropriate than the asymptotic KS reference, consistent with the project's general preference for bootstrap-based uncertainty (PROJECT_KNOWLEDGE §8).
- **Statistical meaning:** PIT uniformity is a necessary condition for a predictive distribution to be well-calibrated in the probabilistic sense (stronger than mere interval coverage at one or two levels, since it checks the entire distribution shape).
- **Expected direction:** Per the project's framing (§2, §4), the MC-dropout baseline is expected to show detectable non-uniformity (evidence of the heuristic, unverified nature of its uncertainty), which is part of the paper's motivating evidence rather than an incidental finding.
- **Failure cases:** With few high-risk events, the PIT histogram/KS test has low power to detect real miscalibration, risking a false reassurance of "no evidence of miscalibration" that reflects insufficient data rather than genuine calibration — must be reported alongside sample size and power caveats.

---

## 10. Label-Noise Sensitivity (Coverage vs. Covariance-Scaling Factor)

- **Formula:**
  Ĉ(s, α) for s across a pre-declared grid of covariance-scaling factors, where labels (true final risk values) are recomputed under each scaling factor s applied to the CDM covariance fields before evaluating coverage as in §4/§5 above.
- **Purpose:** Directly answers the project's second headline research question (PROJECT_KNOWLEDGE §5 goal 3, §13 S3): how much does known miscalibration in the covariance-derived risk labels degrade the trustworthiness of any coverage claim built on those labels?
- **Interpretation:** A curve, not a single number. A flat curve (coverage insensitive to s) would indicate conclusions are robust to this specific data flaw; a steeply changing curve indicates coverage claims are fragile with respect to label quality and must be scoped accordingly.
- **Edge cases:** Depends entirely on the feasibility of recomputing collision probability from public CDM fields (PROJECT_KNOWLEDGE §9 Assumption 4, flagged as the project's largest single technical unknown, §11 Technical Challenge 1); if infeasible for the full test set, this metric is computed only on the subset where recomputation succeeds, with representativeness of that subset itself requiring separate verification (§9 Assumption 4's fallback).
- **Confidence intervals:** Bootstrap CI at each grid point independently, ≥2,000 resamples per point, since each point is itself a coverage estimate (§4 above) computed on a (potentially further-reduced) subset of events.
- **Statistical meaning:** A sensitivity analysis rather than a point estimate — characterizes how a conclusion's validity depends on an assumption (accuracy of the covariance-derived labels) rather than testing a single hypothesis.
- **Expected direction:** No specific direction is presumed in PROJECT_KNOWLEDGE; the project's stated goal (§5 goal 3) is to *quantify* the relationship, not to confirm a particular one — both "coverage degrades noticeably with label miscalibration" and "coverage is robust to it" are treated as valid, reportable findings.
- **Failure cases:** A non-monotone or noisy curve without adequate confidence bands at each grid point would be uninterpretable and could be mistaken for a real pattern; PROJECT_KNOWLEDGE's emphasis on honest reporting (§3 assumption-testing framing) requires the sensitivity curve to be reported with its uncertainty, not smoothed or cherry-picked at favorable grid points.

---

## 11. Decision-Cost Metric (False-Negative Rate / False-Positive Rate under Cost Ratio)

- **Formula:**
  Given a decision threshold applied to the calibrated interval's upper bound (or point prediction), each event is classified maneuver / no-maneuver. Then:
  FNR = (missed true high-risk events) / (total true high-risk events)
  FPR = (unnecessary maneuvers on true low-risk events) / (total true low-risk events)
  Total cost = c_FN · (count of false negatives) + c_FP · (count of false positives), for a pre-declared cost ratio c_FN : c_FP.
- **Purpose:** Translates statistical coverage/calibration quality into the operational consequence that actually matters to a satellite operator (PROJECT_KNOWLEDGE §5 goal 4, §7 FR3.3, §13 S4) — the project's third headline contribution.
- **Interpretation:** Lower total cost is better at a given cost ratio; FNR (missed collisions) and FPR (wasted maneuvers) trade off against each other as the decision threshold varies, and this tradeoff is the operationally meaningful object, not either rate in isolation.
- **Edge cases:** With very few true high-risk events, FNR is computed over a tiny denominator and each individual miss/catch swings the rate substantially — the same power concern as MSE_HR (§3 above) applies directly here. Cost ratios chosen arbitrarily can make almost any method look favorable or unfavorable; PROJECT_KNOWLEDGE requires evaluation "at ≥2 lead times and ≥2 cost ratios" (§13 S4) specifically to avoid a single, cherry-pickable operating point.
- **Confidence intervals:** Bootstrap, event-level, ≥2,000 resamples, on FNR, FPR, and total cost independently at each tested cost ratio and lead time.
- **Statistical meaning:** A cost-weighted classification-error decomposition; distinct from F2 (§2 above) in that it is explicitly parameterized by operator-relevant costs rather than a fixed β weighting, and it operates on decisions derived from calibrated intervals rather than on raw predicted risk values.
- **Expected direction:** PROJECT_KNOWLEDGE §13 S4 expects "calibrated methods dominating or matching uncalibrated baselines at equal alert budgets" — i.e., for a given rate of maneuvers triggered (alert budget), calibrated methods should catch at least as many true high-risk events as uncalibrated point-prediction or naive-Bayesian-uncertainty baselines.
- **Failure cases:** If calibrated intervals turn out too wide to ever change a decision relative to simpler baselines, this is treated in PROJECT_KNOWLEDGE as a valid, honestly reportable outcome (§12's framing that "too wide to be useful" is a legitimate finding), not a project failure — but it would substantially weaken the practical (as opposed to statistical) case for the method.

---

## 12. Bootstrap Confidence Interval (Statistical Apparatus)

- **Formula:**
  For a statistic θ̂ computed on the full event set, generate B ≥ 2,000 resamples by sampling events (not individual CDM rows) with replacement; recompute θ̂*_b on each resample; report the interval [θ̂*_{(⌈B·α/2⌉)}, θ̂*_{(⌈B·(1−α/2)⌉)}] as the percentile confidence interval, typically at the 95% level.
- **Purpose:** The uniform uncertainty-quantification mechanism underlying every metric above; required throughout by PROJECT_KNOWLEDGE §8 (Non-Functional Requirements: "bootstrap CIs (≥2,000 resamples) on all headline metrics") and §7 FR3.4.
- **Interpretation:** A wide bootstrap CI on any metric signals that the point estimate alone is not trustworthy for decision-making (e.g., for a Gate go/no-go call); a narrow CI signals a well-supported estimate given the available data.
- **Edge cases:** Resampling must occur at the event level, not the individual-CDM or individual-message level, since CDMs within an event are not independent observations (PROJECT_KNOWLEDGE's event-grouped data model, §7 FR2.1); resampling at the wrong level would understate true uncertainty. With very few high-risk events, bootstrap resamples can by chance contain zero high-risk events, making some resample-level statistics (e.g., MSE_HR, F2) undefined for that resample — must be handled explicitly (excluded and noted, not silently treated as zero).
- **Confidence intervals:** This entry *is* the confidence-interval mechanism; it does not itself require a further CI, but the choice of B (resample count) and the percentile-vs-other bootstrap variant (e.g., BCa) is itself a methodological decision that should be stated and justified once and applied consistently.
- **Statistical meaning:** A nonparametric method for estimating the sampling distribution of a statistic without assuming a parametric form (e.g., normality) — appropriate here because several of the project's target statistics (coverage proportions with few high-risk events, ratio metrics like L) are unlikely to be well-approximated by normal-theory intervals at the sample sizes involved.
- **Expected direction:** Not applicable (this is a supporting method, not a directional result); the expectation is procedural — consistent application across every reported metric, with no metric reported as a bare point estimate anywhere in the project's outputs (PROJECT_KNOWLEDGE §8's reproducibility requirement).
- **Failure cases:** Under-resampling (too few bootstrap iterations) produces unstable, non-reproducible interval bounds; resampling at the wrong grouping level silently understates uncertainty and would make every metric above look more precise than it actually is — given the project's central concern with statistical power (§9 Assumption 5, §11, §12, §14 R1), this would be a serious and easily overlooked error.
