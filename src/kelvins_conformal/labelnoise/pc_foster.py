"""Foster-type collision-probability (Pc) recomputation — E3 spike version.

Responsibility: recompute a CDM's collision probability from its public state and
covariance fields, so E3 can measure how closely a recomputed log-risk tracks the
reported ``risk`` value (Assumption A4). This is the statistical core (CLAUDE.md
§1, §4): it is unit-tested against analytically known 2D geometries **before** it
touches real data.

Method (2D conjunction-plane / B-plane integral, Foster & Estes 1992):
  1. Assemble each object's 3x3 RTN position covariance from its sigmas and
     position-position correlations; combine as C = C_target + C_chaser.
  2. Build the encounter plane perpendicular to the relative velocity; project the
     relative-position (miss) vector and C onto it -> (miss_xy, cov2d).
  3. Pc = integral of the 2D Gaussian N(miss_xy, cov2d) over a disk of radius HBR
     (combined hard-body radius) centred at the origin.

Documented spike-level assumptions (their validity is exactly what E3 measures;
they are stated here, never hidden):
  * Each object's covariance is taken in a common RTN frame and summed directly
    (no inter-object frame rotation). This is the standard first-order treatment.
  * HBR = (t_span + c_span) / 2, since ``x_span`` is the diameter "size used by the
    collision risk computation algorithm" (dataset documentation).
  * Only the 3x3 position block is used (velocity covariance does not enter the
    instantaneous 2D Pc under the linear relative-motion model).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Fields this computation requires from a CDM row (missing-field prevalence for
# these is reported by the E3 spike, per EXPERIMENT_PLAN.md E3).
REQUIRED_FIELDS: tuple[str, ...] = (
    "relative_position_r", "relative_position_t", "relative_position_n",
    "relative_velocity_r", "relative_velocity_t", "relative_velocity_n",
    "t_sigma_r", "t_sigma_t", "t_sigma_n", "t_ct_r", "t_cn_r", "t_cn_t",
    "c_sigma_r", "c_sigma_t", "c_sigma_n", "c_ct_r", "c_cn_r", "c_cn_t",
    "t_span", "c_span",
)


class PcComputationError(ValueError):
    """Raised for degenerate/invalid geometry (non-PSD covariance, zero velocity)."""


# --- covariance assembly ----------------------------------------------------
def position_covariance_rtn(
    sigma_r: float, sigma_t: float, sigma_n: float,
    ct_r: float, cn_r: float, cn_t: float,
) -> np.ndarray:
    """3x3 RTN position covariance from sigmas + position-position correlations.

    Order: [radial (r), transverse (t), normal (n)]. Correlations are the reported
    ``x_ct_r`` (t vs r), ``x_cn_r`` (n vs r), ``x_cn_t`` (n vs t).
    """
    cov = np.array(
        [
            [sigma_r * sigma_r, ct_r * sigma_r * sigma_t, cn_r * sigma_r * sigma_n],
            [ct_r * sigma_r * sigma_t, sigma_t * sigma_t, cn_t * sigma_t * sigma_n],
            [cn_r * sigma_r * sigma_n, cn_t * sigma_t * sigma_n, sigma_n * sigma_n],
        ],
        dtype=float,
    )
    return cov


def bplane_projection(r_vec: np.ndarray, v_vec: np.ndarray) -> np.ndarray:
    """2x3 projection onto the encounter plane perpendicular to relative velocity.

    Rows are two orthonormal in-plane axes: axis1 = (r x v)/|r x v| and
    axis2 = vhat x axis1. Projecting r gives the 2D miss vector whose magnitude is
    the (linear-model) miss distance.
    """
    v_norm = np.linalg.norm(v_vec)
    if v_norm == 0:
        raise PcComputationError("zero relative velocity: encounter plane undefined")
    vhat = v_vec / v_norm
    w = np.cross(r_vec, v_vec)
    w_norm = np.linalg.norm(w)
    if w_norm == 0:
        # r parallel to v: pick an arbitrary axis orthogonal to vhat.
        seed = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(seed, vhat)) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        axis1 = seed - np.dot(seed, vhat) * vhat
        axis1 /= np.linalg.norm(axis1)
    else:
        axis1 = w / w_norm
    axis2 = np.cross(vhat, axis1)
    return np.vstack([axis1, axis2])


# --- 2D integral over the hard-body disk ------------------------------------
def pc_on_disk(
    miss_xy: np.ndarray,
    cov2d: np.ndarray,
    hbr: float,
    *,
    n_radial: int = 200,
    n_angular: int = 360,
) -> float:
    """Integrate N(miss_xy, cov2d) over a disk of radius ``hbr`` centred at origin.

    Midpoint rule in polar coordinates within the covariance's principal-axis
    frame. Returns Pc in [0, 1]. Deterministic (no randomness).
    """
    if hbr <= 0:
        return 0.0
    # Diagonalise cov2d -> principal axes; rotate the miss vector into that frame.
    # (Rotation is a rigid motion, so the integration disk stays a disk.)
    evals, evecs = np.linalg.eigh(cov2d)
    if np.any(evals <= 0):
        raise PcComputationError(f"non-positive-definite 2D covariance: eigenvalues {evals}")
    a2, b2 = float(evals[0]), float(evals[1])  # principal variances
    m = evecs.T @ np.asarray(miss_xy, dtype=float)  # miss in principal frame
    mx, my = float(m[0]), float(m[1])

    # Polar grid over the disk (origin-centred; the Gaussian is offset by -m).
    r_edges = np.linspace(0.0, hbr, n_radial + 1)
    r_mid = 0.5 * (r_edges[:-1] + r_edges[1:])
    dr = hbr / n_radial
    theta = (np.arange(n_angular) + 0.5) * (2.0 * np.pi / n_angular)
    dtheta = 2.0 * np.pi / n_angular

    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    # Grid points (r_mid[i], theta[j]) -> (x, y).
    x = np.outer(r_mid, cos_t)  # (n_radial, n_angular)
    y = np.outer(r_mid, sin_t)
    quad = ((x - mx) ** 2) / a2 + ((y - my) ** 2) / b2
    density = np.exp(-0.5 * quad) / (2.0 * np.pi * np.sqrt(a2 * b2))
    # Area element in polar coords: r dr dtheta.
    integrand = density * r_mid[:, None]
    pc = float(np.sum(integrand) * dr * dtheta)
    return min(max(pc, 0.0), 1.0)


def log10_pc_on_disk(
    miss_xy: np.ndarray,
    cov2d: np.ndarray,
    hbr: float,
    *,
    n_radial: int = 200,
    n_angular: int = 360,
) -> float:
    """``log10`` of the same integral as :func:`pc_on_disk`, computed stably.

    Identical quadrature; the Gaussian kernel is evaluated in log space with the
    peak factored out (the standard log-sum-exp stabilisation), so a deep-tail
    conjunction whose Pc falls below double precision's ~1e-308 returns its true
    magnitude (e.g. -412) instead of silently collapsing to ``-inf``.

    Added for E14: the anchored label arm *differences* two recomputations, so an
    underflow to zero would not merely lose precision, it would discard an event
    whose rescaling shift is perfectly well defined. :func:`pc_on_disk` is left
    untouched, so the E3 spike's code path is unchanged.
    """
    if hbr <= 0:
        return -np.inf
    evals, evecs = np.linalg.eigh(cov2d)
    if np.any(evals <= 0):
        raise PcComputationError(f"non-positive-definite 2D covariance: eigenvalues {evals}")
    a2, b2 = float(evals[0]), float(evals[1])
    m = evecs.T @ np.asarray(miss_xy, dtype=float)
    mx, my = float(m[0]), float(m[1])

    r_edges = np.linspace(0.0, hbr, n_radial + 1)
    r_mid = 0.5 * (r_edges[:-1] + r_edges[1:])
    dr = hbr / n_radial
    theta = (np.arange(n_angular) + 0.5) * (2.0 * np.pi / n_angular)
    dtheta = 2.0 * np.pi / n_angular

    x = np.outer(r_mid, np.cos(theta))
    y = np.outer(r_mid, np.sin(theta))
    quad = ((x - mx) ** 2) / a2 + ((y - my) ** 2) / b2
    qmin = float(np.min(quad))
    # sum_ij exp(-q_ij/2) r_i = exp(-qmin/2) * sum_ij exp(-(q_ij-qmin)/2) r_i
    shifted = float(np.sum(np.exp(-0.5 * (quad - qmin)) * r_mid[:, None]))
    ln10 = np.log(10.0)
    log10_pc = (
        -0.5 * qmin / ln10
        + np.log10(shifted)
        + np.log10(dr * dtheta)
        - np.log10(2.0 * np.pi * np.sqrt(a2 * b2))
    )
    return float(min(log10_pc, 0.0))


# --- analytic reference (for unit tests) ------------------------------------
def analytic_pc_isotropic_zero_miss(sigma: float, hbr: float) -> float:
    """Exact Pc for isotropic covariance sigma^2 * I with zero miss distance.

    The 2D Gaussian integral over a centred disk of radius R reduces to a Rayleigh
    CDF: Pc = 1 - exp(-R^2 / (2 sigma^2)). Used as a ground-truth test case.
    """
    return 1.0 - np.exp(-(hbr * hbr) / (2.0 * sigma * sigma))


def analytic_pc_isotropic_point_mass(sigma: float, hbr: float, miss: float) -> float:
    """First-order (point-mass) Pc for isotropic covariance and small HBR.

    Pc ~= (HBR^2 / (2 sigma^2)) * exp(-miss^2 / (2 sigma^2)), valid when HBR << sigma.
    Used to check the integrator in the offset-miss regime.
    """
    return (hbr * hbr) / (2.0 * sigma * sigma) * np.exp(-(miss * miss) / (2.0 * sigma * sigma))


# --- per-row recomputation on real data -------------------------------------
@dataclass(frozen=True)
class PcResult:
    pc: float
    log10_pc: float          # clipped at floor_sentinel to match reported `risk`
    miss_distance_2d: float   # |projected miss| — cross-check vs reported miss_distance
    mahalanobis_2d: float     # sqrt(m^T cov2d^-1 m) — cross-check vs reported column
    hbr: float
    combined_pos_cov_det: float
    n_missing_required: int
    # Unfloored log10(Pc) (-inf if Pc underflows to 0). E14's anchored label arm
    # differences two recomputations, and differencing floored values would silently
    # zero out any change that happens below the sentinel.
    log10_pc_unfloored: float = float("nan")


def _get(row: dict, key: str) -> float:
    val = row.get(key, np.nan)
    return float(val) if val is not None else np.nan


def count_missing_required(row: dict) -> int:
    return sum(1 for f in REQUIRED_FIELDS if not np.isfinite(_get(row, f)))


def recompute_pc_for_row(
    row: dict,
    *,
    floor_sentinel: float = -30.0,
    n_radial: int = 200,
    n_angular: int = 360,
    covariance_scale: float = 1.0,
) -> PcResult | None:
    """Recompute Pc for one CDM row (a dict of column -> value).

    Returns ``None`` if any required field is missing (the caller tallies these as
    a missing-field failure mode — never silently imputed). Raises
    ``PcComputationError`` on degenerate geometry that survives the field check.

    ``covariance_scale`` (E14, Q-LBL-02 option (a)) multiplies the COMBINED
    position covariance, ``C = C_target + C_chaser -> s*C``. It is a *variance*
    scale, so each sigma scales by ``sqrt(s)``. The default 1.0 leaves the E3
    spike's code path numerically unchanged. Scaling here (3x3, before the B-plane
    projection) is identical to scaling the projected 2x2 afterwards, because the
    projection is linear — so the semantics carry no ambiguity.
    """
    if count_missing_required(row) > 0:
        return None

    r_vec = np.array([_get(row, "relative_position_r"),
                      _get(row, "relative_position_t"),
                      _get(row, "relative_position_n")])
    v_vec = np.array([_get(row, "relative_velocity_r"),
                      _get(row, "relative_velocity_t"),
                      _get(row, "relative_velocity_n")])

    cov_t = position_covariance_rtn(
        _get(row, "t_sigma_r"), _get(row, "t_sigma_t"), _get(row, "t_sigma_n"),
        _get(row, "t_ct_r"), _get(row, "t_cn_r"), _get(row, "t_cn_t"),
    )
    cov_c = position_covariance_rtn(
        _get(row, "c_sigma_r"), _get(row, "c_sigma_t"), _get(row, "c_sigma_n"),
        _get(row, "c_ct_r"), _get(row, "c_cn_r"), _get(row, "c_cn_t"),
    )
    if covariance_scale <= 0:
        raise PcComputationError(f"covariance_scale must be positive, got {covariance_scale}")
    cov = (cov_t + cov_c) * float(covariance_scale)

    hbr = 0.5 * (_get(row, "t_span") + _get(row, "c_span"))

    proj = bplane_projection(r_vec, v_vec)
    miss_xy = proj @ r_vec
    cov2d = proj @ cov @ proj.T

    pc = pc_on_disk(miss_xy, cov2d, hbr, n_radial=n_radial, n_angular=n_angular)
    # ``log10_pc`` keeps the original expression verbatim so the E3 spike's code
    # path is unchanged. ``log10_pc_unfloored`` uses the stable log-space integral,
    # which agrees with it wherever ``pc`` does not underflow and stays finite where
    # it does — the E14 anchored arm needs the latter (see log10_pc_on_disk).
    log10_pc = max(float(np.log10(pc)) if pc > 0 else -np.inf, floor_sentinel)
    log10_pc_unfloored = log10_pc_on_disk(
        miss_xy, cov2d, hbr, n_radial=n_radial, n_angular=n_angular
    )

    try:
        maha = float(np.sqrt(miss_xy @ np.linalg.inv(cov2d) @ miss_xy))
    except np.linalg.LinAlgError:
        maha = np.nan

    return PcResult(
        pc=pc,
        log10_pc=float(log10_pc),
        miss_distance_2d=float(np.linalg.norm(miss_xy)),
        mahalanobis_2d=maha,
        hbr=float(hbr),
        combined_pos_cov_det=float(np.linalg.det(cov)),
        n_missing_required=0,
        log10_pc_unfloored=log10_pc_unfloored,
    )
