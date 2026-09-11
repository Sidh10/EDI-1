"""Same config + seed => identical outputs (CLAUDE.md §1, invariant I2).

SOFTWARE_ARCHITECTURE.md §3 names this file explicitly. It exercises the two
Phase-1 pipelines end to end on a synthetic dataset — baseline scoring (E5) and
the power analysis (E4) — asserting bit-identical repeat runs, and asserting that
the baseline predictors are pure functions of their inputs.

Synthetic data is used deliberately: determinism must hold independently of the
real archive, so this test runs in CI without the 211 MB download.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal import baselines as bl
from kelvins_conformal.metrics import bootstrap_challenge_score, challenge_score
from kelvins_conformal.power import simulate_precision


def _synthetic_events(n_events: int = 400, seed: int = 0) -> pd.DataFrame:
    """A small event-grouped CDM table with the columns the Phase-1 code needs."""
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_events):
        n_cdms = int(rng.integers(2, 9))
        # Times descending toward TCA, spanning both sides of the 2-day cutoff.
        times = np.sort(rng.uniform(0.05, 6.5, size=n_cdms))[::-1]
        risks = rng.normal(-12.0, 6.0, size=n_cdms)
        for i, (t, r) in enumerate(zip(times, risks, strict=True)):
            rows.append({
                "event_uid": f"train_{e}",
                "split": "train",
                "mission_id": int(e % 7),
                "time_to_tca": float(t),
                "risk": float(r),
                "target_log_risk": float(risks[-1]),
                "cdm_index": i,
            })
    return pd.DataFrame(rows)


# --- baseline scoring (E5) ----------------------------------------------------
def test_baseline_frame_is_deterministic():
    events = _synthetic_events()
    a = bl.build_baseline_frame(events, split="train", cutoff_days=2.0)
    b = bl.build_baseline_frame(events, split="train", cutoff_days=2.0)
    pd.testing.assert_frame_equal(a, b)


def test_baseline_scores_are_deterministic():
    events = _synthetic_events()
    frame = bl.build_baseline_frame(events, split="train", cutoff_days=2.0)
    for col in ("pred_lrp", "pred_crp"):
        s1 = challenge_score(frame["y_true"].to_numpy(), frame[col].to_numpy())
        s2 = challenge_score(frame["y_true"].to_numpy(), frame[col].to_numpy())
        assert s1 == s2


def test_baseline_bootstrap_is_deterministic():
    events = _synthetic_events()
    frame = bl.build_baseline_frame(events, split="train", cutoff_days=2.0)
    y = frame["y_true"].to_numpy()
    p = frame["pred_lrp"].to_numpy()

    a = bootstrap_challenge_score(y, p, n_resamples=250, seed=42)
    b = bootstrap_challenge_score(y, p, n_resamples=250, seed=42)
    for key in ("loss", "mse_hr", "f2"):
        assert (a[key].point, a[key].lo, a[key].hi) == (b[key].point, b[key].lo, b[key].hi)


def test_persistence_prediction_is_a_pure_function():
    latest = pd.Series([-3.0, -7.0, -6.0], index=["a", "b", "c"])
    out1 = bl.persistence_predict(latest, threshold=-6.0, epsilon=0.001)
    out2 = bl.persistence_predict(latest, threshold=-6.0, epsilon=0.001)
    pd.testing.assert_series_equal(out1, out2)
    # And it implements the documented piecewise rule.
    assert out1.tolist() == pytest.approx([-3.0, -6.001, -6.0])


def test_constant_prediction_is_a_pure_function():
    assert np.array_equal(bl.constant_predict(5, -5.0), bl.constant_predict(5, -5.0))
    assert np.all(bl.constant_predict(5, -5.0) == -5.0)


def test_latest_risk_uses_the_last_admissible_cdm_not_the_final_cdm():
    """r_{-2} must come from the latest CDM at or before the cutoff, never later."""
    events = pd.DataFrame([
        {"event_uid": "train_0", "split": "train", "mission_id": 1,
         "time_to_tca": 5.0, "risk": -10.0, "target_log_risk": -4.0},
        {"event_uid": "train_0", "split": "train", "mission_id": 1,
         "time_to_tca": 2.5, "risk": -8.0, "target_log_risk": -4.0},   # <- r_{-2}
        {"event_uid": "train_0", "split": "train", "mission_id": 1,
         "time_to_tca": 0.5, "risk": -4.0, "target_log_risk": -4.0},   # post-cutoff
    ])
    latest = bl.latest_risk_at_or_before_cutoff(events, cutoff_days=2.0)
    assert latest.loc["train_0"] == pytest.approx(-8.0)


def test_events_without_an_admissible_cdm_are_dropped_and_counted():
    """No silent imputation: unpredictable events are removed and tallied."""
    events = pd.DataFrame([
        {"event_uid": "train_0", "split": "train", "mission_id": 1,
         "time_to_tca": 0.5, "risk": -4.0, "target_log_risk": -4.0},
        {"event_uid": "train_1", "split": "train", "mission_id": 1,
         "time_to_tca": 3.0, "risk": -9.0, "target_log_risk": -5.0},
    ])
    frame = bl.build_baseline_frame(events, split="train", cutoff_days=2.0)
    assert frame.attrs["n_total_events"] == 2
    assert frame.attrs["n_dropped_no_admissible_cdm"] == 1
    assert frame["event_uid"].tolist() == ["train_1"]


# --- power analysis (E4) ------------------------------------------------------
def test_power_simulation_is_deterministic_across_runs():
    kwargs = {"nominal": 0.90, "n_simulations": 80, "n_bootstrap": 250, "seed": 42}
    a = simulate_precision(1315, 150, **kwargs)
    b = simulate_precision(1315, 150, **kwargs)
    assert a == b
    assert a.median_half_width_pp == b.median_half_width_pp


def test_power_simulation_grid_is_deterministic():
    """The full (fraction x group) sweep repeats identically."""
    def sweep():
        return [
            simulate_precision(n_cal, n_test, nominal=0.90, n_simulations=40,
                               n_bootstrap=200, seed=42).median_half_width_pp
            for n_cal in (1315, 2631)
            for n_test in (32, 150)
        ]

    assert sweep() == sweep()


# --- Phase 2 models (E6, E7, E8) ----------------------------------------------
# Trained on a tiny synthetic fixture so these run in CI without the real archive
# and without a full training budget (matching the tiny-subset smoke pattern).


def _tiny_tabular(n: int = 120, n_features: int = 6, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        rng.normal(size=(n, n_features)),
        columns=[f"f{i}" for i in range(n_features)],
    )
    y = X["f0"] * 2.0 - X["f1"] + rng.normal(scale=0.3, size=n)
    return X, y.to_numpy()


def _tiny_sequence(n: int = 80, max_len: int = 6, n_features: int = 4, seed: int = 0):
    rng = np.random.default_rng(seed)
    lengths = rng.integers(1, max_len + 1, size=n).astype(np.int64)
    X = np.full((n, max_len, n_features), -999.0, dtype=np.float32)
    y = np.zeros(n, dtype=float)
    for i, ln in enumerate(lengths):
        block = rng.normal(size=(ln, n_features)).astype(np.float32)
        X[i, :ln, :] = block
        y[i] = float(block[:, 0].mean() * 2.0 + rng.normal(scale=0.2))
    return X, lengths, y


def test_gbm_predictions_are_deterministic():
    from kelvins_conformal.models.gbm import fit_gbm

    X, y = _tiny_tabular()
    Xv, yv = _tiny_tabular(n=40, seed=1)

    def run():
        r = fit_gbm(X, y, Xv, yv, seed=42, quantile_levels=(0.1, 0.5, 0.9),
                    num_boost_round=40, early_stopping_rounds=10)
        return r.predict(Xv), r.predict_quantiles(Xv)

    p1, q1 = run()
    p2, q2 = run()
    np.testing.assert_array_equal(p1, p2)
    for level in q1:
        np.testing.assert_array_equal(q1[level], q2[level])


def test_gbm_different_seed_changes_predictions():
    from kelvins_conformal.models.gbm import fit_gbm

    X, y = _tiny_tabular()
    Xv, yv = _tiny_tabular(n=40, seed=1)
    a = fit_gbm(X, y, Xv, yv, seed=42, num_boost_round=40, early_stopping_rounds=10)
    b = fit_gbm(X, y, Xv, yv, seed=43, num_boost_round=40, early_stopping_rounds=10)
    # Bagging seeds differ, so at least some predictions must differ.
    assert not np.array_equal(a.predict(Xv), b.predict(Xv))


def test_gbm_seed_varies_even_when_explicit_params_are_supplied():
    """Regression: a multi-seed run must be N models, not one model N times.

    LightGBM draws feature subsampling, bagging and data ordering from separate
    generators. An earlier version overrode only ``seed`` when the caller passed
    an explicit ``params`` dict (which the hyperparameter search always does), so
    ``feature_fraction_seed`` stayed pinned and all three "seeds" produced
    byte-identical predictions — a 3-seed result that was really one run reported
    three times.
    """
    from kelvins_conformal.models.gbm import fit_gbm, seed_keys

    X, y = _tiny_tabular(n=200, n_features=12)
    Xv, yv = _tiny_tabular(n=60, n_features=12, seed=1)
    # A searched configuration: subsampling on, so the seed must actually bite.
    searched = {
        "objective": "regression", "metric": "l2", "learning_rate": 0.1,
        "num_leaves": 15, "min_data_in_leaf": 5, "feature_fraction": 0.5,
        "bagging_fraction": 0.7, "bagging_freq": 1, "verbosity": -1,
        "deterministic": True, "force_row_wise": True, "num_threads": 1,
        **seed_keys(42),          # deliberately pinned at 42, as the search emits
    }
    preds = [
        fit_gbm(X, y, Xv, yv, seed=s, params=searched,
                num_boost_round=60, early_stopping_rounds=15).predict(Xv)
        for s in (42, 43, 44)
    ]
    assert not np.array_equal(preds[0], preds[1]), "seed 43 reproduced seed 42 exactly"
    assert not np.array_equal(preds[1], preds[2]), "seed 44 reproduced seed 43 exactly"


def test_seed_keys_covers_every_lightgbm_generator():
    from kelvins_conformal.models.gbm import seed_keys

    keys = seed_keys(7)
    assert keys == {"seed": 7, "bagging_seed": 7,
                    "feature_fraction_seed": 7, "data_random_seed": 7}


def test_sequence_model_predictions_are_deterministic():
    from kelvins_conformal.models.sequence import train_sequence_model

    X, L, y = _tiny_sequence()
    Xv, Lv, yv = _tiny_sequence(n=30, seed=1)

    def run():
        r = train_sequence_model(
            X, L, y, Xv, Lv, yv, seed=42, n_features=X.shape[2],
            hidden_size=8, max_epochs=4, batch_size=16, early_stopping_rounds=3,
        )
        return r.predict(Xv, Lv), r.train_losses, r.val_losses

    p1, t1, v1 = run()
    p2, t2, v2 = run()
    np.testing.assert_allclose(p1, p2, rtol=0, atol=0)
    assert t1 == t2 and v1 == v2


def test_sequence_training_curves_are_reproducible():
    from kelvins_conformal.models.sequence import train_sequence_model

    X, L, y = _tiny_sequence(seed=2)
    Xv, Lv, yv = _tiny_sequence(n=30, seed=3)
    kwargs = {"seed": 7, "n_features": X.shape[2], "hidden_size": 8,
              "max_epochs": 5, "batch_size": 16, "early_stopping_rounds": 4}
    a = train_sequence_model(X, L, y, Xv, Lv, yv, **kwargs)
    b = train_sequence_model(X, L, y, Xv, Lv, yv, **kwargs)
    assert a.best_epoch == b.best_epoch
    assert a.best_val_loss == b.best_val_loss


def test_mc_dropout_is_deterministic_given_a_seed():
    from kelvins_conformal.models.bayesian import mc_dropout_predict
    from kelvins_conformal.models.sequence import train_sequence_model

    X, L, y = _tiny_sequence(seed=4)
    Xv, Lv, yv = _tiny_sequence(n=30, seed=5)
    r = train_sequence_model(
        X, L, y, Xv, Lv, yv, seed=42, n_features=X.shape[2],
        hidden_size=8, dropout=0.3, max_epochs=4, batch_size=16,
        early_stopping_rounds=3,
    )

    d1 = mc_dropout_predict(r, Xv, Lv, n_samples=8, aleatoric_std=0.5, seed=99)
    d2 = mc_dropout_predict(r, Xv, Lv, n_samples=8, aleatoric_std=0.5, seed=99)
    np.testing.assert_array_equal(d1.mean, d2.mean)
    np.testing.assert_array_equal(d1.std, d2.std)
    np.testing.assert_array_equal(d1.samples, d2.samples)


def test_mc_dropout_actually_varies_across_passes():
    """Guards the determinism test above from passing vacuously."""
    from kelvins_conformal.models.bayesian import mc_dropout_predict
    from kelvins_conformal.models.sequence import train_sequence_model

    X, L, y = _tiny_sequence(seed=6)
    Xv, Lv, yv = _tiny_sequence(n=30, seed=7)
    r = train_sequence_model(
        X, L, y, Xv, Lv, yv, seed=42, n_features=X.shape[2],
        hidden_size=8, dropout=0.3, max_epochs=4, batch_size=16,
        early_stopping_rounds=3,
    )
    d = mc_dropout_predict(r, Xv, Lv, n_samples=16, aleatoric_std=0.0, seed=1)
    assert np.any(d.epistemic_std > 0), "dropout was not active at inference"
    # Different MC seed => different samples.
    d2 = mc_dropout_predict(r, Xv, Lv, n_samples=16, aleatoric_std=0.0, seed=2)
    assert not np.array_equal(d.samples, d2.samples)


def test_training_pool_splits_are_deterministic_and_disjoint():
    from kelvins_conformal.config import load_config
    from kelvins_conformal.data import training_pool_splits

    cfg = load_config()
    events = _synthetic_events(n_events=200)
    a = training_pool_splits(events, cfg)
    b = training_pool_splits(events, cfg)
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])

    # Disjointness is asserted inside, but check the union too.
    all_uids = np.concatenate(list(a.values()))
    assert len(all_uids) == len(set(all_uids.tolist())) == 200
