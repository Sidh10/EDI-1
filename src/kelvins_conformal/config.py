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
    pc_spike: PcSpikeConfig
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
        pc_spike=pc_spike,
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
