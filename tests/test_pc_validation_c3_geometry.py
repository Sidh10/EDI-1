"""C3 geometry: the code's chaser-to-target RTN rotation against the exact rotation between two RTN frames.

Synthetic orbits only (no real event or CDM). Each case puts a target and a chaser on orbits of known
inclination and RAAN in an inertial frame, at a common position on the line where their planes meet.
Each RTN frame is built by definition (R = r/|r|, N = r x v / |r x v|, T = N x R). The exact rotation is
A_t^T A_c, the chaser's RTN axes in target-RTN components, which is what ``c3_rotation`` approximates
from the relative velocity and the circular speed sqrt(mu / a_t).

* Exactly circular orbits at a common position: the code must match to 1e-6 (C3a with the relative
  velocity read as chaser - target, and C3b with it read as target - chaser).
* Variants that break the circular-orbit premise (eccentric chaser; eccentric target; a 1 km offset
  between the two positions): the deviation is REPORTED, with no pass/fail.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kelvins_conformal.models import pc_validation_runner as pvr

MU = 398600.4418          # km^3/s^2, config/experiments/pc_validation.yaml constants.mu_earth_km3_s2
A_KM = 7000.0
KEYS = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")
CHASER_COV = (80.0, 900.0, 60.0, -0.5, 0.25, 0.1)

# (inclination_t, RAAN_t, inclination_c, RAAN_c) in degrees
CASES = [
    (51.6, 30.0, 97.8, 75.0),     # large crossing angle
    (98.2, 10.0, 98.7, 189.0),    # near-polar, RAAN difference about 180 deg (near head-on)
    (0.1, 0.0, 45.0, 120.0),      # near-equatorial target
    (53.0, 200.0, 53.2, 201.0),   # small crossing angle
]


def plane_normal(inc_deg: float, raan_deg: float) -> np.ndarray:
    i, o = math.radians(inc_deg), math.radians(raan_deg)
    return np.array([math.sin(i) * math.sin(o), -math.sin(i) * math.cos(o), math.cos(i)])


def rtn_axes(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Columns R, T, N in inertial components, by definition."""
    rr = r / np.linalg.norm(r)
    h = np.cross(r, v)
    nn = h / np.linalg.norm(h)
    tt = np.cross(nn, rr)
    return np.column_stack([rr, tt, nn])


def velocity(n_hat: np.ndarray, r_hat: np.ndarray, r_km: float, ecc: float = 0.0, nu_deg: float = 0.0):
    """Inertial velocity (km/s) at radius r_km on the orbit of normal n_hat, eccentricity ecc, true anomaly nu.

    Circular when ecc = 0. Returns (v, semi-major axis in km).
    """
    nu = math.radians(nu_deg)
    p = r_km * (1.0 + ecc * math.cos(nu))
    v_r = math.sqrt(MU / p) * ecc * math.sin(nu)
    v_theta = math.sqrt(MU / p) * (1.0 + ecc * math.cos(nu))
    return v_r * r_hat + v_theta * np.cross(n_hat, r_hat), p / (1.0 - ecc * ecc)


def build(case, *, ecc_c=0.0, nu_c=0.0, ecc_t=0.0, nu_t=0.0, offset_km=0.0):
    """(row for C3a, row for C3b, exact rotation, chaser covariance in chaser RTN)."""
    n_t, n_c = plane_normal(case[0], case[1]), plane_normal(case[2], case[3])
    r_hat = np.cross(n_t, n_c)
    r_hat /= np.linalg.norm(r_hat)
    r_t = A_KM * r_hat
    v_t, a_t = velocity(n_t, r_hat, A_KM, ecc_t, nu_t)
    # The chaser sits at the same point unless offset (along the target's N, i.e. out of plane).
    r_c = r_t + offset_km * n_t
    rc_hat = r_c / np.linalg.norm(r_c)
    v_c, _ = velocity(n_c, rc_hat, float(np.linalg.norm(r_c)), ecc_c, nu_c)
    a_mat_t, a_mat_c = rtn_axes(r_t, v_t), rtn_axes(r_c, v_c)
    exact = a_mat_t.T @ a_mat_c
    v_rel_m_s = a_mat_t.T @ (v_c - v_t) * 1000.0           # chaser - target, target RTN, m/s
    r_rel_m = a_mat_t.T @ (r_c - r_t) * 1000.0

    def row(sign):
        d = {f"relative_velocity_{a}": float(sign * x) for a, x in zip("rtn", v_rel_m_s, strict=True)}
        d.update({f"relative_position_{a}": float(sign * x) for a, x in zip("rtn", r_rel_m, strict=True)})
        d.update({f"c_{k}": x for k, x in zip(KEYS, CHASER_COV, strict=True)})
        d["t_j2k_sma"] = a_t
        return d

    sr, st, sn, ctr, cnr, cnt = CHASER_COV
    cov = np.array([[sr * sr, ctr * sr * st, cnr * sr * sn],
                    [ctr * sr * st, st * st, cnt * st * sn],
                    [cnr * sr * sn, cnt * st * sn, sn * sn]])
    return row(+1.0), row(-1.0), exact, cov


def cov_of(row):
    sr, st, sn, ctr, cnr, cnt = (row[f"c_{k}"] for k in KEYS)
    return np.array([[sr * sr, ctr * sr * st, cnr * sr * sn],
                     [ctr * sr * st, st * st, cnt * st * sn],
                     [cnr * sr * sn, cnt * st * sn, sn * sn]])


@pytest.mark.parametrize("case", CASES)
def test_c3_rotation_is_exact_for_circular_orbits_at_a_common_position(case):
    row_a, row_b, exact, cov = build(case)
    assert exact[0, 0] == pytest.approx(1.0, abs=1e-12)    # the exact rotation is about R
    for conv_id, row in (("C3a", row_a), ("C3b", row_b)):
        rot = pvr.c3_rotation(row, conv_id, mu_km3_s2=MU)
        assert np.max(np.abs(rot - exact)) <= 1e-6, conv_id
        new, scale = pvr.apply_convention(row, conv_id, mu_km3_s2=MU)
        assert scale == 1.0
        ref = exact @ cov @ exact.T
        assert np.max(np.abs(cov_of(new) - ref)) <= 1e-6 * np.max(np.abs(ref)), conv_id


def test_c3_reading_the_relative_velocity_with_the_wrong_sign_is_not_exact():
    # C3a applied to a target - chaser relative velocity must NOT reproduce the exact rotation
    # (guards against a test that would pass for either sign).
    _, row_b, exact, _ = build(CASES[0])
    assert np.max(np.abs(pvr.c3_rotation(row_b, "C3a", mu_km3_s2=MU) - exact)) > 1e-2


VARIANTS = [
    ("eccentric chaser, e = 0.01, nu = 60 deg", {"ecc_c": 0.01, "nu_c": 60.0}),
    ("eccentric chaser, e = 0.1, nu = 120 deg", {"ecc_c": 0.1, "nu_c": 120.0}),
    ("eccentric target, e = 0.01, nu = 60 deg", {"ecc_t": 0.01, "nu_t": 60.0}),
    ("eccentric target, e = 0.1, nu = 120 deg", {"ecc_t": 0.1, "nu_t": 120.0}),
    ("circular, chaser 1 km out of the target's plane", {"offset_km": 1.0}),
]


@pytest.mark.parametrize("label,kw", VARIANTS, ids=[v[0] for v in VARIANTS])
def test_c3_deviation_off_the_circular_premise_is_reported(label, kw, record_property):
    """REPORTED, no pass/fail: max |rot - exact| and the rotation-angle error, per geometry case."""
    worst = 0.0
    for case in CASES:
        row_a, _, exact, _ = build(case, **kw)
        rot = pvr.c3_rotation(row_a, "C3a", mu_km3_s2=MU)
        err = rot.T @ exact                                  # identity if the two agree
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(err) - 1.0) / 2.0))))
        dev = float(np.max(np.abs(rot - exact)))
        worst = max(worst, dev)
        print(f"[C3 deviation] {label} | case {case} | max|rot - exact| = {dev:.3e} | angle error = {ang:.3e} deg")
    record_property("c3_max_abs_deviation", worst)
    assert math.isfinite(worst)
