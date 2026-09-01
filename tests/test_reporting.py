"""Atomic-write and output-lock guarantees for the reporting layer (CLAUDE.md §4).

Regression coverage for the concurrent-write / torn-table hazard logged at the
Phase-2 checkpoint (DECISIONS.md, 2026-08-31 observation): the reporting layer must
write tables atomically and must refuse two concurrent runs into one directory.
"""

from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from kelvins_conformal import reporting
from kelvins_conformal.reporting import (
    OutputLockError,
    output_lock,
    write_table_atomic,
)


def _df(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame({"a": range(n), "b": [x * 2 for x in range(n)]})


# --- atomic write ------------------------------------------------------------
def test_atomic_write_produces_readable_table(tmp_path):
    dst = tmp_path / "t.csv"
    write_table_atomic(_df(), dst)
    back = pd.read_csv(dst, index_col=0)
    pd.testing.assert_frame_equal(back, _df())


def test_failed_write_leaves_no_partial_and_no_temp(tmp_path, monkeypatch):
    """A killed write must leave NEITHER a torn destination NOR a leftover temp."""
    dst = tmp_path / "t.csv"

    def explode(self, *a, **k):
        # Simulate a crash midway through serialisation: write partial bytes to the
        # temp path the writer is using, then die.
        tmp = dst.with_suffix(".csv.tmp")
        tmp.write_text("a,b\n0,par")  # torn, half a row
        raise RuntimeError("killed mid-write")

    monkeypatch.setattr(pd.DataFrame, "to_csv", explode, raising=True)
    with pytest.raises(RuntimeError, match="killed mid-write"):
        write_table_atomic(_df(), dst)

    assert not dst.exists(), "destination must not exist after a failed first write"
    assert not dst.with_suffix(".csv.tmp").exists(), "temp file must be cleaned up"


def test_failed_write_preserves_previous_good_version(tmp_path, monkeypatch):
    """An interrupted overwrite must leave the PREVIOUS good table intact."""
    dst = tmp_path / "t.csv"
    write_table_atomic(_df(3), dst)                    # good v1
    good = dst.read_text()

    real_to_csv = pd.DataFrame.to_csv

    def explode(self, path=None, *a, **k):
        if path is not None and str(path).endswith(".tmp"):
            real_to_csv(self, path, *a, **k)           # temp really written...
            raise RuntimeError("killed after temp write")
        return real_to_csv(self, path, *a, **k)

    monkeypatch.setattr(pd.DataFrame, "to_csv", explode, raising=True)
    with pytest.raises(RuntimeError, match="killed after temp write"):
        write_table_atomic(_df(99), dst)               # attempted v2

    assert dst.read_text() == good, "destination must still hold the v1 content"
    assert not dst.with_suffix(".csv.tmp").exists()


def test_atomic_overwrite_replaces_cleanly(tmp_path):
    dst = tmp_path / "t.csv"
    write_table_atomic(_df(3), dst)
    write_table_atomic(_df(7), dst)
    assert len(pd.read_csv(dst, index_col=0)) == 7


# --- output lock -------------------------------------------------------------
def test_output_lock_blocks_a_second_concurrent_run(tmp_path):
    with output_lock(tmp_path, "runA"):
        with pytest.raises(OutputLockError, match="runA"):
            with output_lock(tmp_path, "runB"):
                pass  # pragma: no cover


def test_output_lock_releases_on_exit(tmp_path):
    with output_lock(tmp_path, "runA"):
        pass
    # Lock is gone, so a later run acquires cleanly.
    with output_lock(tmp_path, "runB"):
        assert (tmp_path / reporting.LOCK_NAME).exists()
    assert not (tmp_path / reporting.LOCK_NAME).exists()


def test_output_lock_is_reentrant_for_the_same_run(tmp_path):
    with output_lock(tmp_path, "runA"):
        with output_lock(tmp_path, "runA"):      # same id: allowed
            assert (tmp_path / reporting.LOCK_NAME).exists()


def test_output_lock_reclaims_a_stale_lock(tmp_path):
    """A lock from a killed run (old timestamp) must be reclaimable."""
    lock = tmp_path / reporting.LOCK_NAME
    lock.write_text(json.dumps({"run_id": "dead", "pid": 999999,
                                "ts": time.time() - 10_000}))
    # stale_after_s below the age -> reclaim rather than raise.
    with output_lock(tmp_path, "runB", stale_after_s=3600):
        current = json.loads(lock.read_text())
        assert current["run_id"] == "runB"


def test_output_lock_does_not_delete_another_runs_lock_on_exit(tmp_path):
    """If our lock got reclaimed by someone else, we must not delete theirs."""
    with output_lock(tmp_path, "runA"):
        # Simulate another run overwriting the lock while we hold it.
        (tmp_path / reporting.LOCK_NAME).write_text(
            json.dumps({"run_id": "runB", "pid": 1, "ts": time.time()})
        )
    # runA's exit must leave runB's lock in place.
    assert (tmp_path / reporting.LOCK_NAME).exists()
    assert json.loads((tmp_path / reporting.LOCK_NAME).read_text())["run_id"] == "runB"


def test_writer_and_lock_compose(tmp_path):
    with output_lock(tmp_path, "runA"):
        write_table_atomic(_df(4), tmp_path / "out.csv")
    assert len(pd.read_csv(tmp_path / "out.csv", index_col=0)) == 4
