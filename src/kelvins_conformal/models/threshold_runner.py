"""Expanded E15 — threshold-based decision analysis (absorbs E16's lead-time dimension).

Responsibility: evaluate the operational rule "alert iff score >= t" over the
pre-registered threshold grid, for every point prediction and every validated bound,
and report missed high-risk events first and whole-population burden second, with
event-level bootstrap CIs. Also: cost-minimizing thresholds under the four
pre-registered read-outs, and the checks that make prediction P1 precise (P1a/P1b/P1c,
Corollary 4 of Proposition 1). Nothing here is a hypothesis test (D4).

Inputs:  the four Phase-2 base learners, the GBM quantile heads, the audited score
         constructions (``decision_runner.rank_audit_scores``), the decision core
         (``decision.py``), and ``config.threshold_analysis`` / ``config.decision_cost``.
Outputs: per-threshold decision tables, paired bound-minus-point differences,
         threshold-selection tables, P1 checks, operating curves, the grid, the
         excluded arms, and per-phase timings (for the runtime estimate).

Serves: EXPERIMENT_PLAN.md E15 (expanded; E16 merged).

Every protocol choice is fixed by the 2026-09-18 "PRE-REGISTRATION: expanded
threshold-based decision analysis" in DECISIONS.md, written before this module
existed (CLAUDE.md §3). The horizon set is PENDING Sidh's resolution of Q-METH-04
(pre-registration §0): only the challenge cutoff is accepted, and anything else
fails loudly.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import decision as dc
from ..config import Config
from ..conformal import diagnostics as diag
from ..conformal.weights import rule_derived_weights
from ..data import load_events
from .conformal_runner import (
    BASE_LEARNERS,
    base_predictions,
    build_weights,
    cqr_quantile_levels,
    prepare_conformal_data,
)
from .decision_runner import (
    CAVEAT,
    POINT,
    SEARCH_EXPERIMENTS,
    _append,
    _fit_upper_heads,
    _seed_mean,
    rank_audit_scores,
    search_integrity,
)

POINT_SIDED = "point"
READOUTS: tuple[str, ...] = (
    "selected_on_self_test",                 # §4 primary (deployable)
    "selected_on_self_test_rule_weighted",   # §4 secondary (deployable, shift-aware)
    "oracle_on_official_test_grid",          # §4 oracle (NOT deployable)
    "unrestricted_oracle_on_official_test",  # §4 unrestricted oracle (NOT deployable)
)
PERSISTENCE_ONE_SIDED_EXCLUSION = (
    "persistence's one-sided bound is degenerate: 65.9% of its signed calibration scores are "
    "exactly zero, so its 80th and 90th score percentiles coincide (Gate 2); excluded with "
    "disclosure, as everywhere else in the project"
)
THRESHOLD_CAVEAT = (
    CAVEAT + " Threshold rule: bounds and point predictions are compared on ONE grid defined in "
    "point-prediction space, so at a fixed threshold a bound alerts more (it sits above its point)."
)


def threshold_progress_path(cfg: Config) -> Path:
    return Path(cfg.path("artifacts_dir")) / "e15_threshold_progress.log"


def threshold_arms(data, weights, preds: dict, heads: dict, level: float, supported_test: np.ndarray,
                   *, exclude_persistence_one_sided: bool):
    """Every pre-registered arm's decision score on the self-test and official-test splits (§1).

    Returns ``(arms, excluded)``. ``arms[(method, learner, sided)]`` holds the score and
    the learner's point prediction on each split plus the structural class;
    ``excluded`` lists arms left out, each with its reason.
    """
    n_self = data.subsets["self_test"]["y"].size
    on_test = rank_audit_scores(data, weights, preds, heads, level, supported_test, split="official_test")
    on_self = rank_audit_scores(data, weights, preds, heads, level, np.ones(n_self, dtype=bool), split="self_test")
    arms: dict = {}
    excluded: list = []
    for lrn in BASE_LEARNERS:
        arms[(POINT, lrn, POINT_SIDED)] = {
            "official_test": np.asarray(preds[lrn]["official_test"], dtype=float),
            "self_test": np.asarray(preds[lrn]["self_test"], dtype=float),
            "point_official_test": np.asarray(preds[lrn]["official_test"], dtype=float),
            "point_self_test": np.asarray(preds[lrn]["self_test"], dtype=float),
            "structural_class": POINT,
        }
    for e_te, e_st in zip(on_test, on_self, strict=True):
        key = (e_te["method"], e_te["learner"], e_te["sided"])
        if exclude_persistence_one_sided and e_te["learner"] == "persistence" and e_te["sided"] == "upper":
            excluded.append({"method": key[0], "learner": key[1], "sided": key[2],
                             "reason": PERSISTENCE_ONE_SIDED_EXCLUSION})
            continue
        arms[key] = {
            "official_test": e_te["score"], "self_test": e_st["score"],
            "point_official_test": e_te["point"], "point_self_test": e_st["point"],
            "structural_class": e_te["structural_class"],
        }
    return arms, excluded


def unrestricted_optimum(score: np.ndarray, is_high_risk: np.ndarray, ratio: float) -> dict:
    """§9: the cost minimiser over every distinct finite score value, plus +inf (no alerts)."""
    s = np.asarray(score, dtype=float)
    candidates = np.r_[np.unique(s[np.isfinite(s)]), np.inf]
    return dc.cost_minimizing_threshold(s, is_high_risk, candidates, ratio)


def run_threshold_analysis(cfg: Config, *, seeds=None, percentiles=None, n_boot: int | None = None) -> dict:
    """Execute the pre-registered threshold-based analysis. Deterministic given (config, seeds).

    ``seeds``, ``percentiles`` and ``n_boot`` default to the pre-registered values; a
    smoke run passes a reduced set, and ``meta['reduced_configuration']`` records that.
    """
    ta = cfg.threshold_analysis
    if tuple(ta.horizons_days) != (float(cfg.cutoff.cutoff_days_before_tca),):
        raise NotImplementedError(
            "threshold_analysis.horizons_days other than the challenge cutoff is pending Sidh's "
            "resolution of Q-METH-04 (pre-registration §0)"
        )
    horizon = float(ta.horizons_days[0])
    path = threshold_progress_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    t0 = time.time()
    timings: dict = {}
    _append(path, "threshold analysis start: loading events and assembling conformal data")

    cache_root = Path(cfg.path("artifacts_dir")) / "search_cache"
    searches_cached_at_start = {
        exp: (cache_root / f"{exp}_{cfg.config_hash[:16]}_seed{cfg.seed}.json").exists()
        for exp in SEARCH_EXPERIMENTS
    }

    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)
    timings["load_data_and_weights_s"] = round(time.time() - t0, 1)

    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    percentiles = [float(p) for p in (percentiles if percentiles is not None else ta.grid_percentiles)]
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    primary_level = cfg.power.nominal_coverage_primary
    ratios = tuple(cfg.decision_cost.cost_ratios)
    head_levels = sorted({round(float(lv), 6) for lv in levels}
                         | {round(float(lv), 6) for lv in cqr_quantile_levels(levels)})
    reduced = (seeds != list(cfg.train.seeds)
               or percentiles != [float(p) for p in ta.grid_percentiles]
               or n_boot != cfg.bootstrap.n_resamples)

    selft, test = data.subsets["self_test"], data.subsets["official_test"]
    hr_te = np.asarray(test["is_high_risk"], dtype=bool)
    hr_st = np.asarray(selft["is_high_risk"], dtype=bool)
    n_te = int(hr_te.size)
    part = diag.positivity_partition(test["recency_ok"])
    sup = part.supported
    # §4 secondary / §9: shift-aware selection weights on self-test events, built exactly as the
    # Gate 2 calibration weights are (conformal_runner.build_weights).
    w_self = rule_derived_weights(
        selft["recency_ok"], selft["risk_last"],
        test_high_risk_prevalence=data.test_high_risk_prevalence,
        train_high_risk_prevalence=data.train_high_risk_prevalence,
        high_risk_threshold=cfg.high_risk_threshold,
        recency_epsilon=0.0,
    ).w

    # --- pass 1: fit (cached hyperparameters; the first seed runs any missing search) ---
    fitted = {}
    for seed in seeds:
        ts = time.time()
        _append(path, f"seed {seed}: fitting base learners")
        preds = base_predictions(cfg, data, seed)
        timings[f"seed_{seed}_fit_learners_s"] = round(time.time() - ts, 1)
        th = time.time()
        _append(path, f"seed {seed}: fitting GBM quantile heads at {head_levels}")
        heads = _fit_upper_heads(cfg, data, seed, head_levels)
        timings[f"seed_{seed}_fit_heads_s"] = round(time.time() - th, 1)
        fitted[seed] = (preds, heads)

    # --- the pre-registered grid (§2): calibration-split point predictions, all learners and seeds ---
    pooled = np.concatenate([np.asarray(fitted[s][0][lrn]["calibration"], dtype=float)
                             for s in seeds for lrn in BASE_LEARNERS])
    grid = dc.threshold_grid(pooled, percentiles, ta.operational_thresholds)
    T = grid["thresholds"]
    _append(path, f"grid: {T.size} thresholds ({grid['n_duplicates_removed']} duplicate percentile values removed)")

    dec_rows, pair_rows, sel_rows, p1_rows, curves = [], [], [], [], []
    excluded_arms: list = []
    n_alert_sets = 0
    for seed in seeds:
        ta0 = time.time()
        preds, heads = fitted[seed]
        W = dc.bootstrap_count_matrix(n_te, n_boot, seed)
        arms_by_level, keys, alert_sets = {}, [], []
        for lvl in levels:
            arms, excluded_arms = threshold_arms(
                data, weights, preds, heads, lvl, sup,
                exclude_persistence_one_sided=ta.exclude_persistence_one_sided,
            )
            arms_by_level[lvl] = arms
            for key, arm in arms.items():
                for t in T:
                    keys.append((*key, lvl, float(t)))
                    alert_sets.append(dc.threshold_alerts(arm["official_test"], t))
        A = np.vstack(alert_sets)
        n_alert_sets = int(A.shape[0])
        _append(path, f"seed {seed}: bootstrap, {n_alert_sets} alert sets x {n_boot} resamples")
        tb = time.time()
        ci = dc.bootstrap_decision_intervals(A, hr_te, ratios, W)
        timings[f"seed_{seed}_bootstrap_s"] = round(time.time() - tb, 1)
        index = {k: i for i, k in enumerate(keys)}

        # §3: per-threshold decisions, and paired bound-minus-point differences.
        for i, (method, lrn, sided, lvl, t) in enumerate(keys):
            point = dc.decision_metrics(dc.decision_counts(A[i], hr_te), ratios)
            row = {"seed": seed, "horizon_days": horizon, "method": method, "learner": lrn,
                   "sided": sided, "nominal": lvl, "threshold": t}
            for name, value in point.items():
                row[name] = value
                row[f"{name}_lo"] = float(ci[name]["lo"][i])
                row[f"{name}_hi"] = float(ci[name]["hi"][i])
            dec_rows.append(row)
            if method != POINT:
                ip = index[(POINT, lrn, POINT_SIDED, lvl, t)]
                for quantity in ("missed_high_risk", "unnecessary_maneuvers"):
                    d = dc.bootstrap_paired_difference(A[i], A[ip], hr_te, W, quantity=quantity)
                    pair_rows.append({
                        "seed": seed, "horizon_days": horizon, "method": method, "learner": lrn,
                        "sided": sided, "nominal": lvl, "threshold": t, "quantity": quantity,
                        "difference_vs_point": d["point"], "difference_lo": d["lo"], "difference_hi": d["hi"],
                    })

        for lvl, arms in arms_by_level.items():
            # §4: cost-minimizing thresholds under the four read-outs.
            chosen = {}
            for key, arm in arms.items():
                for r in ratios:
                    picks = {
                        "selected_on_self_test": dc.cost_minimizing_threshold(arm["self_test"], hr_st, T, r),
                        "selected_on_self_test_rule_weighted": dc.cost_minimizing_threshold(
                            arm["self_test"], hr_st, T, r, event_weights=w_self),
                        "oracle_on_official_test_grid": dc.cost_minimizing_threshold(arm["official_test"], hr_te, T, r),
                    }
                    for readout, pick in picks.items():
                        chosen[(key, r, readout)] = index[(*key, lvl, pick["threshold"])]
                    chosen[(key, r, "unrestricted_oracle_on_official_test")] = unrestricted_optimum(
                        arm["official_test"], hr_te, r)
            for (key, r, readout), val in chosen.items():
                method, lrn, sided = key
                point_val = chosen[((POINT, lrn, POINT_SIDED), r, readout)]
                base = {"seed": seed, "horizon_days": horizon, "method": method, "learner": lrn,
                        "sided": sided, "nominal": lvl, "ratio": r, "readout": readout}
                if readout == "unrestricted_oracle_on_official_test":
                    sel_rows.append({
                        **base, "threshold": val["threshold"], "cost": val["cost"],
                        "missed_high_risk": val["missed_high_risk"],
                        "unnecessary_maneuvers": val["unnecessary_maneuvers"], "n_alerts": val["n_alerts"],
                        "threshold_shift_vs_point": val["threshold"] - point_val["threshold"],
                        "cost_change_vs_point": val["cost"] - point_val["cost"],
                    })
                    continue
                ck = dc.cost_key(r)
                m = dc.decision_metrics(dc.decision_counts(A[val], hr_te), ratios)
                row = {
                    **base, "threshold": keys[val][4],
                    "cost": m[ck], "cost_lo": float(ci[ck]["lo"][val]), "cost_hi": float(ci[ck]["hi"][val]),
                    "missed_high_risk": m["missed_high_risk"],
                    "missed_high_risk_lo": float(ci["missed_high_risk"]["lo"][val]),
                    "missed_high_risk_hi": float(ci["missed_high_risk"]["hi"][val]),
                    "unnecessary_maneuvers": m["unnecessary_maneuvers"],
                    "unnecessary_maneuvers_lo": float(ci["unnecessary_maneuvers"]["lo"][val]),
                    "unnecessary_maneuvers_hi": float(ci["unnecessary_maneuvers"]["hi"][val]),
                    "n_alerts": m["n_alerts"],
                    "threshold_shift_vs_point": keys[val][4] - keys[point_val][4],
                }
                if method == POINT:
                    row.update(cost_change_vs_point=0.0, cost_change_lo=0.0, cost_change_hi=0.0)
                else:
                    d = dc.bootstrap_paired_difference(A[val], A[point_val], hr_te, W, quantity="cost", ratio=r)
                    row.update(cost_change_vs_point=d["point"], cost_change_lo=d["lo"], cost_change_hi=d["hi"])
                sel_rows.append(row)

            # §5 / §9: the P1a, P1b and P1c checks, per bound arm.
            for key, arm in arms.items():
                method, lrn, sided = key
                if method == POINT:
                    continue
                s_te, p_te = arm["official_test"], arm["point_official_test"]
                finite = np.isfinite(s_te)
                offset = s_te[finite] - p_te[finite]
                q = float(np.median(offset))
                c_bound = dc.threshold_counts(s_te, hr_te, T)
                c_shift = dc.threshold_counts(p_te, hr_te, T - q)
                c_same = dc.threshold_counts(p_te, hr_te, T)
                sweep_b, sweep_p = dc.budget_sweep(s_te, hr_te), dc.budget_sweep(p_te, hr_te)
                row = {
                    "seed": seed, "horizon_days": horizon, "method": method, "learner": lrn,
                    "sided": sided, "nominal": lvl, "structural_class": arm["structural_class"],
                    "offset_median_Q": q, "offset_spread": float(np.ptp(offset)),
                    "p1a_max_count_difference": float(max(np.max(np.abs(c_bound[k] - c_shift[k])) for k in ("tp", "fp"))),
                    "mean_alert_set_change_at_fixed_t": float(np.mean(
                        [np.sum(np.abs(dc.threshold_alerts(s_te, t) - dc.threshold_alerts(p_te, t))) for t in T])),
                    "mean_abs_alert_count_change_at_fixed_t": float(np.mean(np.abs(c_bound["n_alerts"] - c_same["n_alerts"]))),
                    "p1b_max_locus_difference_missed": float(np.max(np.abs(
                        sweep_b["missed_high_risk"] - sweep_p["missed_high_risk"]))),
                }
                for r in ratios:
                    row[f"p1c_unrestricted_cost_difference_{r:g}to1"] = (
                        unrestricted_optimum(s_te, hr_te, r)["cost"] - unrestricted_optimum(p_te, hr_te, r)["cost"])
                p1_rows.append(row)

            if lvl == primary_level:
                for (method, lrn, sided), arm in arms.items():
                    sw = dc.budget_sweep(arm["official_test"], hr_te)
                    curves.append(pd.DataFrame({
                        "seed": seed, "method": method, "learner": lrn, "sided": sided, "K": sw["budget"],
                        "missed_high_risk": sw["missed_high_risk"], "unnecessary_maneuvers": sw["unnecessary_maneuvers"],
                    }))
        timings[f"seed_{seed}_analysis_s"] = round(time.time() - ta0, 1)
        _append(path, f"seed {seed}: analysis done in {timings[f'seed_{seed}_analysis_s']} s")

    timings["total_s"] = round(time.time() - t0, 1)
    _append(path, f"threshold analysis done in {timings['total_s']} s")
    keys_dec = ["horizon_days", "method", "learner", "sided", "nominal", "threshold"]
    return {
        "decisions": _seed_mean(pd.DataFrame(dec_rows), keys_dec, sd_col="missed_high_risk"),
        "paired_differences": _seed_mean(pd.DataFrame(pair_rows), [*keys_dec, "quantity"]),
        "selection": _seed_mean(pd.DataFrame(sel_rows),
                                ["horizon_days", "method", "learner", "sided", "nominal", "ratio", "readout"],
                                sd_col="cost"),
        "p1_checks": _seed_mean(pd.DataFrame(p1_rows),
                                ["horizon_days", "method", "learner", "sided", "nominal", "structural_class"]),
        "operating_curves": (pd.concat(curves, ignore_index=True)
                             .groupby(["method", "learner", "sided", "K"], sort=False)
                             [["missed_high_risk", "unnecessary_maneuvers"]].mean().reset_index()),
        "grid": pd.DataFrame({"threshold": T, "operational": np.isin(T, grid["operational_thresholds"])}),
        "excluded_arms": pd.DataFrame(excluded_arms),
        "positivity": pd.DataFrame([{
            "n_test_total": n_te, "n_supported": part.n_supported, "n_unsupported": part.n_unsupported,
            "n_high_risk": int(hr_te.sum()), "n_self_test": int(hr_st.size), "n_self_test_high_risk": int(hr_st.sum()),
        }]),
        "search_integrity": search_integrity(cfg),
        "meta": {
            "seeds": seeds, "percentiles": percentiles, "n_boot": n_boot, "levels": levels,
            "primary_level": primary_level, "cost_ratios": list(ratios), "horizon_days": horizon,
            "n_thresholds": int(T.size), "n_duplicate_percentiles_removed": grid["n_duplicates_removed"],
            "reduced_configuration": bool(reduced), "timings": timings,
            "searches_cached_at_start": searches_cached_at_start,
            "n_alert_sets_per_seed": n_alert_sets, "caveat": THRESHOLD_CAVEAT,
        },
    }
