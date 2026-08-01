"""Event-level split-leakage tests (CLAUDE.md §4, invariant I3).

The standing invariant, enforced from Phase 0 forward: no event uid may appear in
more than one split, ever. These tests exercise the split scaffold on synthetic
uids (fast, no dataset). A slow test also checks real train/test disjointness when
the processed table exists.
"""

from __future__ import annotations

import numpy as np
import pytest

from kelvins_conformal import data


def test_split_events_are_disjoint_and_complete():
    uids = [f"train_{i}" for i in range(1000)]
    splits = data.split_events(uids, {"fit": 0.6, "calibration": 0.2, "self_test": 0.2}, seed=42)
    all_ids = np.concatenate([splits[k] for k in splits])
    # Disjoint (no overlap) and complete (partition covers every uid exactly once).
    assert len(all_ids) == len(set(all_ids)) == len(uids)
    assert set(all_ids) == set(uids)


def test_split_events_is_deterministic():
    uids = [f"e_{i}" for i in range(500)]
    frac = {"a": 0.5, "b": 0.5}
    s1 = data.split_events(uids, frac, seed=7)
    s2 = data.split_events(uids, frac, seed=7)
    for k in frac:
        assert list(s1[k]) == list(s2[k])
    # Different seed -> different partition (with overwhelming probability).
    s3 = data.split_events(uids, frac, seed=8)
    assert list(s1["a"]) != list(s3["a"])


def test_split_events_rejects_bad_fractions():
    with pytest.raises(ValueError, match="sum to 1.0"):
        data.split_events(["a", "b"], {"x": 0.5, "y": 0.4}, seed=0)


def test_assert_events_disjoint_detects_overlap():
    bad = {"train": np.array(["e1", "e2", "e3"]), "test": np.array(["e3", "e4"])}
    with pytest.raises(AssertionError, match="leakage"):
        data.assert_events_disjoint(bad)


def test_assert_events_disjoint_passes_when_clean():
    ok = {"train": np.array(["e1", "e2"]), "test": np.array(["e3", "e4"])}
    data.assert_events_disjoint(ok)  # must not raise


@pytest.mark.slow
def test_real_train_test_events_are_disjoint():
    """Namespaced train/test event uids never collide, despite raw id overlap."""
    from kelvins_conformal.config import load_config

    cfg = load_config()
    events = data.load_events(cfg)
    train_ids = set(events.loc[events["split"] == "train", "event_uid"])
    test_ids = set(events.loc[events["split"] == "test", "event_uid"])
    assert train_ids.isdisjoint(test_ids)
    assert events["event_uid"].nunique() == 13154 + 2167
