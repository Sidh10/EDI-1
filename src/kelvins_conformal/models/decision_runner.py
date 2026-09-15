"""E15 — decision-cost evaluation under a matched alert budget (Phase 5).

Responsibility: turn point predictions and ONE-SIDED upper bounds into maneuver
alerts at matched alert budgets, and report missed high-risk events first and
whole-population costs second, with event-level bootstrap CIs. Nothing here is a
hypothesis test (D4).

Inputs:  the four Phase-2 base learners (via ``conformal_runner.base_predictions``),
         the conformal core (``conformal/``), the decision core (``decision.py``),
         and ``config.decision_cost``.
Outputs: decision tables per (method, learner, level, budget) with CIs; paired
         bootstrap differences in missed high-risk events; budget-sweep tradeoff
         curves; the realised one-sided coverage of every bound (the D2 caveat,
         quantified); the one-sided CQR self-test validation; an alert-identity
         check (pre-registration §4) and a search-integrity check (§8).

Serves: EXPERIMENT_PLAN.md E15.

Every protocol choice is fixed by the 2026-09-18 E15 design review (D1-D4) and the
E15 PRE-REGISTRATION entry in DECISIONS.md, both written before this module read
the official test set (CLAUDE.md §3). The official test set is read once, for
scoring only; nothing is tuned on it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import decision as dc
from ..config import Config
from ..conformal import diagnostics as diag
from ..conformal.cqr import cqr_upper_bound, cqr_upper_scores
from ..conformal.split import Interval, signed_residual_scores, split_interval
from ..conformal.weighted import weighted_interval
from ..data import load_events
from .conformal_runner import (
    BASE_LEARNERS,
    _gbm_params,
    _tab_view,
    base_predictions,
    build_weights,
    coverage_with_ci,
    prepare_conformal_data,
)
from .runner import cached_search

# Pre-registration §7: carried by every E15 table and figure.
CAVEAT = (
    "One-sided upper bounds under-cover on the official test set (E11 diagnostic: the "
    "one-sided machinery is validated under exchangeability, but rule-derived weighting "
    "does not restore one-sided validity); persistence's one-sided bound is additionally "
    "degenerate (a 65.9% zero-atom in its signed scores, Gate 2)."
)

POINT = "point"
E10 = "E10_naive_upper"
E11 = "E11_weighted_rule_upper"
E12 = "E12_cqr_weighted_rule_upper"
E8 = "E8_bayes_upper"
METHODS: tuple[str, ...] = (POINT, E10, E11, E12, E8)

PRIMARY_METRICS: tuple[str, ...] = ("missed_high_risk", "miss_rate_high_risk", "recall_high_risk")
SECONDARY_METRICS: tuple[str, ...] = (
    "unnecessary_maneuvers", "false_positive_rate", "precision", "f2",
)
SEARCH_EXPERIMENTS: tuple[str, ...] = ("e6_gbm", "e7_sequence", "e8_mcdropout")


# --- progress log (observability only; never read back) -----------------------
def progress_path(cfg: Config) -> Path:
    return Path(cfg.path("artifacts_dir")) / "e15_progress.log"


def _log(cfg: Config, message: str) -> None:
    path = progress_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%H:%M:%S')} {message}\n")


# --- the pre-registered budget grid (§2) ---------------------------------------
def budget_grid(cfg: Config, n_events: int, test_high_risk_prevalence: float) -> pd.DataFrame:
    """Matched alert budgets K: prevalence-matched (primary) plus the declared fractions."""
    dcfg = cfg.decision_cost
    named = []
    if dcfg.include_prevalence_matched_budget:
        named.append(("prevalence_matched", float(test_high_risk_prevalence)))
    named.extend((f"frac_{f:g}", float(f)) for f in dcfg.budget_fractions)
    rows = []
    for name, frac in named:
        k = int(round(frac * n_events))
        if not 1 <= k <= n_events:
            raise ValueError(f"budget {name} gives K = {k}, outside [1, {n_events}]")
        rows.append({"budget": name, "fraction": frac, "K": k, "primary": name == dcfg.primary_budget})
    grid = pd.DataFrame(rows)
    if int(grid["primary"].sum()) != 1:
        raise ValueError(f"exactly one primary budget required, got {grid['primary'].sum()}")
    return grid


# --- predictions -------------------------------------------------------------------
def _fit_upper_heads(cfg: Config, data, seed: int, levels) -> dict:
    """GBM quantile heads at each one-sided level (the CQR upper predictor)."""
    from . import gbm as gbm_mod
    from .runner import search_gbm

    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]
    budget = cached_search(cfg, "e6_gbm", cfg.seed,
                           lambda: search_gbm(cfg, _tab_view(data), seed=cfg.seed))
    params = _gbm_params(budget.best_params, seed)
    qlevels = sorted({round(float(lv), 6) for lv in levels})
    qmodels, qbest = gbm_mod.fit_quantile_models(
        fit["tab_X"], fit["y"], val["tab_X"], val["y"], qlevels, seed=seed, params=params,
        num_boost_round=cfg.gbm.num_boost_round,
        early_stopping_rounds=cfg.train.early_stopping_rounds,
    )
    return {
        lv: {
            split: np.asarray(qmodels[lv].predict(data.subsets[split]["tab_X"], num_iteration=qbest[lv]), float)
            for split in ("calibration", "self_test", "official_test")
        }
        for lv in qlevels
    }


def decision_scores(data, weights, preds: dict, heads: dict, level: float, supported: np.ndarray):
    """Per-event decision scores at one nominal level, in official-test order.

    Returns ``(scores, refs)``: ``scores[(method, learner)]`` is the score alerts are
    ranked by; ``refs[(method, learner)]`` is the score it is expected to be
    rank-identical to (pre-registration §4(i)). Bounds defined only on the
    Q-SEL-03 supported region are +inf outside it (always alerted, §1).
    """
    cal, test = data.subsets["calibration"], data.subsets["official_test"]
    n = test["y"].size
    alpha = 1.0 - level
    scores: dict = {}
    refs: dict = {}

    def _expand(hi_supported: np.ndarray) -> np.ndarray:
        hi = np.full(n, np.inf)
        hi[supported] = hi_supported
        return hi

    for lrn in BASE_LEARNERS:
        pred_te = np.asarray(preds[lrn]["official_test"], dtype=float)
        s_cal = signed_residual_scores(cal["y"], preds[lrn]["calibration"])
        scores[(POINT, lrn)] = pred_te
        scores[(E10, lrn)] = split_interval(pred_te, s_cal, alpha, sided="upper").hi
        # Same call as E11 (run_all), including its conditional clipping policy.
        scores[(E11, lrn)] = _expand(
            weighted_interval(pred_te[supported], s_cal, weights.rule, alpha, sided="upper").interval.hi
        )
        refs[(E10, lrn)] = pred_te
        refs[(E11, lrn)] = pred_te

    head = heads[round(float(level), 6)]
    scores[(E12, "gbm")] = _expand(cqr_upper_bound(
        head["official_test"][supported], cqr_upper_scores(cal["y"], head["calibration"]), alpha,
        weights=weights.rule.w, test_weight=weights.rule.test_weight,
    ).hi)
    refs[(E12, "gbm")] = head["official_test"]
    scores[(E8, "mc_dropout")] = preds["_mc_dropout_dist"]["official_test"].upper_bound(level)
    return scores, refs


# --- integrity (§8) -------------------------------------------------------------------
def search_integrity(cfg: Config) -> pd.DataFrame:
    """Do the searches re-run under the new config hash reproduce every earlier cache?

    Adding ``decision_cost`` changed the config hash, so each search ran again under
    a new cache key. The searches are seeded, so the new ``best_params`` must equal
    those cached under every earlier hash. A mismatch is reported, never hidden.
    """
    root = Path(cfg.path("artifacts_dir")) / "search_cache"
    current = cfg.config_hash[:16]
    rows = []
    for exp in SEARCH_EXPERIMENTS:
        cur_path = root / f"{exp}_{current}_seed{cfg.seed}.json"
        base = {"experiment": exp, "current_hash": current}
        if not cur_path.exists():
            rows.append({**base, "reference_hash": None, "status": "no cache under the current hash",
                         "best_params_equal": None, "objective_equal": None})
            continue
        cur = json.loads(cur_path.read_text(encoding="utf-8"))
        refs = sorted(p for p in root.glob(f"{exp}_*_seed{cfg.seed}.json") if p != cur_path)
        if not refs:
            rows.append({**base, "reference_hash": None, "status": "no earlier cache to compare",
                         "best_params_equal": None, "objective_equal": None})
        for p in refs:
            ref = json.loads(p.read_text(encoding="utf-8"))
            rows.append({
                **base,
                "reference_hash": p.name[len(exp) + 1: len(exp) + 17],
                "status": "compared",
                "best_params_equal": cur["best_params"] == ref["best_params"],
                "objective_equal": cur["best_objective_value"] == ref["best_objective_value"],
            })
    return pd.DataFrame(rows)


# --- aggregation ---------------------------------------------------------------------
def _seed_mean(df: pd.DataFrame, keys: list[str], sd_col: str | None = None) -> pd.DataFrame:
    """Mean over seeds of every value column (point and CI bounds alike — project convention)."""
    value_cols = [c for c in df.columns if c not in keys and c != "seed"]
    g = df.groupby(keys, dropna=False, sort=False)
    out = g[value_cols].mean().reset_index()
    out["n_seeds"] = g["seed"].nunique().to_numpy()
    if sd_col is not None:
        out[f"{sd_col}_sd_across_seeds"] = g[sd_col].std().to_numpy()
    return out


# --- the run ---------------------------------------------------------------------------
def run_e15(cfg: Config, *, seeds=None, n_boot: int | None = None) -> dict:
    """Execute E15 end to end. Deterministic given (config, seeds)."""
    progress_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    progress_path(cfg).write_text("", encoding="utf-8")
    t0 = time.time()
    _log(cfg, "E15 start: loading events and assembling conformal data")

    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)

    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    primary_level = cfg.power.nominal_coverage_primary
    ratios = tuple(cfg.decision_cost.cost_ratios)

    cal, test, selft = data.subsets["calibration"], data.subsets["official_test"], data.subsets["self_test"]
    y_te = np.asarray(test["y"], dtype=float)
    hr = np.asarray(test["is_high_risk"], dtype=bool)
    n = int(y_te.size)
    part = diag.positivity_partition(test["recency_ok"])
    sup = part.supported
    budgets = budget_grid(cfg, n, float(np.mean(hr)))
    primary_budget = str(budgets.loc[budgets["primary"], "budget"].iloc[0])

    dec_rows, cov_rows, pair_rows, self_rows, ident_rows, curves = [], [], [], [], [], []
    seed_seconds = {}
    for seed in seeds:
        ts = time.time()
        _log(cfg, f"seed {seed}: fitting base learners (persistence, GBM, GRU, MC-dropout)")
        preds = base_predictions(cfg, data, seed)
        _log(cfg, f"seed {seed}: fitting GBM upper quantile heads at {levels}")
        heads = _fit_upper_heads(cfg, data, seed, levels)
        _log(cfg, f"seed {seed}: scoring decisions")
        W = dc.bootstrap_count_matrix(n, n_boot, seed)

        keys, alert_sets = [], []
        for lvl in levels:
            scores, refs = decision_scores(data, weights, preds, heads, lvl, sup)

            # §5: one-sided CQR machinery validation on the exchangeable self-split.
            head = heads[round(float(lvl), 6)]
            iv_self = cqr_upper_bound(head["self_test"], cqr_upper_scores(cal["y"], head["calibration"]), 1.0 - lvl)
            c = coverage_with_ci(selft["y"], iv_self, seed=seed, n_boot=n_boot)
            self_rows.append({"seed": seed, "nominal": lvl, **{k: c[k] for k in ("coverage", "boot_lo", "boot_hi", "cp_lo", "cp_hi", "n")}})

            # The D2 caveat, quantified: realised one-sided coverage of each bound.
            for (method, lrn), score in scores.items():
                if method == POINT:
                    continue
                for population, mask in (("all_supported", sup), ("high_risk_supported", sup & hr)):
                    m = int(mask.sum())
                    c = coverage_with_ci(
                        y_te[mask], Interval(lo=np.full(m, -np.inf), hi=score[mask]), seed=seed, n_boot=n_boot,
                    )
                    cov_rows.append({
                        "seed": seed, "method": method, "learner": lrn, "nominal": lvl,
                        "population": population,
                        **{k: c[k] for k in ("coverage", "boot_lo", "boot_hi", "cp_lo", "cp_hi", "n")},
                    })

            for _, b in budgets.iterrows():
                k_alerts = int(b["K"])
                for (method, lrn), score in scores.items():
                    alerts = dc.matched_budget_alerts(score, k_alerts)
                    keys.append((method, lrn, lvl, str(b["budget"]), k_alerts))
                    alert_sets.append(alerts)
                    if (method, lrn) in refs:
                        ref_alerts = dc.matched_budget_alerts(refs[(method, lrn)], k_alerts)
                        ident_rows.append({
                            "seed": seed, "method": method, "learner": lrn, "nominal": lvl,
                            "budget": str(b["budget"]), "K": k_alerts,
                            "reference": "own point prediction" if method != E12 else "GBM upper quantile head",
                            "max_abs_alert_difference": float(np.max(np.abs(alerts - ref_alerts))),
                        })

            if lvl == primary_level:
                for (method, lrn), score in scores.items():
                    sw = dc.budget_sweep(score, hr)
                    curves.append(pd.DataFrame({
                        "seed": seed, "method": method, "learner": lrn, "K": sw["budget"],
                        "missed_high_risk": sw["missed_high_risk"],
                        "unnecessary_maneuvers": sw["unnecessary_maneuvers"],
                    }))

        A = np.vstack(alert_sets)
        _log(cfg, f"seed {seed}: bootstrap, {A.shape[0]} alert sets x {n_boot} resamples")
        ci = dc.bootstrap_decision_intervals(A, hr, ratios, W)
        for i, (method, lrn, lvl, bname, k_alerts) in enumerate(keys):
            point = dc.decision_metrics(dc.decision_counts(A[i], hr), ratios)
            row = {"seed": seed, "method": method, "learner": lrn, "nominal": lvl,
                   "budget": bname, "K": k_alerts}
            for name, value in point.items():
                row[name] = value
                row[f"{name}_lo"] = float(ci[name]["lo"][i])
                row[f"{name}_hi"] = float(ci[name]["hi"][i])
                row[f"{name}_n_undefined"] = int(ci[name]["n_undefined"][i])
            dec_rows.append(row)

        # §6: paired differences in missed high-risk events, primary budget and level.
        index = {key[:4]: i for i, key in enumerate(keys)}

        def _alerts(method, lrn, _index=index, _A=A):
            return _A[_index[(method, lrn, primary_level, primary_budget)]]

        compared = [(m, lrn) for m in (E10, E11) for lrn in BASE_LEARNERS] + [(E12, "gbm")]
        for method, lrn in compared:
            for vs_label, (vs_method, vs_lrn) in (("own point prediction", (POINT, lrn)),
                                                  ("E8 Bayesian bound", (E8, "mc_dropout"))):
                d = dc.bootstrap_paired_difference(_alerts(method, lrn), _alerts(vs_method, vs_lrn), hr, W)
                pair_rows.append({
                    "seed": seed, "method": method, "learner": lrn, "vs": vs_label,
                    "vs_method": vs_method, "vs_learner": vs_lrn, "nominal": primary_level,
                    "budget": primary_budget, "diff_missed_high_risk": d["point"],
                    "diff_lo": d["lo"], "diff_hi": d["hi"],
                })
        seed_seconds[seed] = round(time.time() - ts, 1)
        _log(cfg, f"seed {seed}: done in {seed_seconds[seed]} s")

    decisions_raw = pd.DataFrame(dec_rows)
    decisions = _seed_mean(decisions_raw, ["method", "learner", "nominal", "budget", "K"],
                           sd_col="missed_high_risk")
    identity = (pd.DataFrame(ident_rows)
                .groupby(["method", "learner", "nominal", "budget", "K", "reference"], sort=False)
                ["max_abs_alert_difference"].max().reset_index())
    curve_mean = (pd.concat(curves, ignore_index=True)
                  .groupby(["method", "learner", "K"], sort=False)[["missed_high_risk", "unnecessary_maneuvers"]]
                  .mean().reset_index())
    _log(cfg, f"E15 done in {round(time.time() - t0, 1)} s")
    return {
        "decisions": decisions,
        "decisions_raw": decisions_raw,
        "bound_coverage": _seed_mean(pd.DataFrame(cov_rows), ["method", "learner", "nominal", "population"],
                                     sd_col="coverage"),
        "cqr_selftest": _seed_mean(pd.DataFrame(self_rows), ["nominal"], sd_col="coverage"),
        "paired_differences": _seed_mean(
            pd.DataFrame(pair_rows),
            ["method", "learner", "vs", "vs_method", "vs_learner", "nominal", "budget"],
            sd_col="diff_missed_high_risk",
        ),
        "tradeoff_curves": curve_mean,
        "alert_identity": identity,
        "budgets": budgets,
        "positivity": pd.DataFrame([{
            "n_test_total": n, "n_supported": part.n_supported, "n_unsupported": part.n_unsupported,
            "unsupported_high_risk": int(np.sum(hr[~sup])), "n_high_risk": int(hr.sum()),
        }]),
        "search_integrity": search_integrity(cfg),
        "meta": {
            "seeds": seeds, "levels": levels, "primary_level": primary_level,
            "primary_budget": primary_budget, "cost_ratios": list(ratios), "n_boot": n_boot,
            "n_test": n, "n_high_risk": int(hr.sum()), "caveat": CAVEAT,
            "high_risk_threshold": cfg.high_risk_threshold, "seed_seconds": seed_seconds,
        },
    }
