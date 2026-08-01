"""Toy-geometry unit tests for the Foster Pc computation (CLAUDE.md §4).

The statistical core is validated against analytically known cases BEFORE it is
run on real data (E3). Cases:
  1. Isotropic covariance, zero miss -> exact Rayleigh CDF.
  2. Isotropic covariance, offset miss, small HBR -> first-order point-mass value.
  3. Limits and monotonicity (HBR -> 0, HBR -> inf, monotone increasing in HBR).
  4. Covariance-assembly + B-plane-projection sanity (isotropic 3D -> isotropic 2D).
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.labelnoise import pc_foster as pf


@pytest.mark.parametrize("sigma,hbr", [(100.0, 5.0), (250.0, 50.0), (1000.0, 200.0)])
def test_isotropic_zero_miss_matches_rayleigh(sigma, hbr):
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    numeric = pf.pc_on_disk(np.array([0.0, 0.0]), cov2d, hbr, n_radial=400, n_angular=720)
    exact = pf.analytic_pc_isotropic_zero_miss(sigma, hbr)
    assert numeric == pytest.approx(exact, rel=1e-3, abs=1e-6)


@pytest.mark.parametrize("miss", [0.0, 50.0, 150.0, 300.0])
def test_isotropic_small_hbr_matches_point_mass(miss):
    sigma = 500.0
    hbr = 2.0  # HBR << sigma -> first-order approximation is tight
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    numeric = pf.pc_on_disk(np.array([miss, 0.0]), cov2d, hbr, n_radial=300, n_angular=720)
    approx = pf.analytic_pc_isotropic_point_mass(sigma, hbr, miss)
    assert numeric == pytest.approx(approx, rel=2e-3, abs=1e-9)


def test_pc_limits():
    sigma = 300.0
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    # HBR -> 0 gives Pc -> 0.
    assert pf.pc_on_disk(np.array([10.0, 0.0]), cov2d, 0.0) == 0.0
    # Very large HBR captures essentially all mass -> Pc -> 1.
    big = pf.pc_on_disk(np.array([0.0, 0.0]), cov2d, 10_000.0, n_radial=500, n_angular=360)
    assert big == pytest.approx(1.0, abs=1e-3)


def test_pc_monotonic_in_hbr():
    sigma = 400.0
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    miss = np.array([120.0, 0.0])
    hbrs = [1.0, 5.0, 20.0, 50.0, 100.0, 200.0]
    vals = [pf.pc_on_disk(miss, cov2d, h, n_radial=300, n_angular=480) for h in hbrs]
    assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:], strict=False))


def test_pc_is_a_probability():
    rng = np.random.default_rng(0)
    for _ in range(20):
        s1, s2 = rng.uniform(50, 1000, size=2)
        cov2d = np.array([[s1**2, 0.0], [0.0, s2**2]])
        miss = rng.uniform(-500, 500, size=2)
        hbr = rng.uniform(1, 300)
        pc = pf.pc_on_disk(miss, cov2d, hbr, n_radial=150, n_angular=240)
        assert 0.0 <= pc <= 1.0


def test_covariance_rtn_is_symmetric_psd():
    cov = pf.position_covariance_rtn(120.0, 300.0, 80.0, 0.2, -0.1, 0.05)
    assert np.allclose(cov, cov.T)
    assert np.all(np.linalg.eigvalsh(cov) > 0)


def test_bplane_projection_of_isotropic_cov_is_isotropic():
    # Isotropic 3D covariance must project to isotropic 2D regardless of geometry.
    r_vec = np.array([100.0, 2000.0, -50.0])
    v_vec = np.array([-7000.0, 300.0, 10.0])
    proj = pf.bplane_projection(r_vec, v_vec)
    # Rows are orthonormal.
    assert np.allclose(proj @ proj.T, np.eye(2), atol=1e-12)
    sigma = 250.0
    cov3 = (sigma**2) * np.eye(3)
    cov2d = proj @ cov3 @ proj.T
    assert np.allclose(cov2d, (sigma**2) * np.eye(2), atol=1e-9)


def test_bplane_miss_magnitude_equals_perpendicular_component():
    r_vec = np.array([300.0, 400.0, 0.0])
    v_vec = np.array([0.0, 0.0, 1000.0])  # velocity along n -> plane is r-t plane
    proj = pf.bplane_projection(r_vec, v_vec)
    miss_xy = proj @ r_vec
    # Component of r perpendicular to v is the full r here (r has no n-component).
    assert np.linalg.norm(miss_xy) == pytest.approx(np.linalg.norm(r_vec), rel=1e-9)


def test_recompute_returns_none_on_missing_field():
    row = dict.fromkeys(pf.REQUIRED_FIELDS, 1.0)
    del row["c_span"]
    assert pf.recompute_pc_for_row(row) is None


def test_recompute_end_to_end_on_synthetic_row():
    # Construct a physically sane row and verify a finite, in-range Pc.
    row = dict.fromkeys(pf.REQUIRED_FIELDS, 0.0)
    row.update(
        relative_position_r=200.0, relative_position_t=50.0, relative_position_n=0.0,
        relative_velocity_r=0.0, relative_velocity_t=0.0, relative_velocity_n=7500.0,
        t_sigma_r=150.0, t_sigma_t=400.0, t_sigma_n=120.0,
        c_sigma_r=200.0, c_sigma_t=600.0, c_sigma_n=180.0,
        t_span=5.0, c_span=2.0,
    )
    res = pf.recompute_pc_for_row(row)
    assert res is not None
    assert 0.0 <= res.pc <= 1.0
    assert res.hbr == pytest.approx(3.5)
    assert np.isfinite(res.log10_pc)
    # miss magnitude here: r perpendicular to v (v along n) -> sqrt(200^2+50^2).
    assert res.miss_distance_2d == pytest.approx(np.hypot(200.0, 50.0), rel=1e-9)
