"""Typed configuration loading and hashing.

Responsibility (SOFTWARE_ARCHITECTURE.md §2): load ``config/default.yaml`` (plus
optional experiment overrides) into a validated, typed object, and produce a
stable content hash that stamps every artifact (invariant I4). The hash MUST
change if and only if some configuration value changes — this is what makes an
experiment's identity reproducible (CLAUDE.md §9).

Boring on purpose (CLAUDE.md §1): explicit dataclasses, explicit validation, no
dynamic attribute magic a reviewer would have to reverse-engineer.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Repo root = three parents up from this file (src/kelvins_conformal/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


class ConfigError(ValueError):
    """Raised when configuration is missing keys or has wrong-typed values.

    Fail loud, fail early (CLAUDE.md §1): a malformed config aborts immediately
    rather than silently defaulting.
    """


# --- Typed views over the config tree ---------------------------------------
# These dataclasses are thin, validated windows onto the raw dict. The raw dict
# is retained (Config.raw) so the hash covers *everything*, including keys not yet
# surfaced as typed fields (e.g. later-phase settings).


@dataclass(frozen=True)
class BootstrapConfig:
    n_resamples: int
    unit: str


@dataclass(frozen=True)
class DatasetConfig:
    doi: str
    url: str
    zip_filename: str
    md5: str


@dataclass(frozen=True)
class TargetConfig:
    column: str
    definition: str
    include_floor: bool
    per_event: str
    floor_sentinel_value: float


@dataclass(frozen=True)
class CutoffConfig:
    cutoff_days_before_tca: float
    test_recency_filter_days: float
    min_cdms_per_event: int


@dataclass(frozen=True)
class MetricConfig:
    """The challenge metric's own constants (Uriot et al. §4.1, §4.3)."""

    f_beta: float
    prediction_clip_epsilon: float
    f2_zero_convention: str
    empty_high_risk_convention: str


@dataclass(frozen=True)
class BaselinesConfig:
    constant_value: float


@dataclass(frozen=True)
class PowerConfig:
    """E4 power-analysis settings (pre-registered; see DECISIONS.md)."""

    nominal_coverage_primary: float
    nominal_coverage_secondary: tuple[float, ...]
    calibration_fractions: tuple[float, ...]
    useful_half_width_pp: float
    secondary_half_width_pp: float
    n_simulations: int
    group_size_grid: tuple[int, ...]


@dataclass(frozen=True)
class FeaturesConfig:
    """Feature-building policy, governed by feature_dictionary.yaml (E2)."""

    last_k: int
    max_sequence_length: int
    risk_history: bool
    include_ambiguous: bool
    hard_excluded: tuple[str, ...]


@dataclass(frozen=True)
class ModelSplitConfig:
    inner_validation_fraction: float


@dataclass(frozen=True)
class TrainConfig:
    n_seeds: int
    seeds: tuple[int, ...]
    hpo_budget_trials: int
    early_stopping_rounds: int


@dataclass(frozen=True)
class GbmConfig:
    quantile_levels: tuple[float, ...]
    num_boost_round: int


@dataclass(frozen=True)
class DecisionRuleConfig:
    """Validation-selected promotion threshold shared by E6/E7/E8."""

    promotion_thresholds: tuple[float, ...]
    promotion_margin: float


@dataclass(frozen=True)
class SequenceConfig:
    cell: str
    hidden_size: int
    num_layers: int
    dropout: float
    batch_size: int
    max_epochs: int
    learning_rate: float


@dataclass(frozen=True)
class BayesianConfig:
    n_mc_samples: int
    ensemble_size: int
    nominal_levels: tuple[float, ...]


@dataclass(frozen=True)
class PcToleranceConfig:
    abs_log10_risk: float
    min_proportion_within: float


@dataclass(frozen=True)
class PcSpikeConfig:
    n_sample_cdms: int
    n_risk_strata: int
    risk_strata_edges: tuple[float, ...]
    tolerance: PcToleranceConfig


@dataclass(frozen=True)
class LabelNoiseFailureConfig:
    """EXPERIMENT_PLAN E14's failure criterion, instantiated in advance.

    Values fixed by the 2026-09-16 E14 pre-registration (DECISIONS.md) BEFORE the
    official test set was read, so none of them can have been chosen to avoid
    firing (CLAUDE.md §3).
    """

    min_eligible_fraction: float
    min_eligible_high_risk: int
    representativeness_ks_alpha: float
    representativeness_max_prevalence_diff_pp: float


@dataclass(frozen=True)
class LabelNoiseConfig:
    """E14 label-noise sensitivity settings (Phase 4, Gate 3).

    ``scaling_grid`` multiplies the COMBINED position covariance (Q-LBL-02 option
    (a)); it is a variance scale, so sigmas scale by its square root.
    """

    scaling_grid: tuple[float, ...]
    n_radial: int
    n_angular: int
    evaluation_only: bool
    focus_stratum_uses_original_label: bool
    failure_criteria: LabelNoiseFailureConfig


@dataclass(frozen=True)
class DecisionCostConfig:
    """E15 decision-cost settings (Phase 5).

    Fixed by the 2026-09-18 E15 design review (Sidh) and the E15 pre-registration
    in DECISIONS.md, both written before E15 read the official test set
    (CLAUDE.md §3). ``cost_ratios`` are missed-high-risk : unnecessary-maneuver
    costs and the budgets are matched alert counts (D3); ``bound_side`` must be
    ``"upper"`` (D2).
    """

    cost_ratios: tuple[float, ...]
    budget_fractions: tuple[float, ...]
    include_prevalence_matched_budget: bool
    primary_budget: str
    bound_side: str


@dataclass(frozen=True)
class ThresholdAnalysisConfig:
    """Expanded E15 threshold-based analysis settings (absorbs E16).

    Fixed by the 2026-09-18 PRE-REGISTRATION "expanded threshold-based decision
    analysis" in DECISIONS.md, written before any threshold result existed
    (CLAUDE.md §3), as revised by Sidh's 2026-09-19 decisions: ``horizons_days`` is
    {2-day, 3-day}, both on the official test set (Q-METH-04), starting at this
    config's own cutoff (a per-horizon derived config carries exactly one horizon);
    ``grid_source_split`` is the internal validation split. ``smoke_*`` define the
    reduced configuration used ONLY to validate and time the pipeline
    (pre-registration §9).
    """

    grid_percentiles: tuple[float, ...]
    operational_thresholds: tuple[float, ...]
    horizons_days: tuple[float, ...]
    selection_split: str
    selection_tie_break: str
    exclude_persistence_one_sided: bool
    smoke_seeds: tuple[int, ...]
    smoke_grid_percentiles: tuple[float, ...]
    grid_source_split: str


@dataclass(frozen=True)
class Config:
    """Validated configuration with a stable content hash.

    ``raw`` is the full parsed YAML (deep-copied, immutable in spirit); the typed
    fields are validated conveniences. ``config_hash`` is computed over ``raw``.
    """

    raw: dict[str, Any]
    seed: int
    n_seeds: int
    bootstrap: BootstrapConfig
    paths: dict[str, str]
    dataset: DatasetConfig
    target: TargetConfig
    cutoff: CutoffConfig
    high_risk_threshold: float
    metric: MetricConfig
    baselines: BaselinesConfig
    baseline_validation: dict[str, Any]
    power: PowerConfig
    features: FeaturesConfig
    model_split: ModelSplitConfig
    train: TrainConfig
    gbm: GbmConfig
    decision_rule: DecisionRuleConfig
    sequence: SequenceConfig
    bayesian: BayesianConfig
    pc_spike: PcSpikeConfig
    labelnoise: LabelNoiseConfig
    decision_cost: DecisionCostConfig
    threshold_analysis: ThresholdAnalysisConfig
    config_hash: str = field(compare=False)

    # --- path helpers (resolved against repo root) --------------------------
    def path(self, key: str) -> Path:
        """Return an absolute Path for a key under ``paths:``."""
        if key not in self.paths:
            raise ConfigError(f"Unknown path key: {key!r}. Known: {sorted(self.paths)}")
        return (REPO_ROOT / self.paths[key]).resolve()


def _require(d: dict[str, Any], key: str, typ: type | tuple[type, ...], ctx: str) -> Any:
    if key not in d:
        raise ConfigError(f"Missing required config key: {ctx}.{key}")
    val = d[key]
    # bool is a subclass of int; guard against silently accepting True as an int.
    if typ is int and isinstance(val, bool):
        raise ConfigError(f"Config key {ctx}.{key} must be int, got bool: {val!r}")
    if not isinstance(val, typ):
        tname = typ.__name__ if isinstance(typ, type) else typ
        raise ConfigError(
            f"Config key {ctx}.{key} must be {tname}, got {type(val).__name__}: {val!r}"
        )
    return val


def _as_float(d: dict[str, Any], key: str, ctx: str) -> float:
    val = _require(d, key, (int, float), ctx)
    if isinstance(val, bool):
        raise ConfigError(f"Config key {ctx}.{key} must be a number, got bool")
    return float(val)


def compute_config_hash(raw: dict[str, Any]) -> str:
    """Deterministic content hash of the raw config.

    Canonical JSON (sorted keys, no whitespace ambiguity) -> SHA-256. Any change
    to any value or key changes the hash; key ordering in the YAML does not.
    """
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base`` (override wins)."""
    out = copy.deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def validate(raw: dict[str, Any]) -> Config:
    """Validate a raw config dict into a typed Config (raising ConfigError)."""
    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level config must be a mapping, got {type(raw).__name__}")

    seed = _require(raw, "seed", int, "root")
    n_seeds = _require(raw, "n_seeds", int, "root")

    bs_raw = _require(raw, "bootstrap", dict, "root")
    bootstrap = BootstrapConfig(
        n_resamples=_require(bs_raw, "n_resamples", int, "bootstrap"),
        unit=_require(bs_raw, "unit", str, "bootstrap"),
    )

    paths_raw = _require(raw, "paths", dict, "root")
    for pk, pv in paths_raw.items():
        if not isinstance(pv, str):
            raise ConfigError(f"paths.{pk} must be a string, got {type(pv).__name__}")

    ds_raw = _require(raw, "dataset", dict, "root")
    dataset = DatasetConfig(
        doi=_require(ds_raw, "doi", str, "dataset"),
        url=_require(ds_raw, "url", str, "dataset"),
        zip_filename=_require(ds_raw, "zip_filename", str, "dataset"),
        md5=_require(ds_raw, "md5", str, "dataset"),
    )
    if len(dataset.md5) != 32 or not all(c in "0123456789abcdef" for c in dataset.md5.lower()):
        raise ConfigError(f"dataset.md5 is not a 32-char hex md5: {dataset.md5!r}")

    tg_raw = _require(raw, "target", dict, "root")
    target = TargetConfig(
        column=_require(tg_raw, "column", str, "target"),
        definition=_require(tg_raw, "definition", str, "target"),
        include_floor=_require(tg_raw, "include_floor", bool, "target"),
        per_event=_require(tg_raw, "per_event", str, "target"),
        floor_sentinel_value=_as_float(tg_raw, "floor_sentinel_value", "target"),
    )

    ct_raw = _require(raw, "cutoff", dict, "root")
    cutoff = CutoffConfig(
        cutoff_days_before_tca=_as_float(ct_raw, "cutoff_days_before_tca", "cutoff"),
        test_recency_filter_days=_as_float(ct_raw, "test_recency_filter_days", "cutoff"),
        min_cdms_per_event=_require(ct_raw, "min_cdms_per_event", int, "cutoff"),
    )

    high_risk_threshold = _as_float(raw, "high_risk_threshold", "root")

    mt_raw = _require(raw, "metric", dict, "root")
    metric = MetricConfig(
        f_beta=_as_float(mt_raw, "f_beta", "metric"),
        prediction_clip_epsilon=_as_float(mt_raw, "prediction_clip_epsilon", "metric"),
        f2_zero_convention=_require(mt_raw, "f2_zero_convention", str, "metric"),
        empty_high_risk_convention=_require(
            mt_raw, "empty_high_risk_convention", str, "metric"
        ),
    )
    if metric.f2_zero_convention != "infinite":
        raise ConfigError(
            "metric.f2_zero_convention: only 'infinite' is implemented "
            f"(METRICS.md §1 convention), got {metric.f2_zero_convention!r}"
        )
    if metric.empty_high_risk_convention != "undefined":
        raise ConfigError(
            "metric.empty_high_risk_convention: only 'undefined' is implemented "
            f"(METRICS.md §1/§3 convention), got {metric.empty_high_risk_convention!r}"
        )

    bl_raw = _require(raw, "baselines", dict, "root")
    baselines = BaselinesConfig(
        constant_value=_as_float(bl_raw, "constant_value", "baselines"),
    )

    bv_raw = _require(raw, "baseline_validation", dict, "root")
    for section in ("published", "tolerance"):
        _require(bv_raw, section, dict, "baseline_validation")

    pw_raw = _require(raw, "power", dict, "root")

    def _num_tuple(d: dict[str, Any], key: str, ctx: str) -> tuple[float, ...]:
        seq = _require(d, key, list, ctx)
        if not seq or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in seq
        ):
            raise ConfigError(f"{ctx}.{key} must be a non-empty list of numbers")
        return tuple(float(v) for v in seq)

    power = PowerConfig(
        nominal_coverage_primary=_as_float(pw_raw, "nominal_coverage_primary", "power"),
        nominal_coverage_secondary=_num_tuple(pw_raw, "nominal_coverage_secondary", "power"),
        calibration_fractions=_num_tuple(pw_raw, "calibration_fractions", "power"),
        useful_half_width_pp=_as_float(pw_raw, "useful_half_width_pp", "power"),
        secondary_half_width_pp=_as_float(pw_raw, "secondary_half_width_pp", "power"),
        n_simulations=_require(pw_raw, "n_simulations", int, "power"),
        group_size_grid=tuple(int(v) for v in _num_tuple(pw_raw, "group_size_grid", "power")),
    )
    for level in (power.nominal_coverage_primary, *power.nominal_coverage_secondary):
        if not (0.0 < level < 1.0):
            raise ConfigError(f"power coverage levels must be in (0, 1), got {level}")
    for frac in power.calibration_fractions:
        if not (0.0 < frac < 1.0):
            raise ConfigError(f"power.calibration_fractions must be in (0, 1), got {frac}")

    ft_raw = _require(raw, "features", dict, "root")
    excl = _require(ft_raw, "hard_excluded", list, "features")
    if not all(isinstance(c, str) for c in excl):
        raise ConfigError("features.hard_excluded must be a list of column names")
    features = FeaturesConfig(
        last_k=_require(ft_raw, "last_k", int, "features"),
        max_sequence_length=_require(ft_raw, "max_sequence_length", int, "features"),
        risk_history=_require(ft_raw, "risk_history", bool, "features"),
        include_ambiguous=_require(ft_raw, "include_ambiguous", bool, "features"),
        hard_excluded=tuple(excl),
    )
    if features.last_k < 1:
        raise ConfigError(f"features.last_k must be >= 1, got {features.last_k}")
    if features.max_sequence_length < 1:
        raise ConfigError("features.max_sequence_length must be >= 1")

    ms_raw = _require(raw, "model_split", dict, "root")
    model_split = ModelSplitConfig(
        inner_validation_fraction=_as_float(
            ms_raw, "inner_validation_fraction", "model_split"
        ),
    )
    if not (0.0 < model_split.inner_validation_fraction < 1.0):
        raise ConfigError("model_split.inner_validation_fraction must be in (0, 1)")

    tr_raw = _require(raw, "train", dict, "root")
    seeds_raw = _require(tr_raw, "seeds", list, "train")
    if not seeds_raw or not all(
        isinstance(s, int) and not isinstance(s, bool) for s in seeds_raw
    ):
        raise ConfigError("train.seeds must be a non-empty list of ints")
    train = TrainConfig(
        n_seeds=_require(tr_raw, "n_seeds", int, "train"),
        seeds=tuple(int(s) for s in seeds_raw),
        hpo_budget_trials=_require(tr_raw, "hpo_budget_trials", int, "train"),
        early_stopping_rounds=_require(tr_raw, "early_stopping_rounds", int, "train"),
    )
    if len(train.seeds) < train.n_seeds:
        raise ConfigError(
            f"train.seeds lists {len(train.seeds)} seeds but n_seeds={train.n_seeds}"
        )
    if train.n_seeds < 3:
        raise ConfigError("train.n_seeds must be >= 3 for manuscript results (CLAUDE.md §9)")

    gb_raw = _require(raw, "gbm", dict, "root")
    q_raw = _require(gb_raw, "quantile_levels", list, "gbm")
    if not q_raw or not all(
        isinstance(q, (int, float)) and not isinstance(q, bool) and 0.0 < q < 1.0
        for q in q_raw
    ):
        raise ConfigError("gbm.quantile_levels must be a non-empty list of floats in (0, 1)")
    quantiles = tuple(float(q) for q in q_raw)
    if list(quantiles) != sorted(quantiles):
        raise ConfigError(f"gbm.quantile_levels must be ascending, got {quantiles}")
    gbm = GbmConfig(
        quantile_levels=quantiles,
        num_boost_round=_require(gb_raw, "num_boost_round", int, "gbm"),
    )

    dr_raw = _require(raw, "decision_rule", dict, "root")
    pt_raw = _require(dr_raw, "promotion_thresholds", list, "decision_rule")
    if not pt_raw or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in pt_raw
    ):
        raise ConfigError("decision_rule.promotion_thresholds must be a non-empty numeric list")
    decision_rule = DecisionRuleConfig(
        promotion_thresholds=tuple(float(v) for v in pt_raw),
        promotion_margin=_as_float(dr_raw, "promotion_margin", "decision_rule"),
    )
    if decision_rule.promotion_margin <= 0:
        raise ConfigError("decision_rule.promotion_margin must be > 0")

    sq_raw = _require(raw, "sequence", dict, "root")
    sequence = SequenceConfig(
        cell=_require(sq_raw, "cell", str, "sequence"),
        hidden_size=_require(sq_raw, "hidden_size", int, "sequence"),
        num_layers=_require(sq_raw, "num_layers", int, "sequence"),
        dropout=_as_float(sq_raw, "dropout", "sequence"),
        batch_size=_require(sq_raw, "batch_size", int, "sequence"),
        max_epochs=_require(sq_raw, "max_epochs", int, "sequence"),
        learning_rate=_as_float(sq_raw, "learning_rate", "sequence"),
    )
    if sequence.cell not in ("gru", "lstm"):
        raise ConfigError(f"sequence.cell must be 'gru' or 'lstm', got {sequence.cell!r}")
    if not (0.0 <= sequence.dropout < 1.0):
        raise ConfigError(f"sequence.dropout must be in [0, 1), got {sequence.dropout}")

    by_raw = _require(raw, "bayesian", dict, "root")
    lv_raw = _require(by_raw, "nominal_levels", list, "bayesian")
    if not lv_raw or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 < v < 1.0
        for v in lv_raw
    ):
        raise ConfigError("bayesian.nominal_levels must be a non-empty list of floats in (0, 1)")
    bayesian = BayesianConfig(
        n_mc_samples=_require(by_raw, "n_mc_samples", int, "bayesian"),
        ensemble_size=_require(by_raw, "ensemble_size", int, "bayesian"),
        nominal_levels=tuple(float(v) for v in lv_raw),
    )

    ps_raw = _require(raw, "pc_spike", dict, "root")
    tol_raw = _require(ps_raw, "tolerance", dict, "pc_spike")
    edges_raw = _require(ps_raw, "risk_strata_edges", list, "pc_spike")
    if not all(isinstance(e, (int, float)) and not isinstance(e, bool) for e in edges_raw):
        raise ConfigError("pc_spike.risk_strata_edges must be a list of numbers")
    edges = tuple(float(e) for e in edges_raw)
    if list(edges) != sorted(edges):
        raise ConfigError(f"pc_spike.risk_strata_edges must be ascending, got {edges}")
    pc_spike = PcSpikeConfig(
        n_sample_cdms=_require(ps_raw, "n_sample_cdms", int, "pc_spike"),
        n_risk_strata=_require(ps_raw, "n_risk_strata", int, "pc_spike"),
        risk_strata_edges=edges,
        tolerance=PcToleranceConfig(
            abs_log10_risk=_as_float(tol_raw, "abs_log10_risk", "pc_spike.tolerance"),
            min_proportion_within=_as_float(
                tol_raw, "min_proportion_within", "pc_spike.tolerance"
            ),
        ),
    )
    if not (0.0 < pc_spike.tolerance.min_proportion_within <= 1.0):
        raise ConfigError("pc_spike.tolerance.min_proportion_within must be in (0, 1]")
    # The strata are: the floor atom (risk == edges[0]) plus the len(edges)-1 open-closed
    # bands between consecutive edges. That totals len(edges) strata, so the declared
    # n_risk_strata must agree — a mismatch means the sampling design is inconsistent.
    if len(pc_spike.risk_strata_edges) != pc_spike.n_risk_strata:
        raise ConfigError(
            f"pc_spike: n_risk_strata={pc_spike.n_risk_strata} but "
            f"{len(pc_spike.risk_strata_edges)} risk_strata_edges were given "
            "(expected one edge per stratum: floor atom + inter-edge bands)"
        )

    ln_raw = _require(raw, "labelnoise", dict, "root")
    grid_raw = _require(ln_raw, "scaling_grid", list, "labelnoise")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in grid_raw):
        raise ConfigError("labelnoise.scaling_grid must be a list of numbers")
    grid = tuple(float(v) for v in grid_raw)
    if not grid:
        raise ConfigError("labelnoise.scaling_grid must not be empty")
    if any(s <= 0 for s in grid):
        raise ConfigError(f"labelnoise.scaling_grid factors must be positive, got {grid}")
    if list(grid) != sorted(grid):
        raise ConfigError(f"labelnoise.scaling_grid must be ascending, got {grid}")
    # The s = 1.0 anchor is what separates a rescaling effect from a recomputation
    # offset; a grid without it cannot support either curve the pre-registration
    # declares, so its absence is a config error rather than a silent degradation.
    if not any(abs(s - 1.0) < 1e-12 for s in grid):
        raise ConfigError("labelnoise.scaling_grid must contain the 1.0 anchor")
    int_raw = _require(ln_raw, "integration", dict, "labelnoise")
    fail_raw = _require(ln_raw, "failure_criteria", dict, "labelnoise")
    labelnoise = LabelNoiseConfig(
        scaling_grid=grid,
        n_radial=_require(int_raw, "n_radial", int, "labelnoise.integration"),
        n_angular=_require(int_raw, "n_angular", int, "labelnoise.integration"),
        evaluation_only=_require(ln_raw, "evaluation_only", bool, "labelnoise"),
        focus_stratum_uses_original_label=_require(
            ln_raw, "focus_stratum_uses_original_label", bool, "labelnoise"
        ),
        failure_criteria=LabelNoiseFailureConfig(
            min_eligible_fraction=_as_float(
                fail_raw, "min_eligible_fraction", "labelnoise.failure_criteria"
            ),
            min_eligible_high_risk=_require(
                fail_raw, "min_eligible_high_risk", int, "labelnoise.failure_criteria"
            ),
            representativeness_ks_alpha=_as_float(
                fail_raw, "representativeness_ks_alpha", "labelnoise.failure_criteria"
            ),
            representativeness_max_prevalence_diff_pp=_as_float(
                fail_raw,
                "representativeness_max_prevalence_diff_pp",
                "labelnoise.failure_criteria",
            ),
        ),
    )
    if not (0.0 < labelnoise.failure_criteria.min_eligible_fraction <= 1.0):
        raise ConfigError("labelnoise.failure_criteria.min_eligible_fraction must be in (0, 1]")
    if min(labelnoise.n_radial, labelnoise.n_angular) < 1:
        raise ConfigError("labelnoise.integration resolutions must be >= 1")
    # Q-LBL-03 was resolved evaluation-only; a config that flips this would silently
    # change what E14 measures, so it must fail loudly instead (CLAUDE.md §1).
    if not labelnoise.evaluation_only:
        raise ConfigError(
            "labelnoise.evaluation_only=false is not implemented: Q-LBL-03 was "
            "resolved (a) evaluation-only (DECISIONS.md 2026-09-16). Retraining on "
            "rescaled labels is logged as future work, not a supported code path."
        )

    dc_raw = _require(raw, "decision_cost", dict, "root")
    ratios_raw = _require(dc_raw, "cost_ratios", list, "decision_cost")
    fractions_raw = _require(dc_raw, "budget_fractions", list, "decision_cost")
    for name, values in (("cost_ratios", ratios_raw), ("budget_fractions", fractions_raw)):
        if not values or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
        ):
            raise ConfigError(f"decision_cost.{name} must be a non-empty list of numbers")
    decision_cost = DecisionCostConfig(
        cost_ratios=tuple(float(v) for v in ratios_raw),
        budget_fractions=tuple(float(v) for v in fractions_raw),
        include_prevalence_matched_budget=_require(
            dc_raw, "include_prevalence_matched_budget", bool, "decision_cost"
        ),
        primary_budget=_require(dc_raw, "primary_budget", str, "decision_cost"),
        bound_side=_require(dc_raw, "bound_side", str, "decision_cost"),
    )
    if any(r <= 0 for r in decision_cost.cost_ratios):
        raise ConfigError(
            f"decision_cost.cost_ratios must be positive, got {decision_cost.cost_ratios}"
        )
    if any(not (0.0 < f < 1.0) for f in decision_cost.budget_fractions):
        raise ConfigError(
            f"decision_cost.budget_fractions must lie in (0, 1), got {decision_cost.budget_fractions}"
        )
    # D2 (DECISIONS.md, 2026-09-18 E15 design review): the one-sided upper bound is
    # used directly. Any other sidedness would silently change what E15 measures.
    if decision_cost.bound_side != "upper":
        raise ConfigError(
            "decision_cost.bound_side must be 'upper': the E15 design review (D2) fixed the "
            "one-sided upper bound and forbids substituting the two-sided upper edge"
        )
    # Pre-registration §2: the prevalence-matched budget is the one primary point.
    if (decision_cost.primary_budget != "prevalence_matched"
            or not decision_cost.include_prevalence_matched_budget):
        raise ConfigError(
            "decision_cost.primary_budget must be 'prevalence_matched', with "
            "include_prevalence_matched_budget: true (E15 pre-registration §2)"
        )

    ta_raw = _require(raw, "threshold_analysis", dict, "root")
    ta_lists = {}
    for name in ("grid_percentiles", "operational_thresholds", "horizons_days", "smoke_grid_percentiles"):
        values = _require(ta_raw, name, list, "threshold_analysis")
        if not values or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            raise ConfigError(f"threshold_analysis.{name} must be a non-empty list of numbers")
        ta_lists[name] = tuple(float(v) for v in values)
    smoke_seeds_raw = _require(ta_raw, "smoke_seeds", list, "threshold_analysis")
    if not smoke_seeds_raw or not all(isinstance(v, int) and not isinstance(v, bool) for v in smoke_seeds_raw):
        raise ConfigError("threshold_analysis.smoke_seeds must be a non-empty list of integers")
    threshold_analysis = ThresholdAnalysisConfig(
        grid_percentiles=ta_lists["grid_percentiles"],
        operational_thresholds=ta_lists["operational_thresholds"],
        horizons_days=ta_lists["horizons_days"],
        selection_split=_require(ta_raw, "selection_split", str, "threshold_analysis"),
        selection_tie_break=_require(ta_raw, "selection_tie_break", str, "threshold_analysis"),
        exclude_persistence_one_sided=_require(ta_raw, "exclude_persistence_one_sided", bool, "threshold_analysis"),
        smoke_seeds=tuple(int(v) for v in smoke_seeds_raw),
        smoke_grid_percentiles=ta_lists["smoke_grid_percentiles"],
        grid_source_split=_require(ta_raw, "grid_source_split", str, "threshold_analysis"),
    )
    for name in ("grid_percentiles", "smoke_grid_percentiles"):
        pct = getattr(threshold_analysis, name)
        if any(not (0.0 < v < 100.0) for v in pct) or list(pct) != sorted(pct):
            raise ConfigError(f"threshold_analysis.{name} must be ascending values strictly inside (0, 100)")
    if not any(abs(t - high_risk_threshold) < 1e-12 for t in threshold_analysis.operational_thresholds):
        raise ConfigError(
            "threshold_analysis.operational_thresholds must include the challenge high-risk threshold "
            "(pre-registration §2)"
        )
    # Q-METH-04 (resolved by Sidh, 2026-09-19): horizons {2-day, 3-day}, both on the official
    # test set. The list starts at this config's own cutoff (a per-horizon derived config carries
    # exactly one horizon, equal to its cutoff) and rises strictly. A horizon below the cutoff -
    # e.g. the infeasible 1-day horizon, since the official test set has no CDM between 1 and 2
    # days before TCA - fails loudly instead of silently degenerating.
    hz = threshold_analysis.horizons_days
    if hz[0] != float(cutoff.cutoff_days_before_tca) or any(b <= a for a, b in zip(hz, hz[1:], strict=False)):
        raise ConfigError(
            "threshold_analysis.horizons_days must start at cutoff.cutoff_days_before_tca and be "
            "strictly ascending (Q-METH-04, resolved 2026-09-19); a horizon below the cutoff cannot "
            "be built on the official test set"
        )
    # Sidh, 2026-09-19 (Decision 3): the grid is built on the training pool's internal
    # validation split only; the official test set never selects it.
    if threshold_analysis.grid_source_split != "val_inner":
        raise ConfigError(
            "threshold_analysis.grid_source_split must be 'val_inner' (Sidh's 2026-09-19 decision: "
            "grid built on the internal validation split only)"
        )
    if threshold_analysis.selection_split != "self_test":
        raise ConfigError("threshold_analysis.selection_split must be 'self_test' (pre-registration §4)")
    if threshold_analysis.selection_tie_break != "highest_threshold":
        raise ConfigError("threshold_analysis.selection_tie_break must be 'highest_threshold' (pre-registration §9)")

    return Config(
        raw=copy.deepcopy(raw),
        seed=seed,
        n_seeds=n_seeds,
        bootstrap=bootstrap,
        paths=dict(paths_raw),
        dataset=dataset,
        target=target,
        cutoff=cutoff,
        high_risk_threshold=high_risk_threshold,
        metric=metric,
        baselines=baselines,
        baseline_validation=copy.deepcopy(bv_raw),
        power=power,
        features=features,
        model_split=model_split,
        train=train,
        gbm=gbm,
        decision_rule=decision_rule,
        sequence=sequence,
        bayesian=bayesian,
        pc_spike=pc_spike,
        labelnoise=labelnoise,
        decision_cost=decision_cost,
        threshold_analysis=threshold_analysis,
        config_hash=compute_config_hash(raw),
    )


def load_config(
    path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Config:
    """Load, optionally override, validate, and hash the configuration.

    Parameters
    ----------
    path:
        Path to a YAML config. Defaults to ``config/default.yaml``.
    overrides:
        Optional experiment overrides (deep-merged over the base) — used by
        ``config/experiments/*.yaml`` in later phases.
    """
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise ConfigError(f"Config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ConfigError(f"Config at {cfg_path} did not parse to a mapping")
    if overrides:
        raw = _deep_merge(raw, overrides)
    return validate(raw)
