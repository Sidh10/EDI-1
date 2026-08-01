"""Tests for config loading, type validation, and hashing (CLAUDE.md §4).

Requirements exercised:
- config loads with type validation;
- config hash is stable and changes when any value changes.
"""

from __future__ import annotations

import copy

import pytest

from kelvins_conformal.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    compute_config_hash,
    load_config,
    validate,
)


def test_default_config_loads_and_is_typed():
    cfg = load_config()
    assert cfg.seed == 42
    assert cfg.n_seeds >= 3
    assert cfg.bootstrap.n_resamples >= 2000
    assert cfg.bootstrap.unit == "event"
    # Resolved decisions must be present as typed values (not silently defaulted).
    assert cfg.target.definition == "raw_log_risk"
    assert cfg.target.include_floor is True
    assert cfg.cutoff.cutoff_days_before_tca > 0
    assert len(cfg.dataset.md5) == 32
    assert cfg.pc_spike.n_sample_cdms >= 1
    assert 0.0 < cfg.pc_spike.tolerance.min_proportion_within <= 1.0
    # E3's sampling design is declared in config, not hardcoded in the notebook.
    edges = cfg.pc_spike.risk_strata_edges
    assert len(edges) == cfg.pc_spike.n_risk_strata
    assert list(edges) == sorted(edges)
    assert edges[0] == cfg.target.floor_sentinel_value  # first stratum is the floor atom


def test_validate_rejects_unsorted_risk_strata_edges():
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    raw["pc_spike"]["risk_strata_edges"] = [-6.0, -30.0, -10.0, -15.0, 0.0]
    with pytest.raises(ConfigError, match="ascending"):
        validate(raw)


def test_validate_rejects_strata_count_mismatch():
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    raw["pc_spike"]["n_risk_strata"] = 4  # no longer matches the 5 declared edges
    with pytest.raises(ConfigError, match="n_risk_strata"):
        validate(raw)


def test_config_hash_is_deterministic():
    a = load_config().config_hash
    b = load_config().config_hash
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_config_hash_changes_when_any_value_changes():
    cfg = load_config()
    raw2 = copy.deepcopy(cfg.raw)
    raw2["seed"] = cfg.seed + 1
    assert compute_config_hash(raw2) != cfg.config_hash

    raw3 = copy.deepcopy(cfg.raw)
    raw3["pc_spike"]["tolerance"]["abs_log10_risk"] = 0.123456
    assert compute_config_hash(raw3) != cfg.config_hash


def test_config_hash_invariant_to_key_order():
    cfg = load_config()
    reordered = dict(reversed(list(cfg.raw.items())))
    assert compute_config_hash(reordered) == cfg.config_hash


def test_validate_rejects_missing_key():
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    del raw["seed"]
    with pytest.raises(ConfigError, match="seed"):
        validate(raw)


def test_validate_rejects_wrong_type():
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    raw["seed"] = "not-an-int"
    with pytest.raises(ConfigError):
        validate(raw)


def test_validate_rejects_bool_as_int():
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    raw["seed"] = True  # bool is an int subclass; must be rejected explicitly
    with pytest.raises(ConfigError):
        validate(raw)


def test_validate_rejects_bad_md5():
    cfg = load_config()
    raw = copy.deepcopy(cfg.raw)
    raw["dataset"]["md5"] = "tooshort"
    with pytest.raises(ConfigError, match="md5"):
        validate(raw)


def test_overrides_deep_merge():
    cfg = load_config(overrides={"pc_spike": {"n_sample_cdms": 7}})
    assert cfg.pc_spike.n_sample_cdms == 7
    # Sibling keys under the same subtree are preserved by the deep merge.
    assert cfg.pc_spike.tolerance.abs_log10_risk == load_config().pc_spike.tolerance.abs_log10_risk


def test_default_config_path_exists():
    assert DEFAULT_CONFIG_PATH.exists()
