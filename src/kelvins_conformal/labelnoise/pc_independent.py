"""Independent collision-probability methods for validating the Pc engine (REVIEWER_CHECKLIST RP4).

Purpose: compute the same 2D encounter-plane collision probability as ``pc_foster`` by routes that
share NO code with it, so a disagreement can be attributed (DECISIONS.md, 2026-10-24 confirmation of
the Pc validation pre-registration). Serves the Pc engine validation study; not an EXPERIMENT_PLAN
stage.

Inputs:  one CDM row (dict of column -> value) or an encounter-plane geometry.
Outputs: log10 Pc with method-specific diagnostics.

Methods (all in the covariance's principal-axis frame of the encounter plane):
  * Independent input assembly (convention C0, the same convention as the engine, written
    separately): RTN position covariances from sigmas and correlations, summed; encounter-plane basis
    built from the relative velocity, then the miss direction, then their cross product; closed-form
    2x2 principal axes (no ``eigh``).
  * M1 — deterministic 1D reduction. With the disk |x|^2 + |y|^2 <= R^2 and axes-aligned Gaussian
    N((mx, my), diag(sx^2, sy^2)),
        Pc = integral_{-R}^{R} phi((x - mx)/sx)/sx * [Phi((h(x) - my)/sy) - Phi((-h(x) - my)/sy)] dx,
    with h(x) = sqrt(R^2 - x^2). Substituting x = R sin t removes the endpoint singularity. The inner
    probability difference is evaluated in log space with ``log_ndtr``; the outer integral uses
    adaptive Gauss-Kronrod (``scipy.integrate.quad``) on the peak-scaled integrand. Valid at every
    depth. Non-convergence (quad ier != 0) is an event-level failure, never an exception and never
    retried with looser settings (pre-registration item 6).
  * M3 — uniform-in-disk Monte Carlo of the density in log space:
        log Pc = log(pi R^2) + log mean_i f(u_i),   u_i ~ Uniform(disk),
    with a relative standard error from the sample variance (pre-registration item 7).
  * M2 — plain Monte Carlo: sample N((mx, my), diag(sx^2, sy^2)) and count hits in the disk;
    counted only where the relative SE is <= 10%, judged within 3 SE in log10 (item 8).

References: Foster & Estes (1992) for the 2D encounter-plane formulation; the M1 reduction is the
standard one-dimensional form of the same Gaussian-over-disk integral (e.g. Alfano 2005).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import integrate, special

LN10 = math.log(10.0)
_LOG_2PI = math.log(2.0 * math.pi)


# --- geometry ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PlaneGeometry:
    """Encounter-plane problem in the covariance's principal frame (metres)."""

    mx: float     # miss component along the first principal axis
    my: float     # miss component along the second principal axis
    sx: float     # standard deviation along the first principal axis
    sy: float     # standard deviation along the second principal axis
    hbr: float    # hard-body radius


def rtn_position_covariance(sig_r: float, sig_t: float, sig_n: float,
                            rho_tr: float, rho_nr: float, rho_nt: float) -> np.ndarray:
    """3x3 position covariance in [R, T, N] order from sigmas and correlations (CDM x_ct_r, x_cn_r, x_cn_t)."""
    s = np.array([sig_r, sig_t, sig_n], dtype=float)
    corr = np.array([[1.0, rho_tr, rho_nr],
                     [rho_tr, 1.0, rho_nt],
                     [rho_nr, rho_nt, 1.0]], dtype=float)
    return corr * np.outer(s, s)


def encounter_basis(r_vec: np.ndarray, v_vec: np.ndarray) -> np.ndarray:
    """2x3 matrix whose rows span the plane normal to the relative velocity.

    Row 0 is the unit miss direction (the component of r normal to v); row 1 completes the
    right-handed set with the velocity direction. If r has no normal component, row 0 is built from
    the coordinate axis least aligned with v.
    """
    v = np.asarray(v_vec, dtype=float)
    vn = float(np.sqrt(v @ v))
    if vn == 0.0:
        raise ValueError("zero relative velocity: encounter plane undefined")
    ez = v / vn
    r = np.asarray(r_vec, dtype=float)
    r_perp = r - (r @ ez) * ez
    norm = float(np.sqrt(r_perp @ r_perp))
    if norm <= 1e-12 * max(1.0, float(np.sqrt(r @ r))):
        axis = np.eye(3)[int(np.argmin(np.abs(ez)))]
        r_perp = axis - (axis @ ez) * ez
        norm = float(np.sqrt(r_perp @ r_perp))
    ex = r_perp / norm
    ey = np.cross(ez, ex)
    return np.vstack([ex, ey])


def principal_axes_2x2(c2: np.ndarray) -> tuple[float, float, float, float]:
    """Closed-form eigen-decomposition of a symmetric 2x2: (lam_major, lam_minor, cos phi, sin phi).

    (cos phi, sin phi) is the unit eigenvector of the major eigenvalue.
    """
    a, b, c = float(c2[0, 0]), float(c2[0, 1]), float(c2[1, 1])
    mean = 0.5 * (a + c)
    rad = math.hypot(0.5 * (a - c), b)
    phi = 0.5 * math.atan2(2.0 * b, a - c)
    return mean + rad, mean - rad, math.cos(phi), math.sin(phi)


def plane_geometry(miss_xy: np.ndarray, cov2d: np.ndarray, hbr: float) -> PlaneGeometry:
    """Rotate an encounter-plane miss and covariance into the covariance's principal frame."""
    lam1, lam2, cp, sp = principal_axes_2x2(cov2d)
    if not (lam2 > 0.0):
        raise ValueError(f"2D covariance is not positive definite: eigenvalues {lam1}, {lam2}")
    m0, m1 = float(miss_xy[0]), float(miss_xy[1])
    return PlaneGeometry(mx=cp * m0 + sp * m1, my=-sp * m0 + cp * m1,
                         sx=math.sqrt(lam1), sy=math.sqrt(lam2), hbr=float(hbr))


_COV_KEYS = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")


def geometry_from_row(row: dict) -> PlaneGeometry:
    """Convention C0, assembled independently of the engine: covariances summed, HBR = mean span."""
    r = np.array([float(row[f"relative_position_{a}"]) for a in "rtn"])
    v = np.array([float(row[f"relative_velocity_{a}"]) for a in "rtn"])
    cov = (rtn_position_covariance(*[float(row[f"t_{k}"]) for k in _COV_KEYS])
           + rtn_position_covariance(*[float(row[f"c_{k}"]) for k in _COV_KEYS]))
    basis = encounter_basis(r, v)
    hbr = 0.5 * (float(row["t_span"]) + float(row["c_span"]))
    return plane_geometry(basis @ r, basis @ cov @ basis.T, hbr)


# --- log-space helpers ---------------------------------------------------------------------------
def _log1mexp(x: float) -> float:
    """log(1 - exp(x)) for x <= 0, accurate at both ends."""
    if x >= 0.0:
        return -math.inf
    if x > -math.log(2.0):
        return math.log(-math.expm1(x))
    return math.log1p(-math.exp(x))


def _log_ndtr_diff(a: float, b: float) -> float:
    """log(Phi(b) - Phi(a)) for a <= b, stable in both tails."""
    if b <= a:
        return -math.inf
    if a >= 0.0:      # both in the upper tail: use Phi(b) - Phi(a) = Phi(-a) - Phi(-b)
        la, lb = float(special.log_ndtr(-a)), float(special.log_ndtr(-b))
        return la + _log1mexp(lb - la)
    if b <= 0.0:      # both in the lower tail
        la, lb = float(special.log_ndtr(a)), float(special.log_ndtr(b))
        return lb + _log1mexp(la - lb)
    # a < 0 < b: Phi(b) - Phi(a) = (erf(b/sqrt2) + erf(-a/sqrt2)) / 2, a sum of positives (no cancellation)
    return math.log(0.5 * (math.erf(b / math.sqrt(2.0)) + math.erf(-a / math.sqrt(2.0))))


# --- M1 ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class M1Result:
    log10_pc: float
    converged: bool
    ier: int
    abserr_rel: float


def _m1_log_integrand(t: float, g: PlaneGeometry) -> float:
    ct = math.cos(t)
    if ct <= 0.0:
        return -math.inf
    x = g.hbr * math.sin(t)
    h = g.hbr * ct
    zx = (x - g.mx) / g.sx
    log_outer = -0.5 * zx * zx - 0.5 * _LOG_2PI - math.log(g.sx)
    log_inner = _log_ndtr_diff((-h - g.my) / g.sy, (h - g.my) / g.sy)
    return log_outer + log_inner + math.log(g.hbr * ct)


def log10_pc_m1(g: PlaneGeometry, *, epsrel: float = 1e-10, limit: int = 500,
                peak_grid_points: int = 2001) -> M1Result:
    """M1: deterministic 1D reduction (see module docstring). Defaults are the pre-registered values."""
    half = 0.5 * math.pi
    k = np.arange(peak_grid_points)
    grid = -half + math.pi * (k + 0.5) / peak_grid_points
    logs = np.array([_m1_log_integrand(float(t), g) for t in grid])
    if not np.isfinite(logs).any():
        return M1Result(log10_pc=-math.inf, converged=True, ier=0, abserr_rel=0.0)
    i_peak = int(np.argmax(logs))
    peak, t_peak = float(logs[i_peak]), float(grid[i_peak])

    def scaled(t: float) -> float:
        v = _m1_log_integrand(t, g)
        return math.exp(v - peak) if v > -math.inf else 0.0

    out = integrate.quad(scaled, -half, half, epsabs=0.0, epsrel=epsrel, limit=limit,
                         points=[t_peak], full_output=1)
    val, abserr, ier = float(out[0]), float(out[1]), (int(out[3]) if len(out) > 3 else 0)
    if ier != 0 or not (val > 0.0):
        return M1Result(log10_pc=math.nan, converged=False, ier=ier if ier != 0 else -1,
                        abserr_rel=abserr / val if val > 0 else math.inf)
    return M1Result(log10_pc=(peak + math.log(val)) / LN10, converged=True, ier=0, abserr_rel=abserr / val)


# --- M3 ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class M3Estimate:
    log10_pc: float
    rel_se: float
    n: int


def m3_estimate(g: PlaneGeometry, *, seed: int, n: int, chunk: int) -> M3Estimate:
    """M3 with exactly ``n`` uniform-in-disk samples drawn in chunks from ``default_rng(seed)``."""
    rng = np.random.default_rng(seed)
    log_norm = -0.5 * _LOG_2PI * 2.0 - math.log(g.sx * g.sy)
    m = -math.inf
    s1 = s2 = 0.0
    done = 0
    while done < n:
        k = min(chunk, n - done)
        u, w = rng.random(k), rng.random(k)
        rad = g.hbr * np.sqrt(u)
        ang = 2.0 * math.pi * w
        x, y = rad * np.cos(ang), rad * np.sin(ang)
        logf = -0.5 * (((x - g.mx) / g.sx) ** 2 + ((y - g.my) / g.sy) ** 2) + log_norm
        cm = float(logf.max())
        if cm > m:
            if m > -math.inf:
                f = math.exp(m - cm)
                s1 *= f
                s2 *= f * f
            m = cm
        e = np.exp(logf - m)
        s1 += float(e.sum())
        s2 += float((e * e).sum())
        done += k
    mean = s1 / n
    var = max(s2 / n - mean * mean, 0.0)
    rel_se = math.sqrt(var / n) / mean if mean > 0 else math.inf
    log_pc = math.log(math.pi * g.hbr ** 2) + m + math.log(mean)
    return M3Estimate(log10_pc=log_pc / LN10, rel_se=rel_se, n=n)


@dataclass(frozen=True)
class M3Result:
    log10_pc: float
    rel_se: float
    n_used: int
    escalated: bool
    informative: bool


def log10_pc_m3(g: PlaneGeometry, *, seed: int, n_samples: int, n_escalated: int,
                rel_se_target: float, chunk: int) -> M3Result:
    """M3 with the pre-registered rule: ``n_samples``; if the relative SE misses the target, rerun once
    with ``n_escalated``; if it still misses, the event is "not informative" for M3."""
    est = m3_estimate(g, seed=seed, n=n_samples, chunk=chunk)
    if est.rel_se <= rel_se_target:
        return M3Result(est.log10_pc, est.rel_se, est.n, escalated=False, informative=True)
    est = m3_estimate(g, seed=seed, n=n_escalated, chunk=chunk)
    return M3Result(est.log10_pc, est.rel_se, est.n, escalated=True, informative=est.rel_se <= rel_se_target)


# --- M2 ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class M2Result:
    hits: int
    n: int
    p_hat: float
    rel_se: float
    informative: bool
    status: str


def pc_m2(g: PlaneGeometry, *, seed: int, chunk: int, cap: int, min_hits: int, max_rel_se: float,
          prior_log10_pc: float | None = None) -> M2Result:
    """M2: plain Monte Carlo hit counting (pre-registration item 8).

    If ``prior_log10_pc`` (the M1 estimate) implies min_hits / Pc > cap, the event is "not
    informative (a priori)" and is not sampled. Otherwise chunks are drawn until ``min_hits`` hits or
    ``cap`` samples; the result counts only if its relative SE <= ``max_rel_se``.
    """
    if prior_log10_pc is not None and math.isfinite(prior_log10_pc):
        if min_hits / (10.0 ** prior_log10_pc) > cap:
            return M2Result(0, 0, math.nan, math.inf, False, "not informative (a priori)")
    rng = np.random.default_rng(seed)
    r2 = g.hbr ** 2
    hits = n = 0
    while n < cap and hits < min_hits:
        k = min(chunk, cap - n)
        x = rng.normal(g.mx, g.sx, k)
        y = rng.normal(g.my, g.sy, k)
        hits += int(np.count_nonzero(x * x + y * y <= r2))
        n += k
    p = hits / n
    rel_se = math.sqrt((1.0 - p) / (n * p)) if hits > 0 else math.inf
    informative = rel_se <= max_rel_se
    return M2Result(hits, n, p, rel_se, informative, "informative" if informative else "not informative")


def m2_consistent(r: M2Result, engine_log10_pc: float, *, n_se: float) -> bool | None:
    """Within ``n_se`` standard errors in log10 (delta method: SE_log10 = rel_se / ln 10); None if not informative."""
    if not r.informative:
        return None
    return abs(math.log10(r.p_hat) - engine_log10_pc) <= n_se * r.rel_se / LN10
