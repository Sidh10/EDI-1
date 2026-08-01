"""Feature-safety tests: no dictionary-unsafe column may reach a feature set.

CLAUDE.md §4 requires a leakage test, and the Phase-2 brief requires this to be a
**hard assertion, not a lint warning**. The checks below fail the build, not just
the suite: ``features.assert_feature_safety`` runs inside every build call, so a
leak aborts the pipeline.

Covered:
  1. `event_id` and `risk` (the dictionary's two `unsafe` verdicts) never appear.
  2. The two `ambiguous` columns are excluded by default (the dictionary's own
     stated conservative option) and only appear when explicitly opted in.
  3. The target column and event bookkeeping never appear.
  4. A derived column cannot smuggle a barred source through under a new name.
  5. Only pre-cutoff CDMs contribute — a post-cutoff value cannot influence a row.
  6. The dictionary covers exactly the parsed schema (kept in sync, CLAUDE.md §6).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal import features as feat
from kelvins_conformal.config import load_config
from kelvins_conformal.features import FeatureSafetyError


def _synthetic_events(n_events: int = 60, seed: int = 0) -> pd.DataFrame:
    """Minimal event table carrying every column the builder inspects."""
    rng = np.random.default_rng(seed)
    from kelvins_conformal.data import COLUMNS_103

    rows = []
    for e in range(n_events):
        n_cdms = int(rng.integers(3, 8))
        times = np.sort(rng.uniform(0.1, 6.5, size=n_cdms))[::-1]
        risks = rng.normal(-12.0, 5.0, size=n_cdms)
        for i, (t, r) in enumerate(zip(times, risks, strict=True)):
            row = {c: float(rng.normal()) for c in COLUMNS_103}
            row.update({
                "event_id": e, "time_to_tca": float(t), "risk": float(r),
                "mission_id": int(e % 5), "c_object_type": 1.0,
                "event_uid": f"train_{e}", "split": "train", "cdm_index": i,
                "n_cdms": n_cdms, "target_log_risk": float(risks[-1]),
                "target_time_to_tca": float(times[-1]),
                "is_high_risk": bool(risks[-1] >= -6.0),
            })
            rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def events():
    return _synthetic_events()


# --- 1. unsafe columns never appear -------------------------------------------
def test_unsafe_columns_absent_from_tabular_features(cfg, events):
    fm = feat.build_tabular_features(events, cfg, split="train")
    for barred in ("event_id", "risk"):
        assert barred not in fm.X.columns, f"{barred} leaked into the feature matrix"
    # and not as a bare column under any aggregation of event_id either
    assert not any(c.startswith("event_id") for c in fm.X.columns)


def test_every_dictionary_unsafe_column_is_absent(cfg, events):
    """Driven off the dictionary itself, so new unsafe verdicts are covered."""
    d = feat.load_feature_dictionary()
    unsafe = {c for c, v in d["features"].items() if v["leakage_class"] == "unsafe"}
    assert unsafe, "expected the dictionary to mark at least one column unsafe"

    fm = feat.build_tabular_features(events, cfg, split="train")
    for col in fm.X.columns:
        assert col not in unsafe, f"unsafe column {col!r} reached the feature matrix"


def test_assert_feature_safety_rejects_unsafe_column(cfg):
    with pytest.raises(FeatureSafetyError, match="event_id"):
        feat.assert_feature_safety(["miss_distance_last", "event_id"], cfg)


def test_assert_feature_safety_rejects_raw_risk(cfg):
    with pytest.raises(FeatureSafetyError, match="risk"):
        feat.assert_feature_safety(["risk"], cfg)


# --- 2. ambiguous columns --------------------------------------------------------
def test_ambiguous_columns_excluded_by_default(cfg, events):
    """The dictionary's own conservative option is exclusion; that is the default."""
    assert cfg.features.include_ambiguous is False
    fm = feat.build_tabular_features(events, cfg, split="train")
    for amb in ("max_risk_estimate", "max_risk_scaling"):
        assert not any(c.startswith(amb) for c in fm.X.columns), (
            f"ambiguous column {amb} appeared despite the conservative default"
        )


def test_ambiguous_columns_admitted_only_when_opted_in(events):
    permissive = load_config(overrides={"features": {"include_ambiguous": True}})
    fm = feat.build_tabular_features(events, permissive, split="train")
    assert any(c.startswith("max_risk_estimate") for c in fm.X.columns)


def test_classify_columns_partitions_the_whole_dictionary(cfg):
    d = feat.load_feature_dictionary()
    classes = feat.classify_columns(cfg, d)
    total = sum(len(v) for v in classes.values())
    assert total == len(d["features"]) == 103
    assert set(classes["hard_excluded"]) == {"event_id", "risk"}
    assert set(classes["ambiguous_excluded"]) == {"max_risk_estimate", "max_risk_scaling"}


# --- 3. target and bookkeeping ---------------------------------------------------
def test_target_and_bookkeeping_never_appear(cfg, events):
    fm = feat.build_tabular_features(events, cfg, split="train")
    for barred in ("target_log_risk", "target_time_to_tca", "is_high_risk",
                   "event_uid", "split", "cdm_index", "n_cdms"):
        assert barred not in fm.X.columns


def test_assert_feature_safety_rejects_target(cfg):
    with pytest.raises(FeatureSafetyError, match="target_log_risk"):
        feat.assert_feature_safety(["target_log_risk"], cfg)


# --- 4. derived columns cannot smuggle a barred source ---------------------------
def test_derived_column_from_unsafe_source_is_rejected(cfg):
    """`event_id_mean` must be refused even though its literal name is novel."""
    with pytest.raises(FeatureSafetyError, match="event_id"):
        feat.assert_feature_safety(["event_id_mean"], cfg)


def test_derived_ambiguous_column_is_rejected_by_default(cfg):
    with pytest.raises(FeatureSafetyError, match="max_risk_estimate"):
        feat.assert_feature_safety(["max_risk_estimate_last"], cfg)


def test_risk_summaries_rejected_when_risk_history_disabled():
    """Under the dictionary's strict reading, even pre-cutoff risk summaries go."""
    strict = load_config(overrides={"features": {"risk_history": False}})
    with pytest.raises(FeatureSafetyError, match="risk"):
        feat.assert_feature_safety(["risk_last"], strict)


def test_risk_summaries_allowed_only_when_flag_enabled(cfg):
    """With the flag on, pre-cutoff summaries pass but raw `risk` still does not."""
    assert cfg.features.risk_history is True
    feat.assert_feature_safety(["risk_last", "risk_mean"], cfg)   # no raise
    with pytest.raises(FeatureSafetyError):
        feat.assert_feature_safety(["risk"], cfg)


def test_strict_variant_builds_without_any_risk_feature(events):
    strict = load_config(overrides={"features": {"risk_history": False}})
    fm = feat.build_tabular_features(events, strict, split="train")
    assert not any(c.startswith("risk") for c in fm.X.columns)


# --- 5. the temporal cutoff ------------------------------------------------------
def test_only_precutoff_cdms_contribute(cfg, events):
    """Perturbing post-cutoff CDMs must not change a single feature value."""
    baseline = feat.build_tabular_features(events, cfg, split="train")

    tampered = events.copy()
    post = tampered["time_to_tca"] < cfg.cutoff.cutoff_days_before_tca
    assert post.any(), "fixture must contain post-cutoff CDMs for this test to bite"

    # Perturb only genuine per-CDM measurement columns. Identifiers, event
    # bookkeeping, the target, and time_to_tca itself are excluded: changing those
    # legitimately changes the row (or would move a CDM across the cutoff), so
    # including them would test the fixture rather than the cutoff logic.
    from kelvins_conformal.data import COLUMNS_103

    protected = {"event_id", "mission_id", "time_to_tca", "target_log_risk",
                 "target_time_to_tca", "is_high_risk", "cdm_index", "n_cdms"}
    perturbable = [
        c for c in COLUMNS_103
        if c not in protected and pd.api.types.is_float_dtype(tampered[c])
    ]
    assert perturbable, "expected some perturbable float columns"
    tampered.loc[post, perturbable] = tampered.loc[post, perturbable] + 1234.5

    after = feat.build_tabular_features(tampered, cfg, split="train")
    pd.testing.assert_frame_equal(baseline.X, after.X)


def test_admissible_cdms_respects_the_configured_cutoff(cfg, events):
    adm = feat.admissible_cdms(events, cfg)
    assert (adm["time_to_tca"] >= cfg.cutoff.cutoff_days_before_tca).all()


def test_target_value_cannot_be_reconstructed_from_features(cfg, events):
    """No feature column may be exactly equal to the target across all events."""
    fm = feat.build_tabular_features(events, cfg, split="train")
    for col in fm.X.select_dtypes(include=[np.number]).columns:
        vals = fm.X[col].to_numpy(dtype=float)
        if np.allclose(np.nan_to_num(vals), np.nan_to_num(fm.y), atol=1e-12):
            pytest.fail(f"feature {col!r} is identical to the target — leakage")


# --- 6. dictionary stays in sync with the schema ---------------------------------
def test_dictionary_covers_exactly_the_parsed_schema():
    from kelvins_conformal.data import COLUMNS_103

    d = feat.load_feature_dictionary()
    assert set(d["features"]) == set(COLUMNS_103)


def test_sequence_builder_applies_the_same_safety_contract(cfg, events):
    st = feat.build_sequence_tensors(events, cfg, split="train")
    assert "event_id" not in st.feature_names
    assert "max_risk_estimate" not in st.feature_names
    assert "target_log_risk" not in st.feature_names
