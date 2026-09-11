"""Reporting-layer output helpers: atomic table writes and a run-id output lock.

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``reporting``): the reporting
layer is the only place that writes to ``reports/``. Two invariants that the rest of
the pipeline already honours must hold here too, and did not before this module
existed:

* **Atomic writes (SOFTWARE_ARCHITECTURE.md §6).** Every artifact is written
  temp -> fsync -> rename, so a crashed or killed run can never leave a torn,
  half-written table that still looks valid. ``data.write_events_parquet`` already
  did this for the parquet; the notebooks' inline ``save_table`` did a plain
  ``df.to_csv`` and so could be interrupted mid-write.

* **A run-id output guard.** At the previous checkpoint two Phase-2 runs overlapped
  (an orphaned run plus its relaunch) and both wrote ``reports/tables/``. The results
  were identical by determinism, but concurrent writers to one directory is a latent
  corruption path. ``output_lock`` makes a second concurrent run fail loudly instead
  of interleaving its writes.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

LOCK_NAME = ".write_lock"


def write_table_atomic(df: pd.DataFrame, path: str | Path, *, index: bool = True) -> Path:
    """Write ``df`` to ``path`` atomically (temp -> fsync -> rename).

    The destination is never observed in a partial state: it is either the previous
    content (or absent, on a first write) or the fully-written new content. On any
    failure during serialisation the temp file is removed and the destination is
    left untouched, then the error re-raises (fail loud, CLAUDE.md §1).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        df.to_csv(tmp, index=index)
        # Flush to disk before the rename so a crash after rename cannot resurrect
        # stale bytes. fsync needs a writable fd (Windows raises EBADF on a read fd).
        fd = os.open(tmp, os.O_RDWR)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        # A failed write must leave NOTHING partial — neither at the destination
        # (untouched by design) nor as a leftover temp.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
    return path


class OutputLockError(RuntimeError):
    """Raised when an output directory is already locked by another live run."""


@contextmanager
def output_lock(directory: str | Path, run_id: str, *, stale_after_s: float = 3600.0):
    """Guard an output directory so two concurrent runs cannot write to it.

    Creates ``<directory>/.write_lock`` atomically (``O_CREAT | O_EXCL``). If a lock
    from a *different* run already exists and is fresh, raises ``OutputLockError``.
    A lock older than ``stale_after_s`` is treated as abandoned (its run was killed)
    and reclaimed, so a crashed run never blocks the directory forever. Re-entering
    with the same ``run_id`` is allowed. The lock is released on exit only if this
    run still owns it.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / LOCK_NAME
    payload = json.dumps({"run_id": run_id, "pid": os.getpid(), "ts": time.time()})

    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, payload.encode("utf-8"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                existing = json.loads(lock.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = {}
            if existing.get("run_id") == run_id:
                break  # same run re-entering
            age = time.time() - float(existing.get("ts", 0.0))
            if age > stale_after_s:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass
                continue  # reclaim and retry
            raise OutputLockError(
                f"output directory {directory} is locked by run "
                f"{existing.get('run_id')!r} (pid {existing.get('pid')}, "
                f"{age:.0f}s ago); refusing to write concurrently"
            ) from None

    try:
        yield lock
    finally:
        try:
            current = json.loads(lock.read_text(encoding="utf-8"))
            if current.get("run_id") == run_id:
                lock.unlink()
        except (OSError, ValueError):
            pass
