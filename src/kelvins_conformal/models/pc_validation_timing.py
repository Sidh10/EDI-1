"""Wall-clock timing of the Pc validation methods on SYNTHETIC events, and a runtime estimate (3e).

Responsibility: measure, per event and at the pre-registered settings in
``config/experiments/pc_validation.yaml``, the cost of M1, M3 (the 1e6 run and the 1e7 escalation),
M2 (per 1e7 chunk, and one full run to the 1e8 cap) and the unchanged engine (1x and 2x grid), then
extrapolate to the YAML's sample sizes. No real event, real CDM or E3 row is read; nothing is
written to the tables directory. Serves the Pc validation study (Sidh, 2026-10-25, item 3e).

Run:  python -m kelvins_conformal.models.pc_validation_timing [--out path.json]

Extrapolation (stated in the output): the runner is single-process and sequential, so the total is the
sum of per-event costs over the sample (official-test 4 x per_stratum_n + all of (-6, 0], i.e. the
pre-registered 270; E3's 100). M3's cost depends only on n (not geometry); M2's cost is linear in
the number of 1e7 chunks it draws, and it always draws whole chunks. How many events escalate M3 or
run M2 depends on the real data and is NOT known, so three scenarios bound it, each also given at 2x
for machine variance.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import time

import numpy as np

from ..labelnoise import pc_foster as pf
from ..labelnoise import pc_independent as pi
from .pc_validation_runner import load_pcv_config

_KEYS = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")


def synthetic_rows(n: int, seed: int = 2026) -> list[dict]:
    """CDM-like rows with random geometry (metres, m/s), spanning shallow to deep-tail Pc."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        row = {"t_span": float(rng.uniform(2, 10)), "c_span": float(rng.uniform(2, 5))}
        scale = 10.0 ** rng.uniform(1.0, 3.3)                      # covariance scale, 10 m to 2 km
        for a in "rtn":
            row[f"relative_position_{a}"] = float(rng.normal(0.0, scale * rng.uniform(0.2, 8.0)))
            row[f"relative_velocity_{a}"] = float(rng.normal(0.0, 5000.0))
        for obj in "tc":
            for k in _KEYS[:3]:
                row[f"{obj}_{k}"] = float(scale * 10.0 ** rng.uniform(-1.0, 0.5))
            for k in _KEYS[3:]:
                row[f"{obj}_{k}"] = float(rng.uniform(-0.6, 0.6))
        rows.append(row)
    return rows


def _time(fn, reps: int = 1) -> float:
    best = math.inf
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def measure(pcv: dict, *, n_events: int = 40, full_m2_cap: bool = True) -> dict:
    """Per-event wall-clock seconds at the pre-registered settings, on synthetic events."""
    eng, m1c, m3c, m2c = pcv["engine"], pcv["m1"], pcv["m3"], pcv["m2"]
    nr, na, f = int(eng["n_radial"]), int(eng["n_angular"]), int(eng["refined_factor"])
    rows = [r for r in synthetic_rows(n_events) if pf.recompute_pc_for_row(r) is not None]
    geoms = [pi.geometry_from_row(r) for r in rows]

    eng1 = [_time(lambda r=r: pf.recompute_pc_for_row(r, n_radial=nr, n_angular=na)) for r in rows]
    eng2 = [_time(lambda r=r: pf.recompute_pc_for_row(r, n_radial=f * nr, n_angular=f * na)) for r in rows]
    m1_t, m1_l = [], []
    for g in geoms:
        t0 = time.perf_counter()
        res = pi.log10_pc_m1(g, epsrel=float(m1c["epsrel"]), limit=int(m1c["limit"]),
                             peak_grid_points=int(m1c["peak_grid_points"]))
        m1_t.append(time.perf_counter() - t0)
        m1_l.append(res.log10_pc)
    # M1's cost is bounded whatever the geometry: quad's 21-point Gauss-Kronrod rule on at most `limit`
    # subintervals, plus the peak-search grid, times the cost of one log-integrand evaluation.
    g0 = geoms[0]
    n_eval = 20_000
    t_eval = _time(lambda: [math.exp(pi._m1_log_integrand(0.1 + 1e-6 * k, g0)) for k in range(n_eval)],
                   reps=3) / n_eval
    m1_bound = (int(m1c["peak_grid_points"]) + 21 * int(m1c["limit"])) * t_eval
    m3_base = _time(lambda: pi.m3_estimate(g0, seed=1, n=int(m3c["n_samples"]), chunk=int(m3c["chunk"])), reps=3)
    m3_esc = _time(lambda: pi.m3_estimate(g0, seed=1, n=int(m3c["n_escalated"]), chunk=int(m3c["chunk"])), reps=2)
    # M2 on a geometry far below any hit, so no early stop: exactly one chunk, then the full cap.
    deep = pi.PlaneGeometry(mx=5000.0, my=0.0, sx=100.0, sy=50.0, hbr=5.0)
    chunk, cap = int(m2c["chunk"]), int(m2c["cap"])
    m2_chunk = _time(lambda: pi.pc_m2(deep, seed=1, chunk=chunk, cap=chunk, min_hits=int(m2c["min_hits_target"]),
                                      max_rel_se=float(m2c["max_rel_se_counted"])), reps=2)
    m2_cap = (_time(lambda: pi.pc_m2(deep, seed=1, chunk=chunk, cap=cap, min_hits=int(m2c["min_hits_target"]),
                                     max_rel_se=float(m2c["max_rel_se_counted"])))
              if full_m2_cap else math.nan)
    q = lambda xs, p: float(np.percentile(xs, p))  # noqa: E731
    return {
        "n_synthetic_events": len(rows),
        "synthetic_m1_log10_pc_range": [float(np.nanmin(m1_l)), float(np.nanmax(m1_l))],
        "engine_1x_s": {"median": q(eng1, 50), "max": max(eng1)},
        "engine_2x_s": {"median": q(eng2, 50), "max": max(eng2)},
        "m1_s": {"median": q(m1_t, 50), "p95": q(m1_t, 95), "max": max(m1_t), "bound": m1_bound},
        "m1_seconds_per_integrand_eval": t_eval,
        "m3_1e6_s": m3_base,
        "m3_1e7_s": m3_esc,
        "m2_per_chunk_s": m2_chunk,
        "m2_full_cap_s": m2_cap,
        "m2_chunks_at_cap": math.ceil(cap / chunk),
    }


def estimate(pcv: dict, t: dict) -> dict:
    """Total runtime for the YAML sample sizes under three scenarios, each at 1x and 2x."""
    so = pcv["sample"]["official_test"]
    n_off = 4 * int(so["per_stratum_n"]) + 150         # all 150 of (-6, 0] (confirmed population size)
    n_e3 = 100 if pcv["sample"].get("e3_sample") else 0
    n = n_off + n_e3
    n_high = 150 + (20 if n_e3 else 0)                  # E3 drew 100 equally over 5 strata: 20 in (-6, 0]
    n_conv = len(pcv["conventions"])
    chunks_cap = t["m2_chunks_at_cap"]
    per_chunk = t["m2_per_chunk_s"]
    if math.isfinite(t["m2_full_cap_s"]):
        per_chunk = max(per_chunk, t["m2_full_cap_s"] / chunks_cap)

    def total(m1_key, esc_frac, m2_events, m2_chunks):
        base = n * (t["engine_1x_s"]["median"] + t["engine_2x_s"]["median"]     # self-convergence
                    + t["m1_s"][m1_key] + t["m3_1e6_s"] + esc_frac * t["m3_1e7_s"]
                    + n_conv * t["engine_1x_s"]["median"])                    # conventions
        return base + m2_events * m2_chunks * per_chunk

    scen = {
        "A_lower": {"what": "no M3 escalation; M2 runs only for the (-6, 0] events and stops after one chunk",
                    "s": total("median", 0.0, n_high, 1)},
        "B_design": {"what": "every event escalates M3 to 1e7; M2 runs for the (-6, 0] events, each to the 1e8 cap",
                     "s": total("p95", 1.0, n_high, chunks_cap)},
        "C_worst": {"what": ("every event escalates M3; M2 runs for EVERY event to the cap; M1 at its hard "
                             "bound (peak grid + 21 x limit evaluations)"),
                    "s": total("bound", 1.0, n, chunks_cap)},
    }
    for v in scen.values():
        v["hours_1x"] = v["s"] / 3600.0
        v["hours_2x"] = 2.0 * v["s"] / 3600.0
    return {"n_events": n, "n_official": n_off, "n_e3": n_e3, "n_high_risk_assumed": n_high,
            "n_conventions": n_conv, "m2_seconds_per_chunk_used": per_chunk, "scenarios": scen,
            "range_hours": [scen["A_lower"]["hours_1x"], scen["C_worst"]["hours_2x"]]}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=None, help="optional JSON output path (not the tables directory)")
    ap.add_argument("--n-events", type=int, default=40)
    args = ap.parse_args(argv)
    pcv, digest = load_pcv_config()
    t = measure(pcv, n_events=args.n_events)
    est = estimate(pcv, t)
    rec = {"pc_validation_yaml_sha256": digest, "machine": {"platform": platform.platform(),
           "processor": platform.processor(), "python": platform.python_version()},
           "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "timings_s": t, "estimate": est}
    print(json.dumps(rec, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2)


if __name__ == "__main__":
    main()
