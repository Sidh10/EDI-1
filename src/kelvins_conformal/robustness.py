"""Robustness primitives for E17 (Phase 5).

Responsibility: the statistical machinery E17's robustness checks need that does not
already exist elsewhere in the project — a cluster (block) bootstrap that resamples
CLUSTERS rather than individual events, and the Holm–Bonferroni step-down procedure
used to confirm the declared multiple-comparison policy does not alter the primary
conclusion.

Inputs:  per-event indicator/statistic arrays plus a cluster label per event.
Outputs: percentile confidence intervals and adjusted p-values.

Serves: EXPERIMENT_PLAN.md E17 (H1 — robustness, consistency & gap-closure).

Protocol: Q-STAT-03c (coverage uncertainty: event-level bootstrap plus a cluster
bootstrap sensitivity check grouping by mission) and Q-STAT-04 (hierarchical
multiple-comparison policy: one primary contrast formally tested, all else
descriptive). Nothing here introduces a new formal comparison; the Holm procedure
is applied to the EXISTING family to confirm the primary conclusion survives it.

Every resampling unit here is an event or a cluster of events, never a CDM row
(invariant I3).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ClusterBootstrapResult:
    """Percentile cluster-bootstrap interval plus the bookkeeping needed to audit it."""

    point: float
    lo: float
    hi: float
    n_resamples: int
    n_clusters: int
    n_events: int
    largest_cluster_frac: float   # share of events in the biggest cluster
    level: float

    @property
    def half_width(self) -> float:
        return 0.5 * (self.hi - self.lo)


def cluster_bootstrap_mean(
    values: np.ndarray,
    clusters: np.ndarray,
    *,
    n_resamples: int = 2000,
    level: float = 0.95,
    seed: int = 42,
) -> ClusterBootstrapResult:
    """Percentile cluster bootstrap for the MEAN of ``values`` (Q-STAT-03c).

    The event-level bootstrap already in ``metrics.bootstrap_statistic`` resamples
    events independently, which assumes events are independent. Events from the same
    mission plausibly are not (shared object, shared operator, correlated orbital
    regime). The cluster bootstrap relaxes that: each resample draws ``n_clusters``
    whole clusters with replacement and pools their member events, so within-cluster
    dependence of any form is preserved and only between-cluster variation is
    resampled. This is the standard nonparametric block bootstrap for clustered data
    (Field & Welsh 2007, "Bootstrapping clustered data", JRSS-B 69(3), §3, the
    "cluster bootstrap"); it is conservative relative to the iid bootstrap exactly
    when within-cluster correlation is positive.

    The resampled sample size varies between draws (clusters differ in size); this is
    intended — it is the cluster bootstrap's own sampling variability, not a defect.

    ``values`` is a per-EVENT array (for coverage, the 0/1 covered indicator);
    ``clusters`` is a per-event label of the same length. Determinism: given
    ``seed`` the result is exactly reproducible.
    """
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    if values.ndim != 1:
        raise ValueError("values must be a 1-D per-event array")
    if values.shape != clusters.shape:
        raise ValueError(
            f"values and clusters must align per event, got {values.shape} and {clusters.shape}"
        )
    if values.size == 0:
        raise ValueError("cannot bootstrap an empty sample")
    if not np.all(np.isfinite(values)):
        raise ValueError("values must be finite (fail loud, CLAUDE.md §1)")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1, got {n_resamples}")
    if not (0.0 < level < 1.0):
        raise ValueError(f"level must be in (0, 1), got {level}")

    labels, inverse = np.unique(clusters, return_inverse=True)
    n_clusters = labels.size
    # Member event indices per cluster, in stable order.
    order = np.argsort(inverse, kind="stable")
    sorted_inv = inverse[order]
    starts = np.searchsorted(sorted_inv, np.arange(n_clusters), side="left")
    stops = np.searchsorted(sorted_inv, np.arange(n_clusters), side="right")
    members = [order[a:b] for a, b in zip(starts, stops, strict=True)]
    sizes = np.array([m.size for m in members], dtype=float)

    rng = np.random.default_rng(seed)
    draws = np.empty(n_resamples, dtype=float)
    for b in range(n_resamples):
        picked = rng.integers(0, n_clusters, size=n_clusters)
        idx = np.concatenate([members[c] for c in picked])
        draws[b] = values[idx].mean()

    a = 1.0 - level
    lo, hi = np.percentile(draws, [100 * a / 2, 100 * (1 - a / 2)])
    return ClusterBootstrapResult(
        point=float(values.mean()), lo=float(lo), hi=float(hi),
        n_resamples=int(n_resamples), n_clusters=int(n_clusters),
        n_events=int(values.size), largest_cluster_frac=float(sizes.max() / sizes.sum()),
        level=level,
    )


def holm_bonferroni(p_values, alpha: float = 0.05) -> dict:
    """Holm's step-down procedure (Holm 1979, Scand. J. Statist. 6(2), 65–70).

    Sort p-values ascending; compare the i-th (0-indexed) against alpha / (m - i);
    reject while the comparison holds and stop at the first failure, rejecting
    nothing after it. The adjusted p-value is the running maximum of
    (m - i) * p_(i), capped at 1, which is the standard monotone-enforced form.

    Used by E17 only to CONFIRM that the pre-registered primary contrast survives the
    declared policy (Q-STAT-04); it introduces no new comparison.
    """
    p = np.asarray(list(p_values), dtype=float)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("p_values must be a non-empty 1-D sequence")
    if np.any(~np.isfinite(p)) or np.any(p < 0) or np.any(p > 1):
        raise ValueError("p_values must all be finite and within [0, 1]")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    m = p.size
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    scaled = (m - np.arange(m)) * ranked
    # Monotone enforcement: the adjusted p-value is the running maximum of the
    # scaled values, so the sequence is non-decreasing in rank, then capped at 1.
    adjusted_sorted = np.minimum(np.maximum.accumulate(scaled), 1.0)
    adjusted = np.empty(m, dtype=float)
    adjusted[order] = adjusted_sorted

    # Step-down rejection: stop at the first failure.
    passes = ranked <= alpha / (m - np.arange(m))
    n_reject = int(np.argmin(passes)) if not passes.all() else m
    rejected_sorted = np.zeros(m, dtype=bool)
    rejected_sorted[:n_reject] = True
    rejected = np.empty(m, dtype=bool)
    rejected[order] = rejected_sorted

    return {
        "p_adjusted": adjusted,
        "rejected": rejected,
        "n_tests": m,
        "n_rejected": int(rejected.sum()),
        "alpha": alpha,
    }


RESTORED = "RESTORED"
NOT_RESTORED = "not restored"
NO_DEFICIT = "no deficit to restore"


def restoration_verdict(naive_lo: float, naive_hi: float, weighted_lo: float, weighted_hi: float,
                        nominal: float) -> dict:
    """Does rule-weighting restore coverage? Both criteria, the corrected one primary.

    **Primary — the one-sided conformal guarantee** (Sidh, 2026-09-21). Split and weighted
    conformal guarantee coverage >= 1 - alpha (Vovk et al. 2005; Tibshirani et al. 2019,
    Thm 2); the bound is one-sided, so over-coverage satisfies it and only under-coverage
    violates it. Tested on each arm's CI UPPER bound:

      * naive_hi >= nominal                  -> "no deficit to restore"
        (under-coverage was never established, so there is nothing to restore);
      * naive_hi <  nominal, weighted_hi >= nominal -> "RESTORED"
        (under-coverage established for naive, no longer establishable for weighted);
      * naive_hi <  nominal, weighted_hi <  nominal -> "not restored".

    The upper bound, not the point estimate, is used deliberately: every resampling
    scheme shares one point estimate, so a point-estimate rule would make any
    iid-versus-cluster comparison agree by construction.

    **Secondary — CI-containment**, the original E17 implementation, retained only as a
    labelled comparison. It requires nominal to lie INSIDE the weighted CI, which marks
    a conservative (over-covering) arm as a failure. That was a specification bug
    (DECISIONS.md 2026-09-21 correction), not an alternative reading of the guarantee.
    """
    vals = (naive_lo, naive_hi, weighted_lo, weighted_hi, nominal)
    if not all(np.isfinite(v) for v in vals):
        raise ValueError("CI bounds and nominal must all be finite")
    if naive_lo > naive_hi or weighted_lo > weighted_hi:
        raise ValueError("each CI must have lo <= hi")
    if not (0.0 < nominal < 1.0):
        raise ValueError(f"nominal must be in (0, 1), got {nominal}")

    if naive_hi >= nominal:
        primary = NO_DEFICIT
    elif weighted_hi >= nominal:
        primary = RESTORED
    else:
        primary = NOT_RESTORED

    naive_in = naive_lo <= nominal <= naive_hi
    weighted_in = weighted_lo <= nominal <= weighted_hi
    if naive_in and weighted_in:
        containment = NO_DEFICIT
    elif weighted_in and not naive_in:
        containment = RESTORED
    else:
        containment = NOT_RESTORED

    return {"verdict": primary, "verdict_containment": containment,
            "criteria_agree": primary == containment,
            "weighted_ci_wholly_above_nominal": bool(weighted_lo > nominal),
            "weighted_ci_wholly_below_nominal": bool(weighted_hi < nominal)}
