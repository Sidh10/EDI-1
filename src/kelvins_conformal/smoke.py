"""Tiny-subset end-to-end smoke pipeline for CI (SOFTWARE_ARCHITECTURE.md §12).

Runs in seconds with no network and no real dataset: it fabricates a handful of
synthetic CDMs with the release schema, exercises the event-grouping + target
derivation + split-leakage machinery in ``data``, round-trips a parquet, and runs
one Foster Pc computation. Its job is to catch shape/wiring regressions on every
PR, not to validate science (the unit tests do that).

Invoked by CI as ``python -m kelvins_conformal.smoke``; exits nonzero on failure.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .config import load_config
from .labelnoise import pc_foster as pf


def _synthetic_raw(n_events: int, split_offset: int, seed: int) -> pd.DataFrame:
    """Build a schema-complete synthetic CDM frame (2-4 CDMs per event)."""
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_events):
        eid = split_offset + e
        n_cdms = int(rng.integers(2, 5))
        # time_to_tca decreasing towards TCA across the series.
        times = np.sort(rng.uniform(0.1, 6.0, size=n_cdms))[::-1]
        for t in times:
            row = {c: float(rng.normal()) for c in data.COLUMNS_103}
            row["event_id"] = eid
            row["time_to_tca"] = float(t)
            row["mission_id"] = int(rng.integers(1, 5))
            row["risk"] = float(rng.uniform(-30, -3))
            row["c_object_type"] = "DEBRIS"
            rows.append(row)
    df = pd.DataFrame(rows)[list(data.COLUMNS_103)]
    return df


def main() -> int:
    cfg = load_config()

    with tempfile.TemporaryDirectory(prefix="kc_smoke_") as td:
        tdp = Path(td)
        # --- data machinery on synthetic frames ---
        train = data._add_event_structure(data._coerce_types(_synthetic_raw(8, 0, 1)), "train")
        test = data._add_event_structure(data._coerce_types(_synthetic_raw(3, 0, 2)), "test")

        # Event-level disjointness must hold despite raw id overlap (both start at 0).
        data.assert_events_disjoint(
            {"train": train["event_uid"].unique(), "test": test["event_uid"].unique()}
        )

        # Split scaffold: partition train events, assert no leakage.
        splits = data.split_events(
            train["event_uid"].unique(),
            {"fit": 0.5, "calibration": 0.25, "self_test": 0.25},
            seed=cfg.seed,
        )
        data.assert_events_disjoint(splits)

        # Parquet round-trip (atomic write path).
        events = pd.concat([train, test], ignore_index=True)
        events["target_log_risk"] = -10.0
        events["target_time_to_tca"] = 0.5
        events["is_high_risk"] = events["target_log_risk"] > cfg.high_risk_threshold
        out = tdp / "events.parquet"
        events.to_parquet(out, index=False)
        assert pd.read_parquet(out).shape[0] == events.shape[0]

    # --- Pc core: one deterministic computation ---
    row = dict.fromkeys(pf.REQUIRED_FIELDS, 0.0)
    row.update(
        relative_position_r=200.0, relative_position_t=50.0, relative_position_n=0.0,
        relative_velocity_n=7500.0,
        t_sigma_r=150.0, t_sigma_t=400.0, t_sigma_n=120.0,
        c_sigma_r=200.0, c_sigma_t=600.0, c_sigma_n=180.0,
        t_span=5.0, c_span=2.0,
    )
    res = pf.recompute_pc_for_row(row)
    assert res is not None and 0.0 <= res.pc <= 1.0

    print("[smoke] OK: data grouping, split-leakage guard, parquet round-trip, Pc core.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
