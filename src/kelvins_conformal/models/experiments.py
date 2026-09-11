"""End-to-end drivers for E6, E7 and E8.

Each driver runs the same disciplined sequence:

    hyperparameter search (val_inner)
      -> target/decision-rule selection (val_inner)
        -> multi-seed training
          -> ONE final scoring pass on the official test set

The official test set is read exactly once per experiment, in the last step. Every
selection decision above it happens on ``val_inner``, which is carved out of the
``fit`` pool so Phase 3's calibration/self-test subsets stay untouched.

Keeping the drivers here rather than in the notebooks means they are importable
and testable, and that the three experiments provably share the same machinery
(which is what makes the E8 steelman's "equal budget" claim checkable).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import Config
from ..metrics import challenge_score
from . import runner as R
from .gbm import fit_gbm, pinball_loss, quantile_crossing_rate
from .sequence import train_sequence_model


@dataclass
class ExperimentResult:
    """Everything an experiment's report needs, and nothing the test set shouldn't see."""

    experiment: str
    budget: R.SearchBudget
    selection: dict = field(default_factory=dict)
    seed_rows: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    test_predictions: dict[int, np.ndarray] = field(default_factory=dict)
    extras: dict = field(default_factory=dict)


# --- E6 ----------------------------------------------------------------------


def run_e6(cfg: Config, data: R.TabularData, *, budget: R.SearchBudget) -> ExperimentResult:
    """E6: LightGBM point + quantile heads."""
    fit_anchor = R.anchor_column(data.fit_X)
    val_anchor = R.anchor_column(data.val_X)
    test_anchor = R.anchor_column(data.test_X)
    params = dict(budget.best_params)

    # 1. Select the target parameterisation on validation.
    mode_rows = []
    best_mode, best_val_loss = None, float("inf")
    for mode in R.TARGET_MODES:
        r = fit_gbm(
            data.fit_X, R.to_model_target(data.fit_y, fit_anchor, mode),
            data.val_X, R.to_model_target(data.val_y, val_anchor, mode),
            seed=cfg.seed, params={**_base_params(cfg), **params},
            num_boost_round=cfg.gbm.num_boost_round,
            early_stopping_rounds=cfg.train.early_stopping_rounds,
        )
        pv = R.from_model_output(r.predict(data.val_X), val_anchor, mode)
        tau, _ = R.select_promotion_threshold(cfg, data.val_y, pv)
        s = challenge_score(
            data.val_y,
            R.apply_promotion(pv, tau, threshold=cfg.high_risk_threshold,
                              margin=cfg.decision_rule.promotion_margin),
            threshold=cfg.high_risk_threshold, beta=cfg.metric.f_beta,
            clip_epsilon=cfg.metric.prediction_clip_epsilon,
        )
        mode_rows.append({"target mode": mode, "val L": s.loss,
                          "val MSE_HR": s.mse_hr, "val F2": s.f2, "tau": tau})
        if s.is_defined and s.loss < best_val_loss:
            best_mode, best_val_loss = mode, s.loss

    # 2. Fix the promotion threshold on validation using the selected mode.
    ref = fit_gbm(
        data.fit_X, R.to_model_target(data.fit_y, fit_anchor, best_mode),
        data.val_X, R.to_model_target(data.val_y, val_anchor, best_mode),
        seed=cfg.seed, params={**_base_params(cfg), **params},
        num_boost_round=cfg.gbm.num_boost_round,
        early_stopping_rounds=cfg.train.early_stopping_rounds,
    )
    pv = R.from_model_output(ref.predict(data.val_X), val_anchor, best_mode)
    tau, tau_sweep = R.select_promotion_threshold(cfg, data.val_y, pv)

    # 3. Multi-seed training, then the single test pass per seed.
    seed_rows, preds, quantile_rows = [], {}, []
    for seed in cfg.train.seeds[: cfg.train.n_seeds]:
        r = fit_gbm(
            data.fit_X, R.to_model_target(data.fit_y, fit_anchor, best_mode),
            data.val_X, R.to_model_target(data.val_y, val_anchor, best_mode),
            seed=seed, quantile_levels=cfg.gbm.quantile_levels,
            params={**_base_params(cfg), **params},
            num_boost_round=cfg.gbm.num_boost_round,
            early_stopping_rounds=cfg.train.early_stopping_rounds,
        )
        y_test_pred = R.apply_promotion(
            R.from_model_output(r.predict(data.test_X), test_anchor, best_mode),
            tau, threshold=cfg.high_risk_threshold,
            margin=cfg.decision_rule.promotion_margin,
        )
        row = R.score(cfg, data.test_y, y_test_pred, seed=seed)
        row["seed"] = seed
        seed_rows.append(row)
        preds[seed] = y_test_pred

        # Quantile heads: pinball loss on VALIDATION (they are not used for the
        # headline score; they exist for Phase 3's CQR).
        qv = r.predict_quantiles(data.val_X)
        for q, qp in qv.items():
            quantile_rows.append({
                "seed": seed, "quantile": q,
                "val pinball": pinball_loss(
                    R.to_model_target(data.val_y, val_anchor, best_mode), qp, q
                ),
            })
        quantile_rows.append({
            "seed": seed, "quantile": "crossing rate",
            "val pinball": quantile_crossing_rate(qv),
        })

    return ExperimentResult(
        experiment="E6", budget=budget,
        selection={"target_mode": best_mode, "promotion_tau": tau,
                   "val_loss_at_selection": best_val_loss},
        seed_rows=seed_rows,
        summary=R.aggregate_seeds(seed_rows, "E6 GBM (LightGBM)"),
        test_predictions=preds,
        extras={"target_mode_sweep": pd.DataFrame(mode_rows).set_index("target mode"),
                "tau_sweep": tau_sweep,
                "quantiles": pd.DataFrame(quantile_rows)},
    )


def _base_params(cfg: Config) -> dict:
    from .gbm import default_params

    return default_params(cfg.seed)


# --- E7 ----------------------------------------------------------------------


def run_e7(cfg: Config, data: R.SequenceData, *, budget: R.SearchBudget) -> ExperimentResult:
    """E7: recurrent point predictor."""
    params = dict(budget.best_params) or {
        "hidden_size": cfg.sequence.hidden_size, "num_layers": cfg.sequence.num_layers,
        "dropout": cfg.sequence.dropout, "learning_rate": cfg.sequence.learning_rate,
        "batch_size": cfg.sequence.batch_size, "cell": cfg.sequence.cell,
    }

    # Reference run to fix the promotion threshold on validation.
    ref = train_sequence_model(
        data.fit_X, data.fit_len, data.fit_y, data.val_X, data.val_len, data.val_y,
        seed=cfg.seed, n_features=data.fit_X.shape[2],
        max_epochs=cfg.sequence.max_epochs,
        early_stopping_rounds=max(5, cfg.train.early_stopping_rounds // 5),
        feature_names=data.feature_names, **params,
    )
    pv = ref.predict(data.val_X, data.val_len)
    tau, tau_sweep = R.select_promotion_threshold(cfg, data.val_y, pv)

    seed_rows, preds, curves = [], {}, {}
    for seed in cfg.train.seeds[: cfg.train.n_seeds]:
        r = train_sequence_model(
            data.fit_X, data.fit_len, data.fit_y, data.val_X, data.val_len, data.val_y,
            seed=seed, n_features=data.fit_X.shape[2],
            max_epochs=cfg.sequence.max_epochs,
            early_stopping_rounds=max(5, cfg.train.early_stopping_rounds // 5),
            feature_names=data.feature_names, **params,
        )
        y_test_pred = R.apply_promotion(
            r.predict(data.test_X, data.test_len), tau,
            threshold=cfg.high_risk_threshold,
            margin=cfg.decision_rule.promotion_margin,
        )
        row = R.score(cfg, data.test_y, y_test_pred, seed=seed)
        row["seed"] = seed
        row["best_epoch"] = r.best_epoch
        row["best_val_loss"] = r.best_val_loss
        seed_rows.append(row)
        preds[seed] = y_test_pred
        curves[seed] = {"train": r.train_losses, "val": r.val_losses}

    return ExperimentResult(
        experiment="E7", budget=budget,
        selection={"promotion_tau": tau, "params": params},
        seed_rows=seed_rows,
        summary=R.aggregate_seeds(seed_rows, "E7 sequence (GRU/LSTM)"),
        test_predictions=preds,
        extras={"tau_sweep": tau_sweep, "curves": curves},
    )


# --- E8 ----------------------------------------------------------------------


def run_e8(cfg: Config, data: R.SequenceData, *, budget: R.SearchBudget) -> ExperimentResult:
    """E8: steelmanned MC-dropout + deep ensemble, audited for COVERAGE."""
    from .bayesian import (
        coverage_binomial_test,
        ensemble_predict,
        estimate_aleatoric_std,
        mc_dropout_predict,
        pit_uniformity_test,
        pit_values,
        reliability_curve,
    )

    params = dict(budget.best_params) or {
        "hidden_size": cfg.sequence.hidden_size, "num_layers": cfg.sequence.num_layers,
        "dropout": cfg.sequence.dropout, "learning_rate": cfg.sequence.learning_rate,
        "batch_size": cfg.sequence.batch_size, "cell": cfg.sequence.cell,
    }
    levels = cfg.bayesian.nominal_levels

    # A reference run fixes the promotion threshold on VALIDATION, exactly as in
    # E6/E7. Without it E8's point predictions never cross -6, F2 is 0 and the
    # challenge loss is undefined — so E8 could not appear in the comparison table
    # at all. The interval/coverage audit below is untouched by this: it uses the
    # raw predictive distribution, not the promoted point estimate.
    ref = train_sequence_model(
        data.fit_X, data.fit_len, data.fit_y, data.val_X, data.val_len, data.val_y,
        seed=cfg.seed, n_features=data.fit_X.shape[2],
        max_epochs=cfg.sequence.max_epochs,
        early_stopping_rounds=max(5, cfg.train.early_stopping_rounds // 5),
        feature_names=data.feature_names, **params,
    )
    tau, tau_sweep = R.select_promotion_threshold(
        cfg, data.val_y, ref.predict(data.val_X, data.val_len)
    )

    members, coverage_rows, pit_rows = [], [], []
    per_seed_dists = {}

    for seed in cfg.train.seeds[: cfg.train.n_seeds]:
        r = train_sequence_model(
            data.fit_X, data.fit_len, data.fit_y, data.val_X, data.val_len, data.val_y,
            seed=seed, n_features=data.fit_X.shape[2],
            max_epochs=cfg.sequence.max_epochs,
            early_stopping_rounds=max(5, cfg.train.early_stopping_rounds // 5),
            feature_names=data.feature_names, **params,
        )
        members.append(r)

        # Aleatoric term from VALIDATION residuals — part of the steelman.
        sigma = estimate_aleatoric_std(data.val_y, r.predict(data.val_X, data.val_len))

        dist = mc_dropout_predict(
            r, data.test_X, data.test_len,
            n_samples=cfg.bayesian.n_mc_samples, aleatoric_std=sigma, seed=seed,
        )
        per_seed_dists[seed] = dist

        achieved = reliability_curve(data.test_y, dist, levels)
        for level in levels:
            lo, hi = dist.interval(float(level))
            covered = int(np.sum((data.test_y >= lo) & (data.test_y <= hi)))
            coverage_rows.append({
                "method": "MC-dropout", "seed": seed, "nominal": float(level),
                "empirical": achieved[float(level)],
                "gap (pp)": 100 * (achieved[float(level)] - float(level)),
                "mean width": float(np.mean(hi - lo)),
                "median width": float(np.median(hi - lo)),
                "binomial p": coverage_binomial_test(covered, len(data.test_y), float(level)),
                "aleatoric sd": sigma,
            })
        pit = pit_values(data.test_y, dist)
        ks, p = pit_uniformity_test(pit)
        pit_rows.append({"method": "MC-dropout", "seed": seed,
                         "KS statistic": ks, "KS p": p})

    # Deep ensemble over the same members (the second prior-art variant).
    sigma_ens = estimate_aleatoric_std(
        data.val_y,
        np.mean([m.predict(data.val_X, data.val_len) for m in members], axis=0),
    )
    ens = ensemble_predict(members, data.test_X, data.test_len, aleatoric_std=sigma_ens)
    achieved = reliability_curve(data.test_y, ens, levels)
    for level in levels:
        lo, hi = ens.interval(float(level))
        covered = int(np.sum((data.test_y >= lo) & (data.test_y <= hi)))
        coverage_rows.append({
            "method": "deep ensemble", "seed": -1, "nominal": float(level),
            "empirical": achieved[float(level)],
            "gap (pp)": 100 * (achieved[float(level)] - float(level)),
            "mean width": float(np.mean(hi - lo)),
            "median width": float(np.median(hi - lo)),
            "binomial p": coverage_binomial_test(covered, len(data.test_y), float(level)),
            "aleatoric sd": sigma_ens,
        })
    pit_ens = pit_values(data.test_y, ens)
    ks, p = pit_uniformity_test(pit_ens)
    pit_rows.append({"method": "deep ensemble", "seed": -1,
                     "KS statistic": ks, "KS p": p})

    # Point-prediction scores, so E8 sits in the same comparison table. The same
    # validation-selected promotion rule as E6/E7 is applied, so the three rows are
    # comparable; the coverage audit above used the raw distribution.
    seed_rows, promoted_preds = [], {}
    for seed, dist in per_seed_dists.items():
        promoted = R.apply_promotion(
            dist.mean, tau, threshold=cfg.high_risk_threshold,
            margin=cfg.decision_rule.promotion_margin,
        )
        promoted_preds[seed] = promoted
        row = R.score(cfg, data.test_y, promoted, seed=seed)
        row["seed"] = seed
        seed_rows.append(row)

    return ExperimentResult(
        experiment="E8", budget=budget,
        selection={"params": params, "n_mc_samples": cfg.bayesian.n_mc_samples,
                   "promotion_tau": tau},
        seed_rows=seed_rows,
        summary=R.aggregate_seeds(seed_rows, "E8 MC-dropout (point)"),
        test_predictions=promoted_preds,
        extras={
            "coverage": pd.DataFrame(coverage_rows),
            "pit": pd.DataFrame(pit_rows),
            "distributions": per_seed_dists,
            "ensemble": ens,
            "pit_values_ensemble": pit_ens,
            "tau_sweep": tau_sweep,
        },
    )
