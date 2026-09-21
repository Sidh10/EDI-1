"""Unit tests for the E17 robustness primitives (CLAUDE.md §4: tested before trusted).

The cluster bootstrap and the Holm procedure are both checked against hand-computed
or analytically known cases before they touch any Kelvins result.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal.robustness import cluster_bootstrap_mean, holm_bonferroni

# --- Holm–Bonferroni -------------------------------------------------------------


def test_holm_hand_computed_example():
    """Hand-computed: m=4, p = .01, .02, .03, .04 at alpha = .05.

    Sorted comparisons: .01 <= .05/4 = .0125 reject; .02 <= .05/3 = .0167 FAILS.
    Step-down stops there, so exactly one hypothesis is rejected even though .02
    and .03 would pass a naive per-test threshold.
    Adjusted: 4(.01)=.04, 3(.02)=.06, 2(.03)=.06, 1(.04)=.06 after monotonicity.
    """
    r = holm_bonferroni([0.01, 0.02, 0.03, 0.04], alpha=0.05)
    assert r["n_rejected"] == 1
    np.testing.assert_array_equal(r["rejected"], [True, False, False, False])
    np.testing.assert_allclose(r["p_adjusted"], [0.04, 0.06, 0.06, 0.06])


def test_holm_rejects_everything_when_all_tiny():
    r = holm_bonferroni([1e-40, 1e-30, 1e-20], alpha=0.05)
    assert r["n_rejected"] == 3 and r["rejected"].all()


def test_holm_adjusted_p_values_are_monotone_and_capped():
    rng = np.random.default_rng(0)
    p = rng.random(25)
    r = holm_bonferroni(p)
    adj = r["p_adjusted"][np.argsort(p, kind="stable")]
    assert np.all(np.diff(adj) >= -1e-12)          # non-decreasing in rank
    assert np.all(r["p_adjusted"] <= 1.0)
    assert np.all(r["p_adjusted"] >= p - 1e-12)    # never smaller than the raw p


def test_holm_single_test_is_the_raw_p_value():
    r = holm_bonferroni([0.03], alpha=0.05)
    assert r["p_adjusted"][0] == pytest.approx(0.03) and r["rejected"][0]


@pytest.mark.parametrize("bad", [[], [0.5, 1.5], [0.5, -0.1], [0.5, np.nan]])
def test_holm_rejects_invalid_p_values(bad):
    with pytest.raises(ValueError):
        holm_bonferroni(bad)


# --- cluster bootstrap -----------------------------------------------------------


def test_cluster_bootstrap_point_estimate_is_the_plain_mean():
    v = np.array([1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    c = np.array([0, 0, 1, 1, 2, 2])
    r = cluster_bootstrap_mean(v, c, n_resamples=200, seed=1)
    assert r.point == pytest.approx(v.mean())
    assert (r.n_clusters, r.n_events) == (3, 6)
    assert r.largest_cluster_frac == pytest.approx(2 / 6)


def test_singleton_clusters_reproduce_the_iid_bootstrap():
    """With one event per cluster the cluster bootstrap IS the event bootstrap.

    Same seed, same generator calls, so the intervals must agree closely; this is
    the degenerate case that pins the implementation to the familiar one.
    """
    rng = np.random.default_rng(3)
    v = (rng.random(300) < 0.6).astype(float)
    c = np.arange(300)
    r = cluster_bootstrap_mean(v, c, n_resamples=1500, seed=7)
    # Reference: plain iid percentile bootstrap of the mean.
    g = np.random.default_rng(7)
    draws = np.array([v[g.integers(0, 300, size=300)].mean() for _ in range(1500)])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    assert r.lo == pytest.approx(lo, abs=0.02)
    assert r.hi == pytest.approx(hi, abs=0.02)


def test_perfectly_correlated_clusters_widen_the_interval():
    """Within-cluster correlation is where the two bootstraps must disagree.

    Every event in a cluster shares one value, so the effective sample size is the
    number of clusters, not the number of events. The cluster bootstrap must
    reflect that and be materially WIDER than the iid bootstrap, which would treat
    600 perfectly-redundant events as 600 independent ones.
    """
    rng = np.random.default_rng(11)
    per_cluster = (rng.random(30) < 0.5).astype(float)
    v = np.repeat(per_cluster, 20)                 # 30 clusters x 20 identical events
    c = np.repeat(np.arange(30), 20)
    clustered = cluster_bootstrap_mean(v, c, n_resamples=1500, seed=5)
    iid = cluster_bootstrap_mean(v, np.arange(v.size), n_resamples=1500, seed=5)
    assert clustered.half_width > 3 * iid.half_width


def test_cluster_bootstrap_is_deterministic_given_the_seed():
    rng = np.random.default_rng(2)
    v = (rng.random(200) < 0.7).astype(float)
    c = rng.integers(0, 15, size=200)
    a = cluster_bootstrap_mean(v, c, n_resamples=400, seed=99)
    b = cluster_bootstrap_mean(v, c, n_resamples=400, seed=99)
    assert (a.lo, a.hi, a.point) == (b.lo, b.hi, b.point)


def test_cluster_bootstrap_rejects_bad_input():
    with pytest.raises(ValueError):
        cluster_bootstrap_mean(np.array([]), np.array([]))
    with pytest.raises(ValueError):
        cluster_bootstrap_mean(np.array([1.0, 2.0]), np.array([0]))
    with pytest.raises(ValueError):
        cluster_bootstrap_mean(np.array([1.0, np.nan]), np.array([0, 1]))
    with pytest.raises(ValueError):
        cluster_bootstrap_mean(np.array([1.0, 0.0]), np.array([0, 1]), level=1.5)


# --- base_predictions learner restriction (E17, Sidh 2026-09-21) --------------------


def test_base_predictions_signature_defaults_to_every_learner():
    """The restriction must be opt-in: existing callers keep fitting all four.

    Checked on the signature rather than by fitting, so the guarantee is verified
    without the multi-minute real fit. The behavioural half is exercised by the E17
    smoke tests, which pass an explicit restricted set.
    """
    import inspect

    from kelvins_conformal.models.conformal_runner import BASE_LEARNERS, base_predictions

    sig = inspect.signature(base_predictions)
    assert "learners" in sig.parameters
    assert sig.parameters["learners"].default is None      # None => all of BASE_LEARNERS
    assert set(BASE_LEARNERS) == {"persistence", "gbm", "gru", "mc_dropout"}


def test_base_predictions_rejects_unknown_or_empty_learner_sets():
    """Fail loud on a typo rather than silently fitting nothing (CLAUDE.md §1)."""
    from types import SimpleNamespace

    from kelvins_conformal.models.conformal_runner import base_predictions

    dummy = SimpleNamespace(subsets={})
    with pytest.raises(ValueError, match="unknown learners"):
        base_predictions(None, dummy, 42, learners=("gbm", "not_a_learner"))
    with pytest.raises(ValueError, match="at least one learner"):
        base_predictions(None, dummy, 42, learners=())


def test_h1_learner_set_excludes_mc_dropout_and_says_why():
    """The exclusion must be machine-readable, not just prose in a log."""
    from kelvins_conformal.models import robustness_runner as RR

    assert RR.H1_LEARNERS == ("persistence", "gbm", "gru")
    assert RR.H1_EXCLUDED_LEARNERS == ("mc_dropout",)
    assert "E8" in RR.H1_EXCLUSION_REASON and "config hash" in RR.H1_EXCLUSION_REASON


# --- restoration_verdict: the corrected one-sided criterion (Sidh, 2026-09-21) --------

from kelvins_conformal.robustness import (  # noqa: E402
    NO_DEFICIT,
    NOT_RESTORED,
    RESTORED,
    restoration_verdict,
)


def test_over_covering_weighted_arm_is_restored_not_failed():
    """The exact case the containment bug got wrong: the Gate-2 headline's shape.

    Naive under-covers (CI wholly below 0.90); weighted over-covers (CI wholly ABOVE).
    The guarantee is coverage >= nominal, so this is RESTORED. Containment called it a
    failure because 0.90 is not inside [0.9151, 0.9372].
    """
    v = restoration_verdict(0.8426, 0.8736, 0.9151, 0.9372, 0.90)
    assert v["verdict"] == RESTORED
    assert v["verdict_containment"] == NOT_RESTORED        # the bug, preserved as secondary
    assert not v["criteria_agree"]
    assert v["weighted_ci_wholly_above_nominal"]


def test_weighted_ci_containing_nominal_is_restored_under_both():
    v = restoration_verdict(0.820, 0.852, 0.882, 0.908, 0.90)   # split two-sided, H2 matrix
    assert v["verdict"] == RESTORED and v["verdict_containment"] == RESTORED
    assert v["criteria_agree"]


def test_weighted_still_under_covering_is_not_restored_under_both():
    v = restoration_verdict(0.848, 0.877, 0.833, 0.863, 0.90)   # CQR one-sided, the H2 cell
    assert v["verdict"] == NOT_RESTORED and v["verdict_containment"] == NOT_RESTORED
    assert v["weighted_ci_wholly_below_nominal"]


def test_naive_not_under_covering_means_no_deficit_to_restore():
    """If under-coverage was never established there is nothing to restore — and that
    must never be reported as a restoration success."""
    v = restoration_verdict(0.88, 0.93, 0.89, 0.94, 0.90)
    assert v["verdict"] == NO_DEFICIT
    assert v["verdict"] != RESTORED


def test_gbm_80_fragility_flips_on_interval_width_alone():
    """GBM @ 80%: same point estimate (0.7828), different interval widths.

    The weighted upper bound is 0.7997 under iid and 0.8092 under the wider cluster
    bootstrap. The verdict flips on width alone — the documented fragility.
    """
    iid = restoration_verdict(0.7017, 0.7387, 0.7657, 0.7997, 0.80)
    clu = restoration_verdict(0.6827, 0.7556, 0.7520, 0.8092, 0.80)
    assert iid["verdict"] == NOT_RESTORED and clu["verdict"] == RESTORED
    # Neither interval lies wholly above nominal: this is weak restoration at best.
    assert not clu["weighted_ci_wholly_above_nominal"]


def test_upper_bound_exactly_at_nominal_counts_as_not_establishing_undercoverage():
    """Boundary convention, fixed here so it cannot drift: CI upper == nominal means
    under-coverage is NOT established (>=), for both arms."""
    assert restoration_verdict(0.85, 0.90, 0.88, 0.95, 0.90)["verdict"] == NO_DEFICIT
    assert restoration_verdict(0.80, 0.85, 0.85, 0.90, 0.90)["verdict"] == RESTORED


@pytest.mark.parametrize("args", [
    (0.9, 0.8, 0.85, 0.95, 0.9),        # naive lo > hi
    (0.8, 0.85, 0.95, 0.9, 0.9),        # weighted lo > hi
    (0.8, 0.85, 0.85, 0.95, 1.0),       # nominal out of range
    (0.8, np.nan, 0.85, 0.95, 0.9),     # non-finite
])
def test_restoration_verdict_rejects_malformed_input(args):
    with pytest.raises(ValueError):
        restoration_verdict(*args)
