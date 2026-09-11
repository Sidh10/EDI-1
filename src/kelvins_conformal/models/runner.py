"""Shared training / tuning / scoring pipeline for the Phase-2 baselines.

Responsibility: keep E6, E7 and E8's notebooks thin by putting the repeated
mechanics — dataset assembly, the hyperparameter search, multi-seed training, and
the single final test-set scoring pass — in one tested place.

Three disciplines are enforced here rather than trusted to each notebook:

1. **The official test set is read exactly once per experiment**, at the very end,
   by ``final_test_score``. Nothing else in this module touches it. Model
   selection and early stopping run only on ``val_inner``, which is carved out of
   the ``fit`` pool so that Phase 3's ``calibration`` / ``self_test`` subsets stay
   pristine (see ``data.training_pool_splits``).
2. **Search budgets are equal across the three baselines.** ``SearchBudget`` records
   what each experiment actually spent so the E8 steelman claim is auditable
   rather than asserted (Q-BASE-02 option (c), CLAUDE.md §10).
3. **Every reported number is multi-seed** (``cfg.train.seeds``, >= 3) with
   event-level bootstrap CIs from the E5-validated metric code.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import Config
from ..data import training_pool_splits
from ..features import (
    apply_standardisation,
    build_sequence_tensors,
    build_tabular_features,
    standardise,
)
from ..metrics import bootstrap_challenge_score, challenge_score


@dataclass
class SearchBudget:
    """What a hyperparameter search actually cost — reported side by side."""

    experiment: str
    objective: str
    n_trials: int
    n_configs_evaluated: int
    wall_clock_seconds: float
    selection_split: str = "val_inner"
    best_params: dict = field(default_factory=dict)
    best_objective_value: float = float("nan")
    from_cache: bool = False

    def as_row(self) -> dict:
        return {
            "experiment": self.experiment,
            "tuned for": self.objective,
            "trials (budget)": self.n_trials,
            "configs evaluated": self.n_configs_evaluated,
            "selection split": self.selection_split,
            "wall clock (s)": round(self.wall_clock_seconds, 1),
            "best objective": (round(self.best_objective_value, 5)
                               if np.isfinite(self.best_objective_value) else "n/a"),
        }


@dataclass
class TabularData:
    """Tabular matrices for every split the Phase-2 experiments may read."""

    fit_X: pd.DataFrame
    fit_y: np.ndarray
    val_X: pd.DataFrame
    val_y: np.ndarray
    test_X: pd.DataFrame
    test_y: np.ndarray
    test_uids: np.ndarray
    feature_names: tuple[str, ...]
    n_dropped_train: int
    n_dropped_test: int


def prepare_tabular(cfg: Config, events: pd.DataFrame) -> TabularData:
    """Build last-k tabular features and slice them into the internal splits."""
    splits = training_pool_splits(events, cfg)
    train_fm = build_tabular_features(events, cfg, split="train")
    test_fm = build_tabular_features(events, cfg, split="test")

    fit_mask = np.isin(train_fm.event_uids, splits["fit_inner"])
    val_mask = np.isin(train_fm.event_uids, splits["val_inner"])

    return TabularData(
        fit_X=train_fm.X.loc[fit_mask], fit_y=train_fm.y[fit_mask],
        val_X=train_fm.X.loc[val_mask], val_y=train_fm.y[val_mask],
        test_X=test_fm.X, test_y=test_fm.y, test_uids=test_fm.event_uids,
        feature_names=train_fm.feature_names,
        n_dropped_train=int(getattr(train_fm, "n_dropped", 0) or 0),
        n_dropped_test=int(getattr(test_fm, "n_dropped", 0) or 0),
    )


@dataclass
class SequenceData:
    """Standardised, padded sequences for every split, plus their masks."""

    fit_X: np.ndarray
    fit_len: np.ndarray
    fit_y: np.ndarray
    val_X: np.ndarray
    val_len: np.ndarray
    val_y: np.ndarray
    test_X: np.ndarray
    test_len: np.ndarray
    test_y: np.ndarray
    test_uids: np.ndarray
    feature_names: tuple[str, ...]
    conditioned_features: tuple[str, ...]
    mean: np.ndarray
    std: np.ndarray


def prepare_sequence(cfg: Config, events: pd.DataFrame) -> SequenceData:
    """Build padded sequences; standardise using FIT-SPLIT statistics only.

    Computing the mean/std on anything wider than ``fit_inner`` would leak
    information from the validation or test distribution into training.
    """
    splits = training_pool_splits(events, cfg)
    train_st = build_sequence_tensors(events, cfg, split="train")
    test_st = build_sequence_tensors(
        events, cfg, split="test", feature_names=train_st.feature_names
    )

    fit_mask = np.isin(train_st.event_uids, splits["fit_inner"])
    val_mask = np.isin(train_st.event_uids, splits["val_inner"])

    mean, std = standardise(train_st.X[fit_mask], train_st.mask[fit_mask])

    def _std(X, m):
        return apply_standardisation(X, m, mean, std)

    return SequenceData(
        fit_X=_std(train_st.X[fit_mask], train_st.mask[fit_mask]),
        fit_len=train_st.lengths[fit_mask], fit_y=train_st.y[fit_mask],
        val_X=_std(train_st.X[val_mask], train_st.mask[val_mask]),
        val_len=train_st.lengths[val_mask], val_y=train_st.y[val_mask],
        test_X=_std(test_st.X, test_st.mask),
        test_len=test_st.lengths, test_y=test_st.y, test_uids=test_st.event_uids,
        feature_names=train_st.feature_names,
        conditioned_features=train_st.conditioned_features,
        mean=mean, std=std,
    )


# --- decision rule -----------------------------------------------------------


def apply_promotion(
    y_pred: np.ndarray, tau: float, *, threshold: float, margin: float
) -> np.ndarray:
    """Promote predictions at or above ``tau`` to just above the high-risk threshold.

    Implements the rule pre-registered in DECISIONS.md. An L2 regressor on this
    floor-dominated target never crosses -6 on its own, so without a promotion step
    F2 = 0 and the challenge loss is undefined. The challenge's own top team used
    the same device (Uriot et al. Table 4, "steps 0-2").

    ``tau`` MUST have been selected on the internal validation split.
    """
    out = np.asarray(y_pred, dtype=float).copy()
    promote = out >= tau
    out[promote] = np.maximum(out[promote], threshold + margin)
    return out


def select_promotion_threshold(
    cfg: Config, y_val: np.ndarray, pred_val: np.ndarray
) -> tuple[float, pd.DataFrame]:
    """Choose ``tau`` by minimising the challenge loss on VALIDATION data.

    Returns the selected threshold and the full sweep, so the report can show that
    the choice was made on a grid fixed in advance rather than fitted to test.
    """
    rows = []
    best_tau, best_loss = float("nan"), float("inf")
    for tau in cfg.decision_rule.promotion_thresholds:
        promoted = apply_promotion(
            pred_val, tau,
            threshold=cfg.high_risk_threshold,
            margin=cfg.decision_rule.promotion_margin,
        )
        s = challenge_score(
            y_val, promoted,
            threshold=cfg.high_risk_threshold, beta=cfg.metric.f_beta,
            clip_epsilon=cfg.metric.prediction_clip_epsilon,
        )
        rows.append({
            "tau": float(tau), "val L": s.loss, "val MSE_HR": s.mse_hr,
            "val F2": s.f2, "n promoted": int(np.sum(pred_val >= tau)),
            "defined": s.is_defined,
        })
        if s.is_defined and s.loss < best_loss:
            best_tau, best_loss = float(tau), s.loss

    sweep = pd.DataFrame(rows).set_index("tau")
    if not np.isfinite(best_loss):
        raise ValueError(
            "no promotion threshold on the pre-registered grid produced a defined "
            "challenge loss on validation; refusing to pick one silently"
        )
    return best_tau, sweep


# --- scoring -----------------------------------------------------------------


def score(cfg: Config, y_true: np.ndarray, y_pred: np.ndarray, *, seed: int) -> dict:
    """Challenge metric + event-level bootstrap CIs, using the E5-validated code.

    If the loss is undefined (F2 == 0, i.e. the model never correctly flags a true
    high-risk event) the point estimate is still reported honestly as +inf and
    ``defined`` is set False, with NaN interval bounds. The metric core keeps
    raising in that situation — this wrapper catches it so a *report* surfaces the
    degenerate result instead of aborting, which is the difference between hiding
    a finding and printing it.
    """
    s = challenge_score(
        y_true, y_pred,
        threshold=cfg.high_risk_threshold, beta=cfg.metric.f_beta,
        clip_epsilon=cfg.metric.prediction_clip_epsilon,
    )
    out = {
        "L": s.loss, "MSE_HR": s.mse_hr, "F2": s.f2,
        "TP": s.counts.tp, "FP": s.counts.fp, "FN": s.counts.fn, "TN": s.counts.tn,
        "n_HR": s.n_high_risk_true, "defined": s.is_defined,
    }
    try:
        boot = bootstrap_challenge_score(
            y_true, y_pred,
            threshold=cfg.high_risk_threshold, beta=cfg.metric.f_beta,
            clip_epsilon=cfg.metric.prediction_clip_epsilon,
            n_resamples=cfg.bootstrap.n_resamples, level=0.95, seed=seed,
        )
        out.update({
            "L_lo": boot["loss"].lo, "L_hi": boot["loss"].hi,
            "MSE_HR_lo": boot["mse_hr"].lo, "MSE_HR_hi": boot["mse_hr"].hi,
            "F2_lo": boot["f2"].lo, "F2_hi": boot["f2"].hi,
        })
    except ValueError:
        # Every resample was undefined — a real, reportable degeneracy.
        nan = float("nan")
        out.update({"L_lo": nan, "L_hi": nan, "MSE_HR_lo": nan,
                    "MSE_HR_hi": nan, "F2_lo": nan, "F2_hi": nan})
    return out


def aggregate_seeds(rows: list[dict], label: str) -> dict:
    """Mean +/- sd across seeds, plus the seed-wise spread (CLAUDE.md §9)."""
    out: dict = {"model": label, "n_seeds": len(rows)}
    for key in ("L", "MSE_HR", "F2"):
        vals = np.array([r[key] for r in rows], dtype=float)
        out[f"{key} mean"] = float(np.mean(vals))
        out[f"{key} sd"] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
        out[f"{key} min"] = float(np.min(vals))
        out[f"{key} max"] = float(np.max(vals))
    # CI from the median seed, so the reported interval belongs to a real run.
    med = int(np.argsort([r["L"] for r in rows])[len(rows) // 2])
    out["L 95% CI (median seed)"] = f"[{rows[med]['L_lo']:.4f}, {rows[med]['L_hi']:.4f}]"
    out["MSE_HR 95% CI (median seed)"] = (
        f"[{rows[med]['MSE_HR_lo']:.4f}, {rows[med]['MSE_HR_hi']:.4f}]"
    )
    out["F2 95% CI (median seed)"] = f"[{rows[med]['F2_lo']:.4f}, {rows[med]['F2_hi']:.4f}]"
    return out


def leakage_screen(
    model_loss: float, persistence_loss: float, *, factor: float = 2.0
) -> tuple[bool, str]:
    """Flag a suspiciously large improvement over persistence (E6 failure criterion).

    EXPERIMENT_PLAN.md E6 and METRICS.md §1 both say the same thing: on this
    benchmark a *dramatic* gain over the naive forecast is a leakage signal to
    investigate before it is reported as a win. ``factor`` is the ratio of
    persistence loss to model loss beyond which we refuse to call it a result.
    """
    if not np.isfinite(model_loss) or model_loss <= 0:
        return False, "model loss is not a finite positive number"
    ratio = persistence_loss / model_loss
    if ratio >= factor:
        return True, (
            f"model L={model_loss:.4f} is {ratio:.2f}x better than persistence "
            f"L={persistence_loss:.4f} — at or beyond the {factor:g}x leakage-signal "
            "threshold. Re-audit features against feature_dictionary.yaml and the "
            "cutoff logic BEFORE reporting this as a result."
        )
    return False, (
        f"model L={model_loss:.4f} vs persistence L={persistence_loss:.4f} "
        f"(ratio {ratio:.2f}x) — within the expected range for this benchmark."
    )


def timed(fn, *args, **kwargs):
    """Run ``fn`` and return ``(result, elapsed_seconds)``."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


# --- target parameterisation -------------------------------------------------
# Two ways to point a regressor at this task, both standard:
#   "absolute" — regress the final log-risk directly.
#   "residual" — regress (final log-risk - r_last), i.e. anchor the model on the
#                persistence forecast and learn only the correction. On problems
#                where persistence is strong (which the challenge paper documents
#                for this benchmark) anchoring usually helps.
# The choice is made on val_inner, like every other model-selection decision.
TARGET_MODES = ("absolute", "residual")


def anchor_column(X: pd.DataFrame) -> np.ndarray:
    """The persistence anchor r_last, or zeros if risk history is disabled."""
    if "risk_last" in X.columns:
        return X["risk_last"].to_numpy(dtype=float)
    return np.zeros(len(X), dtype=float)


def to_model_target(y: np.ndarray, anchor: np.ndarray, mode: str) -> np.ndarray:
    if mode == "absolute":
        return np.asarray(y, dtype=float)
    if mode == "residual":
        return np.asarray(y, dtype=float) - anchor
    raise ValueError(f"unknown target mode: {mode!r}")


def from_model_output(pred: np.ndarray, anchor: np.ndarray, mode: str) -> np.ndarray:
    if mode == "absolute":
        return np.asarray(pred, dtype=float)
    if mode == "residual":
        return np.asarray(pred, dtype=float) + anchor
    raise ValueError(f"unknown target mode: {mode!r}")


# --- hyperparameter search ---------------------------------------------------
# All three searches are random search over a fixed grid with the SAME trial
# budget (cfg.train.hpo_budget_trials) and the SAME selection split (val_inner).
# Only the OBJECTIVE differs, and that difference is the point: E6/E7 are tuned
# for point accuracy, E8 is tuned for its own coverage quality (the steelman).

# Search-time epoch cap for the recurrent models. Applied identically to E7 and
# E8 so neither gets a longer leash than the other.
SEARCH_MAX_EPOCHS = 25


def sample_gbm_params(rng: np.random.Generator, seed: int) -> dict:
    """Draw one LightGBM configuration from the search grid."""
    from .gbm import default_params

    p = default_params(seed)
    p.update({
        "learning_rate": float(rng.choice([0.02, 0.05, 0.08, 0.12])),
        "num_leaves": int(rng.choice([15, 31, 63, 127])),
        "min_data_in_leaf": int(rng.choice([10, 20, 40, 80])),
        "feature_fraction": float(rng.choice([0.5, 0.7, 0.9])),
        "bagging_fraction": float(rng.choice([0.6, 0.8, 1.0])),
        "lambda_l2": float(rng.choice([0.0, 1.0, 5.0, 20.0])),
    })
    return p


def search_gbm(cfg: Config, data: TabularData, *, seed: int) -> SearchBudget:
    """Random search for the E6 point model, selected on validation MSE."""
    from .gbm import fit_point_model

    rng = np.random.default_rng(seed)
    n_trials = cfg.train.hpo_budget_trials
    best_val = float("inf")
    best_params: dict = {}
    start = time.perf_counter()
    evaluated = 0

    for _ in range(n_trials):
        params = sample_gbm_params(rng, seed)
        booster, best_it = fit_point_model(
            data.fit_X, data.fit_y, data.val_X, data.val_y,
            seed=seed, params=params,
            num_boost_round=cfg.gbm.num_boost_round,
            early_stopping_rounds=cfg.train.early_stopping_rounds,
        )
        pred = booster.predict(data.val_X, num_iteration=best_it)
        val_mse = float(np.mean((np.asarray(pred) - data.val_y) ** 2))
        evaluated += 1
        if val_mse < best_val:
            best_val, best_params = val_mse, params

    return SearchBudget(
        experiment="E6 (LightGBM)", objective="validation MSE (point accuracy)",
        n_trials=n_trials, n_configs_evaluated=evaluated,
        wall_clock_seconds=time.perf_counter() - start,
        best_params={k: v for k, v in best_params.items()
                     if k in ("learning_rate", "num_leaves", "min_data_in_leaf",
                              "feature_fraction", "bagging_fraction", "lambda_l2")},
        best_objective_value=best_val,
    )


def sample_sequence_params(rng: np.random.Generator) -> dict:
    """Draw one recurrent-model configuration from the search grid."""
    return {
        "hidden_size": int(rng.choice([32, 64, 128])),
        "num_layers": int(rng.choice([1, 2])),
        "dropout": float(rng.choice([0.1, 0.2, 0.3, 0.5])),
        "learning_rate": float(rng.choice([1e-3, 3e-3, 1e-2])),
        "batch_size": int(rng.choice([64, 128, 256])),
        "cell": str(rng.choice(["gru", "lstm"])),
    }


def search_sequence(cfg: Config, data: SequenceData, *, seed: int) -> SearchBudget:
    """Random search for the E7 point model, selected on validation MSE."""
    from .sequence import train_sequence_model

    rng = np.random.default_rng(seed)
    n_trials = cfg.train.hpo_budget_trials
    best_val = float("inf")
    best_params: dict = {}
    start = time.perf_counter()
    evaluated = 0

    for _ in range(n_trials):
        params = sample_sequence_params(rng)
        result = train_sequence_model(
            data.fit_X, data.fit_len, data.fit_y,
            data.val_X, data.val_len, data.val_y,
            seed=seed, n_features=data.fit_X.shape[2],
            max_epochs=SEARCH_MAX_EPOCHS, early_stopping_rounds=6,
            feature_names=data.feature_names, **params,
        )
        evaluated += 1
        if result.best_val_loss < best_val:
            best_val, best_params = result.best_val_loss, params

    return SearchBudget(
        experiment="E7 (GRU/LSTM)", objective="validation MSE (point accuracy)",
        n_trials=n_trials, n_configs_evaluated=evaluated,
        wall_clock_seconds=time.perf_counter() - start,
        best_params=best_params, best_objective_value=best_val,
    )


def coverage_objective(
    y_true: np.ndarray, dist, levels
) -> float:
    """Mean absolute coverage error across nominal levels — E8's OWN objective.

    Lower is better; 0 means empirical coverage equals nominal at every level.
    This is what "steelmanned" means operationally: E8's hyperparameters are
    chosen to make ITS coverage as good as possible, not to make its point
    predictions good (which is what E6/E7 optimise).
    """
    from .bayesian import reliability_curve

    achieved = reliability_curve(y_true, dist, levels)
    return float(np.mean([abs(achieved[float(v)] - float(v)) for v in levels]))


def search_mc_dropout(cfg: Config, data: SequenceData, *, seed: int) -> SearchBudget:
    """Random search for E8, selected on COVERAGE quality (the steelman).

    Equal trial budget and equal selection split to E6/E7; only the objective
    differs. Each trial trains a model and then scores the coverage of its
    MC-dropout predictive intervals on ``val_inner``.
    """
    from .bayesian import estimate_aleatoric_std, mc_dropout_predict
    from .sequence import train_sequence_model

    rng = np.random.default_rng(seed)
    n_trials = cfg.train.hpo_budget_trials
    levels = cfg.bayesian.nominal_levels
    best_obj = float("inf")
    best_params: dict = {}
    start = time.perf_counter()
    evaluated = 0

    # A modest MC-sample count during search keeps the budget comparable; the
    # final model uses the full cfg.bayesian.n_mc_samples.
    search_mc_samples = max(30, cfg.bayesian.n_mc_samples // 4)

    for _ in range(n_trials):
        params = sample_sequence_params(rng)
        # Dropout is the primary MC-dropout knob, so give the search a slightly
        # richer range for it than the point models get.
        params["dropout"] = float(rng.choice([0.05, 0.1, 0.2, 0.3, 0.4, 0.5]))

        result = train_sequence_model(
            data.fit_X, data.fit_len, data.fit_y,
            data.val_X, data.val_len, data.val_y,
            seed=seed, n_features=data.fit_X.shape[2],
            max_epochs=SEARCH_MAX_EPOCHS, early_stopping_rounds=6,
            feature_names=data.feature_names, **params,
        )
        # Aleatoric noise is estimated on validation residuals — part of the
        # steelman: omitting it would make the intervals absurdly narrow.
        val_point = result.predict(data.val_X, data.val_len)
        sigma = estimate_aleatoric_std(data.val_y, val_point)
        dist = mc_dropout_predict(
            result, data.val_X, data.val_len,
            n_samples=search_mc_samples, aleatoric_std=sigma, seed=seed,
        )
        obj = coverage_objective(data.val_y, dist, levels)
        evaluated += 1
        if obj < best_obj:
            best_obj, best_params = obj, params

    return SearchBudget(
        experiment="E8 (MC-dropout, steelmanned)",
        objective="mean |empirical - nominal| coverage error (ITS OWN metric)",
        n_trials=n_trials, n_configs_evaluated=evaluated,
        wall_clock_seconds=time.perf_counter() - start,
        best_params=best_params, best_objective_value=best_obj,
    )


# --- search caching ----------------------------------------------------------
# The three hyperparameter searches dominate Phase 2's wall clock (~27 min on the
# CPU-only development machine). Caching them keyed by (config hash, experiment,
# seed) makes an interrupted run cheap to resume without weakening reproducibility:
# the key includes the full config hash, so ANY configuration change invalidates
# every entry, and a cold cache reproduces the same result because each search is
# seeded. Delete `artifacts/search_cache/` to force a clean re-search.

def _search_cache_path(cfg: Config, experiment: str, seed: int) -> Path:
    root = Path(cfg.path("artifacts_dir")) / "search_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{experiment}_{cfg.config_hash[:16]}_seed{seed}.json"


def cached_search(cfg: Config, experiment: str, seed: int, compute):
    """Return a cached SearchBudget if one exists for this exact config, else run.

    `compute` is a zero-argument callable returning a SearchBudget.
    """
    path = _search_cache_path(cfg, experiment, seed)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        budget = SearchBudget(
            experiment=payload["experiment"],
            objective=payload["objective"],
            n_trials=payload["n_trials"],
            n_configs_evaluated=payload["n_configs_evaluated"],
            wall_clock_seconds=payload["wall_clock_seconds"],
            selection_split=payload["selection_split"],
            best_params=payload["best_params"],
            best_objective_value=payload["best_objective_value"],
        )
        budget.from_cache = True
        return budget

    budget = compute()
    payload = {
        "experiment": budget.experiment,
        "objective": budget.objective,
        "n_trials": budget.n_trials,
        "n_configs_evaluated": budget.n_configs_evaluated,
        "wall_clock_seconds": budget.wall_clock_seconds,
        "selection_split": budget.selection_split,
        "best_params": budget.best_params,
        "best_objective_value": budget.best_objective_value,
        "config_hash": cfg.config_hash,
        "seed": seed,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    budget.from_cache = False
    return budget
