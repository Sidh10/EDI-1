"""E17 — robustness, consistency & gap-closure consolidation (Phase 5).

Responsibility: execute the three parts of the revised E17 specification.

  * **H1 — robustness.** Re-examine the project's headline results under reasonable
    alternative statistical choices: (i) the bootstrap's clustering assumption
    (Q-STAT-03c) via a mission-level cluster bootstrap, (ii) the weight-clipping cap
    (Q-SEL-03) — a confirmation that clipping stays untriggered under stricter
    triggers, not a live sweep, because k-hat never approached the trigger, and
    (iii) the declared multiple-comparison policy (Q-STAT-04) applied to the
    existing family.
  * **H2 — gap closure.** The one-sided CQR coverage-restoration cell, completing the
    {split, CQR} x {two-sided, one-sided} matrix. This is the only genuinely NEW
    scientific quantity in E17.
  * **H3 — synthesis.** Whether the five manifestations of the train/test high-risk
    imbalance share a per-event mechanism, with an explicit honest-null outcome if
    they do not.

Inputs:  E11/E12/E14/E15 outputs and machinery; the base learners and GBM quantile
         heads (refit deterministically from cached hyperparameters — no search).
Outputs: robustness tables, the completed coverage-restoration matrix, and the
         cross-experiment synthesis table.

Serves: EXPERIMENT_PLAN.md E17 (revised 2026-09-21).

Protocol: E17's revised specification. H2 matches E11/E12's coverage convention
exactly so the new cell is directly comparable to the other three; H3 introduces no
formal test (Q-STAT-04's single-primary-contrast policy) and reports association
descriptively.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import Config
from ..conformal import diagnostics as diag
from ..conformal.cqr import cqr_upper_bound, cqr_upper_scores
from ..conformal.split import absolute_residual_scores, signed_residual_scores, split_interval
from ..conformal.weighted import weighted_interval
from ..data import event_level_frame, load_events
from .conformal_runner import (
    base_predictions,
    build_weights,
    coverage_with_ci,
    cqr_quantile_levels,
    prepare_conformal_data,
)
from .decision_runner import _append, _fit_upper_heads

# The five manifestations of the Phase-2 train/test high-risk imbalance, in the order
# the Observations Log records them (DECISIONS.md 2026-09-20, updated 2026-09-21).
# H1's robustness checks are scoped to these learners (Sidh, 2026-09-21). MC-dropout /
# E8 is EXCLUDED: its hyperparameters were never cached under the current config hash, and
# re-searching now would fit a different model from the one E8 published, breaking
# like-for-like comparison with E8's own findings. The exclusion is reported in the E17
# output itself, not only in DECISIONS.md.
H1_LEARNERS: tuple[str, ...] = ("persistence", "gbm", "gru")
H1_EXCLUDED_LEARNERS: tuple[str, ...] = ("mc_dropout",)
H1_EXCLUSION_REASON = (
    "MC-dropout (the E8 Bayesian arm) is excluded from E17's H1 robustness checks: no "
    "e8_mcdropout hyperparameter cache exists under the current config hash, and running a "
    "fresh search would select hyperparameters E8 never used, so the arm would no longer be "
    "the model E8 reported (Sidh, 2026-09-21). H2 and H3 do not depend on this arm."
)

MANIFESTATIONS = (
    ("M1", "point-prediction collapse (E6/E7)", "event"),
    ("M2", "conditional-coverage collapse (E14)", "event"),
    ("M3", "matched-budget ranking collapse (E15)", "event"),
    ("M4", "grid-instrument distortion (E15 expanded)", "instrument"),
    ("M5", "asymmetric, partial grid fix (E15 extended grid)", "instrument"),
)


def robustness_progress_path(cfg: Config) -> Path:
    return Path(cfg.path("artifacts_dir")) / "e17_robustness_progress.log"


def _mission_clusters(cfg: Config, events: pd.DataFrame, uids: np.ndarray) -> np.ndarray:
    """Mission id per event, aligned to ``uids`` (the Q-STAT-03c cluster variable).

    Q-DATA-01 asks whether duplicate objects are identifiable; they are not, but
    ``mission_id`` IS carried per event, and Q-STAT-03c/Q-DATA-01 both name a
    mission-level cluster bootstrap as the sensitivity analysis to run regardless.
    """
    per_event = event_level_frame(events).set_index("event_uid")
    missing = [u for u in uids if u not in per_event.index]
    if missing:
        raise ValueError(f"{len(missing)} official-test uids have no mission_id; cannot cluster")
    return per_event.loc[uids, "mission_id"].to_numpy()


# --- H1 (i): cluster bootstrap on the headline coverage results ---------------------


def _headline_covered_indicators(cfg: Config, data, weights, preds: dict, level: float) -> dict:
    """Per-event covered indicators for the Gate-2 headline arms, on the supported region.

    Reproduces the E10 (naive) and E11 (rule-weighted) constructions exactly as
    ``conformal_runner`` builds them, and returns the 0/1 covered vector per arm so the
    SAME indicators can be fed to both the iid and the cluster bootstrap. Only the
    resampling scheme differs between the two — never the underlying quantity.
    """
    cal, test = data.subsets["calibration"], data.subsets["official_test"]
    sup = diag.positivity_partition(test["recency_ok"]).supported
    y = np.asarray(test["y"], dtype=float)[sup]
    alpha = 1.0 - level
    out = {}
    for lrn in H1_LEARNERS:
        p_cal = np.asarray(preds[lrn]["calibration"], dtype=float)
        p_te = np.asarray(preds[lrn]["official_test"], dtype=float)[sup]
        scores = {"upper": signed_residual_scores(cal["y"], p_cal),
                  "two": absolute_residual_scores(cal["y"], p_cal)}
        for sided, s_cal in scores.items():
            naive = split_interval(p_te, s_cal, alpha, sided=sided)
            wtd = weighted_interval(p_te, s_cal, weights.rule, alpha, sided=sided).interval
            out[(lrn, "E10_naive_official", sided)] = naive.covers(y).astype(float)
            out[(lrn, "E11_weighted_rule", sided)] = wtd.covers(y).astype(float)
    return out, sup


def gate2_verdict_table(cluster_tab: pd.DataFrame) -> pd.DataFrame:
    """Does rule-weighting restore two-sided coverage, per learner x level x scheme?

    A pure function of H1's cluster-bootstrap table. Every verdict comes from
    ``robustness.restoration_verdict``: the one-sided guarantee (coverage >= nominal) is
    primary, CI-containment is the labelled secondary comparison (Sidh, 2026-09-21: the
    containment rule was a specification bug that marked over-covering arms as failures).
    The CI bounds are carried alongside so every verdict is auditable from its row.
    """
    from ..robustness import restoration_verdict

    two = cluster_tab[cluster_tab["sided"] == "two"]
    rows = []
    for (lrn, level), g in two.groupby(["learner", "nominal"], sort=True):
        n = g[g["method"] == "E10_naive_official"]
        w = g[g["method"] == "E11_weighted_rule"]
        if n.empty or w.empty:
            raise ValueError(f"missing naive or weighted arm for {lrn} @ {level}")
        n, w = n.iloc[0], w.iloc[0]
        for scheme in ("iid", "cluster"):
            lo, hi = f"{scheme}_lo", f"{scheme}_hi"
            v = restoration_verdict(float(n[lo]), float(n[hi]), float(w[lo]), float(w[hi]), float(level))
            rows.append({
                "scheme": scheme, "learner": lrn, "nominal": level,
                "naive_coverage": float(n["coverage"]), "weighted_coverage": float(w["coverage"]),
                "naive_lo": float(n[lo]), "naive_hi": float(n[hi]),
                "weighted_lo": float(w[lo]), "weighted_hi": float(w[hi]),
                "weighted_over_covers": bool(w["coverage"] > level), **v,
            })
    return pd.DataFrame(rows)


def scheme_agreement(verdict_tab: pd.DataFrame, column: str = "verdict") -> pd.DataFrame:
    """iid vs cluster verdict per learner x level, for one criterion column."""
    p = verdict_tab.pivot_table(index=["learner", "nominal"], columns="scheme",
                                values=column, aggfunc="first")
    p["agree"] = p["iid"] == p["cluster"]
    return p.reset_index()


def run_h1(cfg: Config, *, seeds=None, n_boot: int | None = None, data=None, weights=None,
           fitted: dict | None = None, events=None, progress: Path | None = None) -> dict:
    """H1 — robustness of the headline results to three analysis choices."""
    from ..robustness import cluster_bootstrap_mean, holm_bonferroni

    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    primary = cfg.power.nominal_coverage_primary

    test = data.subsets["official_test"]
    sup = diag.positivity_partition(test["recency_ok"]).supported
    uids_sup = np.asarray(test["uids"])[sup]
    clusters = _mission_clusters(cfg, events, uids_sup)

    # --- (i) clustering assumption ---------------------------------------------
    rows = []
    for level in levels:
        per_seed: dict = {}
        for seed in seeds:
            ind, _ = _headline_covered_indicators(cfg, data, weights, fitted[seed][0], level)
            for key, covered in ind.items():
                per_seed.setdefault(key, []).append(covered)
        for (lrn, method, sided), inds in per_seed.items():
            covered = np.mean(np.stack(inds), axis=0)   # seed-averaged per-event indicator
            iid = coverage_with_ci(np.zeros_like(covered), _IndicatorInterval(covered),
                                   seed=cfg.seed, n_boot=n_boot)
            clu = cluster_bootstrap_mean(covered, clusters, n_resamples=n_boot, seed=cfg.seed)
            rows.append({
                "check": "cluster_bootstrap", "learner": lrn, "method": method, "sided": sided,
                "nominal": level, "coverage": float(covered.mean()),
                "iid_lo": iid["boot_lo"], "iid_hi": iid["boot_hi"],
                "cluster_lo": clu.lo, "cluster_hi": clu.hi,
                "iid_half_width": 0.5 * (iid["boot_hi"] - iid["boot_lo"]),
                "cluster_half_width": clu.half_width,
                "width_ratio": (clu.half_width / (0.5 * (iid["boot_hi"] - iid["boot_lo"]))
                                if iid["boot_hi"] > iid["boot_lo"] else np.nan),
                "n_events": clu.n_events, "n_clusters": clu.n_clusters,
                "largest_cluster_frac": clu.largest_cluster_frac,
            })
    cluster_tab = pd.DataFrame(rows)

    # Does the Gate-2 conclusion survive the clustering assumption? Derived as a pure
    # function of cluster_tab, so the same rule applies whether E17 is computed or
    # re-rendered from its tables (Sidh, 2026-09-21 criterion correction).
    verdict_tab = gate2_verdict_table(cluster_tab)

    # --- (ii) clipping cap ------------------------------------------------------
    clip_rows = []
    for name, wv in (("rule", weights.rule), ("classifier", weights.classifier)):
        k = diag.pareto_khat(wv.w)
        for trigger in (0.7, 0.5, 0.3):
            res = diag.conditional_clip(wv.w, khat_trigger=trigger)
            clip_rows.append({
                "check": "clipping_cap", "weights": name, "khat": k,
                "khat_band": diag.khat_band(k), "khat_trigger": trigger,
                "clipping_triggered": bool(res.clipped), "bound": res.bound,
                "clipped_fraction": res.clipped_fraction, "bias_delta": res.bias_delta,
                "n_effective": diag.effective_sample_size(wv.w), "n_calibration": int(wv.w.size),
            })
    clip_tab = pd.DataFrame(clip_rows)

    # --- (iii) multiple-comparison policy --------------------------------------
    # Q-STAT-04 declares ONE primary contrast (naive vs weighted marginal two-sided
    # coverage on the official test set) as formally tested, everything else
    # descriptive. This check confirms the primary conclusion survives Holm applied
    # across the widest family a reviewer might demand: the primary contrast plus
    # every per-learner two-sided contrast at every level. No new test is run — the
    # p-values are the McNemar p-values E11 already produced, reloaded.
    mcnemar_path = Path(cfg.path("tables_dir")) / "e11_primary_mcnemar.csv"
    if not mcnemar_path.exists():
        raise FileNotFoundError(
            f"E11's McNemar table is missing ({mcnemar_path}); E17 will not fabricate p-values"
        )
    mcn = pd.read_csv(mcnemar_path)
    pcol = next((c for c in mcn.columns
                 if c.lower() in ("p_value", "p", "pvalue", "mcnemar_p")
                 or c.lower().endswith("_p")), None)
    if pcol is None:
        raise ValueError(f"no p-value column in {mcnemar_path}; columns = {list(mcn.columns)}")
    holm = holm_bonferroni(mcn[pcol].to_numpy(float), alpha=0.05)
    # The family size is itself the finding: Q-STAT-04 authorises ONE formal contrast, and a
    # sweep of every committed table confirms exactly one p-value was ever recorded. With a
    # family of one, Holm is the identity, so no multiple-comparison correction of any kind
    # can alter the primary conclusion. That is a stronger statement than "it survived a
    # correction" — it says the declared policy was actually adhered to, and it is only
    # checkable because no other formal test was run.
    mc_tab = mcn.assign(p_adjusted_holm=holm["p_adjusted"], rejected_holm=holm["rejected"],
                        n_tests_in_family=holm["n_tests"], check="multiple_comparison",
                        holm_is_identity=bool(holm["n_tests"] == 1))

    excluded_tab = pd.DataFrame([{"learner": lrn, "scope": "H1 robustness checks",
                                  "included": False, "reason": H1_EXCLUSION_REASON}
                                 for lrn in H1_EXCLUDED_LEARNERS])
    return {"cluster_bootstrap": cluster_tab, "gate2_verdict": verdict_tab,
            "clipping": clip_tab, "multiple_comparison": mc_tab, "excluded_learners": excluded_tab,
            "meta": {"primary_level": primary, "n_clusters": int(np.unique(clusters).size),
                     "n_supported_events": int(sup.sum()), "cluster_variable": "mission_id",
                     "h1_learners": list(H1_LEARNERS),
                     "h1_excluded_learners": list(H1_EXCLUDED_LEARNERS),
                     "h1_exclusion_reason": H1_EXCLUSION_REASON,
                     "p_value_column": pcol}}


class _IndicatorInterval:
    """Adapter so an existing 0/1 covered vector can reuse ``coverage_with_ci``.

    ``coverage_with_ci`` takes an Interval and calls ``.covers(y)``; here the
    indicator is already computed (seed-averaged), so this returns it unchanged and
    reports no width. Using the same function keeps the iid arm of the comparison
    byte-for-byte the convention E11/E12 used, rather than a re-implementation.
    """

    def __init__(self, covered: np.ndarray):
        self._covered = np.asarray(covered, dtype=float)
        self.width = np.full(self._covered.shape, np.nan)

    def covers(self, _y):
        return self._covered


# --- H2: the one-sided CQR coverage-restoration cell --------------------------------


def run_h2(cfg: Config, *, seeds=None, n_boot: int | None = None, data=None, weights=None,
           fitted: dict | None = None) -> dict:
    """H2 — one-sided CQR coverage on the official test set, naive and rule-weighted.

    Completes the {split, CQR} x {two-sided, one-sided} coverage-restoration matrix.
    The construction is E15's already-validated ``cqr_upper_bound`` on the GBM
    quantile head at the nominal level; the coverage convention, the positivity
    restriction and the CI machinery are E11/E12's, unchanged, so the new cell is
    directly comparable to the three already filled.
    """
    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]

    cal, test = data.subsets["calibration"], data.subsets["official_test"]
    selft = data.subsets["self_test"]
    sup = diag.positivity_partition(test["recency_ok"]).supported
    y_te, y_self = np.asarray(test["y"], float)[sup], np.asarray(selft["y"], float)

    rows = []
    for seed in seeds:
        heads = fitted[seed][1]
        for level in levels:
            alpha = 1.0 - level
            head = heads[round(float(level), 6)]
            s_cal = cqr_upper_scores(cal["y"], head["calibration"])

            # (a) exchangeable self-test split: the E9/E12-selftest analog. No shift,
            #     no weights — isolates head miscalibration from selection bias.
            iv_self = cqr_upper_bound(head["self_test"], s_cal, alpha)
            rows.append(_h2_row("E17_cqr_upper_selftest", level, seed,
                                coverage_with_ci(y_self, iv_self, seed=seed, n_boot=n_boot)))
            # (b) official test, naive (unweighted).
            iv_naive = cqr_upper_bound(head["official_test"][sup], s_cal, alpha)
            rows.append(_h2_row("E17_cqr_upper_naive", level, seed,
                                coverage_with_ci(y_te, iv_naive, seed=seed, n_boot=n_boot)))
            # (c) official test, rule-weighted: the restoration attempt.
            iv_w = cqr_upper_bound(head["official_test"][sup], s_cal, alpha,
                                   weights=weights.rule.w, test_weight=weights.rule.test_weight)
            rows.append(_h2_row("E17_cqr_upper_weighted_rule", level, seed,
                                coverage_with_ci(y_te, iv_w, seed=seed, n_boot=n_boot)))
    per_seed = pd.DataFrame(rows)
    agg = (per_seed.groupby(["learner", "method", "sided", "nominal"])
           .agg(coverage_mean=("coverage", "mean"), coverage_sd=("coverage", "std"),
                n=("n", "first"), median_width_mean=("median_width", "mean"),
                cp_lo_mean=("cp_lo", "mean"), cp_hi_mean=("cp_hi", "mean"),
                boot_lo_mean=("boot_lo", "mean"), boot_hi_mean=("boot_hi", "mean"),
                frac_inf_width=("frac_infinite_width", "mean"), n_seeds=("seed", "nunique"))
           .reset_index())
    agg["gap_pp"] = 100.0 * (agg["coverage_mean"] - agg["nominal"])
    return {"per_seed": per_seed, "coverage": agg}


def _h2_row(method: str, level: float, seed: int, c: dict) -> dict:
    return {"learner": "gbm", "method": method, "sided": "upper",
            "nominal": level, "seed": seed, **c}


def coverage_restoration_matrix(cfg: Config, h2_coverage: pd.DataFrame) -> pd.DataFrame:
    """The {split, CQR} x {two-sided, one-sided} matrix, three cells reloaded + H2's.

    Cells 1-3 are read from the committed E9/E11 and E12 tables rather than
    recomputed, so the matrix reports exactly the numbers those experiments
    published. "Restored" means the rule-weighted arm's coverage interval contains
    the nominal level while the naive arm's does not.
    """
    tabs = Path(cfg.path("tables_dir"))
    primary = cfg.power.nominal_coverage_primary
    split_tab = pd.read_csv(tabs / "e9e11_coverage.csv")
    cqr_tab = pd.read_csv(tabs / "e12_coverage_all.csv")

    def cell(family, sided, naive_df, naive_m, wtd_df, wtd_m):
        def pick(df, method):
            r = df[(df.learner == "gbm") & (df.method == method)
                   & (df.sided == sided) & (df.nominal == primary)]
            if r.empty:
                raise ValueError(f"missing cell: {family}/{sided}/{method} at {primary}")
            return r.iloc[0]
        n, w = pick(naive_df, naive_m), pick(wtd_df, wtd_m)
        return {"family": family, "sided": sided, "nominal": primary,
                "naive_coverage": float(n.coverage_mean), "weighted_coverage": float(w.coverage_mean),
                "naive_gap_pp": float(n.gap_pp), "weighted_gap_pp": float(w.gap_pp),
                "change_pp": float(100 * (w.coverage_mean - n.coverage_mean)),
                "n": int(w["n"])}

    rows = [
        cell("split conformal", "two", split_tab, "E10_naive_official", split_tab, "E11_weighted_rule"),
        cell("split conformal", "upper", split_tab, "E10_naive_official", split_tab, "E11_weighted_rule"),
        cell("CQR", "two", cqr_tab, "E12_cqr_naive", cqr_tab, "E12_cqr_weighted_rule"),
        cell("CQR", "upper", h2_coverage, "E17_cqr_upper_naive", h2_coverage, "E17_cqr_upper_weighted_rule"),
    ]
    out = pd.DataFrame(rows)
    out["source"] = ["E9/E11", "E9/E11", "E12", "E17 (H2, new)"]
    return out


def _restoration_verdict(cfg: Config, matrix: pd.DataFrame, split_tab: pd.DataFrame,
                         cqr_tab: pd.DataFrame, h2: pd.DataFrame) -> pd.DataFrame:
    """Label each matrix cell restored / not restored, by CI containment of nominal.

    "Restored" requires the rule-weighted arm's Clopper-Pearson interval to contain
    the nominal level AND the naive arm's not to. Anything else is "not restored";
    a cell where BOTH contain nominal is labelled "no deficit to restore", which is
    a different statement and is not allowed to masquerade as a success.
    """
    primary = cfg.power.nominal_coverage_primary
    src = {("split conformal", "two"): (split_tab, "E10_naive_official", "E11_weighted_rule"),
           ("split conformal", "upper"): (split_tab, "E10_naive_official", "E11_weighted_rule"),
           ("CQR", "two"): (cqr_tab, "E12_cqr_naive", "E12_cqr_weighted_rule"),
           ("CQR", "upper"): (h2, "E17_cqr_upper_naive", "E17_cqr_upper_weighted_rule")}
    from ..robustness import restoration_verdict

    out = []
    for _, row in matrix.iterrows():
        df, nm, wm = src[(row.family, row.sided)]

        def ci(method, _df=df, _sided=row.sided):
            r = _df[(_df.learner == "gbm") & (_df.method == method)
                    & (_df.sided == _sided) & (_df.nominal == primary)].iloc[0]
            return float(r.cp_lo_mean), float(r.cp_hi_mean)

        n_lo, n_hi = ci(nm)
        w_lo, w_hi = ci(wm)
        v = restoration_verdict(n_lo, n_hi, w_lo, w_hi, float(primary))
        out.append({**row.to_dict(), "naive_ci": f"[{n_lo:.3f}, {n_hi:.3f}]",
                    "weighted_ci": f"[{w_lo:.3f}, {w_hi:.3f}]",
                    "naive_lo": n_lo, "naive_hi": n_hi, "weighted_lo": w_lo, "weighted_hi": w_hi,
                    **v})
    return pd.DataFrame(out)


# --- H3: is there a shared per-event mechanism behind the five manifestations? -------


def run_h3(cfg: Config, *, data=None, weights=None, fitted: dict | None = None,
           seeds=None) -> dict:
    """H3 — test for a common per-event diagnostic across the five manifestations.

    The candidate shared diagnostic is the per-event signed point-prediction residual
    on the official test set, seed-averaged: d_i = y_i - yhat_i for the GBM. The
    imbalance hypothesis says the learned models under-predict exactly the high-risk
    events, so d_i should be large and positive there and near zero elsewhere, and
    the SAME d_i should predict which events drive each manifestation.

    Structural limitation, stated up front rather than discovered later: only three
    of the five manifestations are event-level quantities at all. M4 (grid-instrument
    distortion) and M5 (the asymmetric partial fix) are properties of the threshold
    GRID and of a selection criterion over it -- they have no per-event membership to
    predict. A per-event diagnostic therefore cannot, even in principle, unify all
    five; the most it can do is unify M1-M3. This is reported as a limit on the
    claim, not worked around.
    """
    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    test = data.subsets["official_test"]
    sup = diag.positivity_partition(test["recency_ok"]).supported
    y = np.asarray(test["y"], float)[sup]
    hr = np.asarray(test["is_high_risk"], bool)[sup]

    # The shared diagnostic: seed-averaged signed residual of the GBM point prediction.
    resid = np.mean([np.asarray(fitted[s][0]["gbm"]["official_test"], float)[sup] for s in seeds], axis=0)
    d = y - resid

    # Per-event membership in each EVENT-LEVEL manifestation.
    # M1: the event is badly under-predicted by the learned point model (top decile of d).
    m1 = d >= np.quantile(d, 0.90)
    # M2: the event's two-sided weighted-conformal interval fails to cover it
    #     (the conditional-coverage collapse is measured by exactly this indicator).
    level = cfg.power.nominal_coverage_primary
    cal = data.subsets["calibration"]
    covers = []
    for s in seeds:
        p_cal = np.asarray(fitted[s][0]["gbm"]["calibration"], float)
        p_te = np.asarray(fitted[s][0]["gbm"]["official_test"], float)[sup]
        iv = weighted_interval(p_te, absolute_residual_scores(cal["y"], p_cal),
                               weights.rule, 1.0 - level, sided="two").interval
        covers.append(iv.covers(y).astype(float))
    m2 = np.mean(covers, axis=0) < 0.5      # uncovered by majority of seeds
    # M3: the event is a high-risk event the ranking misses at the operational threshold
    #     (persistence-free statement: the GBM point score fails to reach -6).
    m3 = hr & (resid < cfg.high_risk_threshold)

    members = {"M1": m1, "M2": m2, "M3": m3}
    rows = []
    for mid, mask in members.items():
        rows.append({
            "manifestation": mid, "level": "event", "n_members": int(mask.sum()),
            "diagnostic_mean_in": float(d[mask].mean()) if mask.any() else np.nan,
            "diagnostic_mean_out": float(d[~mask].mean()) if (~mask).any() else np.nan,
            "high_risk_share_in": float(hr[mask].mean()) if mask.any() else np.nan,
            "high_risk_share_out": float(hr[~mask].mean()) if (~mask).any() else np.nan,
            "point_biserial_r": float(np.corrcoef(d, mask.astype(float))[0, 1]),
        })
    for mid, _label, lvl in MANIFESTATIONS:
        if lvl == "instrument":
            rows.append({"manifestation": mid, "level": "instrument", "n_members": np.nan,
                         "diagnostic_mean_in": np.nan, "diagnostic_mean_out": np.nan,
                         "high_risk_share_in": np.nan, "high_risk_share_out": np.nan,
                         "point_biserial_r": np.nan})
    assoc = pd.DataFrame(rows).merge(
        pd.DataFrame(MANIFESTATIONS, columns=["manifestation", "description", "level_declared"]),
        on="manifestation", how="right").sort_values("manifestation").reset_index(drop=True)

    # Pairwise overlap among the three event-level manifestations: if one mechanism
    # drives all three, their member sets should overlap far more than chance.
    ov = []
    keys = list(members)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            A, B = members[a], members[b]
            inter = float((A & B).sum())
            expected = float(A.sum()) * float(B.sum()) / A.size
            ov.append({"pair": f"{a}&{b}", "n_a": int(A.sum()), "n_b": int(B.sum()),
                       "n_overlap": int(inter), "expected_if_independent": expected,
                       "lift": (inter / expected) if expected > 0 else np.nan,
                       "jaccard": float(inter / max((A | B).sum(), 1))})
    overlap = pd.DataFrame(ov)
    return {"association": assoc, "overlap": overlap,
            "meta": {"n_events": int(sup.sum()), "diagnostic": "signed GBM point residual y - yhat",
                     "event_level_manifestations": 3, "instrument_level_manifestations": 2}}



# --- orchestration ------------------------------------------------------------------


def run_e17(cfg: Config, *, seeds=None, n_boot: int | None = None) -> dict:
    """Execute E17 end to end. Deterministic given (config, seeds).

    One assembly pass fits the base learners and the GBM quantile heads once per seed
    (from CACHED hyperparameters — no search runs), and H1, H2 and H3 all read those
    same fitted objects. Nothing is refit per hypothesis.
    """
    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    head_levels = sorted({round(float(lv), 6) for lv in levels}
                         | {round(float(lv), 6) for lv in cqr_quantile_levels(levels)})
    path = robustness_progress_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    t0 = time.time()
    timings: dict = {}
    _append(path, f"E17 start: seeds {seeds}, levels {levels}")

    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)
    timings["assemble_s"] = round(time.time() - t0, 1)
    _append(path, f"assembled conformal data and weights in {timings['assemble_s']} s")

    fitted: dict = {}
    for seed in seeds:
        ts = time.time()
        _append(path, f"seed {seed}: fitting base learners")
        # learners= is what prevents the E8 search, not output filtering (decision item 7).
        preds = base_predictions(cfg, data, seed, learners=H1_LEARNERS)
        _append(path, f"seed {seed}: fitting GBM quantile heads at {head_levels}")
        heads = _fit_upper_heads(cfg, data, seed, head_levels)
        fitted[seed] = (preds, heads)
        timings[f"seed_{seed}_fit_s"] = round(time.time() - ts, 1)
        _append(path, f"seed {seed}: fitted in {timings[f'seed_{seed}_fit_s']} s")

    th = time.time()
    _append(path, "H1: cluster bootstrap, clipping cap, multiple-comparison policy")
    h1 = run_h1(cfg, seeds=seeds, n_boot=n_boot, data=data, weights=weights,
                fitted=fitted, events=events, progress=path)
    timings["h1_s"] = round(time.time() - th, 1)
    _append(path, f"H1 done in {timings['h1_s']} s")

    th = time.time()
    _append(path, "H2: one-sided CQR coverage-restoration backfill")
    h2 = run_h2(cfg, seeds=seeds, n_boot=n_boot, data=data, weights=weights, fitted=fitted)
    tabs = Path(cfg.path("tables_dir"))
    matrix = coverage_restoration_matrix(cfg, h2["coverage"])
    matrix = _restoration_verdict(cfg, matrix, pd.read_csv(tabs / "e9e11_coverage.csv"),
                                  pd.read_csv(tabs / "e12_coverage_all.csv"), h2["coverage"])
    timings["h2_s"] = round(time.time() - th, 1)
    _append(path, f"H2 done in {timings['h2_s']} s")

    th = time.time()
    _append(path, "H3: shared-diagnostic search across the five manifestations")
    h3 = run_h3(cfg, data=data, weights=weights, fitted=fitted, seeds=seeds)
    timings["h3_s"] = round(time.time() - th, 1)
    timings["total_s"] = round(time.time() - t0, 1)
    _append(path, f"H3 done in {timings['h3_s']} s; E17 total {timings['total_s']} s")

    return {
        "h1_cluster_bootstrap": h1["cluster_bootstrap"],
        "h1_gate2_verdict": h1["gate2_verdict"],
        "h1_clipping": h1["clipping"],
        "h1_multiple_comparison": h1["multiple_comparison"],
        "h1_excluded_learners": h1["excluded_learners"],
        "h2_coverage": h2["coverage"],
        "h2_per_seed": h2["per_seed"],
        "coverage_restoration_matrix": matrix,
        "h3_association": h3["association"],
        "h3_overlap": h3["overlap"],
        "meta": {"recomputed": True, "seeds": seeds, "n_boot": n_boot, "levels": levels,
                 "primary_level": cfg.power.nominal_coverage_primary,
                 "config_hash": cfg.config_hash, "timings": timings,
                 "h1": h1["meta"], "h3": h3["meta"]},
    }


# --- re-render from already-computed tables (no recomputation) ----------------------

# Tables E17 COMPUTES. Everything else it reports is DERIVED from these by pure functions,
# so a derivation fix (e.g. the 2026-09-21 criterion correction) can be applied without
# re-running the 2,873 s analysis.
COMPUTED_TABLES: tuple[str, ...] = (
    "h1_cluster_bootstrap", "h1_clipping", "h1_multiple_comparison",
    "h2_coverage", "h2_per_seed", "h3_association", "h3_overlap",
)
DERIVED_TABLES: tuple[str, ...] = ("h1_gate2_verdict", "coverage_restoration_matrix",
                                   "h1_excluded_learners")


def _parse_progress_timings(log_path: Path) -> dict:
    """Stage timings as recorded by the run that computed the tables."""
    import re

    timings: dict = {}
    if not log_path.exists():
        return timings
    text = log_path.read_text(encoding="utf-8")
    for pat, key in ((r"assembled conformal data and weights in ([\d.]+) s", "assemble_s"),
                     (r"H1 done in ([\d.]+) s", "h1_s"), (r"H2 done in ([\d.]+) s", "h2_s"),
                     (r"H3 done in ([\d.]+) s", "h3_s"), (r"E17 total ([\d.]+) s", "total_s")):
        m = re.search(pat, text)
        if m:
            timings[key] = float(m.group(1))
    for seed, secs in re.findall(r"seed (\d+): fitted in ([\d.]+) s", text):
        timings[f"seed_{seed}_fit_s"] = float(secs)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    timings["computation_log_first_line"] = lines[0] if lines else ""
    timings["computation_log_last_line"] = lines[-1] if lines else ""
    return timings


def load_e17(cfg: Config) -> dict:
    """Rebuild E17's result dict from the tables a completed run already wrote.

    Recomputes NOTHING. Loads the computed tables, re-derives the verdict tables through
    the same pure functions ``run_e17`` uses, and reconstructs the metadata. Fails loud
    if a table is missing or inconsistent with the current configuration — a re-render
    must never quietly present another run's numbers as this one's.
    """
    import hashlib

    from ..robustness import restoration_verdict  # noqa: F401  (documents the derivation path)

    tabs = Path(cfg.path("tables_dir"))
    missing = [t for t in COMPUTED_TABLES if not (tabs / f"e17_{t}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"cannot re-render E17: computed tables missing: {missing}")

    def _load(name: str) -> pd.DataFrame:
        # float_precision="round_trip": pandas' default fast parser can read a 17-digit
        # float back one ULP away from the double that was written. The re-render must
        # reproduce exactly what the computing run held in memory, so the exact parser
        # is used for the tables E17 computed.
        df = pd.read_csv(tabs / f"e17_{name}.csv", index_col=0, float_precision="round_trip")
        return df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")])

    res = {f"{t}": _load(t) for t in COMPUTED_TABLES}
    sha = {t: hashlib.sha256((tabs / f"e17_{t}.csv").read_bytes()).hexdigest() for t in COMPUTED_TABLES}

    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    cb = res["h1_cluster_bootstrap"]
    # Consistency: these must be the tables of the scope-restricted run (Sidh, 2026-09-21),
    # at this configuration's levels — not the aborted first launch, not another config.
    if set(cb["learner"]) != set(H1_LEARNERS):
        raise ValueError(f"h1_cluster_bootstrap covers {sorted(set(cb['learner']))}, expected "
                         f"{sorted(H1_LEARNERS)}; these are not the scope-restricted run's tables")
    if set(np.round(cb["nominal"], 6)) != set(np.round(levels, 6)):
        raise ValueError(f"table levels {sorted(set(cb['nominal']))} != config levels {sorted(levels)}")
    if set(np.round(res["h2_coverage"]["nominal"], 6)) != set(np.round(levels, 6)):
        raise ValueError("h2_coverage levels do not match the configuration")

    verdict = gate2_verdict_table(cb)
    matrix = coverage_restoration_matrix(cfg, res["h2_coverage"])
    matrix = _restoration_verdict(cfg, matrix, pd.read_csv(tabs / "e9e11_coverage.csv"),
                                  pd.read_csv(tabs / "e12_coverage_all.csv"), res["h2_coverage"])

    mc = res["h1_multiple_comparison"]
    pcol = next((c for c in mc.columns
                 if c.lower() in ("p_value", "p", "pvalue", "mcnemar_p") or c.lower().endswith("_p")), None)
    if pcol is None:
        raise ValueError(f"no p-value column in the multiple-comparison table: {list(mc.columns)}")

    assoc = res["h3_association"]
    n_events = int(cb["n_events"].iloc[0])
    timings = _parse_progress_timings(robustness_progress_path(cfg))
    return {
        "h1_cluster_bootstrap": cb,
        "h1_gate2_verdict": verdict,
        "h1_clipping": res["h1_clipping"],
        "h1_multiple_comparison": mc,
        "h1_excluded_learners": pd.DataFrame([{"learner": lrn, "scope": "H1 robustness checks",
                                               "included": False, "reason": H1_EXCLUSION_REASON}
                                              for lrn in H1_EXCLUDED_LEARNERS]),
        "h2_coverage": res["h2_coverage"],
        "h2_per_seed": res["h2_per_seed"],
        "coverage_restoration_matrix": matrix,
        "h3_association": assoc,
        "h3_overlap": res["h3_overlap"],
        "meta": {
            "recomputed": False,
            "source_table_sha256": sha,
            "seeds": sorted({int(s) for s in res["h2_per_seed"]["seed"]}),
            "levels": levels, "primary_level": cfg.power.nominal_coverage_primary,
            "config_hash": cfg.config_hash, "timings": timings,
            "h1": {"primary_level": cfg.power.nominal_coverage_primary,
                   "n_clusters": int(cb["n_clusters"].iloc[0]), "n_supported_events": n_events,
                   "cluster_variable": "mission_id", "h1_learners": list(H1_LEARNERS),
                   "h1_excluded_learners": list(H1_EXCLUDED_LEARNERS),
                   "h1_exclusion_reason": H1_EXCLUSION_REASON, "p_value_column": pcol},
            "h3": {"n_events": n_events, "diagnostic": "signed GBM point residual y - yhat",
                   "event_level_manifestations": int((assoc["level_declared"] == "event").sum()),
                   "instrument_level_manifestations": int((assoc["level_declared"] == "instrument").sum())},
        },
    }
