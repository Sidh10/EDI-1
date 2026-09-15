"""End-to-end smoke test of the rank-invariance audit on a synthetic problem (CLAUDE.md §4).

The real audit refits the four learners for three seeds, so every data-touching or
expensive dependency is replaced by a seeded synthetic stand-in. The synthetic
scores live on a 0.25 grid, so point + Q is exact in floating point and Proposition 1's
translation classes must come out exactly; the quantile heads and MC dispersion are
drawn independently of the point prediction, so those classes must NOT be
rank-identical to it.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from kelvins_conformal.config import load_config
from kelvins_conformal.conformal.weights import WeightVector
from kelvins_conformal.models import decision_runner as DR
from kelvins_conformal.models.bayesian import PredictiveDistribution

N_CAL, N_SELF, N_TEST = 400, 200, 300
SPLITS = ("calibration", "self_test", "official_test")


def _grid(rng, n):
    return rng.integers(-120, 0, size=n) * 0.25


@pytest.fixture()
def audit(monkeypatch, tmp_path):
    cfg = load_config()
    rng = np.random.default_rng(0)

    def subset(n, hr_frac):
        y = _grid(rng, n)
        hr = rng.random(n) < hr_frac
        y[hr] = rng.integers(-24, 0, size=int(hr.sum())) * 0.25
        return {"y": y, "is_high_risk": y >= cfg.high_risk_threshold, "recency_ok": np.ones(n, dtype=bool)}

    data = SimpleNamespace(subsets={
        "calibration": subset(N_CAL, 0.10), "self_test": subset(N_SELF, 0.10),
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
    monkeypatch.setattr(DR, "audit_progress_path", lambda cfg_: tmp_path / "audit.log")
    return DR.run_rank_invariance_audit(cfg, seeds=[1, 2]), cfg


def test_translation_classes_are_exactly_rank_identical_to_the_point(audit):
    res, _ = audit
    cls = res["classification"]
    tr = cls[cls["structural_class"] == DR.TRANSLATION_OF_POINT]
    assert len(tr) == 4 * len(DR.BASE_LEARNERS)          # E10, E11 x {upper, two} x learners
    assert tr["strictly_increasing_in_point_all"].all()
    assert (tr["offset_spread_vs_point_max"] == 0.0).all()
    al = res["alerts"]
    assert (al[al["method"].isin([DR.E10, DR.E11, DR.E10_TWO, DR.E11_TWO])]
            ["max_abs_alert_difference_vs_point"] == 0.0).all()


def test_cqr_follows_its_head_not_the_point(audit):
    res, _ = audit
    cqr = res["classification"][res["classification"]["structural_class"] == DR.TRANSLATION_OF_QUANTILE_HEAD]
    assert set(cqr["method"]) == {DR.E12, DR.E12_TWO}
    assert cqr["strictly_increasing_in_construction_reference_all"].all()
    assert not cqr["strictly_increasing_in_point_all"].any()


def test_bayesian_bound_has_no_construction_reference_and_is_not_rank_identical_here(audit):
    res, _ = audit
    e8 = res["classification"][res["classification"]["structural_class"] == DR.EVENT_SPECIFIC_DISPERSION]
    assert set(e8["method"]) == {DR.E8, DR.E8_TWO}
    assert not e8["has_construction_reference"].any()
    assert not e8["strictly_increasing_in_point_all"].any()   # synthetic sigma is independent of mu


def test_audit_table_shapes(audit):
    res, cfg = audit
    n_levels = 1 + len(cfg.power.nominal_coverage_secondary)
    n_budgets = 1 + len(cfg.decision_cost.budget_fractions)
    n_scores = 4 * len(DR.BASE_LEARNERS) + 4
    assert len(res["classification"]) == n_scores
    assert len(res["classification_raw"]) == n_scores * n_levels * 2
    assert len(res["alerts"]) == n_scores * n_levels * n_budgets
    assert len(res["e8_dispersion"]) == 2
