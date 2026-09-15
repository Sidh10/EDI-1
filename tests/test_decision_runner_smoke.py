"""End-to-end smoke test of the E15 runner on a tiny synthetic problem (CLAUDE.md §4).

The real E15 run refits four learners for three seeds and takes hours, so a bug in
the runner's bookkeeping must not first appear at the end of that run. Every
expensive or data-touching dependency (event loading, feature assembly, weights,
learner fits, quantile heads, the search-cache audit, the progress log) is replaced
by a small seeded synthetic stand-in, and ``run_e15`` executes its full scoring,
bootstrap and aggregation path in seconds.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal.config import load_config
from kelvins_conformal.conformal.weights import WeightVector
from kelvins_conformal.models import decision_runner as DR
from kelvins_conformal.models.bayesian import PredictiveDistribution

N_CAL, N_SELF, N_TEST = 400, 200, 300
SPLITS = ("calibration", "self_test", "official_test")


def _grid(rng, n):
    """Values on a 0.25 grid, so pred + Q is exact in binary floating point."""
    return rng.integers(-120, 0, size=n) * 0.25


@pytest.fixture()
def result(monkeypatch, tmp_path):
    cfg = load_config()
    rng = np.random.default_rng(0)

    def subset(n, hr_frac):
        y = _grid(rng, n)
        hr = rng.random(n) < hr_frac
        y[hr] = rng.integers(-24, 0, size=int(hr.sum())) * 0.25   # at or above -6
        return {"y": y, "is_high_risk": y >= cfg.high_risk_threshold, "recency_ok": np.ones(n, dtype=bool)}

    data = SimpleNamespace(subsets={
        "calibration": subset(N_CAL, 0.10),
        "self_test": subset(N_SELF, 0.10),
        "official_test": subset(N_TEST, 0.15),
    })
    weights = SimpleNamespace(
        rule=WeightVector(w=rng.uniform(0.5, 2.0, N_CAL), method="rule", test_weight=1.2)
    )

    def preds_for(cfg_, data_, seed):
        r = np.random.default_rng(seed)
        out = {lrn: {s: _grid(r, data.subsets[s]["y"].size) for s in SPLITS} for lrn in DR.BASE_LEARNERS}
        mean = out["mc_dropout"]["official_test"]
        std = r.uniform(0.5, 3.0, N_TEST)
        out["_mc_dropout_dist"] = {"official_test": PredictiveDistribution(
            mean=mean, std=std, epistemic_std=std, aleatoric_std=0.0, samples=np.stack([mean, mean]),
        )}
        return out

    def heads_for(cfg_, data_, seed, levels):
        r = np.random.default_rng(100 + seed)
        return {round(float(lv), 6): {s: _grid(r, data.subsets[s]["y"].size) for s in SPLITS}
                for lv in levels}

    monkeypatch.setattr(DR, "load_events", lambda cfg_: None)
    monkeypatch.setattr(DR, "prepare_conformal_data", lambda cfg_, events: data)
    monkeypatch.setattr(DR, "build_weights", lambda cfg_, data_: weights)
    monkeypatch.setattr(DR, "base_predictions", preds_for)
    monkeypatch.setattr(DR, "_fit_upper_heads", heads_for)
    monkeypatch.setattr(DR, "search_integrity",
                        lambda cfg_: pd.DataFrame([{"experiment": "stub", "status": "stubbed"}]))
    monkeypatch.setattr(DR, "progress_path", lambda cfg_: tmp_path / "e15_progress.log")
    return DR.run_e15(cfg, seeds=[1, 2], n_boot=50), cfg


def test_runner_produces_every_table_with_the_expected_shape(result):
    res, cfg = result
    for key in ("decisions", "bound_coverage", "cqr_selftest", "paired_differences", "tradeoff_curves",
                "alert_identity", "budgets", "positivity", "search_integrity", "meta"):
        assert key in res, key
    n_levels = 1 + len(cfg.power.nominal_coverage_secondary)
    n_budgets = 1 + len(cfg.decision_cost.budget_fractions)
    n_scores = 3 * len(DR.BASE_LEARNERS) + 2          # point, E10, E11 per learner + CQR + E8
    assert len(res["decisions"]) == n_scores * n_levels * n_budgets
    assert set(res["decisions"]["n_seeds"]) == {2}
    assert len(res["paired_differences"]) == (2 * len(DR.BASE_LEARNERS) + 1) * 2
    assert len(res["tradeoff_curves"]) == n_scores * N_TEST
    assert len(res["cqr_selftest"]) == n_levels
    assert res["meta"]["caveat"] == DR.CAVEAT


def test_every_method_raises_exactly_the_matched_budget(result):
    res, _ = result
    d = res["decisions"]
    np.testing.assert_allclose(d["n_alerts"], d["K"])


def test_conformal_bounds_alert_exactly_like_their_reference(result):
    res, _ = result
    assert res["alert_identity"]["max_abs_alert_difference"].max() == 0.0


def test_cost_identity_holds_in_the_aggregated_table(result):
    res, cfg = result
    d = res["decisions"]
    for _, g in d.groupby(["nominal", "budget"]):
        k = g["K"].iloc[0]
        n_hr = g["n_high_risk"].iloc[0]
        for r in cfg.decision_cost.cost_ratios:
            np.testing.assert_allclose(g[DR.dc.cost_key(r)], (r + 1) * g["missed_high_risk"] + k - n_hr)


def test_point_predictions_do_not_depend_on_the_nominal_level(result):
    res, _ = result
    d = res["decisions"]
    point = d[d["method"] == DR.POINT]
    assert point.groupby(["learner", "budget"])["missed_high_risk"].nunique().max() == 1


def test_primary_budget_is_the_prevalence_matched_one(result):
    res, _ = result
    b = res["budgets"]
    assert b.loc[b["primary"], "budget"].tolist() == ["prevalence_matched"]
    assert int(b.loc[b["primary"], "K"].iloc[0]) == int(res["positivity"]["n_high_risk"].iloc[0])
