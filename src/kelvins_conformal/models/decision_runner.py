"""E15 — decision-cost evaluation under a matched alert budget (Phase 5).

Responsibility: turn point predictions and ONE-SIDED upper bounds into maneuver
alerts at matched alert budgets, and report missed high-risk events first and
whole-population costs second, with event-level bootstrap CIs. Nothing here is a
hypothesis test (D4). Also hosts the rank-invariance audit that extends the E15
matched-budget finding with its formal classification (Proposition 1).

Inputs:  the four Phase-2 base learners (via ``conformal_runner.base_predictions``),
         the conformal core (``conformal/``), the decision core (``decision.py``),
         and ``config.decision_cost``.
Outputs: decision tables per (method, learner, level, budget) with CIs; paired
         bootstrap differences in missed high-risk events; budget-sweep tradeoff
         curves; the realised one-sided coverage of every bound (the D2 caveat,
         quantified); the one-sided CQR self-test validation; an alert-identity
         check (pre-registration §4) and a search-integrity check (§8); and, for the
         audit, the per-method rank-invariance classification.

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
from ..conformal.cqr import (
    cqr_interval,
    cqr_scores,
    cqr_upper_bound,
    cqr_upper_scores,
    enforce_monotone_quantiles,
)
from ..conformal.split import (
    Interval,
    absolute_residual_scores,
    signed_residual_scores,
    split_interval,
)
from ..conformal.weighted import weighted_interval
from ..data import load_events
from .conformal_runner import (
    BASE_LEARNERS,
    _gbm_params,
    _tab_view,
    base_predictions,
    build_weights,
    coverage_with_ci,
    cqr_quantile_levels,
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

# Two-sided variants, used by the rank-invariance audit only (their upper edges).
E10_TWO = "E10_naive_two_sided_upper_edge"
E11_TWO = "E11_weighted_rule_two_sided_upper_edge"
E12_TWO = "E12_cqr_weighted_rule_two_sided_upper_edge"
E8_TWO = "E8_bayes_two_sided_upper_edge"

PRIMARY_METRICS: tuple[str, ...] = ("missed_high_risk", "miss_rate_high_risk", "recall_high_risk")
SECONDARY_METRICS: tuple[str, ...] = (
    "unnecessary_maneuvers", "false_positive_rate", "precision", "f2",
)
SEARCH_EXPERIMENTS: tuple[str, ...] = ("e6_gbm", "e7_sequence", "e8_mcdropout")

# Structural classes of Proposition 1 (DECISIONS.md, E15 rank-invariance entry).
TRANSLATION_OF_POINT = "translation_of_point"
TRANSLATION_OF_QUANTILE_HEAD = "translation_of_quantile_head"
EVENT_SPECIFIC_DISPERSION = "event_specific_dispersion"


# --- progress logs (observability only; never read back) -----------------------
def progress_path(cfg: Config) -> Path:
    return Path(cfg.path("artifacts_dir")) / "e15_progress.log"


def audit_progress_path(cfg: Config) -> Path:
    return Path(cfg.path("artifacts_dir")) / "e15_rank_audit_progress.log"


def _append(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%H:%M:%S')} {message}\n")


def _log(cfg: Config, message: str) -> None:
    _append(progress_path(cfg), message)


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
    """GBM quantile heads at the given levels (the CQR quantile predictors)."""
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


# --- rank-invariance audit (extends the 2026-09-18 E15 matched-budget entry) ------------
def rank_audit_scores(
    data, weights, preds: dict, heads: dict, level: float, supported: np.ndarray,
    split: str = "official_test",
) -> list[dict]:
    """Every (method, learner, sidedness) decision score, with what Proposition 1 predicts.

    Each entry carries the score (the one-sided bound, or the upper edge of the
    two-sided interval), the learner's own point prediction, the construction
    reference the score is a translation of (the point prediction; for CQR its
    quantile head; ``None`` for the Bayesian bound, whose dispersion is
    event-specific), and the structural class. Constructions reproduce the E11
    (weighted_interval, incl. conditional clipping), E12 (two-sided CQR with
    quantile-crossing repair) and E15 (one-sided CQR, Bayesian bound) code paths.

    ``split`` selects the scored subset (official test by default; the threshold
    analysis also scores ``self_test`` for threshold selection). Every conformal
    quantile comes from the calibration split and is shared by all events, so the
    same Q applies on any split.
    """
    cal = data.subsets["calibration"]
    n = data.subsets[split]["y"].size
    alpha = 1.0 - level
    tw = weights.rule.test_weight

    def _expand(values_supported: np.ndarray) -> np.ndarray:
        full = np.full(n, np.inf)
        full[supported] = values_supported
        return full

    entries = []
    for lrn in BASE_LEARNERS:
        p = np.asarray(preds[lrn][split], dtype=float)
        cal_scores = {
            "upper": signed_residual_scores(cal["y"], preds[lrn]["calibration"]),
            "two": absolute_residual_scores(cal["y"], preds[lrn]["calibration"]),
        }
        for sided, s_cal in cal_scores.items():
            what = "one-sided upper bound" if sided == "upper" else "upper edge of the two-sided interval"
            entries.append({
                "method": E10 if sided == "upper" else E10_TWO, "learner": lrn, "sided": sided,
                "construction": f"point + Q, one shared split-conformal quantile ({what})",
                "score": split_interval(p, s_cal, alpha, sided=sided).hi,
                "point": p, "construction_reference": p, "structural_class": TRANSLATION_OF_POINT,
            })
            entries.append({
                "method": E11 if sided == "upper" else E11_TWO, "learner": lrn, "sided": sided,
                "construction": f"point + Q_w, one shared weighted quantile, one representative test weight ({what})",
                "score": _expand(weighted_interval(p[supported], s_cal, weights.rule, alpha, sided=sided).interval.hi),
                "point": p, "construction_reference": p, "structural_class": TRANSLATION_OF_POINT,
            })

    p_gbm = np.asarray(preds["gbm"][split], dtype=float)
    head = heads[round(float(level), 6)]
    entries.append({
        "method": E12, "learner": "gbm", "sided": "upper",
        "construction": "q_(1-alpha)(x) + Q, one-sided CQR on the GBM quantile head (rule-weighted)",
        "score": _expand(cqr_upper_bound(
            head[split][supported], cqr_upper_scores(cal["y"], head["calibration"]), alpha,
            weights=weights.rule.w, test_weight=tw).hi),
        "point": p_gbm, "construction_reference": head[split],
        "structural_class": TRANSLATION_OF_QUANTILE_HEAD,
    })
    lo_l, hi_l = round(alpha / 2, 6), round(1.0 - alpha / 2, 6)
    qlo_c, qhi_c = enforce_monotone_quantiles(heads[lo_l]["calibration"], heads[hi_l]["calibration"])
    qlo_t, qhi_t = enforce_monotone_quantiles(heads[lo_l][split], heads[hi_l][split])
    iv_two = cqr_interval(qlo_t[supported], qhi_t[supported], cqr_scores(cal["y"], qlo_c, qhi_c), alpha,
                          weights=weights.rule.w, test_weight=tw)
    entries.append({
        "method": E12_TWO, "learner": "gbm", "sided": "two",
        "construction": "max(q_(alpha/2), q_(1-alpha/2))(x) + Q, two-sided CQR upper edge (rule-weighted)",
        "score": _expand(iv_two.hi), "point": p_gbm, "construction_reference": qhi_t,
        "structural_class": TRANSLATION_OF_QUANTILE_HEAD,
    })

    dist = preds["_mc_dropout_dist"][split]
    mu = np.asarray(dist.mean, dtype=float)
    entries.append({
        "method": E8, "learner": "mc_dropout", "sided": "upper",
        "construction": "mu(x) + z_level * sigma(x), Gaussian predictive (uncalibrated)",
        "score": dist.upper_bound(level), "point": mu, "construction_reference": None,
        "structural_class": EVENT_SPECIFIC_DISPERSION,
    })
    entries.append({
        "method": E8_TWO, "learner": "mc_dropout", "sided": "two",
        "construction": "mu(x) + z_(1-alpha/2) * sigma(x), Gaussian predictive upper edge (uncalibrated)",
        "score": dist.interval(level)[1], "point": mu, "construction_reference": None,
        "structural_class": EVENT_SPECIFIC_DISPERSION,
    })
    return entries


def run_rank_invariance_audit(cfg: Config, *, seeds=None) -> dict:
    """Confirm Proposition 1's classification on the E15 per-event scores.

    Refits the four learners and the GBM quantile heads with the CACHED
    hyperparameters (no search, no model selection; the official test set is
    scored only). The refit is deterministic, so the scores are E15's own; the
    report cross-checks this against the saved E15 table.
    """
    from scipy import stats

    path = audit_progress_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    t0 = time.time()
    _append(path, "rank audit start: loading events and assembling conformal data")

    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)
    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    head_levels = sorted({round(float(lv), 6) for lv in levels}
                         | {round(float(lv), 6) for lv in cqr_quantile_levels(levels)})
    test = data.subsets["official_test"]
    hr = np.asarray(test["is_high_risk"], dtype=bool)
    n = int(hr.size)
    sup = diag.positivity_partition(test["recency_ok"]).supported
    budgets = budget_grid(cfg, n, float(np.mean(hr)))
    z_primary = float(stats.norm.ppf(cfg.power.nominal_coverage_primary))

    cls_rows, alert_rows, disp_rows = [], [], []
    for seed in seeds:
        _append(path, f"seed {seed}: fitting base learners (cached hyperparameters)")
        preds = base_predictions(cfg, data, seed)
        _append(path, f"seed {seed}: fitting GBM quantile heads at {head_levels}")
        heads = _fit_upper_heads(cfg, data, seed, head_levels)
        _append(path, f"seed {seed}: auditing")

        dist = preds["_mc_dropout_dist"]["official_test"]
        mu, sd = np.asarray(dist.mean, float), np.asarray(dist.std, float)
        epi = np.asarray(dist.epistemic_std, float)
        disp_rows.append({
            "seed": seed,
            "aleatoric_std": float(dist.aleatoric_std),
            "epistemic_std_p05": float(np.quantile(epi, 0.05)),
            "epistemic_std_median": float(np.median(epi)),
            "epistemic_std_p95": float(np.quantile(epi, 0.95)),
            "total_std_min": float(sd.min()),
            "total_std_median": float(np.median(sd)),
            "total_std_max": float(sd.max()),
            "aleatoric_share_of_mean_variance": float(dist.aleatoric_std ** 2 / np.mean(sd ** 2)),
            "range_of_mean": float(np.ptp(mu)),
            "range_of_z_primary_times_std": float(np.ptp(z_primary * sd)),
            "spearman_mean_vs_total_std": float(stats.spearmanr(mu, sd).statistic),
        })

        point_alerts: dict = {}
        for lvl in levels:
            for e in rank_audit_scores(data, weights, preds, heads, lvl, sup):
                chk = dc.monotone_transform_check(e["point"], e["score"])
                ref = e["construction_reference"]
                chk_ref = dc.monotone_transform_check(ref, e["score"]) if ref is not None else None
                cls_rows.append({
                    "seed": seed, "nominal": lvl, "method": e["method"], "learner": e["learner"],
                    "sided": e["sided"], "structural_class": e["structural_class"],
                    "construction": e["construction"],
                    "strictly_increasing_in_point": chk["strictly_increasing"],
                    "order_violations_vs_point": chk["order_violations"],
                    "tie_violations_vs_point": chk["tie_violations"],
                    "kendall_tau_vs_point": float(stats.kendalltau(e["point"], e["score"]).statistic),
                    "offset_spread_vs_point": float(np.ptp(e["score"] - e["point"])),
                    "has_construction_reference": chk_ref is not None,
                    "strictly_increasing_in_construction_reference": bool(chk_ref["strictly_increasing"]) if chk_ref else False,
                })
                for _, b in budgets.iterrows():
                    k = int(b["K"])
                    if (e["learner"], k) not in point_alerts:
                        point_alerts[(e["learner"], k)] = dc.matched_budget_alerts(e["point"], k)
                    a_p = point_alerts[(e["learner"], k)]
                    a_s = dc.matched_budget_alerts(e["score"], k)
                    alert_rows.append({
                        "seed": seed, "nominal": lvl, "method": e["method"], "learner": e["learner"],
                        "sided": e["sided"], "budget": str(b["budget"]), "K": k,
                        "max_abs_alert_difference_vs_point": float(np.max(np.abs(a_s - a_p))),
                        "alert_overlap_vs_point": dc.alert_overlap(a_s, a_p),
                        "missed_high_risk": dc.decision_counts(a_s, hr).fn,
                        "missed_high_risk_point": dc.decision_counts(a_p, hr).fn,
                    })
        _append(path, f"seed {seed}: done")

    cls_raw = pd.DataFrame(cls_rows)
    keys = ["method", "learner", "sided", "structural_class", "construction"]
    classification = cls_raw.groupby(keys, sort=False).agg(
        strictly_increasing_in_point_all=("strictly_increasing_in_point", "all"),
        order_violations_vs_point_max=("order_violations_vs_point", "max"),
        tie_violations_vs_point_max=("tie_violations_vs_point", "max"),
        kendall_tau_vs_point_min=("kendall_tau_vs_point", "min"),
        kendall_tau_vs_point_mean=("kendall_tau_vs_point", "mean"),
        offset_spread_vs_point_max=("offset_spread_vs_point", "max"),
        has_construction_reference=("has_construction_reference", "all"),
        strictly_increasing_in_construction_reference_all=("strictly_increasing_in_construction_reference", "all"),
        n_level_seed_rows=("seed", "size"),
    ).reset_index()
    alerts_raw = pd.DataFrame(alert_rows)
    alerts = alerts_raw.groupby(["method", "learner", "sided", "nominal", "budget", "K"], sort=False).agg(
        max_abs_alert_difference_vs_point=("max_abs_alert_difference_vs_point", "max"),
        alert_overlap_vs_point_mean=("alert_overlap_vs_point", "mean"),
        alert_overlap_vs_point_min=("alert_overlap_vs_point", "min"),
        missed_high_risk=("missed_high_risk", "mean"),
        missed_high_risk_point=("missed_high_risk_point", "mean"),
    ).reset_index()
    _append(path, f"rank audit done in {round(time.time() - t0, 1)} s")
    return {
        "classification": classification,
        "classification_raw": cls_raw,
        "alerts": alerts,
        "alerts_raw": alerts_raw,
        "e8_dispersion": pd.DataFrame(disp_rows),
        "budgets": budgets,
        "meta": {"seeds": seeds, "levels": levels, "head_levels": head_levels, "n_test": n,
                 "n_high_risk": int(hr.sum()), "n_supported": int(sup.sum())},
    }
