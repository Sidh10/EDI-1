"""Analytic unit tests for the independent Pc methods (Pc validation, REVIEWER_CHECKLIST RP4).

Pre-registered in DECISIONS.md (2026-10-24 confirmation entry): the independent methods are tested
on analytic cases BEFORE they touch any real event. Every reference value here is computed in this
file, by a route that shares no code with the module under test or with the engine:

  1. isotropic, zero offset          -> exact Rayleigh CDF, 1 - exp(-R^2 / (2 sigma^2));
  2. isotropic, with offset          -> noncentral chi-square CDF, ncx2.cdf(R^2/s^2, 2, d^2/s^2);
  3. tiny-HBR limit                  -> point mass, pi R^2 * (2D Gaussian density at the origin);
  4. deep-tail isotropic             -> radial Bessel form of the same integral, in log space;
  5. anisotropic synthetic cases     -> M1 and M3 must agree within the pre-registered gate
                                        (median |dlog10| <= 0.005).

No real event, CDM or E3 sample is used.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import integrate, special, stats

from kelvins_conformal.labelnoise import pc_independent as pi

LN10 = math.log(10.0)
GATE = 0.005  # config/experiments/pc_validation.yaml gate_m1_m3.max_median_abs_dlog10


# --- independent analytic references ------------------------------------------------------------
def rayleigh_log10(sigma, hbr):
    return math.log10(-math.expm1(-(hbr**2) / (2.0 * sigma**2)))


def ncx2_log10(sigma, d, hbr):
    return math.log10(stats.ncx2.cdf(hbr**2 / sigma**2, 2, d**2 / sigma**2))


def point_mass_log10(mx, my, sx, sy, hbr):
    log_density = -0.5 * ((mx / sx) ** 2 + (my / sy) ** 2) - math.log(2.0 * math.pi * sx * sy)
    return (math.log(math.pi * hbr**2) + log_density) / LN10


def bessel_radial_log10(sigma, d, hbr):
    """Isotropic offset Pc via the radial form, in log space (valid deep in the tail).

    Pc = int_0^R (r / s^2) exp(-(r - d)^2 / (2 s^2)) * i0e(r d / s^2) dr, where i0e is the
    exponentially scaled modified Bessel function; the peak of the log integrand is factored out.
    """
    def logf(r):
        return math.log(r / sigma**2) - (r - d) ** 2 / (2 * sigma**2) + math.log(special.i0e(r * d / sigma**2))

    grid = np.linspace(hbr * 1e-6, hbr, 4001)
    peak = max(logf(r) for r in grid)
    val, _ = integrate.quad(lambda r: math.exp(logf(r) - peak) if r > 0 else 0.0, 0.0, hbr,
                            epsabs=0.0, epsrel=1e-12, limit=500)
    return (peak + math.log(val)) / LN10


def iso(mx, my, sigma, hbr):
    return pi.PlaneGeometry(mx=mx, my=my, sx=sigma, sy=sigma, hbr=hbr)


# --- M1: deterministic 1D reduction --------------------------------------------------------------
@pytest.mark.parametrize("sigma,hbr", [(100.0, 5.0), (250.0, 50.0), (1000.0, 200.0), (10.0, 30.0)])
def test_m1_isotropic_zero_offset_matches_rayleigh(sigma, hbr):
    r = pi.log10_pc_m1(iso(0.0, 0.0, sigma, hbr))
    assert r.converged
    assert r.log10_pc == pytest.approx(rayleigh_log10(sigma, hbr), abs=1e-9)


@pytest.mark.parametrize("sigma,d,hbr", [(100.0, 50.0, 10.0), (100.0, 300.0, 20.0), (500.0, 1500.0, 30.0),
                                         (50.0, 20.0, 60.0)])
def test_m1_isotropic_offset_matches_noncentral_chi_square(sigma, d, hbr):
    # The offset is placed off-axis so the principal-frame rotation is exercised too.
    g = iso(d / math.sqrt(2.0), d / math.sqrt(2.0), sigma, hbr)
    r = pi.log10_pc_m1(g)
    assert r.converged
    assert r.log10_pc == pytest.approx(ncx2_log10(sigma, d, hbr), abs=1e-8)


@pytest.mark.parametrize("mx,my,sx,sy", [(0.0, 0.0, 100.0, 40.0), (300.0, -120.0, 200.0, 50.0),
                                         (30.0, 0.0, 1.0, 1.0)])
def test_m1_tiny_hbr_limit_matches_point_mass(mx, my, sx, sy):
    hbr = 1e-5 * min(sx, sy)
    r = pi.log10_pc_m1(pi.PlaneGeometry(mx=mx, my=my, sx=sx, sy=sy, hbr=hbr))
    assert r.converged
    assert r.log10_pc == pytest.approx(point_mass_log10(mx, my, sx, sy, hbr), abs=1e-6)


# Every case has sigma != 1, so a normalisation error in sigma cannot hide (log sigma = 0 at sigma = 1).
# (3, 60, 1.5) is the original (1, 20, 0.5) case rescaled: the same d/sigma and R/sigma, so the same Pc.
@pytest.mark.parametrize("sigma,d,hbr", [(3.0, 60.0, 1.5), (100.0, 4000.0, 20.0), (25.0, 900.0, 5.0)])
def test_m1_deep_tail_matches_bessel_radial_form(sigma, d, hbr):
    r = pi.log10_pc_m1(iso(d, 0.0, sigma, hbr))
    assert r.converged
    ref = bessel_radial_log10(sigma, d, hbr)
    assert ref < -50.0  # genuinely deep: double precision would underflow outside log space
    assert r.log10_pc == pytest.approx(ref, abs=1e-6)


def test_m1_reports_nonconvergence_as_event_failure(monkeypatch):
    """Pre-registered rule (item 6): quad's ier != 0 is an event-level failure, not an exception."""
    def fake_quad(*args, **kwargs):
        return 1.0, 1.0, {"neval": 21}, 1, "simulated non-convergence"
    monkeypatch.setattr(pi.integrate, "quad", fake_quad)
    r = pi.log10_pc_m1(iso(0.0, 0.0, 100.0, 10.0))
    assert not r.converged and r.ier == 1 and math.isnan(r.log10_pc)


# --- M3: uniform-in-disk Monte Carlo ------------------------------------------------------------
@pytest.mark.parametrize("sigma,hbr", [(100.0, 20.0), (50.0, 80.0)])
def test_m3_isotropic_zero_offset_matches_rayleigh_within_its_se(sigma, hbr):
    est = pi.m3_estimate(iso(0.0, 0.0, sigma, hbr), seed=7, n=200_000, chunk=50_000)
    tol = 4.0 * est.rel_se / LN10
    assert est.log10_pc == pytest.approx(rayleigh_log10(sigma, hbr), abs=tol)


def test_m3_offset_matches_noncentral_chi_square_within_its_se():
    sigma, d, hbr = 100.0, 250.0, 30.0
    est = pi.m3_estimate(iso(d, 0.0, sigma, hbr), seed=11, n=200_000, chunk=50_000)
    assert est.log10_pc == pytest.approx(ncx2_log10(sigma, d, hbr), abs=4.0 * est.rel_se / LN10)


def test_m3_is_deterministic_given_seed_and_chunk():
    g = pi.PlaneGeometry(mx=120.0, my=-40.0, sx=80.0, sy=30.0, hbr=15.0)
    a = pi.m3_estimate(g, seed=3, n=100_000, chunk=25_000)
    b = pi.m3_estimate(g, seed=3, n=100_000, chunk=25_000)
    assert a == b


def test_m3_escalates_once_then_reports_not_informative():
    """Pre-registered rule (item 7): target 0.5% relative SE, one rerun at n_escalated, else not informative."""
    # A wide disk over a steep density: few samples carry the mass, so the relative SE is large.
    g = pi.PlaneGeometry(mx=400.0, my=0.0, sx=20.0, sy=20.0, hbr=400.0)
    r = pi.log10_pc_m3(g, seed=5, n_samples=2_000, n_escalated=4_000, rel_se_target=0.005, chunk=1_000)
    assert r.escalated and r.n_used == 4_000 and not r.informative
    easy = pi.log10_pc_m3(iso(0.0, 0.0, 100.0, 10.0), seed=5, n_samples=200_000, n_escalated=400_000,
                          rel_se_target=0.005, chunk=50_000)
    assert easy.informative and not easy.escalated and easy.n_used == 200_000


# --- M2: plain Monte Carlo on the encounter plane ----------------------------------------------
def test_m2_isotropic_matches_rayleigh_within_three_se():
    sigma, hbr = 100.0, 20.0
    r = pi.pc_m2(iso(0.0, 0.0, sigma, hbr), seed=1, chunk=200_000, cap=5_000_000, min_hits=100,
                 max_rel_se=0.10)
    assert r.informative and r.hits >= 100
    assert pi.m2_consistent(r, rayleigh_log10(sigma, hbr), n_se=3.0)


def test_m2_a_priori_not_informative_when_cap_cannot_reach_100_hits():
    r = pi.pc_m2(iso(0.0, 0.0, 100.0, 10.0), seed=1, chunk=1_000, cap=100_000, min_hits=100,
                 max_rel_se=0.10, prior_log10_pc=-12.0)
    assert not r.informative and r.n == 0 and r.status == "not informative (a priori)"
    assert pi.m2_consistent(r, -12.0, n_se=3.0) is None


def test_m2_cap_reached_without_enough_hits_is_not_informative():
    g = iso(500.0, 0.0, 100.0, 10.0)  # Pc ~ 1e-8: unreachable with a 1e5 cap
    r = pi.pc_m2(g, seed=2, chunk=50_000, cap=100_000, min_hits=100, max_rel_se=0.10)
    assert not r.informative and r.n == 100_000


# --- M1 vs M3 on anisotropic synthetic cases: the pre-registered gate ---------------------------
ANISO = [
    (0.0, 0.0, 100.0, 30.0, 10.0),
    (200.0, 50.0, 150.0, 40.0, 20.0),
    (500.0, -300.0, 200.0, 60.0, 15.0),
    (50.0, 0.0, 10.0, 3.0, 5.0),
    (0.0, 300.0, 40.0, 400.0, 25.0),
    (600.0, 0.0, 100.0, 100.0, 20.0),
]


def test_m1_and_m3_agree_within_pre_registered_gate_on_anisotropic_cases():
    deltas = []
    for k, (mx, my, sx, sy, hbr) in enumerate(ANISO):
        g = pi.PlaneGeometry(mx=mx, my=my, sx=sx, sy=sy, hbr=hbr)
        m1 = pi.log10_pc_m1(g)
        m3 = pi.m3_estimate(g, seed=100 + k, n=1_000_000, chunk=250_000)
        assert m1.converged
        deltas.append(abs(m1.log10_pc - m3.log10_pc))
    assert float(np.median(deltas)) <= GATE
    assert max(deltas) <= 0.02


# --- independent input assembly -----------------------------------------------------------------
def _row(r, v, t=(30.0, 400.0, 20.0, 0.3, -0.2, 0.4), c=(80.0, 900.0, 60.0, -0.5, 0.25, 0.1),
         spans=(5.0, 2.0)):
    keys = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")
    row = {f"relative_position_{a}": x for a, x in zip("rtn", r, strict=False)}
    row.update({f"relative_velocity_{a}": x for a, x in zip("rtn", v, strict=False)})
    row.update({f"t_{k}": x for k, x in zip(keys, t, strict=False)})
    row.update({f"c_{k}": x for k, x in zip(keys, c, strict=False)})
    row["t_span"], row["c_span"] = spans
    return row


def _rtn(sr, st, sn, ctr, cnr, cnt):
    """Reference RTN covariance written out element by element (independent of the module)."""
    return np.array([[sr * sr, ctr * sr * st, cnr * sr * sn],
                     [ctr * sr * st, st * st, cnt * st * sn],
                     [cnr * sr * sn, cnt * st * sn, sn * sn]])


def test_assembly_projects_onto_plane_normal_to_relative_velocity():
    """v along T, r in the R-N plane: the encounter plane IS the R-N plane, so the projected
    covariance's eigenvalues and the miss's Mahalanobis norm must equal the R-N block's."""
    row = _row(r=(100.0, 0.0, 50.0), v=(0.0, 7000.0, 0.0))
    g = pi.geometry_from_row(row)
    keys = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")
    C = _rtn(*[row[f"t_{k}"] for k in keys]) + _rtn(*[row[f"c_{k}"] for k in keys])
    block = C[np.ix_([0, 2], [0, 2])]
    ev = np.sort(np.linalg.eigvalsh(block))
    assert sorted([g.sx**2, g.sy**2]) == pytest.approx(list(ev), rel=1e-12)
    rn = np.array([100.0, 50.0])
    maha_ref = float(rn @ np.linalg.solve(block, rn))
    assert (g.mx / g.sx) ** 2 + (g.my / g.sy) ** 2 == pytest.approx(maha_ref, rel=1e-10)
    assert math.hypot(g.mx, g.my) == pytest.approx(math.hypot(100.0, 50.0), rel=1e-12)
    assert g.hbr == pytest.approx(3.5)  # (t_span + c_span) / 2, convention C0


def test_assembly_handles_miss_parallel_to_relative_velocity():
    g = pi.geometry_from_row(_row(r=(0.0, 10.0, 0.0), v=(0.0, 7000.0, 0.0)))
    assert math.hypot(g.mx, g.my) == pytest.approx(0.0, abs=1e-9)


def test_principal_axes_closed_form_matches_eigh():
    rng = np.random.default_rng(0)
    for _ in range(50):
        a = rng.normal(size=(2, 2))
        c2 = a @ a.T + 0.1 * np.eye(2)
        lam1, lam2, cos_p, sin_p = pi.principal_axes_2x2(c2)
        assert sorted([lam1, lam2]) == pytest.approx(sorted(np.linalg.eigvalsh(c2)), rel=1e-10)
        vec = np.array([cos_p, sin_p])
        assert c2 @ vec == pytest.approx(lam1 * vec, rel=1e-8, abs=1e-12)
