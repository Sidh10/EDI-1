"""E9-E11 driver: split, naive, and weighted conformal over four base learners.

Wires the tested conformal core (``kelvins_conformal.conformal``) to the Phase-2
base learners and the challenge data, following the Phase 3 design-review
resolutions exactly:

  * one nonconformity score per event per horizon, calibrated on the full training
    pool (Q-CONF-01);
  * four base learners — persistence (E5 LRP), GBM (E6), GRU (E7), MC-dropout (E8)
    — the 2026-09-01 amendment set;
  * E9 calibrates on the ``calibration`` subset and evaluates on the exchangeable
    ``self_test`` subset (machinery validation); E10 evaluates the SAME calibrated
    interval on the official test set (naive, biased); E11 reweights with
    rule-derived likelihood ratios (primary) and classifier weights (secondary),
    reporting the full Q-SEL-03 diagnostic set and the positivity partition;
  * the single pre-registered formal contrast is E10 vs E11 marginal coverage at
    the primary level, two-sided (Q-STAT-04) — computed here, tested in the report.

The official test set is READ ONCE per experiment for scoring only; nothing here
tunes on it (CLAUDE.md §3). Model selection reused the Phase-2 cached searches.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Config
from ..conformal import diagnostics as diag
from ..conformal.split import (
    Interval,
    absolute_residual_scores,
    signed_residual_scores,
    split_interval,
)
from ..conformal.weighted import weighted_interval
from ..conformal.weights import (
    WeightVector,
    classifier_weights,
    gamma_divergence,
    rule_derived_weights,
)
from ..data import event_level_frame, load_events, training_pool_splits
from ..features import (
    apply_standardisation,
    build_sequence_tensors,
    build_tabular_features,
    standardise,
)
from .runner import cached_search

BASE_LEARNERS = ("persistence", "gbm", "gru", "mc_dropout")


# --- data assembly -----------------------------------------------------------


@dataclass
class ConformalData:
    """Per-subset features, targets, and the auxiliary arrays weights need."""

    subsets: dict            # name -> dict(uids, y, tab_X, seq_X, seq_len,
                             #              risk_last, recency_ok, last_ttc)
    tab_feature_names: tuple
    seq_feature_names: tuple
    seq_mean: np.ndarray
    seq_std: np.ndarray
    train_high_risk_prevalence: float
    test_high_risk_prevalence: float


def prepare_conformal_data(cfg: Config, events: pd.DataFrame) -> ConformalData:
    """Slice tabular + sequence features into the four training-pool subsets + test."""
    splits = training_pool_splits(events, cfg)   # fit_inner, val_inner, calibration, self_test
    per_event = event_level_frame(events).set_index("event_uid")

    train_fm = build_tabular_features(events, cfg, split="train")
    test_fm = build_tabular_features(events, cfg, split="test")
    train_st = build_sequence_tensors(events, cfg, split="train")
    test_st = build_sequence_tensors(
        events, cfg, split="test", feature_names=train_st.feature_names
    )

    # Standardise sequences on fit-split statistics only (no leakage).
    fit_mask_st = np.isin(train_st.event_uids, splits["fit_inner"])
    mean, std = standardise(train_st.X[fit_mask_st], train_st.mask[fit_mask_st])

    thr = cfg.high_risk_threshold
    rec_days = cfg.cutoff.test_recency_filter_days

    def _subset(uids_wanted, fm, st, split_name):
        # align tabular
        tab_mask = np.isin(fm.event_uids, uids_wanted)
        uids = fm.event_uids[tab_mask]
        tab_X = fm.X.loc[uids]
        y = fm.y[tab_mask]
        # align sequence to the SAME uid order
        st_index = {u: i for i, u in enumerate(st.event_uids)}
        seq_idx = np.array([st_index[u] for u in uids])
        seq_X = apply_standardisation(st.X[seq_idx], st.mask[seq_idx], mean, std)
        seq_len = st.lengths[seq_idx]
        # auxiliaries from the per-event frame
        pe = per_event.loc[uids]
        risk_last = tab_X["risk_last"].to_numpy(float) if "risk_last" in tab_X else pe["last_input_risk"].to_numpy(float)
        last_ttc = pe["target_time_to_tca"].to_numpy(float)
        recency_ok = last_ttc <= rec_days
        return {
            "uids": uids, "y": y, "tab_X": tab_X, "seq_X": seq_X, "seq_len": seq_len,
            "risk_last": risk_last, "recency_ok": recency_ok, "last_ttc": last_ttc,
            "is_high_risk": y >= thr,
        }

    subsets = {}
    for name in ("fit_inner", "val_inner", "calibration", "self_test"):
        subsets[name] = _subset(splits[name], train_fm, train_st, name)
    subsets["official_test"] = _subset(test_fm.event_uids, test_fm, test_st, "official_test")

    train_prev = float(np.mean(np.concatenate([
        subsets[s]["is_high_risk"] for s in ("fit_inner", "val_inner", "calibration", "self_test")
    ])))
    test_prev = float(np.mean(subsets["official_test"]["is_high_risk"]))

    return ConformalData(
        subsets=subsets, tab_feature_names=train_fm.feature_names,
        seq_feature_names=train_st.feature_names, seq_mean=mean, seq_std=std,
        train_high_risk_prevalence=train_prev, test_high_risk_prevalence=test_prev,
    )


# --- base-learner point predictions -----------------------------------------


def base_predictions(cfg: Config, data: ConformalData, seed: int) -> dict:
    """Point predictions per base learner on calibration, self_test, official_test.

    Fits on ``fit_inner`` (early stop on ``val_inner``) using the Phase-2 cached
    best hyperparameters; persistence needs no fit. Returns
    {learner: {split: yhat}} for the three evaluation subsets plus calibration.
    """
    from . import bayesian as by
    from . import gbm as gbm_mod
    from . import sequence as seq_mod
    from .runner import search_gbm, search_mc_dropout, search_sequence

    eval_splits = ("calibration", "self_test", "official_test")
    out: dict = {lrn: {} for lrn in BASE_LEARNERS}

    # persistence: yhat = r_last (observable pre-cutoff persistence forecast).
    for s in eval_splits:
        out["persistence"][s] = data.subsets[s]["risk_last"].copy()

    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]

    # GBM (cached E6 params).
    from .runner import TabularData as _TD  # noqa: F401 (documents provenance)
    gbm_budget = cached_search(cfg, "e6_gbm", cfg.seed,
                               lambda: search_gbm(cfg, _tab_view(data), seed=cfg.seed))
    gbm_res = gbm_mod.fit_gbm(
        fit["tab_X"], fit["y"], val["tab_X"], val["y"], seed=seed,
        params=_gbm_params(gbm_budget.best_params, seed),
        # E9-E11 use POINT predictions only; the quantile heads feed E12/CQR
        # (out of scope for this batch), so they are not fit here.
        quantile_levels=(),
        num_boost_round=cfg.gbm.num_boost_round,
        early_stopping_rounds=cfg.train.early_stopping_rounds,
    )
    for s in eval_splits:
        out["gbm"][s] = gbm_res.predict(data.subsets[s]["tab_X"])

    # GRU (cached E7 params).
    seq_budget = cached_search(cfg, "e7_sequence", cfg.seed,
                               lambda: search_sequence(cfg, _seq_view(data), seed=cfg.seed))
    gru_res = _fit_sequence(seq_mod, cfg, data, seq_budget.best_params, seed)
    for s in eval_splits:
        out["gru"][s] = gru_res.predict(data.subsets[s]["seq_X"], data.subsets[s]["seq_len"])

    # MC-dropout (cached E8 params); point prediction = MC predictive mean.
    mc_budget = cached_search(cfg, "e8_mcdropout", cfg.seed,
                              lambda: search_mc_dropout(cfg, _seq_view(data), seed=cfg.seed))
    mc_res = _fit_sequence(seq_mod, cfg, data, mc_budget.best_params, seed)
    val_pred = mc_res.predict(val["seq_X"], val["seq_len"])
    aleatoric = by.estimate_aleatoric_std(val["y"], val_pred)
    for s in eval_splits:
        dist = by.mc_dropout_predict(
            mc_res, data.subsets[s]["seq_X"], data.subsets[s]["seq_len"],
            n_samples=cfg.bayesian.n_mc_samples, aleatoric_std=aleatoric, seed=seed,
        )
        out["mc_dropout"][s] = dist.mean
        # E15 needs the full predictive distribution for the one-sided Bayesian
        # bound. It is stored under a private key, so the E9-E11 loops over
        # BASE_LEARNERS never see it and their outputs are unchanged.
        out.setdefault("_mc_dropout_dist", {})[s] = dist

    return out


def _gbm_params(best: dict, seed: int) -> dict:
    from .gbm import default_params
    p = default_params(seed)
    p.update(best)
    return p


def _fit_sequence(seq_mod, cfg: Config, data: ConformalData, best: dict, seed: int):
    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]
    return seq_mod.train_sequence_model(
        fit["seq_X"], fit["seq_len"], fit["y"], val["seq_X"], val["seq_len"], val["y"],
        seed=seed, n_features=fit["seq_X"].shape[2],
        hidden_size=best.get("hidden_size", cfg.sequence.hidden_size),
        num_layers=best.get("num_layers", cfg.sequence.num_layers),
        dropout=best.get("dropout", cfg.sequence.dropout),
        cell=best.get("cell", cfg.sequence.cell),
        batch_size=best.get("batch_size", cfg.sequence.batch_size),
        learning_rate=best.get("learning_rate", cfg.sequence.learning_rate),
        max_epochs=cfg.sequence.max_epochs,
        early_stopping_rounds=10,
        feature_names=data.seq_feature_names,
    )


# Lightweight adapters so the Phase-2 search functions (which expect their own
# data views) can run against the conformal fit/val slices if a cache miss occurs.
def _tab_view(data: ConformalData):
    from .runner import TabularData
    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]
    t = data.subsets["official_test"]
    return TabularData(
        fit_X=fit["tab_X"], fit_y=fit["y"], val_X=val["tab_X"], val_y=val["y"],
        test_X=t["tab_X"], test_y=t["y"], test_uids=t["uids"],
        feature_names=data.tab_feature_names, n_dropped_train=0, n_dropped_test=0,
    )


def _seq_view(data: ConformalData):
    from .runner import SequenceData
    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]
    t = data.subsets["official_test"]
    return SequenceData(
        fit_X=fit["seq_X"], fit_len=fit["seq_len"], fit_y=fit["y"],
        val_X=val["seq_X"], val_len=val["seq_len"], val_y=val["y"],
        test_X=t["seq_X"], test_len=t["seq_len"], test_y=t["y"], test_uids=t["uids"],
        feature_names=data.seq_feature_names, conditioned_features=(),
        mean=data.seq_mean, std=data.seq_std,
    )


# --- coverage evaluation -----------------------------------------------------


def coverage_with_ci(
    y: np.ndarray, interval: Interval, *, seed: int, n_boot: int, level: float = 0.95
) -> dict:
    """Empirical coverage + event-level bootstrap CI + Clopper-Pearson interval."""
    from scipy import stats

    covered = interval.covers(y).astype(float)
    cov = float(np.mean(covered))
    n = int(covered.size)
    k = int(covered.sum())
    # Event-level percentile bootstrap on the coverage indicator. Vectorised (draw
    # the full (n_boot, n) index matrix at once) rather than looping in Python —
    # this is the identical percentile bootstrap the audited ``bootstrap_statistic``
    # computes for a mean, just fast enough to call across all method/level/side
    # combinations. Same event-level unit (invariant I3).
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    draws = covered[idx].mean(axis=1)
    a = 1.0 - level
    boot_lo, boot_hi = np.percentile(draws, [100 * a / 2, 100 * (1 - a / 2)])
    cp_lo = 0.0 if k == 0 else float(stats.beta.ppf(a / 2, k, n - k + 1))
    cp_hi = 1.0 if k == n else float(stats.beta.ppf(1 - a / 2, k + 1, n - k))
    widths = interval.width
    finite_w = widths[np.isfinite(widths)]
    return {
        "coverage": cov, "n": n, "n_covered": k,
        "boot_lo": float(boot_lo), "boot_hi": float(boot_hi),
        "cp_lo": cp_lo, "cp_hi": cp_hi,
        "median_width": float(np.median(finite_w)) if finite_w.size else float("inf"),
        "frac_infinite_width": float(np.mean(~np.isfinite(widths))),
    }


def make_scores(y_cal: np.ndarray, pred_cal: np.ndarray, sided: str) -> np.ndarray:
    return (absolute_residual_scores(y_cal, pred_cal) if sided == "two"
            else signed_residual_scores(y_cal, pred_cal))


# --- weight construction on real calibration data ----------------------------


@dataclass
class WeightBundle:
    rule: WeightVector
    classifier: WeightVector
    gamma: float
    classifier_auc: float


def build_weights(cfg: Config, data: ConformalData) -> WeightBundle:
    """Rule-derived (primary) and classifier-estimated (secondary) calibration weights.

    Rule weights use the two documented axes on OBSERVABLE covariates (recency of the
    final CDM; pre-cutoff risk proxy r_last), with the E1 prevalences. Classifier
    weights train a logistic-regression discriminator (calibration vs official-test)
    on the dictionary-safe tabular features and form w = p/(1-p) on calibration
    events. gamma quantifies their agreement (Q-SEL-01).
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    cal = data.subsets["calibration"]
    test = data.subsets["official_test"]

    rule = rule_derived_weights(
        cal["recency_ok"], cal["risk_last"],
        test_high_risk_prevalence=data.test_high_risk_prevalence,
        train_high_risk_prevalence=data.train_high_risk_prevalence,
        high_risk_threshold=cfg.high_risk_threshold,
        recency_epsilon=0.0,
    )

    # Classifier discriminator on safe tabular features (drop categorical mission_id).
    num_cols = [c for c in cal["tab_X"].columns if c != "mission_id"]
    med = pd.concat([cal["tab_X"][num_cols], test["tab_X"][num_cols]], axis=0).median(numeric_only=True)
    X = pd.concat([cal["tab_X"][num_cols], test["tab_X"][num_cols]], axis=0).fillna(med)
    labels = np.concatenate([np.zeros(len(cal["tab_X"])), np.ones(len(test["tab_X"]))])
    clf = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, C=1.0, random_state=cfg.seed),
    )
    clf.fit(X, labels)
    auc = float(roc_auc_score(labels, clf.predict_proba(X)[:, 1]))
    p_cal = clf.predict_proba(cal["tab_X"][num_cols].fillna(med))[:, 1]
    classifier = classifier_weights(p_cal)

    gamma = gamma_divergence(rule.w, classifier.w)
    return WeightBundle(rule=rule, classifier=classifier, gamma=gamma, classifier_auc=auc)


# --- full E9-E11 run ---------------------------------------------------------


def run_all(cfg: Config, *, seeds=None, n_boot: int | None = None) -> dict:
    """Execute E9, E10, E11 across four base learners, seeds, sidedness, levels."""
    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)

    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    primary_level = cfg.power.nominal_coverage_primary
    sides = ("two", "upper")

    test = data.subsets["official_test"]
    self_test = data.subsets["self_test"]
    cal = data.subsets["calibration"]
    part = diag.positivity_partition(test["recency_ok"])

    rows, diag_rows = [], []
    for seed in seeds:
        preds = base_predictions(cfg, data, seed)
        for lrn in BASE_LEARNERS:
            for sided in sides:
                scores_cal = make_scores(cal["y"], preds[lrn]["calibration"], sided)
                for lvl in levels:
                    alpha = 1.0 - lvl
                    iv9 = split_interval(preds[lrn]["self_test"], scores_cal, alpha, sided=sided)
                    c9 = coverage_with_ci(self_test["y"], iv9, seed=seed, n_boot=n_boot)
                    iv10 = split_interval(preds[lrn]["official_test"], scores_cal, alpha, sided=sided)
                    c10 = coverage_with_ci(test["y"], iv10, seed=seed, n_boot=n_boot)
                    sup = part.supported
                    for wname, wv in (("rule", weights.rule), ("classifier", weights.classifier)):
                        res = weighted_interval(
                            preds[lrn]["official_test"][sup], scores_cal, wv, alpha, sided=sided,
                            cal_covariates={"risk_level": cal["risk_last"],
                                            "last_time_to_tca": cal["last_ttc"]},
                        )
                        c11 = coverage_with_ci(test["y"][sup], res.interval, seed=seed, n_boot=n_boot)
                        rows.append(_row(lrn, f"E11_weighted_{wname}", sided, lvl, seed, c11,
                                         alpha_eff=res.alpha_effective))
                        if seed == seeds[len(seeds) // 2] and sided == "two":
                            d = dict(res.diagnostics)
                            d.update(learner=lrn, weight=wname, level=lvl)
                            diag_rows.append(d)
                    rows.append(_row(lrn, "E9_selftest", sided, lvl, seed, c9))
                    rows.append(_row(lrn, "E10_naive_official", sided, lvl, seed, c10))

    coverage = pd.DataFrame(rows)
    return {
        "coverage_raw": coverage,
        "coverage": _aggregate(coverage),
        "diagnostics": pd.DataFrame(diag_rows),
        "weights": pd.DataFrame([{
            "gamma_divergence": weights.gamma, "classifier_auc": weights.classifier_auc,
            "rule_n": int(weights.rule.w.size),
            "rule_n_effective": diag.effective_sample_size(weights.rule.w),
            "rule_khat": diag.pareto_khat(weights.rule.w),
            "classifier_n_effective": diag.effective_sample_size(weights.classifier.w),
            "classifier_khat": diag.pareto_khat(weights.classifier.w),
        }]),
        "primary_contrast": _primary_contrast(coverage, primary_level),
        "positivity": pd.DataFrame([{
            "n_test_total": int(test["y"].size), "n_supported": part.n_supported,
            "n_unsupported": part.n_unsupported,
            "unsupported_high_risk": int(np.sum(test["is_high_risk"][~part.supported])),
        }]),
        "rule_weights": weights.rule.w,
        "meta": {"seeds": seeds, "levels": levels, "primary_level": primary_level,
                 "train_prev": data.train_high_risk_prevalence,
                 "test_prev": data.test_high_risk_prevalence},
    }


def _row(lrn, method, sided, level, seed, c, alpha_eff=None):
    r = {"learner": lrn, "method": method, "sided": sided, "nominal": level, "seed": seed, **c}
    if alpha_eff is not None:
        r["alpha_effective"] = alpha_eff
    return r


def _aggregate(coverage: pd.DataFrame) -> pd.DataFrame:
    g = coverage.groupby(["learner", "method", "sided", "nominal"])
    out = g.agg(
        coverage_mean=("coverage", "mean"), coverage_sd=("coverage", "std"),
        n=("n", "first"), median_width_mean=("median_width", "mean"),
        cp_lo_mean=("cp_lo", "mean"), cp_hi_mean=("cp_hi", "mean"),
        frac_inf_width=("frac_infinite_width", "mean"), n_seeds=("seed", "nunique"),
    ).reset_index()
    out["gap_pp"] = 100.0 * (out["coverage_mean"] - out["nominal"])
    return out


def _primary_contrast(coverage: pd.DataFrame, primary_level: float) -> pd.DataFrame:
    sub = coverage[(coverage["nominal"] == primary_level) & (coverage["sided"] == "two")]
    rows = []
    for lrn in sub["learner"].unique():
        e10 = sub[(sub["learner"] == lrn) & (sub["method"] == "E10_naive_official")]
        e11 = sub[(sub["learner"] == lrn) & (sub["method"] == "E11_weighted_rule")]
        rows.append({
            "learner": lrn, "nominal": primary_level,
            "E10_coverage": float(e10["coverage"].mean()),
            "E11_rule_coverage": float(e11["coverage"].mean()),
            "gap_closed_pp": 100.0 * (float(e11["coverage"].mean()) - float(e10["coverage"].mean())),
            "E10_gap_pp": 100.0 * (float(e10["coverage"].mean()) - primary_level),
            "E11_gap_pp": 100.0 * (float(e11["coverage"].mean()) - primary_level),
        })
    return pd.DataFrame(rows)


# --- E12: Conformalized Quantile Regression -----------------------------------


def cqr_quantile_levels(nominal_levels) -> list:
    """The GBM quantile heads CQR needs: {alpha/2, 1-alpha/2} for each nominal level.

    Derived from the (config-declared) nominal coverage levels, so no quantile
    level is a hardcoded magic number.
    """
    levels = set()
    for nl in nominal_levels:
        a = 1.0 - nl
        levels.add(round(a / 2, 6))
        levels.add(round(1.0 - a / 2, 6))
    return sorted(levels)


def run_e12(cfg: Config, *, seeds=None, n_boot: int | None = None) -> dict:
    """E12 CQR on the GBM quantile heads: naive + weighted, vs E11 split conformal.

    CQR uses genuine quantile predictors, so it runs on the GBM pinball heads (the
    E6 quantile capability); the point-only learners (persistence/GRU/MC-dropout)
    have no native quantiles and are out of E12's scope per the spec. Both a naive
    and a rule-weighted CQR interval are produced on the SUPPORTED official-test
    region, at every nominal level, two-sided, and compared per-event against the
    weighted split-conformal interval (E11) for the efficiency (width) analysis.
    """
    from ..conformal.cqr import cqr_interval, cqr_scores, enforce_monotone_quantiles
    from . import gbm as gbm_mod
    from .runner import search_gbm

    events = load_events(cfg)
    data = prepare_conformal_data(cfg, events)
    weights = build_weights(cfg, data)

    seeds = list(seeds if seeds is not None else cfg.train.seeds)
    n_boot = int(n_boot if n_boot is not None else cfg.bootstrap.n_resamples)
    nominal_levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    primary = cfg.power.nominal_coverage_primary
    qlevels = cqr_quantile_levels(nominal_levels)

    fit, val = data.subsets["fit_inner"], data.subsets["val_inner"]
    cal, test = data.subsets["calibration"], data.subsets["official_test"]
    part = diag.positivity_partition(test["recency_ok"])
    sup = part.supported

    gbm_budget = cached_search(cfg, "e6_gbm", cfg.seed,
                               lambda: search_gbm(cfg, _tab_view(data), seed=cfg.seed))
    params = _gbm_params(gbm_budget.best_params, cfg.seed)

    rows = []
    width_pairs = []      # per-(level,seed): CQR vs split median widths (efficiency)
    adapt = None
    for seed in seeds:
        p = _gbm_params(gbm_budget.best_params, seed)
        # Quantile heads at the CQR levels, and the point model for the split-CP baseline.
        qmodels, qbest = gbm_mod.fit_quantile_models(
            fit["tab_X"], fit["y"], val["tab_X"], val["y"], qlevels, seed=seed, params=p,
            num_boost_round=cfg.gbm.num_boost_round,
            early_stopping_rounds=cfg.train.early_stopping_rounds,
        )
        point, best_it = gbm_mod.fit_point_model(
            fit["tab_X"], fit["y"], val["tab_X"], val["y"], seed=seed, params=params,
            num_boost_round=cfg.gbm.num_boost_round,
            early_stopping_rounds=cfg.train.early_stopping_rounds,
        )

        def qpred(level, X, _m=qmodels, _b=qbest):
            return np.asarray(_m[level].predict(X, num_iteration=_b[level]), dtype=float)

        pt_cal = np.asarray(point.predict(cal["tab_X"], num_iteration=best_it), dtype=float)
        pt_te = np.asarray(point.predict(test["tab_X"], num_iteration=best_it), dtype=float)[sup]
        selft = data.subsets["self_test"]

        for nl in nominal_levels:
            a = 1.0 - nl
            lo_l = round(a / 2, 6)
            hi_l = round(1.0 - a / 2, 6)

            qlo_c, qhi_c = enforce_monotone_quantiles(qpred(lo_l, cal["tab_X"]), qpred(hi_l, cal["tab_X"]))
            qlo_t, qhi_t = enforce_monotone_quantiles(
                qpred(lo_l, test["tab_X"])[sup], qpred(hi_l, test["tab_X"])[sup]
            )
            s_cqr = cqr_scores(cal["y"], qlo_c, qhi_c)

            # CQR machinery validation on the EXCHANGEABLE self-test split (the E9
            # analog for CQR): no shift, no weights. Distinguishes a shift-driven
            # official-test result from GBM quantile-head miscalibration.
            qlo_s, qhi_s = enforce_monotone_quantiles(qpred(lo_l, selft["tab_X"]), qpred(hi_l, selft["tab_X"]))
            iv_cs = cqr_interval(qlo_s, qhi_s, s_cqr, a)
            c_cs = coverage_with_ci(selft["y"], iv_cs, seed=seed, n_boot=n_boot)
            rows.append(_row("gbm", "E12_cqr_selftest", "two", nl, seed, c_cs))

            iv_cn = cqr_interval(qlo_t, qhi_t, s_cqr, a)
            iv_cw = cqr_interval(qlo_t, qhi_t, s_cqr, a,
                                 weights=weights.rule.w, test_weight=weights.rule.test_weight)
            c_cn = coverage_with_ci(test["y"][sup], iv_cn, seed=seed, n_boot=n_boot)
            c_cw = coverage_with_ci(test["y"][sup], iv_cw, seed=seed, n_boot=n_boot)
            rows.append(_row("gbm", "E12_cqr_naive", "two", nl, seed, c_cn))
            rows.append(_row("gbm", "E12_cqr_weighted_rule", "two", nl, seed, c_cw))

            # Weighted split-conformal (E11-equivalent) on the GBM POINT model, same
            # seed and events, for the paired width-efficiency comparison.
            s_split = absolute_residual_scores(cal["y"], pt_cal)
            iv_sw = split_interval(pt_te, s_split, a, sided="two",
                                   weights=weights.rule.w, test_weight=weights.rule.test_weight)
            c_sw = coverage_with_ci(test["y"][sup], iv_sw, seed=seed, n_boot=n_boot)
            rows.append(_row("gbm", "E11ref_split_weighted_rule", "two", nl, seed, c_sw))

            width_pairs.append({
                "nominal": nl, "seed": seed,
                "cqr_median_width": float(np.median(iv_cw.width[np.isfinite(iv_cw.width)])),
                "split_median_width": float(np.median(iv_sw.width[np.isfinite(iv_sw.width)])),
                "cqr_width_sd": float(np.std(iv_cw.width[np.isfinite(iv_cw.width)])),
                "split_width_sd": float(np.std(iv_sw.width[np.isfinite(iv_sw.width)])),
            })

            if nl == primary and seed == seeds[len(seeds) // 2]:
                adapt = pd.DataFrame({
                    "risk_last": test["risk_last"][sup],
                    "cqr_width": iv_cw.width,
                    "split_width": iv_sw.width,
                    "is_high_risk": test["is_high_risk"][sup],
                })

    coverage = pd.DataFrame(rows)
    widths = pd.DataFrame(width_pairs)
    wagg = widths.groupby("nominal").agg(
        cqr_median_width=("cqr_median_width", "mean"),
        split_median_width=("split_median_width", "mean"),
        cqr_width_sd=("cqr_width_sd", "mean"),
        split_width_sd=("split_width_sd", "mean"),
    ).reset_index()
    wagg["width_ratio_cqr_over_split"] = wagg["cqr_median_width"] / wagg["split_median_width"]

    return {
        "coverage_raw": coverage,
        "coverage": _aggregate(coverage),
        "widths": wagg,
        "adaptivity": adapt,
        "gamma_divergence": weights.gamma,
        "meta": {"seeds": seeds, "nominal_levels": nominal_levels, "primary_level": primary,
                 "cqr_quantile_levels": qlevels, "n_supported": int(sup.sum())},
    }
