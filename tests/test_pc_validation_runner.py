"""Logic tests for the Pc validation runner (pre-registered in DECISIONS.md, 2026-10-24).

Synthetic inputs only: no real event, CDM or E3 sample. Covers the sampling procedure, the
self-convergence statistic, the M1-vs-M3 gate, the per-stratum agreement rule (both methods, engine
errors as disagreements, and the OPEN missing-value policy), and the convention input transforms.
"""

from __future__ import annotations

import json
import math
import subprocess

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
    ar, _ = pvr.apply_convention(row, "C3a_R", mu_km3_s2=398600.4418)
    b, _ = pvr.apply_convention(row, "C3b", mu_km3_s2=398600.4418)
    ev0 = np.sort(np.linalg.eigvalsh(_chaser_cov(row)))
    for new in (a, ar, b):
        assert np.sort(np.linalg.eigvalsh(_chaser_cov(new))) == pytest.approx(ev0, rel=1e-9)
        for k in ("t_sigma_r", "t_sigma_t", "t_sigma_n", "t_ct_r", "t_cn_r", "t_cn_t",
                  "relative_position_r", "relative_position_t", "relative_position_n",
                  "relative_velocity_r", "relative_velocity_t", "relative_velocity_n"):
            assert new[k] == row[k]                                             # target and geometry untouched
    for new in (ar, b):
        assert new["c_sigma_r"] == pytest.approx(row["c_sigma_r"], rel=1e-12)  # C3a_R, C3b: about R
    assert a["c_sigma_r"] != pytest.approx(row["c_sigma_r"], rel=1e-12)        # C3a: R tilts with the offset
    assert not np.allclose(_chaser_cov(ar), _chaser_cov(b))                     # opposite crossing angles


def test_c3_with_no_normal_relative_velocity_is_no_rotation():
    row = _row(v=(30.0, -900.0, 0.0))
    new, _ = pvr.apply_convention(row, "C3a_R", mu_km3_s2=398600.4418)
    assert _chaser_cov(new) == pytest.approx(_chaser_cov(row), rel=1e-12)
    # C3a: no rotation only when the offset is also purely radial (the chaser's axes then coincide).
    for k, x in zip(("relative_position_t", "relative_position_n"), (0.0, 0.0), strict=True):
        row[k] = x
    new, _ = pvr.apply_convention(row, "C3a", mu_km3_s2=398600.4418)
    assert _chaser_cov(new) == pytest.approx(_chaser_cov(row), rel=1e-12)


def test_c3a_uses_the_offset_position_in_metres_with_a_t_converted_from_km():
    # Source formulation: chaser position (1000 a_t + rel_R, rel_T, rel_N) m. A 7 km along-T offset at
    # a_t = 7000 km tilts the chaser's R by atan(7000 / 7e6) about N; reading a_t as metres would give
    # atan(7000 / 7000) = 45 deg instead.
    row = _row(v=(0.0, 0.0, 0.0))
    row.update({"relative_position_r": 0.0, "relative_position_t": 7000.0, "relative_position_n": 0.0})
    m = pvr.c3_rotation(row, "C3a", mu_km3_s2=398600.4418)
    phi = math.atan(7000.0 / 7.0e6)
    assert m == pytest.approx(np.array([[math.cos(phi), -math.sin(phi), 0.0],
                                        [math.sin(phi), math.cos(phi), 0.0],
                                        [0.0, 0.0, 1.0]]), abs=1e-12)


def test_c3_rotation_refuses_an_unknown_convention():
    with pytest.raises(ValueError):
        pvr.c3_rotation(_row(), "C3c", mu_km3_s2=398600.4418)


def test_convention_list_is_the_yaml_list_with_c3a_r_added_after_c3a():
    pcv, _ = pvr.load_pcv_config()
    assert [c["id"] for c in pcv["conventions"]] == ["C0", "C1", "C3a", "C3b", "C4a", "C4b"]   # YAML unedited
    assert pvr.convention_ids(pcv) == ["C0", "C1", "C3a", "C3a_R", "C3b", "C4a", "C4b"]


# --- the E3/E14 flag rule (amendment of 2026-10-27) --------------------------------------------------
def _summary(change_pp):
    convs = ["C0", "C1", "C3a", "C3a_R", "C3b", "C4a", "C4b"]
    rows = [{"convention": c, "stratum": st, "change_vs_c0_pp": (0.0 if c == "C0" else change_pp)}
            for c in convs for st in ("ALL", "(-6, 0]")]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("change_pp", [15.0, -15.0, 100.0])
def test_flag_rule_flags_c3a_and_c4_only_when_agreement_moves_more_than_10_pp(change_pp):
    s = _summary(change_pp)
    flags = pvr.finding_flags(s, threshold_pp=10.0)
    flagged = set(s.loc[flags, "convention"])
    assert flagged == {"C3a", "C4a", "C4b"}                    # C4a/C4b rule unchanged
    assert not flags[s["stratum"] != "ALL"].any()              # overall agreement only


@pytest.mark.parametrize("change_pp", [10.0, -10.0, 9.99, 0.0])
def test_flag_rule_does_not_flag_at_or_below_10_pp(change_pp):
    assert not pvr.finding_flags(_summary(change_pp), threshold_pp=10.0).any()


@pytest.mark.parametrize("conv", ["C3a_R", "C3b", "C0", "C1"])
def test_flag_rule_never_flags_c3a_r_c3b_c0_or_c1(conv):
    s = _summary(1000.0)
    assert not pvr.finding_flags(s, threshold_pp=10.0)[s["convention"] == conv].any()


# --- known behaviours kept as loud failures (amendment of 2026-10-31, U9 and U10) ---------------------
@pytest.mark.parametrize("conv", ["C3a", "C3a_R", "C3b"])
@pytest.mark.parametrize("sma,exc", [(0.0, ZeroDivisionError), (-1.0, ValueError)])
def test_c3_with_nonpositive_semi_major_axis_stays_a_loud_failure(conv, sma, exc):
    row = _row()
    row["t_j2k_sma"] = sma
    with pytest.raises(exc):
        pvr.apply_convention(row, conv, mu_km3_s2=398600.4418)


def test_c3a_with_zero_chaser_angular_momentum_stays_a_loud_failure():
    mu = 398600.4418
    row = _row(v=(30.0, 0.0, 0.0))
    row["relative_velocity_t"] = -math.sqrt(mu / row["t_j2k_sma"]) * 1000.0     # chaser velocity along R
    row.update({"relative_position_t": 0.0, "relative_position_n": 0.0})        # chaser position along R
    with pytest.raises(ValueError, match="N axis is undefined"):
        pvr.apply_convention(row, "C3a", mu_km3_s2=mu)


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


def _git_test(repo, *args):
    out = subprocess.run(["git", "-c", "user.name=pcv-test", "-c", "user.email=pcv-test@example.invalid", *args],
                         cwd=repo, check=True, capture_output=True)
    return out.stdout.decode("ascii", "replace").strip()


# The three headings the guard requires (amendment of 2026-10-27): the confirmation entry (d181408), the
# C3a designation amendment (as introduced in fb4f957) and the second-branch amendment (8d64986).
CONFIRMATION_LINE = "### 2026-10-24 — PRE-REGISTRATION CONFIRMED (Sidh): Pc engine independent validation — test copy"
DESIGNATION_LINE = ("### 2026-10-26 — AMENDMENT to the Pc validation pre-registration: C3a designated the "
                    "documented convention (Sidh)")
SECOND_BRANCH_LINE = ("### 2026-10-27 — AMENDMENT to the Pc validation pre-registration: C3a: second branch of "
                      "the sensitivity rule")
REQUIRED_LINES = (CONFIRMATION_LINE, DESIGNATION_LINE, SECOND_BRANCH_LINE)


def decisions_with(lines):
    return "# Decisions (synthetic test repository)" + "".join(chr(10) * 2 + ln + chr(10) + "text" for ln in lines) + chr(10)


DECISIONS_WITH_HEADING = decisions_with(REQUIRED_LINES)
DECISIONS_WITHOUT_HEADING = """# Decisions (synthetic test repository)

### 2026-10-24 — some other entry
"""


def make_prereg_repo(root, pcv, *, decisions=DECISIONS_WITH_HEADING):
    """A throwaway git repository holding a DECISIONS.md and the validation YAML, committed once."""
    root.mkdir(parents=True)
    _git_test(root, "init", "-q")
    (root / "DECISIONS.md").write_text(decisions, encoding="utf-8")
    yp = root / pvr.PCV_CONFIG_REPO_PATH
    yp.parent.mkdir(parents=True)
    yp.write_text(yaml.safe_dump(pcv), encoding="utf-8")
    _git_test(root, "add", "-A")
    _git_test(root, "commit", "-q", "-m", "pre-registration")
    return root, _git_test(root, "rev-parse", "HEAD"), yp


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

    def prereg(policy):
        pcv["agreement"]["missing_independent_value_policy"] = policy
        return make_prereg_repo(tmp_path / f"repo_{policy}", pcv)

    return load_config(), tables, prereg


def test_steps_run_end_to_end_on_synthetic_cdms_through_the_guard(synthetic_run):
    """The guard's PASS case, on synthetic data: every step runs with a valid pre-registration commit."""
    cfg, tables, prereg = synthetic_run
    open_repo, open_sha, open_yaml = prereg(None)
    set_repo, set_sha, set_yaml = prereg("exclude")
    for step in ("sample", "self-convergence", "gate"):
        pvr.run_step(cfg, step, open_yaml, prereg_commit=open_sha, repo=open_repo)
    with pytest.raises(pvr.OpenDecisionError):
        pvr.run_step(cfg, "compare", open_yaml, prereg_commit=open_sha, repo=open_repo)
    assert not (tables / "pcv_agreement.csv").exists()
    for step in ("compare", "m2", "conventions"):
        pvr.run_step(cfg, step, set_yaml, prereg_commit=set_sha, repo=set_repo)

    off = pd.read_csv(tables / "pcv_sample_official.csv")
    assert off["stratum"].value_counts().to_dict() == {
        "floor (== -30)": 3, "(-30, -15]": 3, "(-15, -10]": 3, "(-10, -6]": 3, "(-6, 0]": 5}
    assert len(pd.read_csv(tables / "pcv_sample_e3.csv")) == 10
    assert set(pd.read_csv(tables / "pcv_gate.csv")["set"]) == {"official", "e3"}
    agree = pd.read_csv(tables / "pcv_agreement.csv")
    assert len(agree) == 10 and set(agree["missing_policy"]) == {"exclude"}
    assert "classification" in agree.columns and (tables / "pcv_excluded.csv").exists()
    m2 = pd.read_csv(tables / "pcv_m2.csv")
    ind = pd.read_csv(tables / "pcv_independent.csv")
    assert len(m2) == 27 and set(m2["m2_seed"]).isdisjoint(set(ind["m3_seed"]))
    summ = pd.read_csv(tables / "pcv_convention_summary.csv")
    assert set(summ["convention"]) == {"C0", "C1", "C3a", "C3a_R", "C3b", "C4a", "C4b"}
    assert not summ.loc[summ["convention"].isin(["C0", "C1", "C3a_R", "C3b"]), "finding_flag_e3_e14"].any()
    assert len(pd.read_csv(tables / "pcv_c1_expectation.csv")) == 10
    for step in pvr.STEPS:
        prov = json.loads((tables / f"pcv_provenance_{step.replace('-', '_')}.json").read_text(encoding="utf-8"))
        assert len(prov["pc_validation_yaml_sha256"]) == 64
        assert prov["prereg_commit"] == (open_sha if step in ("sample", "self-convergence", "gate") else set_sha)


# --- step_m2 in the deep tail (amendment of 2026-10-31) ------------------------------------------------
def test_m2_step_completes_on_deep_tail_floor_like_rows_and_labels_them_a_priori(synthetic_run, monkeypatch):
    from kelvins_conformal import data as data_mod

    cfg, tables, prereg = synthetic_run
    official = data_mod.official_test_target_cdms(cfg)
    deep = official.index % 2 == 0                 # far beyond any Pc a double can hold
    official.loc[deep, ["relative_position_r", "relative_position_t", "relative_position_n"]] = [5.0e4, 5.0e4, -5.0e4]
    for obj in "tc":
        official.loc[deep, [f"{obj}_sigma_r", f"{obj}_sigma_t", f"{obj}_sigma_n"]] = 10.0
        official.loc[deep, [f"{obj}_ct_r", f"{obj}_cn_r", f"{obj}_cn_t"]] = 0.0
    monkeypatch.setattr(data_mod, "official_test_target_cdms", lambda cfg: official.copy())
    repo, sha, yp = prereg("exclude")
    for step in ("sample", "self-convergence", "gate", "m2"):
        pvr.run_step(cfg, step, yp, prereg_commit=sha, repo=repo)
    ind = pvr._read_csv(tables / "pcv_independent.csv")
    m2 = pvr._read_csv(tables / "pcv_m2.csv")
    assert len(m2) == len(ind) == 27
    both = ind.merge(m2, on=["set", "sample_index", "event_uid", "stratum"], validate="one_to_one")
    below = both[both["m1_log10"] < -324.0]
    assert len(below) > 0
    assert set(below["status"]) == {"not informative (a priori)"}
    assert (below["n"] == 0).all() and (below["hits"] == 0).all()


def test_m2_step_treats_a_minus_inf_m1_as_a_priori_and_a_nan_m1_as_no_prior(synthetic_run):
    cfg, tables, prereg = synthetic_run
    repo, sha, yp = prereg("exclude")
    for step in ("sample", "self-convergence", "gate"):
        pvr.run_step(cfg, step, yp, prereg_commit=sha, repo=repo)
    ind = pvr._read_csv(tables / "pcv_independent.csv")
    ind.loc[0, "m1_log10"] = -math.inf             # as the CSV round trip carries it
    ind.loc[1, "m1_log10"] = math.nan
    ind.to_csv(tables / "pcv_independent.csv", index=False)
    pvr.run_step(cfg, "m2", yp, prereg_commit=sha, repo=repo)
    m2 = pvr._read_csv(tables / "pcv_m2.csv")
    assert m2.loc[0, "status"] == "not informative (a priori)" and m2.loc[0, "n"] == 0
    assert m2.loc[1, "status"] != "not informative (a priori)" and m2.loc[1, "n"] > 0


# --- the pre-registration guard (Sidh, 2026-10-25) --------------------------------------------------
@pytest.fixture
def guard_repo(tmp_path):
    pcv, _ = pvr.load_pcv_config()
    return make_prereg_repo(tmp_path / "repo", pcv)


def test_guard_passes_for_a_valid_pre_registration_commit(guard_repo):
    repo, sha, yp = guard_repo
    got = pvr.verify_prereg(sha, yaml_path=yp, repo=repo)
    assert got["prereg_commit"] == sha and got["head"] == sha
    assert got["pc_validation_yaml_sha256"] == pvr.load_pcv_config(yp)[1]


def test_guard_refuses_without_a_prereg_commit(guard_repo, synthetic_run):
    repo, _, yp = guard_repo
    cfg, tables, _ = synthetic_run
    with pytest.raises(pvr.PreregGuardError, match="required"):
        pvr.verify_prereg(None, yaml_path=yp, repo=repo)
    with pytest.raises(pvr.PreregGuardError):
        pvr.run_step(cfg, "sample", yp, repo=repo)
    assert not list(tables.glob("pcv_*"))           # refused before anything was written


def test_guard_refuses_a_commit_that_is_not_an_ancestor_of_head(guard_repo):
    repo, base, yp = guard_repo
    _git_test(repo, "checkout", "-q", "-b", "side")
    (repo / "notes.txt").write_text("a commit off the side branch", encoding="utf-8")
    _git_test(repo, "add", "notes.txt")
    _git_test(repo, "commit", "-q", "-m", "side")
    side = _git_test(repo, "rev-parse", "HEAD")
    _git_test(repo, "checkout", "-q", base)          # HEAD back at the base: side is not its ancestor
    with pytest.raises(pvr.PreregGuardError, match="not an ancestor"):
        pvr.verify_prereg(side, yaml_path=yp, repo=repo)
    assert pvr.verify_prereg(base, yaml_path=yp, repo=repo)["prereg_commit"] == base


def test_guard_refuses_a_yaml_whose_hash_differs_from_the_recorded_one(guard_repo, tmp_path):
    repo, sha, yp = guard_repo
    edited = tmp_path / "edited.yaml"
    edited.write_bytes(yp.read_bytes().replace(b"rel_se_target: 0.005", b"rel_se_target: 0.01"))
    with pytest.raises(pvr.PreregGuardError, match="differs"):
        pvr.verify_prereg(sha, yaml_path=edited, repo=repo)
    yp.write_bytes(yp.read_bytes() + b"# an uncommitted edit" + bytes((10,)))
    with pytest.raises(pvr.PreregGuardError, match="differs"):
        pvr.verify_prereg(sha, repo=repo)


def test_guard_refuses_when_decisions_lacks_the_confirmation_heading(tmp_path):
    pcv, _ = pvr.load_pcv_config()
    repo, sha, yp = make_prereg_repo(tmp_path / "repo", pcv, decisions=DECISIONS_WITHOUT_HEADING)
    with pytest.raises(pvr.PreregGuardError, match="confirmation heading"):
        pvr.verify_prereg(sha, yaml_path=yp, repo=repo)


def test_guard_passes_with_the_confirmation_and_both_c3a_amendment_headings(tmp_path):
    pcv, _ = pvr.load_pcv_config()
    repo, sha, yp = make_prereg_repo(tmp_path / "repo", pcv, decisions=decisions_with(REQUIRED_LINES))
    assert pvr.verify_prereg(sha, yaml_path=yp, repo=repo)["prereg_commit"] == sha


@pytest.mark.parametrize("missing,match", [(CONFIRMATION_LINE, "confirmation heading"),
                                           (DESIGNATION_LINE, "C3a designation amendment"),
                                           (SECOND_BRANCH_LINE, "second-branch amendment")],
                         ids=["confirmation", "c3a-designation", "second-branch"])
def test_guard_refuses_when_any_required_heading_is_missing(tmp_path, missing, match):
    pcv, _ = pvr.load_pcv_config()
    lines = [ln for ln in REQUIRED_LINES if ln != missing]
    repo, sha, yp = make_prereg_repo(tmp_path / "repo", pcv, decisions=decisions_with(lines))
    with pytest.raises(pvr.PreregGuardError, match=match):
        pvr.verify_prereg(sha, yaml_path=yp, repo=repo)


def test_guard_amendment_headings_must_be_heading_lines_not_mentions(tmp_path):
    # Quoting a heading inside body text does not satisfy the guard; it must be the entry's own heading.
    pcv, _ = pvr.load_pcv_config()
    body = decisions_with([CONFIRMATION_LINE, DESIGNATION_LINE]) + "see " + SECOND_BRANCH_LINE[4:] + chr(10)
    repo, sha, yp = make_prereg_repo(tmp_path / "repo", pcv, decisions=body)
    with pytest.raises(pvr.PreregGuardError, match="second-branch amendment"):
        pvr.verify_prereg(sha, yaml_path=yp, repo=repo)


def test_the_required_amendment_headings_are_those_in_the_repository():
    # Guards against a typo that would make the guard refuse every real run.
    from kelvins_conformal.config import REPO_ROOT

    lines = {ln.rstrip() for ln in (REPO_ROOT / "DECISIONS.md").read_text(encoding="utf-8").splitlines()}
    assert DESIGNATION_LINE in lines and SECOND_BRANCH_LINE in lines
    assert pvr.C3A_DESIGNATION_HEADING == DESIGNATION_LINE
    assert pvr.C3A_SECOND_BRANCH_HEADING == SECOND_BRANCH_LINE
    got = subprocess.run(["git", "show", "fb4f957", "--", "DECISIONS.md"], cwd=REPO_ROOT, capture_output=True)
    if got.returncode == 0:                         # the designation heading as introduced in fb4f957
        assert ("+" + DESIGNATION_LINE) in got.stdout.decode("utf-8").splitlines()


def test_guard_refuses_an_unknown_commit(guard_repo):
    repo, _, yp = guard_repo
    with pytest.raises(pvr.PreregGuardError, match="not a commit"):
        pvr.verify_prereg("0" * 40, yaml_path=yp, repo=repo)


@pytest.mark.parametrize("step", ["sample", "self-convergence", "gate", "compare", "m2", "conventions"])
def test_cli_refuses_every_step_without_a_valid_prereg_commit(step):
    # Runs against the real repository but never with a valid commit, so the guard refuses before
    # any config, data or output directory is touched.
    from typer.testing import CliRunner

    from kelvins_conformal.cli import app

    runner = CliRunner()
    for extra in ([], ["--prereg-commit", "0" * 40]):
        res = runner.invoke(app, ["pc-validate", step, *extra])
        assert res.exit_code == 3, res.output
