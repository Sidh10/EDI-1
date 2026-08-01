"""E6 — LightGBM point predictor plus quantile regression heads.

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``baselines``/tree models):
a competent tabular point predictor over the last-k CDM features, and a set of
quantile heads at the levels Phase 3's CQR (E12) will consume. The quantile
capability is built now, per the Phase-2 brief, even though nothing in Phase 2
uses it.

Scope note (CLAUDE.md §2): this is a commodity baseline. The project does not
claim point-prediction novelty, and a large unexplained gain over persistence is
treated as a leakage signal to investigate, not a result to report — see
``EXPERIMENT_PLAN.md`` E6's failure criteria and the audit in the E6 notebook.

Determinism: LightGBM is seeded through ``seed``/``bagging_seed``/``feature_fraction_seed``
and forced single-threaded during training, because LightGBM's multi-threaded
histogram construction is not bitwise reproducible across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd


@dataclass
class GbmResult:
    """A fitted point model plus its quantile heads and their training record."""

    point_model: lgb.Booster
    quantile_models: dict[float, lgb.Booster] = field(default_factory=dict)
    best_iteration: int = 0
    quantile_best_iterations: dict[float, int] = field(default_factory=dict)
    feature_names: tuple[str, ...] = ()
    seed: int = 0

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Point predictions (log10 risk)."""
        return np.asarray(
            self.point_model.predict(X, num_iteration=self.best_iteration), dtype=float
        )

    def predict_quantiles(self, X: pd.DataFrame) -> dict[float, np.ndarray]:
        """Per-level quantile predictions, sorted ascending by level."""
        return {
            q: np.asarray(
                m.predict(X, num_iteration=self.quantile_best_iterations.get(q, 0)),
                dtype=float,
            )
            for q, m in sorted(self.quantile_models.items())
        }


def default_params(seed: int, *, objective: str = "regression") -> dict:
    """Baseline LightGBM parameters.

    Single-threaded and fully seeded so repeat runs are bit-identical
    (CLAUDE.md §1: determinism is a requirement).
    """
    return {
        "objective": objective,
        "metric": "l2" if objective == "regression" else "quantile",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 20,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "verbosity": -1,
        "seed": seed,
        "bagging_seed": seed,
        "feature_fraction_seed": seed,
        "data_random_seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": 1,
    }


def fit_point_model(
    X_fit: pd.DataFrame,
    y_fit: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    *,
    seed: int,
    params: dict | None = None,
    num_boost_round: int = 2000,
    early_stopping_rounds: int = 50,
) -> tuple[lgb.Booster, int]:
    """Fit the L2 point model with early stopping on the INTERNAL validation split."""
    p = dict(params) if params is not None else default_params(seed)
    p.update({"objective": "regression", "metric": "l2", "seed": seed})

    dtrain = lgb.Dataset(X_fit, label=y_fit, free_raw_data=False)
    dval = lgb.Dataset(X_val, label=y_val, reference=dtrain, free_raw_data=False)
    booster = lgb.train(
        p, dtrain,
        num_boost_round=num_boost_round,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
    )
    return booster, int(booster.best_iteration or num_boost_round)


def fit_quantile_models(
    X_fit: pd.DataFrame,
    y_fit: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    quantile_levels,
    *,
    seed: int,
    params: dict | None = None,
    num_boost_round: int = 2000,
    early_stopping_rounds: int = 50,
) -> tuple[dict[float, lgb.Booster], dict[float, int]]:
    """Fit one pinball-loss model per quantile level (feeds Phase-3 CQR)."""
    models: dict[float, lgb.Booster] = {}
    best: dict[float, int] = {}
    dtrain_raw = (X_fit, y_fit)
    for q in quantile_levels:
        p = dict(params) if params is not None else default_params(seed)
        p.update({"objective": "quantile", "alpha": float(q),
                  "metric": "quantile", "seed": seed})
        dtrain = lgb.Dataset(dtrain_raw[0], label=dtrain_raw[1], free_raw_data=False)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain, free_raw_data=False)
        booster = lgb.train(
            p, dtrain,
            num_boost_round=num_boost_round,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
        )
        models[float(q)] = booster
        best[float(q)] = int(booster.best_iteration or num_boost_round)
    return models, best


def fit_gbm(
    X_fit: pd.DataFrame,
    y_fit: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    *,
    seed: int,
    quantile_levels=(),
    params: dict | None = None,
    num_boost_round: int = 2000,
    early_stopping_rounds: int = 50,
) -> GbmResult:
    """Fit the point model and (optionally) the quantile heads."""
    point, best_it = fit_point_model(
        X_fit, y_fit, X_val, y_val, seed=seed, params=params,
        num_boost_round=num_boost_round, early_stopping_rounds=early_stopping_rounds,
    )
    qmodels, qbest = ({}, {})
    if len(quantile_levels):
        qmodels, qbest = fit_quantile_models(
            X_fit, y_fit, X_val, y_val, quantile_levels, seed=seed, params=params,
            num_boost_round=num_boost_round, early_stopping_rounds=early_stopping_rounds,
        )
    return GbmResult(
        point_model=point, quantile_models=qmodels,
        best_iteration=best_it, quantile_best_iterations=qbest,
        feature_names=tuple(X_fit.columns), seed=int(seed),
    )


# --- quantile diagnostics ----------------------------------------------------


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, quantile: float) -> float:
    """Mean pinball (quantile) loss at level ``quantile``.

    ``L_q(y, f) = mean( max(q*(y-f), (q-1)*(y-f)) )``. Lower is better.
    """
    if not (0.0 < quantile < 1.0):
        raise ValueError(f"quantile must be in (0, 1), got {quantile}")
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    diff = y_true - y_pred
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1.0) * diff)))


def quantile_crossing_rate(quantile_preds: dict[float, np.ndarray]) -> float:
    """Fraction of events where predicted quantiles are non-monotone in the level.

    Independently-fitted quantile heads can cross; E6's success criterion asks for
    "well-formed (monotonic, sane pinball loss)" heads, so this is measured rather
    than assumed. A high rate is a signal to isotonically re-sort before CQR uses
    them in Phase 3.
    """
    levels = sorted(quantile_preds)
    if len(levels) < 2:
        return 0.0
    stacked = np.stack([quantile_preds[q] for q in levels], axis=1)
    crossings = np.any(np.diff(stacked, axis=1) < 0, axis=1)
    return float(np.mean(crossings))


def feature_importance(result: GbmResult, importance_type: str = "gain") -> pd.Series:
    """Feature importances of the point model, descending."""
    vals = result.point_model.feature_importance(importance_type=importance_type)
    return (
        pd.Series(vals, index=list(result.feature_names))
        .sort_values(ascending=False)
    )
