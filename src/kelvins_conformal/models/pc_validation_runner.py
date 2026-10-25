"""Pc engine independent validation (REVIEWER_CHECKLIST RP4) — the runner behind ``kc pc-validate``.

Responsibility: compare the existing Pc engine (``labelnoise.pc_foster``, UNCHANGED) with the
independent methods in ``labelnoise.pc_independent``, and run the convention sensitivity set, exactly
as pre-registered. Every protocol value comes from ``config/experiments/pc_validation.yaml``; every
rule comes from the DECISIONS.md entries of 2026-10-14 (reconstruction) and 2026-10-24 (Sidh's
confirmation). Serves the Pc validation study; not an EXPERIMENT_PLAN stage, and it changes no E3 or
E14 number.

Inputs:  the official-test target-defining CDMs (``data.official_test_target_cdms``), E3's 100-CDM
         sample (``e3_full_comparison.csv`` matched back to the training rows), the YAML above.
Outputs: ``pcv_*`` tables in the tables directory, each step with a provenance sidecar.

Steps, each of which requires the previous step's tables:
  sample           -> pcv_sample_official.csv, pcv_sample_e3.csv
  self-convergence -> pcv_engine.csv, pcv_self_convergence.csv          (engine at 1x and 2x grid)
  gate             -> pcv_independent.csv, pcv_gate.csv                  (M1, M3; step (ii) gate)
  compare          -> pcv_agreement.csv, pcv_out_of_tolerance.csv, pcv_excluded.csv
                                                                         (refuses if the missing-value
                                                                          policy is null)
  m2               -> pcv_m2.csv
  conventions      -> pcv_conventions.csv, pcv_convention_summary.csv, pcv_c1_expectation.csv

Classification rules (item 9 as amended): the engine agrees with a method in a stratum when >= 95% of
events are within tau_s, none is beyond 0.1 and the median |dlog10| is <= 0.005; a stratum agrees only
if this holds for BOTH M1 and M3; an engine evaluation error counts as a disagreement (|d| = inf).
Missing-value policy (Sidh, 2026-10-25): an event with no valid M1 or M3 value is excluded from that
method's fractions and listed in pcv_excluded.csv; a stratum where more than 10% of events lack an M1
or an M3 value is classed "not informative".
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ..config import REPO_ROOT, Config
from ..labelnoise import pc_foster as pf
from ..labelnoise import pc_independent as pi
from ..reporting import write_table_atomic

PCV_CONFIG = REPO_ROOT / "config" / "experiments" / "pc_validation.yaml"
STEPS: tuple[str, ...] = ("sample", "self-convergence", "gate", "compare", "m2", "conventions")
MISSING_POLICIES: tuple[str, ...] = ("exclude", "count_as_disagreement")
SETS: tuple[str, ...] = ("official", "e3")
_COV_KEYS = ("sigma_r", "sigma_t", "sigma_n", "ct_r", "cn_r", "cn_t")


class OpenDecisionError(RuntimeError):
    """Raised where the pre-registration leaves a decision OPEN for Sidh."""


class PreregGuardError(RuntimeError):
    """Raised when a step is asked to run without a verifiable pre-registration commit."""


# The heading of the 2026-10-24 confirmation entry; the guard requires it in DECISIONS.md at the
# pre-registration commit.
PREREG_HEADING = "PRE-REGISTRATION CONFIRMED (Sidh): Pc engine independent validation"
PCV_CONFIG_REPO_PATH = "config/experiments/pc_validation.yaml"
_CRLF, _LF = bytes((13, 10)), bytes((10,))


# --- config ------------------------------------------------------------------------------------
def canonical_sha256(raw: bytes) -> str:
    """SHA-256 of the YAML in git's canonical form (CRLF -> LF), i.e. the hash of the committed blob.

    A Windows checkout with core.autocrlf rewrites line endings, so hashing the raw working-copy bytes
    would make the recorded hash depend on the machine. The canonical form does not.
    """
    return hashlib.sha256(raw.replace(_CRLF, _LF)).hexdigest()


def load_pcv_config(path: str | Path | None = None) -> tuple[dict, str]:
    """The pre-registered YAML and its canonical SHA-256 (stamped into every provenance sidecar)."""
    raw = Path(path or PCV_CONFIG).read_bytes()
    return yaml.safe_load(raw), canonical_sha256(raw)


# --- the pre-registration guard (Sidh, 2026-10-25) ------------------------------------------------
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True)


def _resolve_commit(repo: Path, ref: str) -> str:
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    sha = r.stdout.decode("ascii", "replace").strip()
    if r.returncode != 0 or not sha:
        raise PreregGuardError(f"--prereg-commit {ref!r} is not a commit in {repo}")
    return sha


def _is_ancestor(repo: Path, sha: str) -> bool:
    r = _git(repo, "merge-base", "--is-ancestor", sha, "HEAD")
    if r.returncode not in (0, 1):
        raise PreregGuardError(f"git merge-base failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.returncode == 0


def verify_prereg(prereg_commit: str | None, *, yaml_path: str | Path | None = None,
                  repo: str | Path = REPO_ROOT) -> dict:
    """Refuse unless the pre-registration is verifiable; every step reads real data or its products.

    Requires (1) ``prereg_commit`` given and a commit; (2) an ancestor of HEAD; (3) DECISIONS.md at that
    commit containing the confirmation heading; (4) the canonical SHA-256 of the validation YAML in use
    equal to that of the YAML committed at that commit. Returns what was verified, for provenance.
    """
    repo = Path(repo)
    if not prereg_commit:
        raise PreregGuardError("every pc-validate step reads real data or its products: --prereg-commit <sha> "
                               "is required")
    sha = _resolve_commit(repo, prereg_commit)
    if not _is_ancestor(repo, sha):
        raise PreregGuardError(f"pre-registration commit {sha[:12]} is not an ancestor of HEAD")
    dec = _git(repo, "show", f"{sha}:DECISIONS.md")
    if dec.returncode != 0 or PREREG_HEADING.encode("utf-8") not in dec.stdout:
        raise PreregGuardError(f"DECISIONS.md at {sha[:12]} does not contain the confirmation heading "
                               f"{PREREG_HEADING!r}")
    blob = _git(repo, "show", f"{sha}:{PCV_CONFIG_REPO_PATH}")
    if blob.returncode != 0:
        raise PreregGuardError(f"{PCV_CONFIG_REPO_PATH} does not exist at {sha[:12]}")
    recorded = canonical_sha256(blob.stdout)
    in_use = canonical_sha256(Path(yaml_path or repo / PCV_CONFIG_REPO_PATH).read_bytes())
    if in_use != recorded:
        raise PreregGuardError(f"validation YAML sha256 {in_use[:16]}... differs from {recorded[:16]}... "
                               f"recorded at {sha[:12]}")
    head = _git(repo, "rev-parse", "HEAD").stdout.decode("ascii", "replace").strip()
    return {"prereg_commit": sha, "head": head, "pc_validation_yaml_sha256": recorded}


# --- sampling (items 1, 2) -----------------------------------------------------------------------
def stratum_labels(edges) -> list[str]:
    edges = list(edges)
    return [f"floor (== {edges[0]:g})"] + [f"({lo:g}, {hi:g}]" for lo, hi in zip(edges[:-1], edges[1:], strict=False)]


def assign_strata(y, edges) -> np.ndarray:
    """E3's strata: the floor atom (y <= first edge), then (lo, hi] bands. Values above the last edge raise."""
    y = np.asarray(y, dtype=float)
    edges = list(edges)
    labels = stratum_labels(edges)
    out = np.empty(y.size, dtype=object)
    out[y <= edges[0]] = labels[0]
    for lab, lo, hi in zip(labels[1:], edges[:-1], edges[1:], strict=False):
        out[(y > lo) & (y <= hi)] = lab
    unassigned = np.array([v is None for v in out])
    if unassigned.any():
        raise ValueError(f"{int(unassigned.sum())} values fall outside the strata edges {edges}")
    return out


def draw_official_sample(df: pd.DataFrame, *, uid_col: str, y_col: str, edges, seed: int,
                         per_stratum_n: int, take_all=("(-6, 0]",)) -> pd.DataFrame:
    """Item 2 as drafted: uids sorted, ``default_rng(seed)``, without replacement, strata in E3 order.

    Strata in ``take_all`` are taken whole; every other stratum contributes ``per_stratum_n`` events.
    The draw consumes the generator in stratum order, so the result depends only on the uid set.
    """
    d = df.sort_values(uid_col, kind="mergesort").reset_index(drop=True).copy()
    d["stratum"] = assign_strata(d[y_col].to_numpy(float), edges)
    rng = np.random.default_rng(seed)
    parts = []
    for lab in stratum_labels(edges):
        s = d[d["stratum"] == lab]
        if lab in take_all:
            parts.append(s)
            continue
        if len(s) < per_stratum_n:
            raise ValueError(f"stratum {lab!r} has {len(s)} events; {per_stratum_n} are pre-registered")
        idx = np.sort(rng.choice(len(s), size=per_stratum_n, replace=False))
        parts.append(s.iloc[idx])
    return pd.concat(parts, ignore_index=True)


# --- statistics (items 9, step (ii)) ---------------------------------------------------------------
def self_convergence_e_s(one, two) -> float:
    """e_s: 95th percentile of |engine(refined grid) - engine(base grid)| over pairs where both are finite."""
    d = np.abs(np.asarray(two, float) - np.asarray(one, float))
    d = d[np.isfinite(d)]
    if d.size == 0:
        return math.nan
    return float(np.percentile(d, 95))


def tau_s(e_s: float, agreement: dict) -> float:
    return max(float(agreement["tau_floor"]), float(agreement["tau_mult"]) * float(e_s))


def m1_m3_gate(m1, m3, threshold: float) -> dict:
    """Step (ii): median |M1 - M3| over events where both are valid; above ``threshold`` is outcome b'."""
    d = np.abs(np.asarray(m1, float) - np.asarray(m3, float))
    ok = np.isfinite(d)
    med = float(np.median(d[ok])) if ok.any() else math.nan
    return {"n_compared": int(ok.sum()), "n_missing": int((~ok).sum()), "median_abs_dlog10": med,
            "max_abs_dlog10": float(d[ok].max()) if ok.any() else math.nan, "threshold": float(threshold),
            "outcome": "pass" if ok.any() and med <= threshold else "b'"}


def _method_stats(d, err, tau: float, agreement: dict, missing_policy: str, lacks=None) -> dict:
    d = np.abs(np.asarray(d, float))
    lacks = ~np.isfinite(d) if lacks is None else np.asarray(lacks, bool)
    missing = lacks & ~err                    # an engine error stays a disagreement even if the method lacks a value
    eff = d.copy()
    eff[err] = math.inf                       # engine error: a disagreement (item 9 as amended)
    if missing_policy == "count_as_disagreement":
        eff[missing] = math.inf
        keep = np.ones(d.size, bool)
    else:                                     # "exclude"
        keep = ~missing
    idx = np.flatnonzero(keep)
    e = eff[keep]
    excluded = [int(i) for i in np.flatnonzero(missing)] if missing_policy == "exclude" else []
    if e.size == 0:
        return {"n": 0, "n_missing": int(missing.sum()), "frac_within": math.nan, "median_abs": math.nan,
                "max_abs": math.nan, "agree": False, "out_of_tolerance": [], "excluded": excluded}
    frac = float(np.mean(e <= tau))
    med = float(np.median(e))
    agree = (frac >= float(agreement["min_frac_within"]) and not bool(np.any(e > float(agreement["max_abs_any"])))
             and med <= float(agreement["max_median_abs"]))
    return {"n": int(e.size), "n_missing": int(missing.sum()), "frac_within": frac, "median_abs": med,
            "max_abs": float(e.max()), "agree": bool(agree),
            "out_of_tolerance": [int(i) for i in idx[e > tau]], "excluded": excluded}


def classify_stratum(d_m1, d_m3, engine_error_mask, *, tau: float, agreement: dict,
                     missing_policy: str | None, m1_lacks=None, m3_lacks=None) -> dict:
    """Per-stratum agreement of the engine with M1 and with M3 (item 9 as amended; policy of 2026-10-25).

    ``d_m1`` / ``d_m3`` are engine-minus-method log10 differences (NaN where either side has no
    value); ``engine_error_mask`` marks events where the engine raised or returned nothing;
    ``m1_lacks`` / ``m3_lacks`` mark events with no valid M1 / M3 value (default: non-finite d).
    ``missing_policy`` ``None`` refuses to classify. ``classification`` is "not informative" when more
    than ``agreement.not_informative_if_frac_missing_above`` of the stratum's events lack an M1 or an
    M3 value; otherwise "agree" (both methods) or "disagree".
    """
    if missing_policy is None:
        raise OpenDecisionError(
            "agreement.missing_independent_value_policy is null: how an event with no valid independent "
            "value enters the agreement fractions is OPEN (DECISIONS.md 2026-10-24) and is Sidh's to set")
    if missing_policy not in MISSING_POLICIES:
        raise ValueError(f"unknown missing_independent_value_policy {missing_policy!r}; expected {MISSING_POLICIES}")
    if not (agreement.get("require_both_m1_m3") and agreement.get("engine_errors_count_as_disagreement")):
        raise ValueError("the confirmed item 9 requires require_both_m1_m3 and engine_errors_count_as_disagreement")
    threshold = float(agreement["not_informative_if_frac_missing_above"])
    err = np.asarray(engine_error_mask, bool)
    l1 = ~np.isfinite(np.asarray(d_m1, float)) if m1_lacks is None else np.asarray(m1_lacks, bool)
    l3 = ~np.isfinite(np.asarray(d_m3, float)) if m3_lacks is None else np.asarray(m3_lacks, bool)
    s1 = _method_stats(d_m1, err, tau, agreement, missing_policy, l1)
    s3 = _method_stats(d_m3, err, tau, agreement, missing_policy, l3)
    frac_lacking = float(np.mean(l1 | l3)) if err.size else math.nan
    agree = bool(s1["agree"] and s3["agree"])
    not_informative = bool(err.size == 0 or frac_lacking > threshold)
    out = {"n_events": int(err.size), "n_engine_errors": int(err.sum()), "tau": float(tau),
           "missing_policy": missing_policy, "frac_lacking_m1_or_m3": frac_lacking,
           "not_informative": not_informative, "agree": agree,
           "classification": "not informative" if not_informative else ("agree" if agree else "disagree")}
    for tag, s in (("m1", s1), ("m3", s3)):
        out.update({f"agree_{tag}": s["agree"], f"n_{tag}": s["n"], f"n_missing_{tag}": s["n_missing"],
                    f"frac_within_{tag}": s["frac_within"], f"median_abs_{tag}": s["median_abs"],
                    f"max_abs_{tag}": s["max_abs"], f"out_of_tolerance_{tag}": s["out_of_tolerance"],
                    f"excluded_{tag}": s["excluded"]})
    return out


# --- conventions (item 11) --------------------------------------------------------------------------
def _cov_from_row(row: dict, prefix: str) -> np.ndarray:
    sr, st, sn, ctr, cnr, cnt = (float(row[f"{prefix}_{k}"]) for k in _COV_KEYS)
    return np.array([[sr * sr, ctr * sr * st, cnr * sr * sn],
                     [ctr * sr * st, st * st, cnt * st * sn],
                     [cnr * sr * sn, cnt * st * sn, sn * sn]])


def _write_cov(row: dict, prefix: str, c: np.ndarray) -> None:
    s = np.sqrt(np.diag(c))
    row[f"{prefix}_sigma_r"], row[f"{prefix}_sigma_t"], row[f"{prefix}_sigma_n"] = (float(v) for v in s)
    row[f"{prefix}_ct_r"] = float(c[1, 0] / (s[1] * s[0]))
    row[f"{prefix}_cn_r"] = float(c[2, 0] / (s[2] * s[0]))
    row[f"{prefix}_cn_t"] = float(c[2, 1] / (s[2] * s[1]))


def crossing_angle(row: dict, *, sign: float, mu_km3_s2: float) -> float:
    """Angle about R between the target's and the chaser's along-track directions (circular orbits).

    Target velocity in its own RTN is (0, v_t, 0) with v_t = sqrt(mu / a_t) (``t_j2k_sma`` in km,
    converted to m/s to match the relative velocity). The chaser velocity is v_t + sign * v_rel, where
    sign = +1 reads the relative velocity as chaser - target (C3a) and -1 as target - chaser (C3b).
    """
    v_t = math.sqrt(mu_km3_s2 / float(row["t_j2k_sma"])) * 1000.0
    v_rel_t = float(row["relative_velocity_t"])
    v_rel_n = float(row["relative_velocity_n"])
    return math.atan2(sign * v_rel_n, v_t + sign * v_rel_t)


def c3_rotation(row: dict, conv_id: str, *, mu_km3_s2: float) -> np.ndarray:
    """C3's rotation: the chaser's RTN axes as columns, in target RTN components (a rotation about R).

    A vector with chaser-RTN components x has target-RTN components ``rot @ x``, so a chaser covariance
    C becomes ``rot @ C @ rot.T``. Exact for circular orbits at a common position; an approximation
    otherwise (see ``crossing_angle``).
    """
    if conv_id not in ("C3a", "C3b"):
        raise ValueError(f"c3_rotation applies to C3a / C3b, not {conv_id!r}")
    th = crossing_angle(row, sign=1.0 if conv_id == "C3a" else -1.0, mu_km3_s2=mu_km3_s2)
    c, s = math.cos(th), math.sin(th)
    rot = np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])   # chaser RTN axes in target RTN
    return rot


def apply_convention(row: dict, conv_id: str, *, mu_km3_s2: float):
    """The convention's input transform: ``(new_row, covariance_scale)``, or ``None`` (C4 with k <= 0).

    Inputs only; the engine is called unchanged afterwards.
    """
    new = dict(row)
    if conv_id == "C0":
        return new, 1.0
    if conv_id == "C1":                       # x_span read as a radius: HBR = t_span + c_span
        new["t_span"] = 2.0 * float(row["t_span"])
        new["c_span"] = 2.0 * float(row["c_span"])
        return new, 1.0
    if conv_id in ("C3a", "C3b"):
        rot = c3_rotation(row, conv_id, mu_km3_s2=mu_km3_s2)
        _write_cov(new, "c", rot @ _cov_from_row(row, "c") @ rot.T)
        return new, 1.0
    if conv_id in ("C4a", "C4b"):
        k = float(row["max_risk_scaling"])
        if not (math.isfinite(k) and k > 0.0):
            return None
        return new, (k if conv_id == "C4a" else k * k)
    raise ValueError(f"unknown convention {conv_id!r}")


def c1_expectation_report(dlog10, expected: float) -> dict:
    """C1's per-stratum median log10 Pc(C1) - log10 Pc(C0) against +0.602. Reported; no pass/fail."""
    d = np.asarray(dlog10, float)
    d = d[np.isfinite(d)]
    med = float(np.median(d)) if d.size else math.nan
    return {"n": int(d.size), "median_dlog10": med, "expected": float(expected),
            "median_minus_expected": med - float(expected)}


# --- engine evaluation -----------------------------------------------------------------------------
def engine_eval(row: dict, *, n_radial: int, n_angular: int, covariance_scale: float = 1.0) -> dict:
    """The UNCHANGED engine on one row; errors are captured per event, never raised."""
    try:
        r = pf.recompute_pc_for_row(row, n_radial=n_radial, n_angular=n_angular,
                                    covariance_scale=covariance_scale)
    except pf.PcComputationError as exc:
        return {"log10_pc": math.nan, "log10_pc_unfloored": math.nan, "error": f"PcComputationError: {exc}"}
    if r is None:
        return {"log10_pc": math.nan, "log10_pc_unfloored": math.nan, "error": "missing required field"}
    return {"log10_pc": float(r.log10_pc), "log10_pc_unfloored": float(r.log10_pc_unfloored), "error": ""}


# --- the run ---------------------------------------------------------------------------------------
def _tables(cfg: Config) -> Path:
    return cfg.path("tables_dir")


def _read_csv(path: Path) -> pd.DataFrame:
    # round_trip: time_to_tca is a join key, and the default float parser does not always return the
    # exact double that to_csv wrote.
    return pd.read_csv(path, float_precision="round_trip", keep_default_na=False, na_values=["", "NaN", "nan"])


def _require(cfg: Config, *names: str) -> list[pd.DataFrame]:
    out = []
    for n in names:
        p = _tables(cfg) / n
        if not p.exists():
            raise FileNotFoundError(f"{n} is missing: run the earlier `kc pc-validate` step first")
        out.append(_read_csv(p))
    return out


def _provenance(cfg: Config, step: str, digest: str, written: list[str], guard: dict) -> None:
    rec = {"step": step, "pc_validation_yaml_sha256": digest, "base_config_hash": cfg.config_hash,
           "git_commit": guard["head"], "prereg_commit": guard["prereg_commit"],
           "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tables": written}
    path = _tables(cfg) / f"pcv_provenance_{step.replace('-', '_')}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    tmp.replace(path)


def _sample_rows(cfg: Config, set_name: str) -> pd.DataFrame:
    """The full CDM rows of one sample set, in sample order (``sample_index`` is the row position)."""
    from ..data import _coerce_types, _read_train, official_test_target_cdms

    if set_name == "official":
        (s,) = _require(cfg, "pcv_sample_official.csv")
        rows = official_test_target_cdms(cfg).set_index("event_uid").loc[s["event_uid"]].reset_index()
        rows = rows.rename(columns={"target_log_risk": "reported"})
    else:
        (s,) = _require(cfg, "pcv_sample_e3.csv")
        train = _coerce_types(_read_train(cfg))
        train["event_uid"] = "train_" + train["event_id"].astype("int64").astype(str)
        rows = s[["event_uid", "time_to_tca"]].merge(train, on=["event_uid", "time_to_tca"], how="left",
                                                     validate="one_to_one")
        rows = rows.rename(columns={"risk": "reported"})
    rows["stratum"] = s["stratum"].to_numpy()
    rows["sample_index"] = np.arange(len(rows))
    return rows


def step_sample(cfg: Config, pcv: dict) -> list[str]:
    from ..data import _coerce_types, _read_train, official_test_target_cdms

    edges = cfg.pc_spike.risk_strata_edges
    so = pcv["sample"]["official_test"]
    off = draw_official_sample(official_test_target_cdms(cfg), uid_col="event_uid", y_col="target_log_risk",
                               edges=edges, seed=int(pcv["seed"]), per_stratum_n=int(so["per_stratum_n"]),
                               take_all=tuple(so["take_all_strata"]))
    off = off[["event_uid", "time_to_tca", "target_log_risk", "stratum"]].rename(
        columns={"target_log_risk": "reported"})
    written = [str(write_table_atomic(off, _tables(cfg) / "pcv_sample_official.csv", index=False))]
    if pcv["sample"].get("e3_sample"):
        e3 = _read_csv(_tables(cfg) / "e3_full_comparison.csv")
        train = _coerce_types(_read_train(cfg))
        train["event_uid"] = "train_" + train["event_id"].astype("int64").astype(str)
        m = e3[["event_uid", "time_to_tca", "stratum", "reported"]].merge(
            train[["event_uid", "time_to_tca", "risk"]], on=["event_uid", "time_to_tca"], how="left",
            validate="one_to_one")
        if m["risk"].isna().any() or not np.array_equal(m["risk"].to_numpy(float), m["reported"].to_numpy(float)):
            raise ValueError("E3 sample rows do not all match the training data with reported == risk (item 3)")
        written.append(str(write_table_atomic(m.drop(columns="risk"), _tables(cfg) / "pcv_sample_e3.csv",
                                              index=False)))
    return written


def event_seeds(pcv: dict, sample_index: int) -> dict:
    """Per-event seeds (Sidh, 2026-10-25): M3 and M2 draw from distinct streams.

    seed + m3.seed_offset + index for M3 (42 + index, the pre-registered rule) and
    seed + m2.seed_offset + index for M2. The offsets must differ by more than any sample index, so no
    M2 seed can equal any M3 seed in either set.
    """
    base, i = int(pcv["seed"]), int(sample_index)
    m3_off, m2_off = int(pcv["m3"]["seed_offset"]), int(pcv["m2"]["seed_offset"])
    if i < 0 or i >= abs(m2_off - m3_off):
        raise ValueError(f"sample index {i} would let the M2 and M3 seed streams overlap "
                         f"(offsets {m3_off}, {m2_off})")
    return {"m3": base + m3_off + i, "m2": base + m2_off + i}


def _sets(pcv: dict) -> tuple[str, ...]:
    return SETS if pcv["sample"].get("e3_sample") else ("official",)


def step_self_convergence(cfg: Config, pcv: dict) -> list[str]:
    eng = pcv["engine"]
    nr, na, f = int(eng["n_radial"]), int(eng["n_angular"]), int(eng["refined_factor"])
    recs = []
    for set_name in _sets(pcv):
        for row in _sample_rows(cfg, set_name).to_dict("records"):
            one = engine_eval(row, n_radial=nr, n_angular=na)
            two = engine_eval(row, n_radial=f * nr, n_angular=f * na)
            recs.append({"set": set_name, "sample_index": row["sample_index"], "event_uid": row["event_uid"],
                         "time_to_tca": row["time_to_tca"], "stratum": row["stratum"], "reported": row["reported"],
                         "engine_log10": one["log10_pc_unfloored"], "engine_log10_floored": one["log10_pc"],
                         "engine_error": one["error"], "engine2x_log10": two["log10_pc_unfloored"],
                         "engine2x_error": two["error"]})
    engine = pd.DataFrame(recs)
    rows = []
    for (set_name, stratum), g in engine.groupby(["set", "stratum"], sort=False):
        e_s = self_convergence_e_s(g["engine_log10"], g["engine2x_log10"])
        rows.append({"set": set_name, "stratum": stratum, "n": len(g),
                     "n_nonfinite_pairs": int((~np.isfinite(g["engine_log10"] - g["engine2x_log10"])).sum()),
                     "e_s": e_s, "tau_s": tau_s(e_s, pcv["agreement"]) if math.isfinite(e_s) else math.nan})
    return [str(write_table_atomic(engine, _tables(cfg) / "pcv_engine.csv", index=False)),
            str(write_table_atomic(pd.DataFrame(rows), _tables(cfg) / "pcv_self_convergence.csv", index=False))]


def step_gate(cfg: Config, pcv: dict) -> list[str]:
    _require(cfg, "pcv_engine.csv")
    m1c, m3c = pcv["m1"], pcv["m3"]
    recs = []
    for set_name in _sets(pcv):
        for row in _sample_rows(cfg, set_name).to_dict("records"):
            m3_seed = event_seeds(pcv, row["sample_index"])["m3"]
            rec = {"set": set_name, "sample_index": row["sample_index"], "event_uid": row["event_uid"],
                   "stratum": row["stratum"], "m3_seed": m3_seed}
            try:
                g = pi.geometry_from_row(row)
            except (KeyError, TypeError, ValueError) as exc:
                recs.append({**rec, "assembly_error": str(exc), "m1_log10": math.nan, "m1_converged": False,
                             "m1_ier": -2, "m3_log10": math.nan, "m3_rel_se": math.nan, "m3_n_used": 0,
                             "m3_escalated": False, "m3_informative": False})
                continue
            m1 = pi.log10_pc_m1(g, epsrel=float(m1c["epsrel"]), limit=int(m1c["limit"]),
                                peak_grid_points=int(m1c["peak_grid_points"]))
            m3 = pi.log10_pc_m3(g, seed=m3_seed, n_samples=int(m3c["n_samples"]),
                                n_escalated=int(m3c["n_escalated"]), rel_se_target=float(m3c["rel_se_target"]),
                                chunk=int(m3c["chunk"]))
            recs.append({**rec, "assembly_error": "", "m1_log10": m1.log10_pc if m1.converged else math.nan,
                         "m1_converged": m1.converged, "m1_ier": m1.ier,
                         "m3_log10": m3.log10_pc if m3.informative else math.nan, "m3_rel_se": m3.rel_se,
                         "m3_n_used": m3.n_used, "m3_escalated": m3.escalated, "m3_informative": m3.informative})
    ind = pd.DataFrame(recs)
    rows = [{"set": s, **m1_m3_gate(g["m1_log10"], g["m3_log10"], float(pcv["gate_m1_m3"]["max_median_abs_dlog10"]))}
            for s, g in ind.groupby("set", sort=False)]
    return [str(write_table_atomic(ind, _tables(cfg) / "pcv_independent.csv", index=False)),
            str(write_table_atomic(pd.DataFrame(rows), _tables(cfg) / "pcv_gate.csv", index=False))]


def step_compare(cfg: Config, pcv: dict) -> list[str]:
    policy = pcv["agreement"].get("missing_independent_value_policy")
    if policy is None:   # refuse before reading any comparison input
        classify_stratum([], [], [], tau=0.0, agreement=pcv["agreement"], missing_policy=None)
    engine, sc, ind, gate = _require(cfg, "pcv_engine.csv", "pcv_self_convergence.csv", "pcv_independent.csv",
                                     "pcv_gate.csv")
    df = engine.merge(ind, on=["set", "sample_index", "event_uid", "stratum"], validate="one_to_one")
    df["engine_error"] = df["engine_error"].fillna("")
    df["d_m1"] = df["engine_log10"] - df["m1_log10"]
    df["d_m3"] = df["engine_log10"] - df["m3_log10"]
    df["assembly_error"] = df["assembly_error"].fillna("")
    rows, oot, excl = [], [], []
    for (set_name, stratum), g in df.groupby(["set", "stratum"], sort=False):
        tau = float(sc.loc[(sc["set"] == set_name) & (sc["stratum"] == stratum), "tau_s"].iloc[0])
        res = classify_stratum(g["d_m1"].to_numpy(float), g["d_m3"].to_numpy(float),
                               (g["engine_error"] != "").to_numpy(bool), tau=tau, agreement=pcv["agreement"],
                               missing_policy=policy, m1_lacks=~np.isfinite(g["m1_log10"].to_numpy(float)),
                               m3_lacks=~np.isfinite(g["m3_log10"].to_numpy(float)))
        gate_outcome = gate.loc[gate["set"] == set_name, "outcome"].iloc[0]
        rows.append({"set": set_name, "stratum": stratum, "gate_outcome": gate_outcome,
                     **{k: (len(v) if isinstance(v, list) else v) for k, v in res.items()
                        if not k.startswith("out_of_tolerance")}})
        for tag in ("m1", "m3"):
            for i in res[f"out_of_tolerance_{tag}"]:
                r = g.iloc[i]
                oot.append({"set": set_name, "stratum": stratum, "method": tag.upper(),
                            "event_uid": r["event_uid"], "sample_index": r["sample_index"],
                            "engine_log10": r["engine_log10"], "engine_error": r["engine_error"],
                            "method_log10": r[f"{tag}_log10"], "dlog10": r[f"d_{tag}"]})
            for i in res[f"excluded_{tag}"]:   # the per-stratum list of excluded events (policy of 2026-10-25)
                r = g.iloc[i]
                if r["assembly_error"]:
                    reason = f"input assembly error: {r['assembly_error']}"
                elif tag == "m1":
                    reason = f"M1 non-convergence (quad ier {int(r['m1_ier'])})"
                else:
                    reason = f"M3 not informative (rel SE {r['m3_rel_se']:.4g} at n {int(r['m3_n_used'])})"
                excl.append({"set": set_name, "stratum": stratum, "method": tag.upper(),
                             "event_uid": r["event_uid"], "sample_index": r["sample_index"], "reason": reason})
    excl_cols = ["set", "stratum", "method", "event_uid", "sample_index", "reason"]
    return [str(write_table_atomic(pd.DataFrame(rows), _tables(cfg) / "pcv_agreement.csv", index=False)),
            str(write_table_atomic(pd.DataFrame(oot), _tables(cfg) / "pcv_out_of_tolerance.csv", index=False)),
            str(write_table_atomic(pd.DataFrame(excl, columns=excl_cols), _tables(cfg) / "pcv_excluded.csv",
                                   index=False))]


def step_m2(cfg: Config, pcv: dict) -> list[str]:
    engine, ind = _require(cfg, "pcv_engine.csv", "pcv_independent.csv")
    df = engine.merge(ind, on=["set", "sample_index", "event_uid", "stratum"], validate="one_to_one")
    c = pcv["m2"]
    rows_by_key = {(s, int(r["sample_index"])): r for s in _sets(pcv)
                   for r in _sample_rows(cfg, s).to_dict("records")}
    recs = []
    for r in df.to_dict("records"):
        m2_seed = event_seeds(pcv, r["sample_index"])["m2"]
        rec = {"set": r["set"], "sample_index": r["sample_index"], "event_uid": r["event_uid"], "stratum": r["stratum"],
               "m2_seed": m2_seed}
        if r["assembly_error"] and isinstance(r["assembly_error"], str):
            recs.append({**rec, "status": "assembly error", "hits": 0, "n": 0, "p_hat": math.nan,
                         "rel_se": math.nan, "consistent_with_engine": None})
            continue
        g = pi.geometry_from_row(rows_by_key[(r["set"], int(r["sample_index"]))])
        res = pi.pc_m2(g, seed=m2_seed, chunk=int(c["chunk"]), cap=int(c["cap"]),
                       min_hits=int(c["min_hits_target"]), max_rel_se=float(c["max_rel_se_counted"]),
                       prior_log10_pc=r["m1_log10"] if math.isfinite(r["m1_log10"]) else None)
        cons = (pi.m2_consistent(res, r["engine_log10"], n_se=float(c["n_se"]))
                if math.isfinite(r["engine_log10"]) else None)
        recs.append({**rec, "status": res.status, "hits": res.hits, "n": res.n, "p_hat": res.p_hat,
                     "rel_se": res.rel_se, "consistent_with_engine": cons})
    return [str(write_table_atomic(pd.DataFrame(recs), _tables(cfg) / "pcv_m2.csv", index=False))]


def step_conventions(cfg: Config, pcv: dict) -> list[str]:
    _require(cfg, "pcv_engine.csv")
    eng = pcv["engine"]
    nr, na = int(eng["n_radial"]), int(eng["n_angular"])
    mu = float(pcv["constants"]["mu_earth_km3_s2"])
    tol = float(pcv["reported_tolerance"])
    convs = [c["id"] for c in pcv["conventions"]]
    recs = []
    for set_name in _sets(pcv):
        for row in _sample_rows(cfg, set_name).to_dict("records"):
            for cid in convs:
                tr = apply_convention(row, cid, mu_km3_s2=mu)
                anchor = "max_risk_estimate" if cid.startswith("C4") else "reported"
                base = {"set": set_name, "sample_index": row["sample_index"], "event_uid": row["event_uid"],
                        "stratum": row["stratum"], "convention": cid, "anchor": anchor,
                        "anchor_value": float(row[anchor])}
                if tr is None:
                    recs.append({**base, "excluded_k_nonpositive": True, "log10_pc": math.nan,
                                 "log10_pc_unfloored": math.nan, "error": ""})
                    continue
                new, scale = tr
                ev = engine_eval(new, n_radial=nr, n_angular=na, covariance_scale=scale)
                recs.append({**base, "excluded_k_nonpositive": False, **ev})
    df = pd.DataFrame(recs)
    df["within_tol"] = (df["log10_pc"] - df["anchor_value"]).abs() <= tol
    used = df[~df["excluded_k_nonpositive"]]
    summ = (used.groupby(["set", "convention", "stratum"], sort=False)
            .agg(n=("within_tol", "size"), n_errors=("error", lambda e: int((e != "").sum())),
                 frac_within=("within_tol", "mean")).reset_index())
    overall = (used.groupby(["set", "convention"], sort=False)
               .agg(n=("within_tol", "size"), n_errors=("error", lambda e: int((e != "").sum())),
                    frac_within=("within_tol", "mean")).reset_index().assign(stratum="ALL"))
    summ = pd.concat([summ, overall], ignore_index=True)
    c0 = summ[summ["convention"] == "C0"].set_index(["set", "stratum"])["frac_within"]
    summ["change_vs_c0_pp"] = [100.0 * (f - c0.get((s, st), math.nan))
                               for s, st, f in zip(summ["set"], summ["stratum"], summ["frac_within"], strict=False)]
    summ["n_excluded_k_nonpositive"] = [int(df[(df["set"] == s) & (df["convention"] == c)
                                               & (df["stratum"].eq(st) | (st == "ALL"))]["excluded_k_nonpositive"].sum())
                                        for s, c, st in zip(summ["set"], summ["convention"], summ["stratum"], strict=False)]
    thr = float(pcv["conventions_material_change_pp"])
    c1 = next(c for c in pcv["conventions"] if c["id"] == "C1")
    is_all = summ["stratum"] == "ALL"
    summ["finding_flag_e3_e14"] = (is_all & ~summ["convention"].isin(["C0", "C1"])
                                   & (summ["change_vs_c0_pp"].abs() > thr))
    summ["c1_insensitive_to_hbr"] = np.where(
        is_all & (summ["convention"] == "C1"),
        summ["change_vs_c0_pp"].abs() < float(c1["insensitivity_threshold_pp"]), None)
    # C1 expectation report: per-stratum median log10 Pc(C1) - log10 Pc(C0), unfloored, no pass/fail.
    wide = df.pivot_table(index=["set", "sample_index", "stratum"], columns="convention",
                          values="log10_pc_unfloored", aggfunc="first").reset_index()
    exp_rows = [{"set": s, "stratum": st, **c1_expectation_report(g["C1"] - g["C0"],
                                                                 float(c1["expected_median_dlog10"]))}
                for (s, st), g in wide.groupby(["set", "stratum"], sort=False)]
    return [str(write_table_atomic(df, _tables(cfg) / "pcv_conventions.csv", index=False)),
            str(write_table_atomic(summ, _tables(cfg) / "pcv_convention_summary.csv", index=False)),
            str(write_table_atomic(pd.DataFrame(exp_rows), _tables(cfg) / "pcv_c1_expectation.csv", index=False))]


_STEP_FUNCS = {"sample": step_sample, "self-convergence": step_self_convergence, "gate": step_gate,
               "compare": step_compare, "m2": step_m2, "conventions": step_conventions}


def run_step(cfg: Config, step: str, pcv_path: str | Path | None = None, *,
             prereg_commit: str | None = None, repo: str | Path = REPO_ROOT) -> list[str]:
    """Run one pre-registered step, behind the pre-registration guard, and write its provenance sidecar."""
    if step not in _STEP_FUNCS:
        raise ValueError(f"unknown step {step!r}; expected one of {STEPS}")
    yaml_path = Path(pcv_path) if pcv_path else Path(repo) / PCV_CONFIG_REPO_PATH
    guard = verify_prereg(prereg_commit, yaml_path=yaml_path, repo=repo)
    pcv, digest = load_pcv_config(yaml_path)
    if digest != guard["pc_validation_yaml_sha256"]:
        raise PreregGuardError("the validation YAML changed between the guard and the load")
    written = _STEP_FUNCS[step](cfg, pcv)
    _provenance(cfg, step, digest, written, guard)
    return written
