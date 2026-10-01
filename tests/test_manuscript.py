"""Tests for the E18 manuscript builder (``kelvins_conformal.manuscript``).

Covers the pieces that could silently misstate a number: the Markdown writer, the
Clopper–Pearson interval used for E8, the guard that keeps E17's circular H3 statistics
out of the manuscript, and — when the experiment tables are present — a full build that
must be traceable and byte-for-byte deterministic.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal import manuscript as M
from kelvins_conformal.config import load_config


def test_to_markdown_escapes_pipes_and_formats_missing():
    df = pd.DataFrame({"a|b": [1.0, np.nan], "c": ["x|y", "z\nw"], "d": [1e-5, 0.0]})
    lines = M.to_markdown(df, title="T", caption="C").splitlines()
    assert lines[0] == "### T"
    assert lines[2] == "| a\\|b | c | d |"
    assert lines[4] == "| 1 | x\\|y | 1e-05 |"
    assert lines[5] == "| — | z w | 0 |"
    assert lines[-1] == "C"


def test_cp_interval_matches_closed_forms():
    # k = 0 and k = n have closed forms; the interior is symmetric under k -> n - k.
    lo, hi = M._cp_interval(0, 10)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** (1 / 10), abs=1e-12)
    lo, hi = M._cp_interval(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** (1 / 10), abs=1e-12)
    lo3, hi3 = M._cp_interval(3, 20)
    lo17, hi17 = M._cp_interval(17, 20)
    assert lo3 == pytest.approx(1 - hi17, abs=1e-12) and hi3 == pytest.approx(1 - lo17, abs=1e-12)
    assert M._cp_interval(5, 10) == pytest.approx((0.187086, 0.812914), abs=1e-6)


def test_h3_tables_are_refused_at_read_time(tmp_path):
    b = M.Builder(load_config(), out_root=tmp_path)
    for name in ("e17_h3_association", "e17_h3_overlap"):
        with pytest.raises(PermissionError, match="circular"):
            b.table(name)


def test_no_builder_names_an_h3_table():
    # The only occurrence of the prefix is the guard itself: no builder can even ask.
    src = inspect.getsource(M)
    assert src.count("e17_h3_") == 1
    assert not re.search(r"table\(\s*[\"']e17_h3", src)
    assert M.build_t13_five_manifestations in M.BUILDERS


def _needs_tables():
    cfg = load_config()
    tables = cfg.path("tables_dir")
    if not (tables / "e17_coverage_restoration_matrix.csv").exists() or not (tables / "e12_adaptivity.csv").exists():
        pytest.skip("experiment tables not present (full-data artifacts are not in CI)")
    return cfg


def _digests(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_full_build_is_traceable_and_deterministic(tmp_path):
    cfg = _needs_tables()
    arts = M.build_all(cfg, out_root=tmp_path / "a")
    M.build_all(cfg, out_root=tmp_path / "b")

    # Determinism (CLAUDE.md §4): same tables + code => identical bytes, figures included.
    da, db = _digests(tmp_path / "a"), _digests(tmp_path / "b")
    assert da == db

    manifest = json.loads((tmp_path / "a" / "reports" / "manuscript_manifest.json").read_text(encoding="utf-8"))
    assert [a["id"] for a in manifest["artifacts"]] == [a.ident for a in arts]
    for a in manifest["artifacts"]:
        assert a["experiments"] and a["files"] and a["source_sha256"]
        assert not any(s.startswith("e17_h3_") for s in a["source_sha256"])
        for f in a["files"]:
            assert (tmp_path / "a" / f).exists()
    for exp, p in manifest["experiments"].items():
        assert re.fullmatch(r"[0-9a-f]{40}", p["git_commit_sha"]), exp
    for a in arts:
        assert a.caption and "nan" not in a.caption.lower().replace("nanosecond", "")
    t13 = next(a for a in arts if a.ident == "T13_five_manifestations")
    assert not any("h3" in s for s in t13.sources)
