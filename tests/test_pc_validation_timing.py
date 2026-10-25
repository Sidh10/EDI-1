"""Smoke test of the synthetic timing module (3e) with tiny budgets; no real data, no timing claims."""

from __future__ import annotations

import copy

from kelvins_conformal.models import pc_validation_runner as pvr
from kelvins_conformal.models import pc_validation_timing as pvt


def test_timing_measures_and_extrapolates_to_the_yaml_sample_sizes():
    pcv, _ = pvr.load_pcv_config()
    small = copy.deepcopy(pcv)
    small["m3"].update({"n_samples": 2_000, "n_escalated": 4_000, "chunk": 1_000})
    small["m2"].update({"chunk": 2_000, "cap": 8_000})
    t = pvt.measure(small, n_events=4)
    assert t["n_synthetic_events"] >= 1 and t["m2_chunks_at_cap"] == 4
    est = pvt.estimate(pcv, t)                      # the YAML's own sample sizes
    assert est["n_events"] == 4 * 30 + 150 + 100
    s = est["scenarios"]
    assert s["A_lower"]["s"] <= s["B_design"]["s"] <= s["C_worst"]["s"]
    assert est["range_hours"][0] <= est["range_hours"][1]
    assert all(v["hours_2x"] == 2.0 * v["hours_1x"] for v in s.values())
