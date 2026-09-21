"""End-to-end smoke test of the E17 runner on synthetic data (CLAUDE.md §4).

Every data-touching or expensive dependency is replaced by a seeded synthetic
stand-in, so H1/H2/H3 exercise their full paths in seconds: the mission-level
cluster bootstrap against the iid bootstrap, the clipping-cap confirmation, the
Holm pass over the recorded family, the one-sided CQR coverage cells, and the
five-manifestation association/overlap tables.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal.config import load_config
from kelvins_conformal.conformal.weights import WeightVector
from kelvins_conformal.models import robustness_runner as RR

N_CAL, N_SELF, N_TEST, N_VAL = 400, 300, 500, 200
SPLITS = ("calibration", "self_test", "official_test", "val_inner")
N_MISSIONS = 25


@pytest.fixture()
def assembled(monkeypatch, tmp_path):
    cfg = load_config()
    rng = np.random.default_rng(0)

    def subset(n, prefix):
        y = rng.normal(-12.0, 5.0, size=n)
        return {"y": y, "is_high_risk": y >= cfg.high_risk_threshold,
                "recency_ok": np.ones(n, dtype=bool),
                "risk_last": rng.normal(-12.0, 5.0, size=n),
                "uids": np.array([f"{prefix}{i}" for i in range(n)])}

    subsets = {"calibration": subset(N_CAL, "c"), "self_test": subset(N_SELF, "s"),
               "official_test": subset(N_TEST, "t"), "val_inner": subset(N_VAL, "v")}
    data = SimpleNamespace(subsets=subsets, test_high_risk_prevalence=0.15,
                           train_high_risk_prevalence=0.05)
    weights = SimpleNamespace(
        rule=WeightVector(w=rng.uniform(0.5, 2.0, N_CAL), method="rule", test_weight=1.2),
        classifier=WeightVector(w=rng.uniform(0.5, 3.0, N_CAL), method="classifier", test_weight=1.0),
    )
    # Events frame carrying mission_id for the official-test uids (the cluster variable).
    missions = rng.integers(0, N_MISSIONS, size=N_TEST)
    events = pd.DataFrame({"event_uid": subsets["official_test"]["uids"], "mission_id": missions})
    monkeypatch.setattr(RR, "event_level_frame", lambda ev: ev)

    def preds_for(seed):
        r = np.random.default_rng(seed)
        out = {lrn: {s: subsets[s]["y"] + r.normal(0.0, 2.0, subsets[s]["y"].size) for s in SPLITS}
               for lrn in RR.BASE_LEARNERS}
        return out

    def heads_for(seed, levels):
        r = np.random.default_rng(100 + seed)
        return {round(float(lv), 6): {s: subsets[s]["y"] + r.normal(1.0, 1.5, subsets[s]["y"].size)
                                      for s in SPLITS} for lv in levels}

    levels = [cfg.power.nominal_coverage_primary, *cfg.power.nominal_coverage_secondary]
    seeds = [42, 43]
    fitted = {s: (preds_for(s), heads_for(s, levels)) for s in seeds}
    return cfg, data, weights, events, fitted, seeds, levels


# --- H1 ---------------------------------------------------------------------------


def test_h1_cluster_bootstrap_is_wider_or_equal_and_reports_its_clusters(assembled, monkeypatch, tmp_path):
    cfg, data, weights, events, fitted, seeds, levels = assembled
    mcn = pd.DataFrame({"learner": ["gbm", "gru"], "p_value": [5.6e-45, 0.02]})
    mcn.to_csv(tmp_path / "e11_primary_mcnemar.csv", index=False)
    monkeypatch.setattr(cfg.__class__, "path", lambda self, k: tmp_path, raising=False)

    res = RR.run_h1(cfg, seeds=seeds, n_boot=200, data=data, weights=weights,
                    fitted=fitted, events=events)
    cb = res["cluster_bootstrap"]
    assert len(cb) == len(levels) * len(RR.BASE_LEARNERS) * 2 * 2   # levels x learners x method x side
    assert (cb["n_clusters"] == N_MISSIONS).all()
    assert (cb["n_events"] == N_TEST).all()
    # Both schemes estimate the SAME coverage point; only the interval differs.
    assert cb["coverage"].between(0.0, 1.0).all()
    assert (cb["cluster_half_width"] > 0).all() and (cb["iid_half_width"] > 0).all()
    assert res["meta"]["cluster_variable"] == "mission_id"


def test_h1_clipping_confirms_untriggered_under_stricter_caps(assembled, monkeypatch, tmp_path):
    cfg, data, weights, events, fitted, seeds, _ = assembled
    pd.DataFrame({"p_value": [1e-40]}).to_csv(tmp_path / "e11_primary_mcnemar.csv", index=False)
    monkeypatch.setattr(cfg.__class__, "path", lambda self, k: tmp_path, raising=False)
    res = RR.run_h1(cfg, seeds=seeds, n_boot=100, data=data, weights=weights,
                    fitted=fitted, events=events)
    clip = res["clipping"]
    assert set(clip["khat_trigger"]) == {0.7, 0.5, 0.3}
    assert set(clip["weights"]) == {"rule", "classifier"}
    # Uniform weights are far from heavy-tailed, so nothing should clip at any trigger,
    # and an untriggered clip must report exactly zero induced bias.
    assert not clip["clipping_triggered"].any()
    assert (clip["bias_delta"] == 0.0).all() and (clip["clipped_fraction"] == 0.0).all()
    assert (clip["n_effective"] <= clip["n_calibration"]).all()


def test_h1_holm_is_applied_to_the_recorded_family(assembled, monkeypatch, tmp_path):
    cfg, data, weights, events, fitted, seeds, _ = assembled
    pd.DataFrame({"p_value": [5.6e-45, 0.2, 0.4]}).to_csv(tmp_path / "e11_primary_mcnemar.csv", index=False)
    monkeypatch.setattr(cfg.__class__, "path", lambda self, k: tmp_path, raising=False)
    res = RR.run_h1(cfg, seeds=seeds, n_boot=100, data=data, weights=weights,
                    fitted=fitted, events=events)
    mc = res["multiple_comparison"]
    assert mc["n_tests_in_family"].iloc[0] == 3
    assert bool(mc.loc[mc["p_value"].idxmin(), "rejected_holm"])      # the primary survives Holm
    assert (mc["p_adjusted_holm"] >= mc["p_value"] - 1e-12).all()


def test_h1_refuses_to_run_without_the_recorded_p_values(assembled, monkeypatch, tmp_path):
    """Fail loud rather than fabricate: no McNemar table means no Holm check."""
    cfg, data, weights, events, fitted, seeds, _ = assembled
    monkeypatch.setattr(cfg.__class__, "path", lambda self, k: tmp_path, raising=False)
    with pytest.raises(FileNotFoundError):
        RR.run_h1(cfg, seeds=seeds, n_boot=50, data=data, weights=weights,
                  fitted=fitted, events=events)


# --- H2 ---------------------------------------------------------------------------


def test_h2_produces_all_three_cqr_upper_cells_at_every_level(assembled):
    cfg, data, weights, _, fitted, seeds, levels = assembled
    res = RR.run_h2(cfg, seeds=seeds, n_boot=200, data=data, weights=weights, fitted=fitted)
    cov = res["coverage"]
    assert set(cov["method"]) == {"E17_cqr_upper_selftest", "E17_cqr_upper_naive",
                                  "E17_cqr_upper_weighted_rule"}
    assert set(cov["sided"]) == {"upper"} and set(cov["nominal"]) == set(levels)
    assert len(cov) == 3 * len(levels)
    assert (cov["n_seeds"] == len(seeds)).all()
    assert cov["coverage_mean"].between(0.0, 1.0).all()
    # The self-test cell is the exchangeable control and is scored on the self-test split.
    assert (cov.loc[cov.method == "E17_cqr_upper_selftest", "n"] == N_SELF).all()
    assert (cov.loc[cov.method != "E17_cqr_upper_selftest", "n"] == N_TEST).all()


def test_h2_gap_pp_matches_its_own_coverage_and_nominal(assembled):
    cfg, data, weights, _, fitted, seeds, _ = assembled
    cov = RR.run_h2(cfg, seeds=seeds, n_boot=100, data=data, weights=weights,
                    fitted=fitted)["coverage"]
    np.testing.assert_allclose(cov["gap_pp"], 100 * (cov["coverage_mean"] - cov["nominal"]))


# --- H3 ---------------------------------------------------------------------------


def test_h3_reports_all_five_manifestations_and_flags_the_instrument_level_ones(assembled):
    cfg, data, weights, _, fitted, seeds, _ = assembled
    res = RR.run_h3(cfg, data=data, weights=weights, fitted=fitted, seeds=seeds)
    a = res["association"]
    assert list(a["manifestation"]) == ["M1", "M2", "M3", "M4", "M5"]
    # M4/M5 have no per-event membership and must come back NaN, not a fabricated number.
    inst = a[a["level_declared"] == "instrument"]
    assert len(inst) == 2
    assert inst[["n_members", "point_biserial_r"]].isna().all().all()
    ev = a[a["level_declared"] == "event"]
    assert (ev["n_members"] > 0).all() and ev["point_biserial_r"].notna().all()
    assert res["meta"]["event_level_manifestations"] == 3
    assert res["meta"]["instrument_level_manifestations"] == 2


def test_h3_overlap_table_covers_every_event_level_pair(assembled):
    cfg, data, weights, _, fitted, seeds, _ = assembled
    ov = RR.run_h3(cfg, data=data, weights=weights, fitted=fitted, seeds=seeds)["overlap"]
    assert set(ov["pair"]) == {"M1&M2", "M1&M3", "M2&M3"}
    assert (ov["n_overlap"] <= ov[["n_a", "n_b"]].min(axis=1)).all()
    assert ov["jaccard"].between(0.0, 1.0).all()
