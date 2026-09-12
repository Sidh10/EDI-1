"""Analytic tests for E14's covariance-scaling label regeneration (CLAUDE.md §4).

``labelnoise`` is named in the mandatory-tested statistical core, so the scaling
path is validated against hand-computable cases BEFORE it regenerates a single
official-test label. Cases:
  1. ``covariance_scale=1.0`` leaves the E3 code path numerically unchanged.
  2. Isotropic zero-miss Pc under C -> sC matches the exact Rayleigh form with
     sigma^2 -> s*sigma^2 (this is what pins the VARIANCE-scale semantics).
  3. Scaling the 3x3 before projection == scaling the projected 2x2 after.
  4. Direction of the effect: inflating covariance LOWERS Pc for a near-zero miss
     but RAISES it for a distant miss. Both directions are asserted, so a sign
     error in either regime fails loudly.
  5. The two label arms (direct / anchored) behave as the pre-registration defines,
     including the floor and the unfloored differencing.
  6. Eligibility never imputes: a row missing a required field is excluded, and a
     grid without the 1.0 anchor is rejected rather than silently handled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal.labelnoise import pc_foster as pf
from kelvins_conformal.labelnoise import rescale as rs


def _row(**over) -> dict:
    row = dict.fromkeys(pf.REQUIRED_FIELDS, 0.0)
    row.update(
        relative_position_r=200.0, relative_position_t=50.0, relative_position_n=0.0,
        relative_velocity_r=0.0, relative_velocity_t=0.0, relative_velocity_n=7500.0,
        t_sigma_r=150.0, t_sigma_t=400.0, t_sigma_n=120.0,
        c_sigma_r=200.0, c_sigma_t=600.0, c_sigma_n=180.0,
        t_span=5.0, c_span=2.0,
    )
    row.update(over)
    return row


def test_scale_one_is_the_unscaled_path():
    row = _row()
    base = pf.recompute_pc_for_row(row)
    scaled = pf.recompute_pc_for_row(row, covariance_scale=1.0)
    assert base is not None and scaled is not None
    assert scaled.pc == base.pc
    assert scaled.log10_pc == base.log10_pc
    assert scaled.combined_pos_cov_det == base.combined_pos_cov_det


@pytest.mark.parametrize("scale", [0.8, 1.0, 1.5, 2.0])
def test_isotropic_zero_miss_scales_as_variance(scale):
    """C -> sC must act as sigma^2 -> s*sigma^2 (NOT sigma -> s*sigma)."""
    sigma, hbr = 300.0, 40.0
    # Isotropic 3D covariance projects to isotropic 2D, so the analytic form applies.
    row = _row(
        relative_position_r=0.0, relative_position_t=0.0, relative_position_n=0.0,
        t_sigma_r=sigma, t_sigma_t=sigma, t_sigma_n=sigma,
        c_sigma_r=0.0, c_sigma_t=0.0, c_sigma_n=0.0,
        t_span=hbr, c_span=hbr,
    )
    res = pf.recompute_pc_for_row(
        row, covariance_scale=scale, n_radial=400, n_angular=720
    )
    assert res is not None
    exact = pf.analytic_pc_isotropic_zero_miss(sigma * np.sqrt(scale), hbr)
    assert res.pc == pytest.approx(exact, rel=2e-3)


def test_scaling_before_or_after_projection_agree():
    scale = 1.7
    cov3 = pf.position_covariance_rtn(150.0, 400.0, 120.0, 0.2, -0.1, 0.05)
    proj = pf.bplane_projection(
        np.array([200.0, 50.0, 0.0]), np.array([0.0, 0.0, 7500.0])
    )
    before = proj @ (scale * cov3) @ proj.T
    after = scale * (proj @ cov3 @ proj.T)
    assert np.allclose(before, after, rtol=1e-12, atol=1e-12)


def test_inflating_covariance_lowers_pc_for_a_near_hit():
    """Near-zero miss: spreading the same probability mass thins the peak."""
    row = _row(relative_position_r=0.0, relative_position_t=0.0, relative_position_n=0.0)
    vals = [pf.recompute_pc_for_row(row, covariance_scale=s).pc
            for s in (0.8, 1.0, 1.4, 2.0)]
    assert all(b < a for a, b in zip(vals, vals[1:], strict=False))


def test_inflating_covariance_raises_pc_for_a_distant_miss():
    """Far miss: a wider distribution puts MORE mass on the hard-body disk."""
    row = _row(relative_position_r=5000.0, relative_position_t=0.0, relative_position_n=0.0)
    vals = [pf.recompute_pc_for_row(row, covariance_scale=s).pc
            for s in (0.8, 1.0, 1.4, 2.0)]
    assert all(b > a for a, b in zip(vals, vals[1:], strict=False))


def test_negative_scale_raises():
    with pytest.raises(pf.PcComputationError):
        pf.recompute_pc_for_row(_row(), covariance_scale=0.0)


@pytest.mark.parametrize("miss", [0.0, 100.0, 400.0])
def test_log_space_integral_agrees_where_the_linear_one_is_valid(miss):
    sigma, hbr = 300.0, 25.0
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    linear = pf.pc_on_disk(np.array([miss, 0.0]), cov2d, hbr, n_radial=300, n_angular=480)
    logged = pf.log10_pc_on_disk(np.array([miss, 0.0]), cov2d, hbr,
                                 n_radial=300, n_angular=480)
    assert logged == pytest.approx(np.log10(linear), rel=1e-9, abs=1e-9)


def test_log_space_integral_survives_underflow():
    """Below ~1e-308 the linear integral collapses to 0; the log one must not.

    Checked against the first-order point-mass form, which is exact to high
    relative accuracy when HBR << sigma:
        log10 Pc = log10(HBR^2 / (2 sigma^2)) - miss^2 / (2 sigma^2 ln 10).
    """
    sigma, hbr, miss = 100.0, 0.5, 4000.0     # miss/sigma = 40 -> Pc ~ 1e-350
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    assert pf.pc_on_disk(np.array([miss, 0.0]), cov2d, hbr) == 0.0
    logged = pf.log10_pc_on_disk(np.array([miss, 0.0]), cov2d, hbr,
                                 n_radial=200, n_angular=360)
    expected = (np.log10(hbr**2 / (2 * sigma**2))
                - (miss**2) / (2 * sigma**2 * np.log(10.0)))
    assert np.isfinite(logged)
    assert logged == pytest.approx(expected, rel=1e-4)


def test_log_space_integral_never_exceeds_certainty():
    sigma = 5.0
    cov2d = np.array([[sigma**2, 0.0], [0.0, sigma**2]])
    assert pf.log10_pc_on_disk(np.array([0.0, 0.0]), cov2d, 10_000.0,
                               n_radial=400, n_angular=360) <= 0.0


def test_unfloored_log_pc_is_retained_below_the_sentinel():
    # A hugely separated pair drives Pc far below 1e-30; the floored label clips
    # while the unfloored value keeps the magnitude the anchored arm differences.
    row = _row(relative_position_r=5.0e5, relative_position_t=0.0, relative_position_n=0.0)
    res = pf.recompute_pc_for_row(row, floor_sentinel=-30.0)
    assert res is not None
    assert res.log10_pc == -30.0
    assert res.log10_pc_unfloored < -30.0


# --- label arms -------------------------------------------------------------
def _target_frame(rows: list[dict], uids: list[str], reported: list[float]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["event_uid"] = uids
    df["target_log_risk"] = reported
    return df


def test_eligibility_excludes_rows_with_a_missing_field():
    good, bad = _row(), _row()
    bad["c_span"] = np.nan
    frame = _target_frame([good, bad], ["test_1", "test_2"], [-6.0, -7.0])
    elig = rs.eligibility(frame)
    assert elig["m7_eligible"].tolist() == [True, False]
    assert elig["n_missing_required"].tolist() == [0, 1]


def test_regenerate_produces_both_arms_and_drops_ineligible():
    good, bad = _row(), _row()
    bad["t_sigma_r"] = np.nan
    frame = _target_frame([good, bad], ["test_1", "test_2"], [-6.0, -7.0])
    labels = rs.regenerate_labels(frame, [0.8, 1.0, 2.0], n_radial=80, n_angular=120)

    assert set(labels["event_uid"]) == {"test_1"}
    assert sorted(labels["scale"].unique()) == [0.8, 1.0, 2.0]
    assert list(labels.columns) == list(rs.SCALE_FRAME_COLUMNS)

    # At the anchor the anchored arm returns the REPORTED label exactly (delta = 0),
    # which is the property that makes it isolate the rescaling effect.
    at1 = labels[np.isclose(labels["scale"], 1.0)].iloc[0]
    assert at1["y_anchored"] == pytest.approx(-6.0)
    # ... while the direct arm returns the recomputation, which need not agree.
    assert at1["y_direct"] == pytest.approx(at1["log10_pc_unfloored"])

    # Away from the anchor the anchored arm is the reported label plus the shift.
    at2 = labels[np.isclose(labels["scale"], 2.0)].iloc[0]
    shift = at2["log10_pc_unfloored"] - at1["log10_pc_unfloored"]
    assert at2["y_anchored"] == pytest.approx(-6.0 + shift)


def test_regenerate_requires_the_anchor_in_the_grid():
    frame = _target_frame([_row()], ["test_1"], [-6.0])
    with pytest.raises(ValueError, match="1.0 anchor"):
        rs.regenerate_labels(frame, [0.8, 1.2], n_radial=40, n_angular=60)


def test_labels_are_floored_at_the_sentinel():
    # Pc here is small but non-zero, so both arms are defined and both clip.
    row = _row(relative_position_r=3000.0, relative_position_t=0.0, relative_position_n=0.0,
               t_span=1e-3, c_span=1e-3)
    frame = _target_frame([row], ["test_1"], [-25.0])   # uncensored reported label
    labels = rs.regenerate_labels(frame, [1.0, 2.0], floor_sentinel=-30.0,
                                  n_radial=80, n_angular=120)
    assert labels["anchored_defined"].all()
    assert (labels["y_direct"] >= -30.0).all()
    assert (labels["y_anchored"] >= -30.0).all()


def test_deep_tail_recomputation_stays_finite():
    """A conjunction far below 1e-308 must still yield a finite recomputed magnitude.

    This is the case that motivated the log-space integral: with the linear
    quadrature it underflowed to Pc = 0, losing the magnitude entirely.
    """
    row = _row(relative_position_r=5.0e5, relative_position_t=0.0, relative_position_n=0.0)
    frame = _target_frame([row], ["test_1"], [-12.0])
    labels = rs.regenerate_labels(frame, [1.0, 2.0], floor_sentinel=-30.0,
                                  n_radial=80, n_angular=120)
    assert np.isfinite(labels["log10_pc_unfloored"]).all()
    assert labels["log10_pc_unfloored"].max() < -30.0
    # The DIRECT arm floors at the sentinel, as the reported label convention does.
    assert (labels["y_direct"] == -30.0).all()


def test_anchored_arm_is_undefined_where_the_reported_label_is_censored():
    """At the sentinel the reported label has no magnitude to displace.

    Displacing a censored -30 by a shift computed thousands of log-units lower
    produced labels above 0 — impossible probabilities — so those events must be
    flagged undefined rather than carried into the analysis.
    """
    row = _row(relative_position_r=5.0e5, relative_position_t=0.0, relative_position_n=0.0)
    frame = _target_frame([row], ["test_1"], [-30.0])
    labels = rs.regenerate_labels(frame, [1.0, 2.0], floor_sentinel=-30.0,
                                  n_radial=80, n_angular=120)
    assert not labels["anchored_defined"].any()
    assert labels["y_anchored"].isna().all()


def test_anchored_labels_are_probabilities():
    """y_anchored must stay within [floor, 0]: log10 Pc > 0 would mean Pc > 1."""
    # Distant miss + tiny anchor covariance: inflating s raises Pc steeply.
    row = _row(relative_position_r=4000.0, relative_position_t=0.0, relative_position_n=0.0,
               t_sigma_r=30.0, t_sigma_t=30.0, t_sigma_n=30.0,
               c_sigma_r=0.0, c_sigma_t=0.0, c_sigma_n=0.0, t_span=50.0, c_span=50.0)
    frame = _target_frame([row], ["test_1"], [-1.0])
    labels = rs.regenerate_labels(frame, [1.0, 2.0], floor_sentinel=-30.0,
                                  n_radial=80, n_angular=120)
    defined = labels[labels["anchored_defined"]]
    assert len(defined) == 2
    assert (defined["y_anchored"] <= 0.0).all()
    assert (defined["y_anchored"] >= -30.0).all()


def test_undefined_anchor_is_flagged_not_imputed():
    """Where the shift genuinely has no value (zero hard-body radius), say so."""
    row = _row(t_span=0.0, c_span=0.0)
    frame = _target_frame([row], ["test_1"], [-30.0])
    labels = rs.regenerate_labels(frame, [1.0, 2.0], floor_sentinel=-30.0,
                                  n_radial=80, n_angular=120)
    assert not labels["anchored_defined"].any()
    assert labels["y_anchored"].isna().all()
    assert (labels["y_direct"] == -30.0).all()


def test_underflow_away_from_the_anchor_is_well_defined():
    """A finite anchor with underflow at another scale floors — it is not undefined."""
    # Near-hit at s = 1 (finite Pc); inflating the covariance enormously thins the
    # peak until Pc underflows, which is a real label going to the floor.
    row = _row(relative_position_r=0.0, relative_position_t=0.0, relative_position_n=0.0,
               t_span=1e-8, c_span=1e-8)
    frame = _target_frame([row], ["test_1"], [-12.0])
    labels = rs.regenerate_labels(frame, [1.0, 2.0], floor_sentinel=-30.0,
                                  n_radial=80, n_angular=120)
    assert labels["anchored_defined"].all()
    assert labels["y_anchored"].notna().all()


def test_regeneration_is_deterministic():
    frame = _target_frame([_row(), _row(relative_position_r=900.0)],
                          ["test_1", "test_2"], [-6.0, -8.0])
    a = rs.regenerate_labels(frame, [0.8, 1.0, 2.0], n_radial=80, n_angular=120)
    b = rs.regenerate_labels(frame, [0.8, 1.0, 2.0], n_radial=80, n_angular=120)
    pd.testing.assert_frame_equal(a, b)


def test_agreement_at_anchor_matches_hand_computation():
    frame = _target_frame([_row()], ["test_1"], [-6.0])
    labels = rs.regenerate_labels(frame, [1.0, 1.5], n_radial=80, n_angular=120)
    agree = rs.agreement_at_anchor(labels, rs.eligibility(frame))
    assert len(agree) == 1
    expected = abs(agree["log10_pc_recomputed"].iloc[0] - (-6.0))
    assert agree["abs_delta"].iloc[0] == pytest.approx(expected)
