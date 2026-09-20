"""Expanded E15 — threshold-based decision analysis over lead times (absorbs E16).

Responsibility: evaluate the operational rule "alert iff score >= t" over the
pre-registered threshold grid, at each lead time, for every point prediction and every
validated bound, and report missed high-risk events first and whole-population burden
second, with event-level bootstrap CIs. Also: cost-minimizing thresholds under the four
pre-registered read-outs, and the checks that make prediction P1 precise (P1a/P1b/P1c,
Corollary 4 of Proposition 1). Nothing here is a hypothesis test (D4).

Inputs:  the four Phase-2 base learners, the GBM quantile heads, the audited score
         constructions (``decision_runner.rank_audit_scores``), the decision core
         (``decision.py``), and ``config.threshold_analysis`` / ``config.decision_cost``.
Outputs: per-threshold decision tables, paired bound-minus-point differences,
         threshold-selection tables, P1 checks, operating curves, the grids, the event
         populations, the excluded arms, and per-phase timings — each per horizon.

Serves: EXPERIMENT_PLAN.md E15 (expanded; E16 merged).

Protocol: the 2026-09-18 "PRE-REGISTRATION: expanded threshold-based decision analysis",
Sidh's 2026-09-19 decisions, and the 2026-09-19 implementation AMENDMENT (DECISIONS.md),
all written before any full-grid result existed (CLAUDE.md §3). In particular:
  * horizons {2-day, 3-day}, both on the official test set (Q-METH-04, revised); each runs
    from a derived configuration (cutoff = horizon), so features, splits, calibration and
    the search cache (fresh 24-trial searches) are horizon-specific;
  * two event populations: ``common_across_horizons`` — official-test events predictable
    at every horizon, the lead-time comparison's population — and ``horizon_full``;
  * the grid is built on each horizon's internal validation split (``val_inner``), never
    on the official test set; −6 is always included.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import decision as dc
from ..config import Config, validate
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
COMMON = "common_across_horizons"   # amendment item 1: the lead-time comparison population
FULL = "horizon_full"
POPULATIONS: tuple[str, ...] = (COMMON, FULL)
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


def horizon_config(cfg: Config, horizon_days: float) -> Config:
    """The per-horizon derived configuration (2026-09-19 amendment, item 2).

    Identical to ``cfg`` except that the feature cutoff equals the horizon and the horizon
    list is reduced to it. Features, splits, calibration and the search cache (keyed by
    the config hash) are therefore all horizon-specific, and the derived config is
    re-validated like any other.
    """
    raw = copy.deepcopy(cfg.raw)
    raw["cutoff"]["cutoff_days_before_tca"] = float(horizon_days)
    raw["threshold_analysis"]["horizons_days"] = [float(horizon_days)]
    return validate(raw)


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


def grid_bound_values(data, weights, preds: dict, heads: dict, levels, *,
                      split: str, exclude_persistence_one_sided: bool) -> np.ndarray:
    """Every validated bound's finite values on ``split`` — component (b) of the grid.

    Sidh's 2026-09-20 decision: the grid is extended with percentiles of the pooled
    values of every validated bound, across all methods and both sidednesses, computed
    on the internal validation split only. The arms are exactly those the analysis
    scores — persistence's one-sided bounds are excluded here for the same reason they
    are excluded there (degenerate quantile, Gate 2), so they are not validated bounds.
    Values that are ``+inf`` outside the Q-SEL-03 supported region carry no threshold
    information and are dropped.
    """
    n = data.subsets[split]["y"].size
    supported = diag.positivity_partition(data.subsets[split]["recency_ok"]).supported
    pooled = []
    for level in levels:
        for e in rank_audit_scores(data, weights, preds, heads, level, supported, split=split):
            if exclude_persistence_one_sided and e["learner"] == "persistence" and e["sided"] == "upper":
                continue
            s = np.asarray(e["score"], dtype=float)
            pooled.append(s[np.isfinite(s)])
    values = np.concatenate(pooled) if pooled else np.empty(0)
    if values.size == 0:
        raise ValueError(f"no finite validated bound values on {split!r} (n={n}); cannot build the grid")
    return values


def unrestricted_optimum(score: np.ndarray, is_high_risk: np.ndarray, ratio: float) -> dict:
    """§9: the cost minimiser over every distinct finite score value, plus +inf (no alerts)."""
    s = np.asarray(score, dtype=float)
    candidates = np.r_[np.unique(s[np.isfinite(s)]), np.inf]
    return dc.cost_minimizing_threshold(s, is_high_risk, candidates, ratio)


def _analyse(*, tag: dict, mask: np.ndarray, arms_by_level: dict, T: np.ndarray, primary_level: float,
             ratios: tuple, n_boot: int, hr_full: np.ndarray, hr_self: np.ndarray, w_self: np.ndarray,
             out: dict) -> dict:
    """All §3-§5 quantities for one (horizon, population, seed); rows are appended to ``out``."""
    hr_te = hr_full[mask]
    n_te = int(hr_te.size)
    W = dc.bootstrap_count_matrix(n_te, n_boot, tag["seed"])

    sliced: dict = {}
    keys, alert_sets = [], []
    for lvl, arms in arms_by_level.items():
        sliced[lvl] = {}
        for key, arm in arms.items():
            s = {"official_test": arm["official_test"][mask], "point_official_test": arm["point_official_test"][mask],
                 "self_test": arm["self_test"], "structural_class": arm["structural_class"]}
            sliced[lvl][key] = s
            for t in T:
                keys.append((*key, lvl, float(t)))
                alert_sets.append(dc.threshold_alerts(s["official_test"], t))
    A = np.vstack(alert_sets)
    tb = time.time()
    ci = dc.bootstrap_decision_intervals(A, hr_te, ratios, W)
    bootstrap_s = round(time.time() - tb, 1)
    index = {k: i for i, k in enumerate(keys)}

    # §3: per-threshold decisions, and paired bound-minus-point differences.
    for i, (method, lrn, sided, lvl, t) in enumerate(keys):
        point = dc.decision_metrics(dc.decision_counts(A[i], hr_te), ratios)
        row = {**tag, "method": method, "learner": lrn, "sided": sided, "nominal": lvl, "threshold": t}
        for name, value in point.items():
            row[name] = value
            row[f"{name}_lo"] = float(ci[name]["lo"][i])
            row[f"{name}_hi"] = float(ci[name]["hi"][i])
        out["decisions"].append(row)
        if method != POINT:
            ip = index[(POINT, lrn, POINT_SIDED, lvl, t)]
            for quantity in ("missed_high_risk", "unnecessary_maneuvers"):
                d = dc.bootstrap_paired_difference(A[i], A[ip], hr_te, W, quantity=quantity)
                out["paired"].append({
                    **tag, "method": method, "learner": lrn, "sided": sided, "nominal": lvl, "threshold": t,
                    "quantity": quantity, "difference_vs_point": d["point"],
                    "difference_lo": d["lo"], "difference_hi": d["hi"],
                })

    for lvl, arms in sliced.items():
        # §4: cost-minimizing thresholds under the four read-outs.
        chosen = {}
        for key, arm in arms.items():
            for r in ratios:
                picks = {
                    "selected_on_self_test": dc.cost_minimizing_threshold(arm["self_test"], hr_self, T, r),
                    "selected_on_self_test_rule_weighted": dc.cost_minimizing_threshold(
                        arm["self_test"], hr_self, T, r, event_weights=w_self),
                    "oracle_on_official_test_grid": dc.cost_minimizing_threshold(arm["official_test"], hr_te, T, r),
                }
                for readout, pick in picks.items():
                    chosen[(key, r, readout)] = index[(*key, lvl, pick["threshold"])]
                chosen[(key, r, "unrestricted_oracle_on_official_test")] = unrestricted_optimum(
                    arm["official_test"], hr_te, r)
        for (key, r, readout), val in chosen.items():
            method, lrn, sided = key
            point_val = chosen[((POINT, lrn, POINT_SIDED), r, readout)]
            base = {**tag, "method": method, "learner": lrn, "sided": sided, "nominal": lvl,
                    "ratio": r, "readout": readout}
            if readout == "unrestricted_oracle_on_official_test":
                out["selection"].append({
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
            out["selection"].append(row)

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
                **tag, "method": method, "learner": lrn, "sided": sided, "nominal": lvl,
                "structural_class": arm["structural_class"],
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
            out["p1"].append(row)

        if lvl == primary_level:
            for (method, lrn, sided), arm in arms.items():
                sw = dc.budget_sweep(arm["official_test"], hr_te)
                out["curves"].append(pd.DataFrame({
                    **tag, "method": method, "learner": lrn, "sided": sided, "K": sw["budget"],
                    "missed_high_risk": sw["missed_high_risk"], "unnecessary_maneuvers": sw["unnecessary_maneuvers"],
                }))
    return {"n_alert_sets": int(A.shape[0]), "bootstrap_s": bootstrap_s}


def run_threshold_analysis(cfg: Config, *, seeds=None, percentiles=None, n_boot: int | None = None) -> dict:
    """Execute the pre-registered threshold-based analysis over all horizons.

    Deterministic given (config, seeds). ``seeds``, ``percentiles`` and ``n_boot`` default to
    the pre-registered values; a smoke run passes a reduced set, and
    ``meta['reduced_configuration']`` records that.
    """
    ta = cfg.threshold_analysis
    horizons = [float(h) for h in ta.horizons_days]
    path = threshold_progress_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    t0 = time.time()
    timings: dict = {}
    _append(path, f"threshold analysis start: horizons {horizons} d")

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

    events = load_events(cfg)
    timings["load_events_s"] = round(time.time() - t0, 1)

    # --- per-horizon assembly (derived configs, amendment item 2) ---
    hcfgs = {h: horizon_config(cfg, h) for h in horizons}
    datas, weights_by_h, w_self_by_h, searches_cached_at_start = {}, {}, {}, {}
    for h in horizons:
        hc = hcfgs[h]
        cache_root = Path(hc.path("artifacts_dir")) / "search_cache"
        searches_cached_at_start[f"{h:g}d"] = {
            exp: (cache_root / f"{exp}_{hc.config_hash[:16]}_seed{hc.seed}.json").exists()
            for exp in SEARCH_EXPERIMENTS
        }
        th = time.time()
        _append(path, f"horizon {h:g} d: assembling conformal data and weights")
        data = prepare_conformal_data(hc, events)
        datas[h] = data
        weights_by_h[h] = build_weights(hc, data)
        selft = data.subsets["self_test"]
        # §4 secondary / §9: shift-aware selection weights, built exactly as the calibration weights are.
        w_self_by_h[h] = rule_derived_weights(
            selft["recency_ok"], selft["risk_last"],
            test_high_risk_prevalence=data.test_high_risk_prevalence,
            train_high_risk_prevalence=data.train_high_risk_prevalence,
            high_risk_threshold=hc.high_risk_threshold,
            recency_epsilon=0.0,
        ).w
        timings[f"h{h:g}_assemble_s"] = round(time.time() - th, 1)

    # --- event populations (amendment item 1) ---
    uid_sets = [set(np.asarray(datas[h].subsets["official_test"]["uids"]).tolist()) for h in horizons]
    common_uids = set.intersection(*uid_sets)
    masks, population_rows = {}, []
    for h in horizons:
        test = datas[h].subsets["official_test"]
        uids = np.asarray(test["uids"])
        hr = np.asarray(test["is_high_risk"], dtype=bool)
        in_common = np.isin(uids, np.array(sorted(common_uids), dtype=uids.dtype))
        masks[(h, COMMON)] = in_common
        masks[(h, FULL)] = np.ones(uids.size, dtype=bool)
        population_rows.append({"horizon_days": h, "population": FULL, "n_events": int(uids.size),
                                "n_high_risk": int(hr.sum()), "n_excluded_from_common": 0,
                                "n_excluded_high_risk": 0})
        population_rows.append({"horizon_days": h, "population": COMMON, "n_events": int(in_common.sum()),
                                "n_high_risk": int(hr[in_common].sum()),
                                "n_excluded_from_common": int((~in_common).sum()),
                                "n_excluded_high_risk": int(hr[~in_common].sum())})
    _append(path, f"populations: common set {len(common_uids)} events; per horizon "
                  f"{[int(masks[(h, FULL)].sum()) for h in horizons]}")

    # --- pass 1: fit (the first seed of each horizon runs that horizon's searches) ---
    fitted = {}
    for h in horizons:
        for seed in seeds:
            ts = time.time()
            _append(path, f"horizon {h:g} d, seed {seed}: fitting base learners")
            preds = base_predictions(hcfgs[h], datas[h], seed)
            timings[f"h{h:g}_seed_{seed}_fit_learners_s"] = round(time.time() - ts, 1)
            tq = time.time()
            _append(path, f"horizon {h:g} d, seed {seed}: fitting GBM quantile heads at {head_levels}")
            heads = _fit_upper_heads(hcfgs[h], datas[h], seed, head_levels)
            timings[f"h{h:g}_seed_{seed}_fit_heads_s"] = round(time.time() - tq, 1)
            fitted[(h, seed)] = (preds, heads)

    # --- pass 2: grids (val_inner, Decision 3) and the analysis ---
    out = {"decisions": [], "paired": [], "selection": [], "p1": [], "curves": []}
    grid_rows, excluded_rows, meta_h = [], [], {}
    for h in horizons:
        data = datas[h]
        # Component (a): pooled point predictions on val_inner (the original design).
        pooled = np.concatenate([np.asarray(fitted[(h, s)][0][lrn][ta.grid_source_split], dtype=float)
                                 for s in seeds for lrn in BASE_LEARNERS])
        # Component (b): pooled values of every validated bound on the same split
        # (Sidh, 2026-09-20 — the ceiling fix). Same seeds, same split, same percentiles.
        pooled_bounds = np.concatenate([
            grid_bound_values(data, weights_by_h[h], fitted[(h, s)][0], fitted[(h, s)][1], levels,
                              split=ta.grid_source_split,
                              exclude_persistence_one_sided=ta.exclude_persistence_one_sided)
            for s in seeds
        ])
        grid = dc.threshold_grid(pooled, percentiles, ta.operational_thresholds,
                                 pooled_bound_values=pooled_bounds)
        T = grid["thresholds"]
        point_vals = np.unique(grid["percentile_values"])
        bound_vals = np.unique(grid["bound_percentile_values"])
        for t_ in T:
            from_point = bool(np.isin(t_, point_vals))
            from_bound = bool(np.isin(t_, bound_vals))
            grid_rows.append({
                "horizon_days": h, "threshold": float(t_),
                "operational": bool(np.isin(t_, grid["operational_thresholds"])),
                "from_point_percentiles": from_point, "from_bound_percentiles": from_bound,
                "source": ("point+bound" if from_point and from_bound
                           else "point" if from_point else "bound" if from_bound else "operational"),
            })
        meta_h[f"{h:g}d"] = {
            "config_hash": hcfgs[h].config_hash, "n_thresholds": int(T.size),
            "n_duplicate_percentiles_removed": grid["n_duplicates_removed"],
            "n_bound_duplicate_percentiles_removed": grid["n_bound_duplicates_removed"],
            "n_grid_from_point_percentiles": grid["n_from_point_only"],
            "n_grid_from_bound_percentiles_only": grid["n_from_bound_only"],
            "grid_min": float(T.min()), "grid_max": float(T.max()),
            "n_grid_above_operational": int((T > float(ta.operational_thresholds[0])).sum()),
            "n_pooled_point_values": int(pooled.size), "n_pooled_bound_values": int(pooled_bounds.size),
        }
        _append(path, f"horizon {h:g} d: grid {T.size} thresholds in [{T.min():.3f}, {T.max():.3f}] "
                      f"({grid['n_from_bound_only']} contributed by bound percentiles only, "
                      f"{int((T > float(ta.operational_thresholds[0])).sum())} above "
                      f"{float(ta.operational_thresholds[0]):g})")

        test = data.subsets["official_test"]
        hr_full = np.asarray(test["is_high_risk"], dtype=bool)
        hr_self = np.asarray(data.subsets["self_test"]["is_high_risk"], dtype=bool)
        sup = diag.positivity_partition(test["recency_ok"]).supported
        for seed in seeds:
            ta0 = time.time()
            preds, heads = fitted[(h, seed)]
            arms_by_level = {}
            for lvl in levels:
                arms, excluded = threshold_arms(
                    data, weights_by_h[h], preds, heads, lvl, sup,
                    exclude_persistence_one_sided=ta.exclude_persistence_one_sided,
                )
                arms_by_level[lvl] = arms
            if seed == seeds[0]:
                excluded_rows.extend({"horizon_days": h, **e} for e in excluded)
            for population in POPULATIONS:
                _append(path, f"horizon {h:g} d, seed {seed}: analysing population {population}")
                info = _analyse(
                    tag={"seed": seed, "horizon_days": h, "population": population},
                    mask=masks[(h, population)], arms_by_level=arms_by_level, T=T,
                    primary_level=primary_level, ratios=ratios, n_boot=n_boot,
                    hr_full=hr_full, hr_self=hr_self, w_self=w_self_by_h[h], out=out,
                )
                meta_h[f"{h:g}d"]["n_alert_sets_per_seed_population"] = info["n_alert_sets"]
                timings[f"h{h:g}_seed_{seed}_{population}_bootstrap_s"] = info["bootstrap_s"]
            timings[f"h{h:g}_seed_{seed}_analysis_s"] = round(time.time() - ta0, 1)
            _append(path, f"horizon {h:g} d, seed {seed}: analysis done in {timings[f'h{h:g}_seed_{seed}_analysis_s']} s")

    positivity_rows = []
    integrity = []
    for h in horizons:
        test = datas[h].subsets["official_test"]
        part = diag.positivity_partition(test["recency_ok"])
        positivity_rows.append({"horizon_days": h, "n_test_total": int(test["y"].size),
                                "n_supported": part.n_supported, "n_unsupported": part.n_unsupported,
                                "n_self_test": int(datas[h].subsets["self_test"]["y"].size)})
        si = search_integrity(hcfgs[h], legacy_cutoff_days=float(cfg.cutoff.cutoff_days_before_tca))
        integrity.append(si.assign(horizon_days=h))

    timings["total_s"] = round(time.time() - t0, 1)
    _append(path, f"threshold analysis done in {timings['total_s']} s")
    tag_keys = ["horizon_days", "population"]
    keys_dec = [*tag_keys, "method", "learner", "sided", "nominal", "threshold"]
    return {
        "decisions": _seed_mean(pd.DataFrame(out["decisions"]), keys_dec, sd_col="missed_high_risk"),
        "paired_differences": _seed_mean(pd.DataFrame(out["paired"]), [*keys_dec, "quantity"]),
        "selection": _seed_mean(pd.DataFrame(out["selection"]),
                                [*tag_keys, "method", "learner", "sided", "nominal", "ratio", "readout"],
                                sd_col="cost"),
        "p1_checks": _seed_mean(pd.DataFrame(out["p1"]),
                                [*tag_keys, "method", "learner", "sided", "nominal", "structural_class"]),
        "operating_curves": (pd.concat(out["curves"], ignore_index=True)
                             .groupby([*tag_keys, "method", "learner", "sided", "K"], sort=False)
                             [["missed_high_risk", "unnecessary_maneuvers"]].mean().reset_index()),
        "grid": pd.DataFrame(grid_rows),
        "populations": pd.DataFrame(population_rows),
        "excluded_arms": pd.DataFrame(excluded_rows),
        "positivity": pd.DataFrame(positivity_rows),
        "search_integrity": pd.concat(integrity, ignore_index=True),
        "meta": {
            "horizons_days": horizons, "seeds": seeds, "percentiles": percentiles, "n_boot": n_boot,
            "levels": levels, "primary_level": primary_level, "cost_ratios": list(ratios),
            "grid_source_split": ta.grid_source_split, "n_common_events": len(common_uids),
            "per_horizon": meta_h, "reduced_configuration": bool(reduced), "timings": timings,
            "searches_cached_at_start": searches_cached_at_start, "caveat": THRESHOLD_CAVEAT,
        },
    }
