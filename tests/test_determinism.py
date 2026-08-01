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
