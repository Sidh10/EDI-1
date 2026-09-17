"""End-to-end smoke test of the expanded E15 threshold analysis on synthetic data (CLAUDE.md §4).

Every data-touching or expensive dependency is replaced by a seeded synthetic stand-in, so
``run_threshold_analysis`` exercises its full path in seconds: per-horizon derived configs,
the two event populations, arms and exclusions, the val_inner grid, per-threshold decisions
with bootstrap CIs, paired differences, all four selection read-outs, and the P1 checks.
The synthetic 3-day horizon LOSES some official-test events, so the common-population logic
is exercised. Scores live on a 0.25 grid, so for the translation class P1a, P1b and P1c must
hold EXACTLY.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal.config import load_config
from kelvins_conformal.conformal.weights import WeightVector
from kelvins_conformal.models import decision_runner as DR
from kelvins_conformal.models import threshold_runner as TR
from kelvins_conformal.models.bayesian import PredictiveDistribution

N_CAL, N_SELF, N_TEST, N_VAL, N_TEST_3D = 400, 250, 300, 200, 260
SPLITS = ("calibration", "self_test", "official_test", "val_inner")


def _grid(rng, n):
    return rng.integers(-120, 0, size=n) * 0.25


@pytest.fixture()
def result(monkeypatch, tmp_path):
    cfg = load_config()
    rng = np.random.default_rng(0)

    def subset(n, hr_frac, prefix):
        y = _grid(rng, n)
        hr = rng.random(n) < hr_frac
        y[hr] = rng.integers(-24, 0, size=int(hr.sum())) * 0.25
        return {"y": y, "is_high_risk": y >= cfg.high_risk_threshold, "recency_ok": rng.random(n) < 0.8,
                "risk_last": _grid(rng, n), "uids": np.array([f"{prefix}{i}" for i in range(n)])}

    test_2d = subset(N_TEST, 0.15, "t")
    test_2d["recency_ok"] = np.ones(N_TEST, dtype=bool)
    shared = {"calibration": subset(N_CAL, 0.05, "c"), "self_test": subset(N_SELF, 0.05, "s")}
    data_2d = SimpleNamespace(subsets={**shared, "official_test": test_2d},
                              test_high_risk_prevalence=0.15, train_high_risk_prevalence=0.05)
    keep = np.sort(np.random.default_rng(7).choice(N_TEST, size=N_TEST_3D, replace=False))
    data_3d = SimpleNamespace(subsets={**shared, "official_test": {k: v[keep] for k, v in test_2d.items()}},
                              test_high_risk_prevalence=0.15, train_high_risk_prevalence=0.05)
    weights = SimpleNamespace(rule=WeightVector(w=rng.uniform(0.5, 2.0, N_CAL), method="rule", test_weight=1.2))

    def n_of(data_, split):
        return N_VAL if split == "val_inner" else data_.subsets[split]["y"].size

    def preds_for(cfg_, data_, seed):
        r = np.random.default_rng(seed)
        out = {lrn: {s: _grid(r, n_of(data_, s)) for s in SPLITS} for lrn in DR.BASE_LEARNERS}
        out["_mc_dropout_dist"] = {}
        for s in SPLITS:
            mean = out["mc_dropout"][s]
            std = r.uniform(0.5, 3.0, mean.size)
            out["_mc_dropout_dist"][s] = PredictiveDistribution(
                mean=mean, std=std, epistemic_std=std, aleatoric_std=0.0, samples=np.stack([mean, mean]))
        return out

    def heads_for(cfg_, data_, seed, levels):
        r = np.random.default_rng(100 + seed)
        return {round(float(lv), 6): {s: _grid(r, n_of(data_, s)) for s in SPLITS} for lv in levels}

    monkeypatch.setattr(TR, "load_events", lambda cfg_: None)
    monkeypatch.setattr(TR, "prepare_conformal_data",
                        lambda cfg_, events: data_3d if cfg_.cutoff.cutoff_days_before_tca == 3.0 else data_2d)
    monkeypatch.setattr(TR, "build_weights", lambda cfg_, data_: weights)
    monkeypatch.setattr(TR, "base_predictions", preds_for)
    monkeypatch.setattr(TR, "_fit_upper_heads", heads_for)
    monkeypatch.setattr(TR, "search_integrity", lambda cfg_, **kw: pd.DataFrame([{"status": "stubbed"}]))
    monkeypatch.setattr(TR, "threshold_progress_path", lambda cfg_: tmp_path / "threshold.log")
    ta = cfg.threshold_analysis
    res = TR.run_threshold_analysis(cfg, seeds=list(ta.smoke_seeds),
                                    percentiles=list(ta.smoke_grid_percentiles), n_boot=60)
    return res, cfg


N_ARMS = 4 + (3 + 4) + (3 + 4) + 2 + 2   # point; E10 up/two; E11 up/two (persistence one-sided out); CQR; E8


def test_horizon_config_is_derived_and_hashed_per_horizon():
    cfg = load_config()
    h2, h3 = TR.horizon_config(cfg, 2.0), TR.horizon_config(cfg, 3.0)
    assert (h2.cutoff.cutoff_days_before_tca, h3.cutoff.cutoff_days_before_tca) == (2.0, 3.0)
    assert h2.threshold_analysis.horizons_days == (2.0,) and h3.threshold_analysis.horizons_days == (3.0,)
    assert len({cfg.config_hash, h2.config_hash, h3.config_hash}) == 3


def test_populations_harmonise_the_lead_time_comparison(result):
    res, _ = result
    pop = res["populations"].set_index(["horizon_days", "population"])
    assert pop.loc[(2.0, TR.FULL), "n_events"] == N_TEST
    assert pop.loc[(2.0, TR.COMMON), "n_events"] == N_TEST_3D
    assert pop.loc[(2.0, TR.COMMON), "n_excluded_from_common"] == N_TEST - N_TEST_3D
    assert pop.loc[(3.0, TR.FULL), "n_events"] == N_TEST_3D
    assert pop.loc[(3.0, TR.COMMON), "n_events"] == N_TEST_3D
    assert pop.loc[(2.0, TR.COMMON), "n_high_risk"] == pop.loc[(3.0, TR.COMMON), "n_high_risk"]
    assert res["meta"]["n_common_events"] == N_TEST_3D


def test_arms_exclusions_and_table_shapes(result):
    res, cfg = result
    n_levels = 1 + len(cfg.power.nominal_coverage_secondary)
    n_ratios = len(cfg.decision_cost.cost_ratios)
    per_h = res["meta"]["per_horizon"]
    assert res["meta"]["reduced_configuration"] is True
    assert res["meta"]["grid_source_split"] == "val_inner"
    assert len(res["excluded_arms"]) == 2 * 2   # 2 persistence one-sided arms x 2 horizons
    assert -6.0 in set(res["grid"]["threshold"])
    expected_dec = sum(2 * N_ARMS * n_levels * per_h[f"{h:g}d"]["n_thresholds"] for h in (2.0, 3.0))
    assert len(res["decisions"]) == expected_dec
    assert len(res["selection"]) == 2 * 2 * N_ARMS * n_levels * n_ratios * len(TR.READOUTS)
    assert len(res["p1_checks"]) == 2 * 2 * (N_ARMS - 4) * n_levels
    for h in (2.0, 3.0):
        d = res["decisions"][res["decisions"]["horizon_days"] == h]
        assert set(d["population"]) == set(TR.POPULATIONS)


def test_p1_predictions_hold_exactly_for_the_translation_class(result):
    res, cfg = result
    p1 = res["p1_checks"]
    tr = p1[p1["structural_class"] == DR.TRANSLATION_OF_POINT]
    assert len(tr) > 0
    assert (tr["offset_spread"] == 0.0).all()
    assert (tr["p1a_max_count_difference"] == 0.0).all()             # P1a
    assert (tr["p1b_max_locus_difference_missed"] == 0.0).all()      # P1b
    for r in cfg.decision_cost.cost_ratios:
        assert (tr[f"p1c_unrestricted_cost_difference_{r:g}to1"] == 0.0).all()   # P1c


def test_point_rows_have_zero_change_against_themselves(result):
    res, _ = result
    sel = res["selection"]
    point = sel[sel["method"] == DR.POINT]
    assert (point["cost_change_vs_point"] == 0.0).all()
    assert (point["threshold_shift_vs_point"] == 0.0).all()


def test_counts_are_consistent_in_every_population(result):
    res, _ = result
    d = res["decisions"]
    np.testing.assert_allclose(d["n_alerts"], (d["n_high_risk"] - d["missed_high_risk"]) + d["unnecessary_maneuvers"])
