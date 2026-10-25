"""Logic tests for the Pc validation runner (pre-registered in DECISIONS.md, 2026-10-24).

Synthetic inputs only: no real event, CDM or E3 sample. Covers the sampling procedure, the
self-convergence statistic, the M1-vs-M3 gate, the per-stratum agreement rule (both methods, engine
errors as disagreements, and the OPEN missing-value policy), and the convention input transforms.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import yaml

from kelvins_conformal.labelnoise import pc_foster as pf
from kelvins_conformal.models import pc_validation_runner as pvr

EDGES = [-30.0, -15.0, -10.0, -6.0, 0.0]
AGREE = {"tau_floor": 0.01, "tau_mult": 3.0, "min_frac_within": 0.95, "max_abs_any": 0.1,
         "max_median_abs": 0.005, "require_both_m1_m3": True, "engine_errors_count_as_disagreement": True,
         "not_informative_if_frac_missing_above": 0.10}


def test_pre_registered_config_loads_with_the_2026_10_25_policy_and_seed_streams():
    cfg, digest = pvr.load_pcv_config()
    assert len(digest) == 64
    assert cfg["seed"] == 42 and cfg["m3"]["rel_se_target"] == 0.005
    a = cfg["agreement"]
    assert a["missing_independent_value_policy"] == "exclude"
    assert a["engine_errors_count_as_disagreement"] is True and a["list_excluded_events_per_stratum"] is True
    assert a["not_informative_if_frac_missing_above"] == 0.10
    assert cfg["m3"]["seed_offset"] == 0 and cfg["m2"]["seed_offset"] == 1_000_000


def test_stratum_is_not_informative_when_more_than_10pct_lack_an_independent_value():
    d = np.zeros(20)
    d_m1, d_m3 = d.copy(), d.copy()
    d_m1[0] = np.nan                              # 1 event lacks M1 ...
    d_m3[[1, 2]] = np.nan                         # ... and 2 others lack M3: 3 of 20 = 15% > 10%
    res = pvr.classify_stratum(d_m1, d_m3, np.zeros(20, bool), tau=0.01, agreement=AGREE, missing_policy="exclude")
    assert res["frac_lacking_m1_or_m3"] == pytest.approx(0.15)
    assert res["classification"] == "not informative" and res["not_informative"]
    d_m3[2] = 0.0                                 # 2 of 20 = 10%: not MORE than 10%, so classified
    res = pvr.classify_stratum(d_m1, d_m3, np.zeros(20, bool), tau=0.01, agreement=AGREE, missing_policy="exclude")
    assert res["classification"] == "agree"


def test_excluded_events_are_listed_per_method_and_engine_errors_are_never_excluded():
    d_m1, d_m3 = np.zeros(30), np.zeros(30)
    m3_lacks = np.zeros(30, bool)
    m3_lacks[[4, 9]] = True
    d_m3[[4, 9]] = np.nan
    err = np.zeros(30, bool)
    err[9] = True                                 # engine error on an event that also lacks M3
    res = pvr.classify_stratum(d_m1, d_m3, err, tau=0.01, agreement=AGREE, missing_policy="exclude",
                               m3_lacks=m3_lacks)
    assert res["excluded_m3"] == [4] and res["excluded_m1"] == []
    assert 9 in res["out_of_tolerance_m3"] and res["classification"] == "disagree"


def test_strata_labels_follow_e3_edges():
    y = np.array([-30.0, -20.0, -12.0, -8.0, -3.0, -15.0, -6.0])
    assert pvr.assign_strata(y, EDGES).tolist() == [
        "floor (== -30)", "(-30, -15]", "(-15, -10]", "(-10, -6]", "(-6, 0]", "(-30, -15]", "(-10, -6]"]


def _population(seed=0):
    rng = np.random.default_rng(seed)
    parts = []
    for label, lo, hi, n in (("floor", -30, -30, 300), ("a", -29.9, -15, 80), ("b", -14.9, -10, 70),
                             ("c", -9.9, -6, 60), ("hr", -5.9, -1, 40)):
        y = np.full(n, -30.0) if label == "floor" else rng.uniform(lo, hi, n)
        parts.append(pd.DataFrame({"event_uid": [f"test_{label}_{i:04d}" for i in range(n)], "y": y}))
    return pd.concat(parts, ignore_index=True)


def test_official_sample_draw_is_deterministic_and_order_independent():
    pop = _population()
    a = pvr.draw_official_sample(pop, uid_col="event_uid", y_col="y", edges=EDGES, seed=42,
                                 per_stratum_n=30, take_all=("(-6, 0]",))
    shuffled = pop.sample(frac=1.0, random_state=9).reset_index(drop=True)
    b = pvr.draw_official_sample(shuffled, uid_col="event_uid", y_col="y", edges=EDGES, seed=42,
                                 per_stratum_n=30, take_all=("(-6, 0]",))
    assert a["event_uid"].tolist() == b["event_uid"].tolist()
    counts = a["stratum"].value_counts().to_dict()
    assert counts == {"floor (== -30)": 30, "(-30, -15]": 30, "(-15, -10]": 30, "(-10, -6]": 30, "(-6, 0]": 40}
    assert a["event_uid"].is_unique


def test_self_convergence_is_the_95th_percentile_of_absolute_differences():
    one = np.arange(100, dtype=float)
    two = one + np.linspace(0.0, 0.099, 100)
    assert pvr.self_convergence_e_s(one, two) == pytest.approx(np.percentile(np.linspace(0, 0.099, 100), 95))


def test_tau_is_floored_at_point_zero_one():
    assert pvr.tau_s(0.001, AGREE) == 0.01
    assert pvr.tau_s(0.02, AGREE) == pytest.approx(0.06)


def test_m1_m3_gate_uses_the_median_and_reports_b_prime_on_failure():
    m1 = np.zeros(9)
    assert pvr.m1_m3_gate(m1, m1 + 0.004, threshold=0.005)["outcome"] == "pass"
    assert pvr.m1_m3_gate(m1, m1 + 0.006, threshold=0.005)["outcome"] == "b'"


def test_classification_refuses_while_missing_value_policy_is_unset():
    d = np.zeros(10)
    with pytest.raises(pvr.OpenDecisionError):
        pvr.classify_stratum(d, d, np.zeros(10, bool), tau=0.01, agreement=AGREE, missing_policy=None)


def test_classification_requires_both_methods():
    d_ok = np.zeros(40)
    d_bad = np.zeros(40)
    d_bad[:5] = 0.05   # 87.5% within tau against M3 -> fails the 95% rule
    res = pvr.classify_stratum(d_ok, d_bad, np.zeros(40, bool), tau=0.01, agreement=AGREE,
                               missing_policy="exclude")
    assert res["agree_m1"] and not res["agree_m3"] and not res["agree"]


def test_engine_errors_count_as_disagreements():
    d = np.zeros(20)
    err = np.zeros(20, bool)
    err[0] = True
    res = pvr.classify_stratum(d, d, err, tau=0.01, agreement=AGREE, missing_policy="exclude")
    assert res["n_engine_errors"] == 1
    assert not res["agree"]           # an error is beyond 0.1, so the stratum cannot agree
    assert res["frac_within_m1"] == pytest.approx(19 / 20)


def test_missing_independent_values_follow_the_chosen_policy():
    d = np.zeros(20)
    d_m3 = d.copy()
    d_m3[0] = np.nan                  # M3 not informative for one event
    excl = pvr.classify_stratum(d, d_m3, np.zeros(20, bool), tau=0.01, agreement=AGREE, missing_policy="exclude")
    assert excl["agree"] and excl["n_missing_m3"] == 1
    dis = pvr.classify_stratum(d, d_m3, np.zeros(20, bool), tau=0.01, agreement=AGREE,
                               missing_policy="count_as_disagreement")
    assert not dis["agree"]
    with pytest.raises(ValueError):
        pvr.classify_stratum(d, d_m3, np.zeros(20, bool), tau=0.01, agreement=AGREE, missing_policy="ignore")


def test_out_of_tolerance_events_are_listed():
    d = np.zeros(30)
    d[[3, 7]] = 0.02
    res = pvr.classify_stratum(d, d, np.zeros(30, bool), tau=0.01, agreement=AGREE, missing_policy="exclude")
    assert res["out_of_tolerance_m1"] == [3, 7] and res["out_of_tolerance_m3"] == [3, 7]


# --- convention input transforms (engine untouched; inputs only) --------------------------------
def _row(v=(30.0, 1.0, 0.0)):
    keys = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")
    row = {f"relative_position_{a}": x for a, x in zip("rtn", (120.0, 40.0, -60.0), strict=False)}
    row.update({f"relative_velocity_{a}": x for a, x in zip("rtn", v, strict=False)})
    row.update({f"t_{k}": x for k, x in zip(keys, (30.0, 400.0, 20.0, 0.3, -0.2, 0.4), strict=False)})
    row.update({f"c_{k}": x for k, x in zip(keys, (80.0, 900.0, 60.0, -0.5, 0.25, 0.1), strict=False)})
    row.update({"t_span": 5.0, "c_span": 2.0, "t_j2k_sma": 7000.0, "max_risk_scaling": 4.0})
    return row


def _chaser_cov(row):
    return pf.position_covariance_rtn(*[row[f"c_{k}"] for k in ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")])


def test_c0_is_the_identity():
    row = _row()
    new, scale = pvr.apply_convention(row, "C0", mu_km3_s2=398600.4418)
    assert new == row and scale == 1.0


def test_c1_doubles_the_hard_body_radius():
    row = _row()
    new, scale = pvr.apply_convention(row, "C1", mu_km3_s2=398600.4418)
    assert scale == 1.0
    base = pf.recompute_pc_for_row(row)
    doubled = pf.recompute_pc_for_row(new)
    assert doubled.hbr == pytest.approx(2.0 * base.hbr)


def test_c3_rotation_preserves_the_chaser_covariance_spectrum_and_is_signed():
    row = _row(v=(30.0, -900.0, 2500.0))
    a, _ = pvr.apply_convention(row, "C3a", mu_km3_s2=398600.4418)
    b, _ = pvr.apply_convention(row, "C3b", mu_km3_s2=398600.4418)
    ev0 = np.sort(np.linalg.eigvalsh(_chaser_cov(row)))
    for new in (a, b):
        assert np.sort(np.linalg.eigvalsh(_chaser_cov(new))) == pytest.approx(ev0, rel=1e-9)
        assert new["c_sigma_r"] == pytest.approx(row["c_sigma_r"], rel=1e-12)   # rotation is about R
    assert not np.allclose(_chaser_cov(a), _chaser_cov(b))                      # opposite crossing angles
    for k in ("t_sigma_r", "t_sigma_t", "t_sigma_n", "t_ct_r", "t_cn_r", "t_cn_t", "relative_position_r"):
        assert a[k] == row[k]                                                   # target and geometry untouched


def test_c3_with_no_normal_relative_velocity_is_no_rotation():
    row = _row(v=(30.0, -900.0, 0.0))
    new, _ = pvr.apply_convention(row, "C3a", mu_km3_s2=398600.4418)
    assert _chaser_cov(new) == pytest.approx(_chaser_cov(row), rel=1e-12)


def test_c4_scales_variance_or_sigma_and_skips_nonpositive_k():
    row = _row()
    assert pvr.apply_convention(row, "C4a", mu_km3_s2=398600.4418)[1] == 4.0
    assert pvr.apply_convention(row, "C4b", mu_km3_s2=398600.4418)[1] == 16.0
    row["max_risk_scaling"] = 0.0
    assert pvr.apply_convention(row, "C4a", mu_km3_s2=398600.4418) is None


def test_c1_median_change_is_reported_against_0_602_without_a_threshold():
    rep = pvr.c1_expectation_report(np.array([0.60, 0.61, 0.55]), expected=0.602)
    assert rep["median_dlog10"] == pytest.approx(0.60) and rep["expected"] == 0.602
    assert "pass" not in rep and "fail" not in rep


# --- seed streams (Sidh, 2026-10-25) -----------------------------------------------------------------
def test_m2_and_m3_draw_from_distinct_streams_for_the_same_event():
    from kelvins_conformal.labelnoise import pc_independent as pi

    pcv, _ = pvr.load_pcv_config()
    seeds = [pvr.event_seeds(pcv, i) for i in range(400)]   # more than either sample set holds
    assert {s["m2"] for s in seeds}.isdisjoint({s["m3"] for s in seeds})
    assert seeds[0]["m3"] == 42                              # M3 keeps the pre-registered 42 + index
    s = seeds[7]
    # The raw streams the two methods consume differ ...
    a = np.random.default_rng(s["m3"]).random(1000)
    b = np.random.default_rng(s["m2"]).random(1000)
    assert not np.allclose(a, b)
    # ... so M2's samples for this event are not the ones it would draw from M3's seed (with a shared
    # seed, M2's normals would be a deterministic transform of the bits behind M3's uniforms).
    g = pi.PlaneGeometry(mx=50.0, my=-20.0, sx=100.0, sy=40.0, hbr=10.0)
    m2_x = np.random.default_rng(s["m2"]).normal(g.mx, g.sx, 1000)
    m2_x_if_shared = np.random.default_rng(s["m3"]).normal(g.mx, g.sx, 1000)
    assert not np.allclose(m2_x, m2_x_if_shared)


def test_m2_and_m3_are_each_deterministic_for_an_event():
    from kelvins_conformal.labelnoise import pc_independent as pi

    pcv, _ = pvr.load_pcv_config()
    assert pvr.event_seeds(pcv, 11) == pvr.event_seeds(pcv, 11)
    s = pvr.event_seeds(pcv, 11)
    g = pi.PlaneGeometry(mx=30.0, my=10.0, sx=40.0, sy=25.0, hbr=8.0)
    m3 = [pi.m3_estimate(g, seed=s["m3"], n=50_000, chunk=10_000) for _ in range(2)]
    m2 = [pi.pc_m2(g, seed=s["m2"], chunk=20_000, cap=200_000, min_hits=100, max_rel_se=0.10) for _ in range(2)]
    assert m3[0] == m3[1] and m2[0] == m2[1]


def test_seed_streams_refuse_an_index_that_would_overlap():
    pcv, _ = pvr.load_pcv_config()
    with pytest.raises(ValueError):
        pvr.event_seeds(pcv, 1_000_000)


# --- the six steps, end to end, on SYNTHETIC CDMs only ------------------------------------------
# Structural smoke test of the step chain: tables, provenance and the refusal. The data loaders are
# replaced by synthetic frames and the tables directory by tmp_path, so no real event, CDM or E3 row
# is read. Sample sizes and Monte Carlo budgets are shrunk in a copy of the YAML; no numeric outcome
# is asserted, because that would be a comparison.
def _synthetic_cdms(prefix, reported, seed):
    rng = np.random.default_rng(seed)
    n = len(reported)
    keys = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")
    d = {"event_id": np.arange(n), "time_to_tca": rng.uniform(0.1, 2.0, n),
         "reported": np.asarray(reported, float), "max_risk_estimate": rng.uniform(-30, -3, n),
         "max_risk_scaling": np.where(np.arange(n) % 7 == 0, 0.0, rng.uniform(1.0, 9.0, n)),
         "t_span": rng.uniform(2.0, 10.0, n), "c_span": rng.uniform(2.0, 5.0, n), "t_j2k_sma": rng.uniform(6800, 7400, n)}
    for a in "rtn":
        d[f"relative_position_{a}"] = rng.normal(0.0, 300.0, n)
        d[f"relative_velocity_{a}"] = rng.normal(0.0, 4000.0, n)
    for obj in "tc":
        for k, (lo, hi) in zip(keys, ((10, 200), (50, 2000), (10, 200), (-0.5, 0.5), (-0.5, 0.5), (-0.5, 0.5)),
                               strict=False):
            d[f"{obj}_{k}"] = rng.uniform(lo, hi, n)
    df = pd.DataFrame(d)
    df["event_uid"] = prefix + df["event_id"].astype(str)
    return df


def _reported(n_per):
    vals = [-30.0] * n_per
    for lo, hi in ((-30, -15), (-15, -10), (-10, -6), (-6, 0)):
        vals += list(np.linspace(lo + 0.5, hi - 0.5, n_per))
    return vals


@pytest.fixture
def synthetic_run(tmp_path, monkeypatch):
    from kelvins_conformal import data as data_mod
    from kelvins_conformal.config import load_config

    official = _synthetic_cdms("test_", _reported(5), seed=1).rename(columns={"reported": "target_log_risk"})
    train = _synthetic_cdms("train_", _reported(2), seed=2).rename(columns={"reported": "risk"})
    tables = tmp_path / "tables"
    tables.mkdir()
    e3 = train[["event_uid", "time_to_tca", "risk"]].rename(columns={"risk": "reported"})
    e3["stratum"] = pvr.assign_strata(e3["reported"], EDGES)
    e3.to_csv(tables / "e3_full_comparison.csv", index=False)
    monkeypatch.setattr(data_mod, "official_test_target_cdms", lambda cfg: official.copy())
    monkeypatch.setattr(data_mod, "_read_train", lambda cfg: train.drop(columns="event_uid"))
    monkeypatch.setattr(data_mod, "_coerce_types", lambda df: df)
    monkeypatch.setattr(pvr, "_tables", lambda cfg: tables)

    pcv, _ = pvr.load_pcv_config()
    pcv["sample"]["official_test"]["per_stratum_n"] = 3
    pcv["m3"].update({"n_samples": 20_000, "n_escalated": 40_000, "chunk": 10_000})
    pcv["m2"].update({"chunk": 20_000, "cap": 40_000})

    def write(policy):
        pcv["agreement"]["missing_independent_value_policy"] = policy
        p = tmp_path / f"pcv_{policy}.yaml"
        p.write_text(yaml.safe_dump(pcv), encoding="utf-8")
        return p

    return load_config(), tables, write


def test_steps_run_end_to_end_on_synthetic_cdms_and_compare_refuses_while_open(synthetic_run):
    cfg, tables, write = synthetic_run
    open_yaml, set_yaml = write(None), write("exclude")
    for step in ("sample", "self-convergence", "gate"):
        pvr.run_step(cfg, step, open_yaml)
    with pytest.raises(pvr.OpenDecisionError):
        pvr.run_step(cfg, "compare", open_yaml)
    assert not (tables / "pcv_agreement.csv").exists()
    for step in ("compare", "m2", "conventions"):
        pvr.run_step(cfg, step, set_yaml)

    off = pd.read_csv(tables / "pcv_sample_official.csv")
    assert off["stratum"].value_counts().to_dict() == {
        "floor (== -30)": 3, "(-30, -15]": 3, "(-15, -10]": 3, "(-10, -6]": 3, "(-6, 0]": 5}
    assert len(pd.read_csv(tables / "pcv_sample_e3.csv")) == 10
    assert set(pd.read_csv(tables / "pcv_gate.csv")["set"]) == {"official", "e3"}
    agree = pd.read_csv(tables / "pcv_agreement.csv")
    assert len(agree) == 10 and set(agree["missing_policy"]) == {"exclude"}
    assert "classification" in agree.columns and (tables / "pcv_excluded.csv").exists()
    assert len(pd.read_csv(tables / "pcv_m2.csv")) == 27
    summ = pd.read_csv(tables / "pcv_convention_summary.csv")
    assert set(summ["convention"]) == {"C0", "C1", "C3a", "C3b", "C4a", "C4b"}
    assert len(pd.read_csv(tables / "pcv_c1_expectation.csv")) == 10
    for step in pvr.STEPS:
        prov = json.loads((tables / f"pcv_provenance_{step.replace('-', '_')}.json").read_text(encoding="utf-8"))
        assert len(prov["pc_validation_yaml_sha256"]) == 64
