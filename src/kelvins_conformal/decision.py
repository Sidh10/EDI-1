"""Decision-cost evaluation under a matched alert budget — E15 (Phase 5).

Purpose: turn per-event decision scores (point predictions or one-sided upper
bounds) into maneuver/no-maneuver alerts, and score those alerts with the true
high-risk events as the primary lens and the whole population as secondary
context, with event-level bootstrap CIs.

Inputs:  per-event scores, the true high-risk indicator, an alert budget K, and
         the pre-registered cost ratios (``config.decision_cost``).
Outputs: fractional alert vectors, confusion counts, decision metrics, and
         percentile bootstrap intervals.
Serves:  EXPERIMENT_PLAN.md E15.

Protocol, fixed by the 2026-09-18 E15 design review and the E15 pre-registration
in DECISIONS.md (both written before E15 read the official test set):

  * Matched alert budget (D3). Every compared method raises exactly K alerts: the
    K events with the highest score. Events tied at the budget boundary share the
    remaining alerts equally — the EXPECTED alert under uniform random
    tie-breaking — so the rule is deterministic and exact, and no method gains or
    loses from an arbitrary tie order.
  * Cost of a decision set at ratio r (missed-high-risk : unnecessary-maneuver):
    C_r = r * FN + FP.
  * Descriptive only (D4): nothing in this module is a hypothesis test.

Two identities follow from these definitions. The E15 report relies on both, so
the test suite asserts them:

  1. Alerts depend on the score only through its ORDER. Any strictly increasing
     transform of the score — in particular ``score + c`` for a constant ``c`` —
     yields identical alerts. A split- or weighted-conformal upper bound built with
     one shared quantile is exactly such a shift of its point prediction.
  2. At a matched budget, sum(alerts) = K, so FP = K - TP and TP = n_HR - FN, hence
     C_r = (r + 1) * FN + K - n_HR. At a fixed K, ordering methods by cost is the
     same for every r and equals ordering by missed high-risk events.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .metrics import ConfusionCounts, f_beta


# --- alerting ------------------------------------------------------------------
def matched_budget_alerts(score: np.ndarray, budget: int) -> np.ndarray:
    """Fractional alert vector raising exactly ``budget`` alerts on the top scores.

    Events scoring strictly above the K-th highest score get alert 1; events tied
    AT that score share the remaining ``K - n_above`` alerts equally; the rest get
    0. ``+inf`` scores are allowed (an unbounded upper bound always ranks first);
    NaN is rejected loudly.
    """
    score = np.asarray(score, dtype=float)
    if score.ndim != 1 or score.size == 0:
        raise ValueError("score must be a non-empty 1-D array")
    if np.any(np.isnan(score)):
        raise ValueError("score contains NaN; refusing to rank (CLAUDE.md §1)")
    n = score.size
    if isinstance(budget, bool) or int(budget) != budget:
        raise ValueError(f"budget must be an integer, got {budget!r}")
    budget = int(budget)
    if not (0 <= budget <= n):
        raise ValueError(f"budget must be in [0, {n}], got {budget}")
    if budget == 0:
        return np.zeros(n, dtype=float)
    if budget == n:
        return np.ones(n, dtype=float)
    kth = np.sort(score)[n - budget]          # the K-th highest score
    above = score > kth
    tied = score == kth
    remaining = budget - int(above.sum())     # 1 <= remaining <= tied.sum()
    alerts = above.astype(float)
    alerts[tied] = remaining / int(tied.sum())
    return alerts


def budget_sweep(score: np.ndarray, is_high_risk: np.ndarray) -> dict[str, np.ndarray]:
    """Missed high-risk events and unnecessary maneuvers at EVERY budget K = 1..n.

    Identical to ``matched_budget_alerts`` followed by ``decision_counts`` at each K
    (same fractional tie sharing), but computed in one O(n log n) pass for the
    tradeoff figure: sort by score, group ties, and within the tie group holding
    the K-th alert credit each alerted slot with that group's high-risk share.
    """
    s = np.asarray(score, dtype=float)
    h = np.asarray(is_high_risk, dtype=bool)
    if s.ndim != 1 or s.size == 0 or s.shape != h.shape:
        raise ValueError("score and is_high_risk must be matching non-empty 1-D arrays")
    if np.any(np.isnan(s)):
        raise ValueError("score contains NaN; refusing to rank (CLAUDE.md §1)")
    n = s.size
    order = np.argsort(-s, kind="mergesort")
    ss = s[order]
    hh = h[order].astype(float)
    new_group = np.r_[True, ss[1:] != ss[:-1]]
    group_of = np.cumsum(new_group) - 1
    starts = np.flatnonzero(new_group)
    sizes = np.diff(np.r_[starts, n])
    group_hr = np.add.reduceat(hh, starts)
    hr_before = np.r_[0.0, np.cumsum(group_hr)[:-1]]
    budgets = np.arange(1, n + 1)
    g = group_of[budgets - 1]
    tp = hr_before[g] + (budgets - starts[g]) * group_hr[g] / sizes[g]
    return {
        "budget": budgets,
        "missed_high_risk": hh.sum() - tp,
        "unnecessary_maneuvers": budgets - tp,
    }


# --- counts and metrics -----------------------------------------------------------
@dataclass(frozen=True)
class DecisionCounts:
    """Expected confusion counts of a (possibly fractional) alert vector."""

    tp: float   # high-risk events alerted
    fn: float   # high-risk events MISSED — the E15 lead number (D1)
    fp: float   # unnecessary maneuvers
    tn: float

    @property
    def n_high_risk(self) -> float:
        return self.tp + self.fn

    @property
    def n_low_risk(self) -> float:
        return self.fp + self.tn

    @property
    def n_alerts(self) -> float:
        return self.tp + self.fp


def decision_counts(alerts: np.ndarray, is_high_risk: np.ndarray) -> DecisionCounts:
    """Confusion counts of ``alerts`` (values in [0, 1]) against the true classes."""
    a = np.asarray(alerts, dtype=float)
    h = np.asarray(is_high_risk, dtype=bool)
    if a.ndim != 1 or a.shape != h.shape:
        raise ValueError(f"alerts {a.shape} and is_high_risk {h.shape} must be matching 1-D arrays")
    if not np.all(np.isfinite(a)) or np.any(a < 0.0) or np.any(a > 1.0):
        raise ValueError("alerts must be finite and lie in [0, 1]")
    return DecisionCounts(
        tp=float(np.sum(a[h])),
        fn=float(np.sum(1.0 - a[h])),
        fp=float(np.sum(a[~h])),
        tn=float(np.sum(1.0 - a[~h])),
    )


def cost_key(ratio: float) -> str:
    """Column name for the cost at ``ratio``:1, e.g. ``cost_5to1``."""
    return f"cost_{float(ratio):g}to1"


def decision_metrics(
    counts: DecisionCounts, cost_ratios, *, beta: float = 2.0
) -> dict[str, float]:
    """Decision metrics of one alert set.

    PRIMARY — high-risk events (D1): ``missed_high_risk`` = FN (the lead number),
    ``miss_rate_high_risk`` = FN / n_HR, ``recall_high_risk`` = TP / n_HR.

    SECONDARY — whole population (D1): ``unnecessary_maneuvers`` = FP,
    ``false_positive_rate`` = FP / n_low, ``precision`` = TP / n_alerts (0 when
    nothing is alerted, the challenge convention), ``f2`` = F_beta with beta = 2
    (``metrics.f_beta``, Uriot et al. challenge definition), and
    ``cost_<r>to1`` = r * FN + FP for each pre-registered ratio r.

    A rate with an empty denominator is NaN (undefined), never silently 0.
    """
    n_hr = counts.n_high_risk
    n_lo = counts.n_low_risk
    f2 = f_beta(ConfusionCounts(tp=counts.tp, fp=counts.fp, fn=counts.fn, tn=counts.tn), beta=beta)
    out = {
        "n_alerts": counts.n_alerts,
        "n_high_risk": n_hr,
        "missed_high_risk": counts.fn,
        "miss_rate_high_risk": counts.fn / n_hr if n_hr > 0 else float("nan"),
        "recall_high_risk": counts.tp / n_hr if n_hr > 0 else float("nan"),
        "unnecessary_maneuvers": counts.fp,
        "false_positive_rate": counts.fp / n_lo if n_lo > 0 else float("nan"),
        "precision": counts.tp / counts.n_alerts if counts.n_alerts > 0 else 0.0,
        "f2": f2,
    }
    for r in cost_ratios:
        if not (r > 0):
            raise ValueError(f"cost ratios must be positive, got {r!r}")
        out[cost_key(r)] = float(r) * counts.fn + counts.fp
    return out


# --- event-level bootstrap (vectorised) ----------------------------------------
def bootstrap_count_matrix(n_events: int, n_resamples: int, seed: int) -> np.ndarray:
    """Event multiplicities for ``n_resamples`` event-level bootstrap draws.

    Row b counts how often each event appears in resample b. Draws come from
    ``np.random.default_rng(seed).integers(0, n, size=(n_resamples, n))`` — the same
    call ``conformal_runner.coverage_with_ci`` makes — so for a given seed decision
    and coverage intervals resample the SAME events (invariant I3). Summing a
    per-event quantity over a resample is then one matrix product, which keeps
    thousands of resamples times many alert sets fast.
    """
    if n_events < 1 or n_resamples < 1:
        raise ValueError("n_events and n_resamples must both be >= 1")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n_events, size=(n_resamples, n_events))
    offsets = (np.arange(n_resamples) * n_events)[:, None]
    flat = np.bincount((idx + offsets).ravel(), minlength=n_resamples * n_events)
    return flat.reshape(n_resamples, n_events).astype(float)


def _percentile_interval(draws: np.ndarray, level: float, name: str) -> dict[str, np.ndarray]:
    finite = np.isfinite(draws)
    n_valid = finite.sum(axis=0)
    if np.any(n_valid == 0):
        raise ValueError(
            f"{name} is undefined on every bootstrap resample; refusing to report an "
            "interval (fail loud, CLAUDE.md §1)"
        )
    a = 1.0 - level
    lo, hi = np.nanpercentile(np.where(finite, draws, np.nan), [100 * a / 2, 100 * (1 - a / 2)], axis=0)
    return {"lo": lo, "hi": hi, "n_undefined": draws.shape[0] - n_valid}


def bootstrap_decision_intervals(
    alerts: np.ndarray,
    is_high_risk: np.ndarray,
    cost_ratios,
    counts_matrix: np.ndarray,
    *,
    level: float = 0.95,
    beta: float = 2.0,
) -> dict[str, dict[str, np.ndarray]]:
    """Percentile bootstrap intervals for every ``decision_metrics`` quantity.

    ``alerts`` is (m, n) — m alert sets over the same n events — or a single 1-D set.
    Decisions are held FIXED at their full-sample values and the events are
    resampled (rows of ``counts_matrix``), so an interval reflects sampling
    variability in which events occur, not re-optimisation of the budget. A
    resample on which a metric is undefined (e.g. no high-risk event drawn) is
    excluded and counted, matching ``metrics.bootstrap_statistic``.

    Returns {metric: {"lo": (m,), "hi": (m,), "n_undefined": (m,)}}.
    """
    A = np.atleast_2d(np.asarray(alerts, dtype=float))
    h = np.asarray(is_high_risk, dtype=bool)
    W = np.asarray(counts_matrix, dtype=float)
    if h.ndim != 1 or A.shape[1] != h.size or W.ndim != 2 or W.shape[1] != h.size:
        raise ValueError("alerts, is_high_risk and counts_matrix must share the event axis")
    if not np.all(np.isfinite(A)) or np.any(A < 0.0) or np.any(A > 1.0):
        raise ValueError("alerts must be finite and lie in [0, 1]")
    if not (0.0 < level < 1.0):
        raise ValueError(f"level must be in (0, 1), got {level}")

    hf = h.astype(float)
    tp = W @ (A * hf).T                      # (n_resamples, m)
    fn = W @ ((1.0 - A) * hf).T
    fp = W @ (A * (1.0 - hf)).T
    tn = W @ ((1.0 - A) * (1.0 - hf)).T
    n_hr, n_lo, n_al = tp + fn, fp + tn, tp + fp
    b2 = beta * beta
    with np.errstate(divide="ignore", invalid="ignore"):
        precision = np.where(n_al > 0, tp / n_al, 0.0)
        recall = np.where(n_hr > 0, tp / n_hr, 0.0)       # f_beta's zero convention
        denom = b2 * precision + recall
        draws = {
            "n_alerts": n_al,
            "n_high_risk": n_hr,
            "missed_high_risk": fn,
            "miss_rate_high_risk": np.where(n_hr > 0, fn / n_hr, np.nan),
            "recall_high_risk": np.where(n_hr > 0, tp / n_hr, np.nan),
            "unnecessary_maneuvers": fp,
            "false_positive_rate": np.where(n_lo > 0, fp / n_lo, np.nan),
            "precision": precision,
            "f2": np.where(denom > 0, (1.0 + b2) * precision * recall / denom, 0.0),
        }
    for r in cost_ratios:
        draws[cost_key(r)] = float(r) * fn + fp
    return {name: _percentile_interval(d, level, name) for name, d in draws.items()}


def bootstrap_paired_difference(
    alerts_a: np.ndarray,
    alerts_b: np.ndarray,
    is_high_risk: np.ndarray,
    counts_matrix: np.ndarray,
    *,
    level: float = 0.95,
) -> dict[str, float]:
    """Paired bootstrap interval for missed_high_risk(a) - missed_high_risk(b).

    Both alert sets are scored on the SAME resamples, so the interval describes the
    difference itself rather than two independent intervals. Positive means ``a``
    misses more high-risk events than ``b``. Descriptive (D4): no p-value.
    """
    a = np.asarray(alerts_a, dtype=float)
    b = np.asarray(alerts_b, dtype=float)
    h = np.asarray(is_high_risk, dtype=bool)
    W = np.asarray(counts_matrix, dtype=float)
    if a.ndim != 1 or not (a.shape == b.shape == h.shape) or W.ndim != 2 or W.shape[1] != a.size:
        raise ValueError("alerts_a, alerts_b, is_high_risk and counts_matrix must share the event axis")
    delta = (b - a) * h                      # per event: missed under a minus missed under b
    draws = W @ delta
    alpha = 1.0 - level
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"point": float(delta.sum()), "lo": float(lo), "hi": float(hi)}


# --- rank-invariance audit (E15 extension) ---------------------------------------
def monotone_transform_check(reference: np.ndarray, score: np.ndarray) -> dict:
    """Is ``score`` a strictly increasing function of ``reference`` on these events?

    Proposition 1 (DECISIONS.md, E15 rank-invariance entry): the matched-budget
    alerts from ``score`` equal those from ``reference`` at EVERY budget if and only
    if the two are order-isomorphic — ``reference_i < reference_j`` exactly when
    ``score_i < score_j``, and ties exactly when ties. On a finite set that is
    precisely "``score`` is a strictly increasing function of ``reference``".

    Checked on adjacent pairs after ordering events by (reference, score):
      * ``order_violations``: the reference rises but the score does not;
      * ``tie_violations``: the reference ties but the score differs.
    Both zero is necessary and sufficient (by transitivity along the ordering).
    Non-finite values are rejected: an infinite bound has no order information.
    """
    r = np.asarray(reference, dtype=float)
    s = np.asarray(score, dtype=float)
    if r.ndim != 1 or r.size == 0 or r.shape != s.shape:
        raise ValueError("reference and score must be matching non-empty 1-D arrays")
    if not (np.all(np.isfinite(r)) and np.all(np.isfinite(s))):
        raise ValueError("reference and score must be finite")
    order = np.lexsort((s, r))               # by reference, then by score within ties
    dr = np.diff(r[order])
    ds = np.diff(s[order])
    order_violations = int(np.sum((dr > 0) & ~(ds > 0)))
    tie_violations = int(np.sum((dr == 0) & (ds != 0)))
    return {
        "strictly_increasing": order_violations == 0 and tie_violations == 0,
        "order_violations": order_violations,
        "tie_violations": tie_violations,
    }


def alert_overlap(alerts_a: np.ndarray, alerts_b: np.ndarray) -> float:
    """Shared alerts ``sum(min(a, b))`` as a fraction of ``sum(a)``; 1 means identical sets.

    Intended for two alert vectors raised at the SAME matched budget (equal sums).
    """
    a = np.asarray(alerts_a, dtype=float)
    b = np.asarray(alerts_b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape:
        raise ValueError("alert vectors must be matching 1-D arrays")
    total = float(a.sum())
    if total <= 0:
        raise ValueError("alerts_a raises no alerts; overlap is undefined")
    return float(np.minimum(a, b).sum() / total)
