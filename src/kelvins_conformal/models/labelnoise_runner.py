"""E14 — label-noise sensitivity of the Gate-2 coverage claim (Phase 4, Gate 3).

Responsibility: re-evaluate the ALREADY-FIT conformal machinery's coverage against
official-test labels regenerated under a covariance-scaling grid, and quantify how
far known covariance miscalibration moves the validity established at Gate 2. This
is Contribution 2.

Inputs:  the E9-E12 conformal core (`conformal/`), the E6 GBM learner, the E3 Pc
         engine via `labelnoise.rescale`, and `config.labelnoise`.
Outputs: coverage-vs-scaling curves with CIs, an M7 representativeness check, an
         anchor-agreement table, and the pre-registered failure-criterion verdict.

Serves: EXPERIMENT_PLAN.md E14.

Every protocol choice below is fixed by the 2026-09-16 E14 PRE-REGISTRATION entry
in DECISIONS.md, written before this module read the official test set
(CLAUDE.md §3). In particular:
  * SCOPED M7 (2026-09-16 Assumption-A4 / Q-LBL-01 resolution): complete-field
    subset; PRIMARY interpretive focus on the high-risk stratum, whose membership
    is fixed by the ORIGINAL reported label so the population cannot drift with s.
  * Evaluation-only (Q-LBL-03): no model is refit and calibration keeps its
    original labels; only official-test labels are regenerated.
  * Two label arms, direct and anchored, both declared in advance (see
    `labelnoise.rescale` for their definitions).
  * Trend statistics are DESCRIPTIVE: Q-STAT-04 spends the project's single formal
    confirmatory contrast on E10-vs-E11, so nothing here is a hypothesis test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..conformal import diagnostics as diag
from ..conformal.split import (
    Interval,
    absolute_residual_scores,
    split_interval,
)
from ..data import load_events, official_test_target_cdms
from ..labelnoise import rescale as rs
from .conformal_runner import (
    _gbm_params,
    _tab_view,
    build_weights,
    coverage_with_ci,
    cqr_quantile_levels,
    prepare_conformal_data,
)
from .runner import cached_search

# Methods E14 re-evaluates (pre-registration §6). Two-sided throughout, matching
# the Gate 2 decision's scoping of the coverage claim.
METHODS: tuple[str, ...] = ("E10_naive_official", "E11_weighted_rule", "E12_cqr_weighted_rule")
LEARNERS: tuple[str, ...] = ("persistence", "gbm")
ARMS: tuple[str, ...] = ("direct", "anchored")
POPULATIONS: tuple[str, ...] = ("m7_all", "m7_high_risk")


def _subset_interval(iv: Interval, mask: np.ndarray) -> Interval:
    return Interval(lo=np.asarray(iv.lo)[mask], hi=np.asarray(iv.hi)[mask])


# --- fitting: only what E14's declared method set needs ----------------------
def _fit_learners(cfg: Config, data, seed: int) -> dict:
    """Point predictions (+ GBM quantile heads) for the two declared learners.

    Deliberately does NOT call ``base_predictions``: that fits the GRU and the
    MC-dropout ensemble too, and the pre-registration excludes both from E14 for
    runtime. Fitting them anyway would burn hours producing numbers E14 has
    pre-committed not to report.
    """
    from . import gbm as gbm_mod
    from .runner import search_gbm

    cal, test = data.subsets["calibration"], data.subsets["official_test"]
    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]

    out: dict = {"persistence": {
        "calibration": cal["risk_last"].copy(),
        "official_test": test["risk_last"].copy(),
    }}

    budget = cached_search(cfg, "e6_gbm", cfg.seed,
                           lambda: search_gbm(cfg, _tab_view(data), seed=cfg.seed))
    params = _gbm_params(budget.best_params, seed)
    point, best_it = gbm_mod.fit_point_model(
        fit["tab_X"], fit["y"], val["tab_X"], val["y"], seed=seed, params=params,
        num_boost_round=cfg.gbm.num_boost_round,
        early_stopping_rounds=cfg.train.early_stopping_rounds,
    )
    out["gbm"] = {
        "calibration": np.asarray(point.predict(cal["tab_X"], num_iteration=best_it), float),
        "official_test": np.asarray(point.predict(test["tab_X"], num_iteration=best_it), float),
    }

    qlevels = cqr_quantile_levels(
        [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    )
    qmodels, qbest = gbm_mod.fit_quantile_models(
        fit["tab_X"], fit["y"], val["tab_X"], val["y"], qlevels, seed=seed, params=params,
        num_boost_round=cfg.gbm.num_boost_round,
        early_stopping_rounds=cfg.train.early_stopping_rounds,
    )
    out["_quantiles"] = {
        lvl: {
            "calibration": np.asarray(
                qmodels[lvl].predict(cal["tab_X"], num_iteration=qbest[lvl]), float),
            "official_test": np.asarray(
                qmodels[lvl].predict(test["tab_X"], num_iteration=qbest[lvl]), float),
        }
        for lvl in qlevels
    }
    out["_search_best_params"] = dict(budget.best_params)
    out["_search_from_cache"] = bool(getattr(budget, "from_cache", False))
    return out


def _intervals(cfg: Config, data, weights, preds: dict, level: float, sup: np.ndarray) -> dict:
    """The (method, learner) -> Interval map at one nominal level, in TEST order.

    E11 and CQR are defined on the supported region only (Q-SEL-03 positivity), so
    their arrays are expanded back to full test order with +/-inf outside it; the
    caller intersects with the M7 mask afterwards. Expanding with an infinite
    (vacuous) interval never manufactures coverage, because unsupported events are
    excluded from every E14 population anyway.
    """
    from ..conformal.cqr import cqr_interval, cqr_scores, enforce_monotone_quantiles

    cal, test = data.subsets["calibration"], data.subsets["official_test"]
    alpha = 1.0 - level
    n_test = test["y"].size
    out: dict = {}

    def _expand(iv: Interval) -> Interval:
        lo = np.full(n_test, -np.inf)
        hi = np.full(n_test, np.inf)
        lo[sup] = iv.lo
        hi[sup] = iv.hi
        return Interval(lo=lo, hi=hi)

    for lrn in LEARNERS:
        scores = absolute_residual_scores(cal["y"], preds[lrn]["calibration"])
        out[("E10_naive_official", lrn)] = split_interval(
            preds[lrn]["official_test"], scores, alpha, sided="two")
        out[("E11_weighted_rule", lrn)] = _expand(split_interval(
            preds[lrn]["official_test"][sup], scores, alpha, sided="two",
            weights=weights.rule.w, test_weight=weights.rule.test_weight))

    lo_l = round(alpha / 2, 6)
    hi_l = round(1.0 - alpha / 2, 6)
    q = preds["_quantiles"]
    qlo_c, qhi_c = enforce_monotone_quantiles(q[lo_l]["calibration"], q[hi_l]["calibration"])
    qlo_t, qhi_t = enforce_monotone_quantiles(
        q[lo_l]["official_test"][sup], q[hi_l]["official_test"][sup])
    out[("E12_cqr_weighted_rule", "gbm")] = _expand(cqr_interval(
        qlo_t, qhi_t, cqr_scores(cal["y"], qlo_c, qhi_c), alpha,
        weights=weights.rule.w, test_weight=weights.rule.test_weight))
    return out


# --- representativeness + agreement -----------------------------------------
def representativeness(
    elig: pd.DataFrame, high_risk_threshold: float, floor_sentinel: float
) -> pd.DataFrame:
    """M7-eligible subset vs. the FULL official test set (pre-registration §8).

    Mandated by the Assumption-A4 resolution: a scope restriction that is not
    quantified is an undisclosed change of estimand.
    """
    from scipy import stats

    full = elig["target_log_risk"].to_numpy(float)
    sub = elig.loc[elig["m7_eligible"], "target_log_risk"].to_numpy(float)
    ks = stats.ks_2samp(sub, full)
    rows = []
    for name, y in (("full_official_test", full), ("m7_eligible_subset", sub)):
        rows.append({
            "population": name, "n": int(y.size),
            "high_risk_prevalence": float(np.mean(y > high_risk_threshold)),
            "floor_mass": float(np.mean(y <= floor_sentinel)),
            "mean_log_risk": float(np.mean(y)),
            "q10": float(np.quantile(y, 0.10)), "median": float(np.median(y)),
            "q90": float(np.quantile(y, 0.90)),
        })
    out = pd.DataFrame(rows)
    out["ks_statistic"] = float(ks.statistic)
    out["ks_pvalue"] = float(ks.pvalue)
    return out


def anchor_agreement_by_stratum(
    agree: pd.DataFrame, edges, tolerance: float
) -> pd.DataFrame:
    """Recomputed-vs-reported agreement at s = 1, by reported-risk stratum.

    E3 measured this on a 100-CDM stratified sample; repeating it over every
    M7-eligible official-test event is what tells a reader whether the PARTIAL HOLD
    recorded for A4 also describes the population E14 actually uses. Strata are the
    pre-declared ``pc_spike.risk_strata_edges`` bands, reused rather than re-cut.
    """
    y = agree["target_log_risk"].to_numpy(float)
    d = agree["abs_delta"].to_numpy(float)
    edges = list(edges)
    rows = [{
        "stratum": f"floor (== {edges[0]:g})", "n": int(np.sum(y <= edges[0])),
        "median_abs_delta": float(np.median(d[y <= edges[0]])) if np.any(y <= edges[0]) else np.nan,
        "frac_within_tolerance": (float(np.mean(d[y <= edges[0]] <= tolerance))
                                  if np.any(y <= edges[0]) else np.nan),
    }]
    for lo, hi in zip(edges[:-1], edges[1:], strict=False):
        m = (y > lo) & (y <= hi)
        rows.append({
            "stratum": f"({lo:g}, {hi:g}]", "n": int(m.sum()),
            "median_abs_delta": float(np.median(d[m])) if m.any() else np.nan,
            "frac_within_tolerance": float(np.mean(d[m] <= tolerance)) if m.any() else np.nan,
        })
    rows.append({
        "stratum": "ALL", "n": int(d.size),
        "median_abs_delta": float(np.median(d)),
        "frac_within_tolerance": float(np.mean(d <= tolerance)),
    })
    return pd.DataFrame(rows)


def failure_criterion_check(
    cfg: Config, elig: pd.DataFrame, rep: pd.DataFrame, n_official_test: int
) -> pd.DataFrame:
    """EXPERIMENT_PLAN E14's failure criterion, as instantiated in advance (§11).

    Reported as a verdict table; Claude Code never switches to the Q-LBL-01 (c)
    fallback on its own authority (CLAUDE.md §9, §10).
    """
    fc = cfg.labelnoise.failure_criteria
    sub = elig[elig["m7_eligible"]]
    n_elig = int(len(sub))
    frac = n_elig / n_official_test if n_official_test else 0.0
    n_hr = int(np.sum(sub["target_log_risk"].to_numpy(float) > cfg.high_risk_threshold))
    prev_full = float(rep.loc[rep.population == "full_official_test", "high_risk_prevalence"].iloc[0])
    prev_sub = float(rep.loc[rep.population == "m7_eligible_subset", "high_risk_prevalence"].iloc[0])
    prev_diff_pp = abs(prev_sub - prev_full) * 100.0
    ks_p = float(rep["ks_pvalue"].iloc[0])
    ks_rejects = ks_p < fc.representativeness_ks_alpha
    unrep = bool(ks_rejects and prev_diff_pp > fc.representativeness_max_prevalence_diff_pp)
    too_small = bool(frac < fc.min_eligible_fraction or n_hr < fc.min_eligible_high_risk)
    return pd.DataFrame([{
        "criterion": "too_small", "threshold":
            f"frac >= {fc.min_eligible_fraction} AND n_high_risk >= {fc.min_eligible_high_risk}",
        "observed": f"frac = {frac:.4f}, n_high_risk = {n_hr}", "fires": too_small,
    }, {
        "criterion": "unrepresentative",
        "threshold": (f"KS p < {fc.representativeness_ks_alpha} AND prevalence gap > "
                      f"{fc.representativeness_max_prevalence_diff_pp} pp"),
        "observed": f"KS p = {ks_p:.4g}, prevalence gap = {prev_diff_pp:.3f} pp",
        "fires": unrep,
    }, {
        "criterion": "E14_FAILURE_CRITERION_MET", "threshold": "either of the above",
        "observed": f"n_eligible = {n_elig} / {n_official_test}",
        "fires": bool(too_small or unrep),
    }])


# --- descriptive trend statistics -------------------------------------------
def trend_statistics(coverage: pd.DataFrame) -> pd.DataFrame:
    """OLS slope of coverage on the scaling factor + Spearman rho, per curve.

    DESCRIPTIVE ONLY (pre-registration §9). The Q-STAT-04 resolution spends the
    project's single formal confirmatory contrast on E10-vs-E11, so no p-value
    produced here is a confirmatory test; the slope CI is the informative part.
    """
    from scipy import stats

    keys = ["arm", "population", "method", "learner", "nominal"]
    rows = []
    for key, g in coverage.groupby(keys, dropna=False):
        g = g.sort_values("scale")
        x = g["scale"].to_numpy(float)
        y = g["coverage_mean"].to_numpy(float)
        rec = dict(zip(keys, key, strict=False))
        if np.unique(x).size < 3 or not np.all(np.isfinite(y)):
            rows.append({**rec, "slope_per_unit_scale": np.nan, "slope_lo": np.nan,
                         "slope_hi": np.nan, "spearman_rho": np.nan, "n_grid": int(x.size)})
            continue
        lr = stats.linregress(x, y)
        tcrit = float(stats.t.ppf(0.975, df=max(x.size - 2, 1)))
        rho = stats.spearmanr(x, y).statistic
        rows.append({
            **rec,
            "slope_per_unit_scale": float(lr.slope),
            "slope_lo": float(lr.slope - tcrit * lr.stderr),
            "slope_hi": float(lr.slope + tcrit * lr.stderr),
            "spearman_rho": float(rho),
            "n_grid": int(x.size),
            "coverage_at_anchor": float(y[np.isclose(x, 1.0)][0]) if np.any(np.isclose(x, 1.0)) else np.nan,
            "coverage_range_pp": float(100.0 * (y.max() - y.min())),
        })
    return pd.DataFrame(rows)


# --- the run -----------------------------------------------------------------
def run_e14(cfg: Config, *, seeds=None, n_boot: int | None = None) -> dict:
    """Execute E14 end to end. Deterministic given (config, seeds)."""
    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)

    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    primary_level = cfg.power.nominal_coverage_primary
    floor = cfg.target.floor_sentinel_value
    thr = cfg.high_risk_threshold

    test = data.subsets["official_test"]
    uids = np.asarray(test["uids"])
    n_test = int(uids.size)
    sup = diag.positivity_partition(test["recency_ok"]).supported

    # --- labels: the target-defining CDM of each official-test event -----------
    target = official_test_target_cdms(cfg).set_index("event_uid").loc[uids].reset_index()
    elig_all = rs.eligibility(target)
    # The events table's reported label must match the private file's, or the two
    # halves of E14 are describing different quantities. Checked, not assumed.
    lab_delta = np.abs(elig_all["target_log_risk"].to_numpy(float) - test["y"])
    if np.nanmax(lab_delta) > 1e-9:
        raise ValueError(
            f"target-CDM labels disagree with the events table (max |delta| = "
            f"{np.nanmax(lab_delta):.3g}); E14 must not proceed on mismatched labels"
        )

    labels = rs.regenerate_labels(
        target, cfg.labelnoise.scaling_grid, floor_sentinel=floor,
        n_radial=cfg.labelnoise.n_radial, n_angular=cfg.labelnoise.n_angular,
    )
    elig_mask = elig_all["m7_eligible"].to_numpy(bool)

    # Events whose geometry fails, or whose anchored shift is undefined, are dropped
    # from the affected arm UNIFORMLY across scales, so no population drifts with s.
    at_anchor = labels[np.isclose(labels["scale"], 1.0)].set_index("event_uid")
    ok_direct = pd.Series(True, index=at_anchor.index) & ~at_anchor["failed"]
    ok_anchored = ok_direct & at_anchor["anchored_defined"]
    arm_ok = {
        "direct": _mask_for(uids, ok_direct, elig_mask),
        "anchored": _mask_for(uids, ok_anchored, elig_mask),
    }

    # Label matrices in TEST order: y[arm][scale] -> (n_test,) with NaN off-subset.
    wide = {arm: {} for arm in ARMS}
    col = {"direct": "y_direct", "anchored": "y_anchored"}
    for s in cfg.labelnoise.scaling_grid:
        chunk = labels[np.isclose(labels["scale"], s)].set_index("event_uid")
        for arm in ARMS:
            vals = np.full(n_test, np.nan)
            present = chunk.reindex(uids)[col[arm]].to_numpy(float)
            vals[:] = present
            wide[arm][float(s)] = vals

    # --- populations, fixed before any coverage is computed --------------------
    y_reported = test["y"]
    is_hr = y_reported > thr            # ORIGINAL label (pre-registration §7)
    n_threshold_ties = int(np.sum(y_reported == thr))
    pops = {
        "m7_all": np.ones(n_test, dtype=bool),
        "m7_high_risk": is_hr,
    }

    # --- fit once per seed, then sweep the grid --------------------------------
    rows = []
    search_params = None
    for seed in seeds:
        preds = _fit_learners(cfg, data, seed)
        search_params = preds["_search_best_params"]
        for lvl in levels:
            ivs = _intervals(cfg, data, weights, preds, lvl, sup)
            for (method, lrn), iv in ivs.items():
                for arm in ARMS:
                    base = sup & elig_mask & arm_ok[arm]
                    for pop_name, pop_mask in pops.items():
                        mask = base & pop_mask
                        if mask.sum() == 0:
                            continue
                        iv_m = _subset_interval(iv, mask)
                        for s in cfg.labelnoise.scaling_grid:
                            y_s = wide[arm][float(s)][mask]
                            if not np.all(np.isfinite(y_s)):
                                raise ValueError(
                                    f"non-finite regenerated label in arm {arm!r} at "
                                    f"scale {s} — population masking is wrong"
                                )
                            c = coverage_with_ci(y_s, iv_m, seed=seed, n_boot=n_boot)
                            rows.append({
                                "arm": arm, "population": pop_name, "method": method,
                                "learner": lrn, "nominal": lvl, "scale": float(s),
                                "seed": seed, **c,
                            })

    raw = pd.DataFrame(rows)
    agg = (raw.groupby(["arm", "population", "method", "learner", "nominal", "scale"])
           .agg(coverage_mean=("coverage", "mean"), coverage_sd=("coverage", "std"),
                n=("n", "first"), cp_lo_mean=("cp_lo", "mean"), cp_hi_mean=("cp_hi", "mean"),
                boot_lo_mean=("boot_lo", "mean"), boot_hi_mean=("boot_hi", "mean"),
                median_width_mean=("median_width", "mean"), n_seeds=("seed", "nunique"))
           .reset_index())
    agg["gap_pp"] = 100.0 * (agg["coverage_mean"] - agg["nominal"])

    rep = representativeness(elig_all, thr, floor)
    agree = rs.agreement_at_anchor(labels, elig_all)
    agree = agree[agree["event_uid"].isin(uids[elig_mask])]
    strata = anchor_agreement_by_stratum(
        agree, cfg.pc_spike.risk_strata_edges, cfg.pc_spike.tolerance.abs_log10_risk)

    return {
        "coverage_raw": raw,
        "coverage": agg,
        "trend": trend_statistics(agg),
        "representativeness": rep,
        "anchor_agreement": strata,
        "failure_check": failure_criterion_check(cfg, elig_all, rep, n_test),
        "eligibility": pd.DataFrame([{
            "n_official_test": n_test,
            "n_m7_eligible": int(elig_mask.sum()),
            "frac_m7_eligible": float(elig_mask.mean()),
            "n_supported": int(sup.sum()),
            "n_analysis_direct": int((sup & elig_mask & arm_ok["direct"]).sum()),
            "n_analysis_anchored": int((sup & elig_mask & arm_ok["anchored"]).sum()),
            "n_analysis_direct_high_risk": int((sup & elig_mask & arm_ok["direct"] & is_hr).sum()),
            "n_analysis_anchored_high_risk": int(
                (sup & elig_mask & arm_ok["anchored"] & is_hr).sum()),
            "n_label_exactly_at_threshold": n_threshold_ties,
        }]),
        "labels": labels,
        "meta": {
            "seeds": seeds, "levels": levels, "primary_level": primary_level,
            "scaling_grid": list(cfg.labelnoise.scaling_grid),
            "methods": list(METHODS), "learners": list(LEARNERS),
            "gbm_search_best_params": search_params,
            "n_boot": n_boot, "floor_sentinel": floor, "high_risk_threshold": thr,
        },
    }


def _mask_for(uids: np.ndarray, flags: pd.Series, elig_mask: np.ndarray) -> np.ndarray:
    """Lift a per-eligible-event boolean Series onto the full test-order mask."""
    out = np.zeros(uids.size, dtype=bool)
    lifted = flags.reindex(uids).fillna(False).to_numpy(bool)
    out[:] = lifted & elig_mask
    return out
