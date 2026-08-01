"""E0 — dataset acquisition & integrity verification.

Responsibility (SOFTWARE_ARCHITECTURE.md §2, component ``ingest``): download the
Zenodo zip, verify its md5 against the pinned checksum, unpack into ``data/raw``,
freeze that directory read-only (invariant I1), and record a provenance manifest.

Fails loud (CLAUDE.md §1, §10): any checksum mismatch raises ``IntegrityError``
and leaves no partial output. Raw data is written exactly once; re-ingest requires
an explicit ``force`` (which must unfreeze first) so the immutable store cannot be
silently clobbered.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from .config import Config

_CHUNK = 1 << 20  # 1 MiB streaming chunk
MANIFEST_NAME = "PROVENANCE.json"


class IntegrityError(RuntimeError):
    """Raised on checksum mismatch or corrupt/unreadable archive (E0 abort)."""


# --- checksums --------------------------------------------------------------
def compute_md5(path: str | Path, chunk: int = _CHUNK) -> str:
    """Streaming md5 of a file (constant memory)."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_checksum(path: str | Path, expected_md5: str) -> str:
    """Verify ``path``'s md5 equals ``expected_md5`` (case-insensitive).

    Returns the actual md5 on success; raises ``IntegrityError`` on mismatch.
    """
    actual = compute_md5(path)
    if actual.lower() != expected_md5.lower():
        raise IntegrityError(
            f"Checksum mismatch for {path}:\n  expected md5 = {expected_md5}\n"
            f"  actual   md5 = {actual}\nRefusing to proceed (E0 failure criterion)."
        )
    return actual


# --- read-only freezing (invariant I1), cross-platform ----------------------
def _freeze_posix(root: Path) -> None:
    # Files -> r--r--r--, directories -> r-xr-xr-x (no write bit for anyone,
    # including the owner, so creating new files inside is denied for non-root).
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            os.chmod(Path(dirpath) / name, 0o444)
        for name in dirnames:
            os.chmod(Path(dirpath) / name, 0o555)
    os.chmod(root, 0o555)


def _icacls(args: list[str]) -> None:
    subprocess.run(["icacls", *args], check=True, capture_output=True, text=True)


def _freeze_windows(root: Path) -> None:
    # Mark every file read-only, then deny write/append/delete on the directory
    # tree for the current user via an inherited ACE. The RO attribute alone does
    # not stop file *creation* inside a directory on Windows, so icacls is needed
    # for a real guarantee.
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            os.chmod(Path(dirpath) / name, stat.S_IREAD)
    user = getpass.getuser()
    _icacls([str(root), "/deny", f"{user}:(OI)(CI)(WD,AD,DE)"])


def freeze_directory(path: str | Path) -> None:
    """Make ``path`` and its contents read-only (deny new writes)."""
    root = Path(path)
    if os.name == "nt":
        _freeze_windows(root)
    else:
        _freeze_posix(root)


def _unfreeze_posix(root: Path) -> None:
    os.chmod(root, 0o755)
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            os.chmod(Path(dirpath) / name, 0o755)
        for name in filenames:
            os.chmod(Path(dirpath) / name, 0o644)


def _unfreeze_windows(root: Path) -> None:
    user = getpass.getuser()
    # Remove the deny ACE, then clear the read-only attribute on files.
    _icacls([str(root), "/remove:d", user])
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            os.chmod(Path(dirpath) / name, stat.S_IWRITE | stat.S_IREAD)


def unfreeze_directory(path: str | Path) -> None:
    """Reverse ``freeze_directory`` (used by ``force`` re-ingest and by tests)."""
    root = Path(path)
    if os.name == "nt":
        _unfreeze_windows(root)
    else:
        _unfreeze_posix(root)


def is_frozen(path: str | Path) -> bool:
    """Best-effort check that a directory rejects new file creation."""
    root = Path(path)
    probe = root / ".__write_probe__"
    try:
        with open(probe, "w") as fh:
            fh.write("x")
    except OSError:
        return True
    else:
        probe.unlink(missing_ok=True)
        return False


# --- download ---------------------------------------------------------------
def download(url: str, dest: str | Path, *, progress: bool = True) -> Path:
    """Stream ``url`` to ``dest`` (atomic: temp file -> rename). Returns dest."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = Request(url, headers={"User-Agent": "kelvins-conformal/0.0 (research)"})
    with urlopen(req) as resp:  # noqa: S310 - fixed, pinned Zenodo URL
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        last = 0.0
        with open(tmp, "wb") as out:
            for block in iter(lambda: resp.read(_CHUNK), b""):
                out.write(block)
                done += len(block)
                if progress and total and (time.time() - last) > 1.0:
                    pct = 100.0 * done / total
                    print(f"  downloading… {done/1e6:6.1f}/{total/1e6:.1f} MB ({pct:4.1f}%)",
                          file=sys.stderr)
                    last = time.time()
    os.replace(tmp, dest)
    return dest


# --- manifest ---------------------------------------------------------------
def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def build_manifest(cfg: Config, raw_dir: Path, zip_md5: str, zip_size: int) -> dict:
    """Provenance record: what was fetched, from where, when, and its integrity."""
    files = []
    for p in sorted(raw_dir.rglob("*")):
        if p.is_file() and p.name != MANIFEST_NAME:
            files.append(
                {
                    "path": p.relative_to(raw_dir).as_posix(),
                    "size_bytes": p.stat().st_size,
                    "md5": compute_md5(p),
                }
            )
    return {
        "dataset_doi": cfg.dataset.doi,
        "source_url": cfg.dataset.url,
        "zip_filename": cfg.dataset.zip_filename,
        "zip_md5_expected": cfg.dataset.md5,
        "zip_md5_actual": zip_md5,
        "zip_size_bytes": zip_size,
        "download_timestamp_utc": datetime.now(UTC).isoformat(),
        "extracted_files": files,
        "python_version": sys.version.split()[0],
        "tool": "kelvins_conformal.ingest",
        "config_hash": cfg.config_hash,
        "note": (
            "Raw data is immutable after this step (invariant I1). Do not edit or "
            "re-download without an explicit forced re-ingest recorded in DECISIONS.md."
        ),
    }


# --- orchestration ----------------------------------------------------------
def run_ingest(
    cfg: Config,
    *,
    source_zip: str | Path | None = None,
    force: bool = False,
    progress: bool = True,
) -> Path:
    """Full E0 pipeline: obtain zip -> verify md5 -> unpack -> manifest -> freeze.

    Parameters
    ----------
    cfg:
        Loaded project config (provides URL, expected md5, paths).
    source_zip:
        Optional path to a pre-downloaded zip. If given, it is checksum-verified
        and used instead of downloading (supports offline/deterministic re-runs).
    force:
        If the raw store already exists, unfreeze and overwrite it. Without this,
        an existing raw store aborts (the store is immutable by default).
    """
    raw_dir = cfg.path("raw_dir")

    if raw_dir.exists() and any(raw_dir.iterdir()):
        if not force:
            raise IntegrityError(
                f"Raw store already exists and is non-empty: {raw_dir}\n"
                "Refusing to overwrite immutable raw data. Pass force=True "
                "(and record the reason in DECISIONS.md) to re-ingest."
            )
        if is_frozen(raw_dir):
            unfreeze_directory(raw_dir)
        shutil.rmtree(raw_dir)

    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. Obtain the archive.
    with tempfile.TemporaryDirectory(prefix="kc_ingest_") as td:
        tdp = Path(td)
        if source_zip is not None:
            zip_path = Path(source_zip)
            if not zip_path.exists():
                raise IntegrityError(f"source_zip does not exist: {zip_path}")
        else:
            zip_path = download(cfg.dataset.url, tdp / cfg.dataset.zip_filename,
                                progress=progress)

        # 2. Verify integrity BEFORE any extraction (abort on mismatch).
        zip_md5 = verify_checksum(zip_path, cfg.dataset.md5)
        zip_size = zip_path.stat().st_size

        # 3. Extract atomically: unpack into a temp dir, then move into place.
        extract_dir = tdp / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise IntegrityError(f"Corrupt entry in archive: {bad}")
            zf.extractall(extract_dir)

        # Flatten a single top-level wrapper directory if present, so raw_dir holds
        # the data files directly (adapt-to-what-you-find; documented in the audit).
        entries = list(extract_dir.iterdir())
        roots = entries
        if len(entries) == 1 and entries[0].is_dir():
            roots = list(entries[0].iterdir())
        for item in roots:
            shutil.move(str(item), str(raw_dir / item.name))

    # 4. Provenance manifest (written before freezing).
    manifest = build_manifest(cfg, raw_dir, zip_md5, zip_size)
    _write_json_atomic(raw_dir / MANIFEST_NAME, manifest)

    # 5. Freeze read-only (invariant I1).
    freeze_directory(raw_dir)
    return raw_dir
