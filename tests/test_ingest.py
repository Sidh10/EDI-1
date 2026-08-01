"""Tests for E0 ingest integrity + freezing (CLAUDE.md §4).

Requirements exercised:
- checksum mismatch raises and aborts (no partial/invalid output trusted);
- the raw directory is unwritable after freezing.

These tests never download the 211 MB dataset — they operate on tiny local
fixtures so the CI smoke run stays well under budget.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from kelvins_conformal import ingest


def _write(p: Path, data: bytes) -> Path:
    p.write_bytes(data)
    return p


def test_compute_md5_matches_hashlib(tmp_path):
    f = _write(tmp_path / "a.bin", b"hello world")
    assert ingest.compute_md5(f) == hashlib.md5(b"hello world").hexdigest()


def test_verify_checksum_passes_on_match(tmp_path):
    f = _write(tmp_path / "a.bin", b"payload")
    expected = hashlib.md5(b"payload").hexdigest()
    # Must not raise, and returns the actual checksum.
    assert ingest.verify_checksum(f, expected) == expected


def test_verify_checksum_raises_on_mismatch(tmp_path):
    f = _write(tmp_path / "a.bin", b"payload")
    wrong = "0" * 32
    with pytest.raises(ingest.IntegrityError, match="Checksum mismatch"):
        ingest.verify_checksum(f, wrong)


def test_run_ingest_aborts_on_bad_source_zip_checksum(tmp_path, monkeypatch):
    """A source zip whose md5 != the pinned value aborts with IntegrityError,
    and leaves no extracted files behind."""
    import zipfile

    from kelvins_conformal.config import load_config

    # Build a valid zip whose checksum will NOT match the pinned dataset md5.
    zpath = tmp_path / "fake.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("train_data.csv", "event_id,risk\n0,-6.0\n")

    raw_dir = tmp_path / "raw"
    cfg = load_config(overrides={"paths": {"raw_dir": str(raw_dir)}})

    with pytest.raises(ingest.IntegrityError, match="Checksum mismatch"):
        ingest.run_ingest(cfg, source_zip=zpath, progress=False)

    # No trusted output: raw_dir must not contain the extracted data file.
    assert not (raw_dir / "train_data.csv").exists()


def test_freeze_makes_directory_unwritable_then_unfreeze(tmp_path):
    d = tmp_path / "frozen"
    d.mkdir()
    (d / "keep.txt").write_text("data")

    ingest.freeze_directory(d)
    assert ingest.is_frozen(d) is True

    # Creating a new file inside a frozen directory must fail loudly.
    with pytest.raises(OSError):
        with open(d / "intruder.txt", "w") as fh:
            fh.write("nope")

    # Reads still work while frozen.
    assert (d / "keep.txt").read_text() == "data"

    # Cleanup path: unfreeze restores writability (so tmp_path teardown succeeds).
    ingest.unfreeze_directory(d)
    assert ingest.is_frozen(d) is False
    (d / "now_ok.txt").write_text("ok")
    assert (d / "now_ok.txt").read_text() == "ok"


def test_run_ingest_succeeds_with_matching_source_zip(tmp_path, monkeypatch):
    """End-to-end ingest against a synthetic zip whose md5 is injected as the
    expected value — exercises extract -> manifest -> freeze without networking."""
    import zipfile

    from kelvins_conformal.config import load_config

    # A zip with a single top-level wrapper dir (mirrors many Zenodo archives).
    zpath = tmp_path / "ds.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("dataset/train_data.csv", "event_id,risk\n0,-6.0\n1,-30.0\n")
        zf.writestr("dataset/test_data.csv", "event_id,risk\n2,-4.0\n")

    real_md5 = ingest.compute_md5(zpath)
    raw_dir = tmp_path / "raw"
    cfg = load_config(
        overrides={"paths": {"raw_dir": str(raw_dir)}, "dataset": {"md5": real_md5}}
    )

    out = ingest.run_ingest(cfg, source_zip=zpath, progress=False)
    assert out == raw_dir

    # Wrapper dir flattened: files sit directly under raw_dir.
    assert (raw_dir / "train_data.csv").exists()
    assert (raw_dir / "test_data.csv").exists()
    # Provenance manifest present and well-formed.
    assert (raw_dir / ingest.MANIFEST_NAME).exists()
    # Frozen after ingest.
    assert ingest.is_frozen(raw_dir) is True

    # A second ingest without force must refuse (immutable store).
    with pytest.raises(ingest.IntegrityError, match="already exists"):
        ingest.run_ingest(cfg, source_zip=zpath, progress=False, force=False)

    # Cleanup so tmp_path teardown can remove the frozen tree.
    ingest.unfreeze_directory(raw_dir)
