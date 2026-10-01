"""E18 — final manuscript figures and tables (Phase 5, final consolidation).

Responsibility: build every manuscript figure and table with ONE command
(``kc manuscript``), as a pure function of the experiments' committed result tables
(plus, for E1's two histograms only, the frozen processed events), with one consistent
style, captions generated from the data rather than typed (CLAUDE.md §10), and a
provenance manifest that traces each artifact to its source tables (SHA-256) and to the
commit and config hash of the run that computed them.

Inputs:  ``reports/tables/*.csv`` written by E1 and E5–E17; each experiment's provenance
         sidecar in ``reports/``; ``data/processed`` events (E1 histograms, read-only).
Outputs: ``reports/manuscript_figures/`` (PNG + PDF), ``reports/manuscript_tables/``
         (CSV + Markdown), ``reports/manuscript_captions.md`` and
         ``reports/manuscript_manifest.json``.

Serves: EXPERIMENT_PLAN.md E18, Part B.

Nothing here recomputes a result. Every number is read from a table an experiment wrote.
Coverage verdicts use the project's single definitions in ``robustness``
(``meets_coverage_guarantee`` for validity under shift, ``consistent_with_exact_coverage``
for exactness on exchangeable data, ``restoration_verdict`` for naive-versus-weighted), so
the manuscript cannot state a criterion differently from the experiment that computed it
(DECISIONS.md 2026-09-21, methodological note). Two things are derived here rather than
read: Clopper–Pearson intervals for E8, which recorded coverage and n but no interval,
and E1's histograms, which are drawn from the events. Both are disclosed in the manifest.

Deliberately NOT built: any statistic from E17's H3 association or overlap tables. H3 was
closed as an honest null because those numbers are circular by construction (DECISIONS.md
2026-09-21, E17 CLOSED, item 1); the five-manifestation table is qualitative, and
``tests/test_manuscript.py`` asserts that its builder never reads the H3 tables.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import REPO_ROOT, Config, compute_config_hash
from .robustness import (
    NO_DEFICIT,
    NOT_RESTORED,
    RESTORED,
    consistent_with_exact_coverage,
    meets_coverage_guarantee,
    restoration_verdict,
)

# --- style: the dataviz reference palette, light mode (validated 2026-09-22) ---------
# Categorical slots 1-4 in fixed order; the first three pass the all-pairs CVD gate, the
# first four the adjacent gate. Aqua and yellow sit below 3:1 contrast on the surface, so
# every figure ships with its table (the relief rule) and every series also carries its
# own marker, which keeps identity readable in greyscale print (REVIEWER_CHECKLIST F4).
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MARK = ("o", "s", "^", "D")
# Status colours are reserved for state and always travel with a text label.
GOOD, CRITICAL = "#0ca30c", "#d03b3b"

DOUBLE_COL_IN, SINGLE_COL_IN = 7.2, 3.5     # Elsevier double / single column (190 / 90 mm)

LEARNERS = ("persistence", "gbm", "gru", "mc_dropout")
LEARNER_LABEL = {"persistence": "persistence", "gbm": "GBM", "gru": "GRU", "mc_dropout": "MC-dropout"}


def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK2,
        "axes.titlecolor": INK, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "grid.linestyle": "-",
        "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
        "lines.linewidth": 1.5, "lines.markersize": 5, "savefig.dpi": 300,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        # Journals require embedded TrueType, not Type 3 bitmap fonts.
        "pdf.fonttype": 42, "ps.fonttype": 42,
    })
    return plt


def _nominal_line(ax, y=0.0, *, horizontal=True, label=None):
    """The one dashed line on any figure: a threshold, never a gridline."""
    kw = {"color": INK, "lw": 0.9, "ls": (0, (4, 3)), "zorder": 1, "label": label}
    return ax.axhline(y, **kw) if horizontal else ax.axvline(y, **kw)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True,
                          check=True).stdout.strip()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --- sources and provenance ----------------------------------------------------------

# Each experiment's provenance sidecar: the run that wrote its tables.
PROVENANCE_FILE = {
    "E1": "00_data_audit_provenance.json", "E5": "01b_baseline_validation_provenance.json",
    "E6": "02_baselines_provenance.json", "E7": "02_baselines_provenance.json",
    "E8": "02_baselines_provenance.json", "E9": "03_conformal_provenance.json",
    "E10": "03_conformal_provenance.json", "E11": "03_conformal_provenance.json",
    "E12": "03b_cqr_provenance.json", "E14": "04_labelnoise_provenance.json",
    "E15": "05_decision_cost_provenance.json", "E15b": "05b_rank_invariance_provenance.json",
    "E15c": "05c_threshold_analysis_provenance.json", "E17": "06_robustness_provenance.json",
}

# E0-E2 ran before the repository existed; git was initialised at 5a309ac "at completed
# Phase 0 (E0-E3) state". The link is CHECKED, not asserted: the config committed there
# must hash to the value E1's sidecar recorded.
PRE_GIT_COMMIT = {"E1": "5a309ac"}

# E17's sidecar comes from a from-tables re-render (33440cd), which predates the
# ``computed_by`` convention, so it names only the render. The computing run's commit is
# the one DECISIONS.md records; it is checked to exist, and the sidecar's per-table
# SHA-256 is checked against the tables read today.
RECORDED_COMPUTING_COMMIT = {"E17": ("f53d27a", "DECISIONS.md 2026-09-21, E17 findings entry")}

PROVENANCE_NOTES = {
    "E12": "Re-run at dfb48a9 under config 00d1cb2d in E18 Part A; its tables are byte-identical to the original "
           "run (5422ccd, config eb89df79), verified against a pre-run snapshot.",
    "E15c": "Computed at 6e8debd; re-rendered from its computed tables in E18 Part A (display caveat only).",
}


def _provenance(reports: Path, exp: str) -> dict:
    """The run that computed ``exp``'s tables: commit, config hash, time, and how it is known."""
    path = reports / PROVENANCE_FILE[exp]
    if not path.exists():
        raise FileNotFoundError(f"provenance sidecar for {exp} missing: {path}")
    p = json.loads(path.read_text(encoding="utf-8"))
    computed = p.get("computed_by") or {}
    out = {
        "sidecar": f"reports/{PROVENANCE_FILE[exp]}",
        "git_commit_sha": computed.get("git_commit_sha") or p.get("git_commit_sha"),
        "config_hash": computed.get("config_hash") or p.get("config_hash"),
        "executed_utc": computed.get("executed_utc") or p.get("executed_utc"),
        "established_by": "provenance sidecar",
    }
    if exp in PRE_GIT_COMMIT and str(out["git_commit_sha"]).startswith("UNAVAILABLE"):
        import yaml

        sha = _git("rev-parse", PRE_GIT_COMMIT[exp] + "^{commit}")
        raw = yaml.safe_load(_git("show", f"{sha}:config/default.yaml"))
        if compute_config_hash(raw) != out["config_hash"]:
            raise ValueError(f"{exp}: the config at {sha[:10]} does not hash to the sidecar's config hash")
        out.update(git_commit_sha=sha, established_by=(
            "run predates the repository; traced to the initial commit, whose config/default.yaml hashes "
            "to the sidecar's config hash (checked at build time)"))
    if exp in RECORDED_COMPUTING_COMMIT and not computed and p.get("recomputed") is False:
        short, where = RECORDED_COMPUTING_COMMIT[exp]
        recorded = ast.literal_eval(p["source_table_sha256"]) if isinstance(p["source_table_sha256"], str) \
            else p["source_table_sha256"]
        tables = reports / "tables"
        for name, digest in recorded.items():
            f = tables / f"e17_{name}.csv"
            if hashlib.sha256(f.read_bytes()).hexdigest() != digest:
                raise ValueError(f"{exp}: {f.name} differs from the table its render sidecar verified")
        out.update(git_commit_sha=_git("rev-parse", short + "^{commit}"),
                   rendered_git_sha=p.get("rendered_git_sha"), executed_utc=None,
                   established_by=(f"computing commit from {where} (the from-tables render sidecar names only the "
                                   f"render); every table's SHA-256 checked against the render sidecar"))
    if exp in PROVENANCE_NOTES:
        out["note"] = PROVENANCE_NOTES[exp]
    return out


@dataclass
class Artifact:
    """One manuscript figure or table, with everything needed to trace it."""

    ident: str
    kind: str                      # "figure" | "table"
    title: str
    experiments: tuple[str, ...]
    caption: str = ""
    files: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)      # table name -> sha256
    notes: list[str] = field(default_factory=list)


class Builder:
    """Reads committed tables, writes manuscript artifacts, records provenance.

    ``out_root`` redirects the outputs (tests); inputs always come from the configured
    tables and reports directories.
    """

    def __init__(self, cfg: Config, out_root: Path | None = None):
        self.cfg = cfg
        self.tables = Path(cfg.path("tables_dir"))
        self.reports = Path(cfg.path("reports_dir"))
        self.root = Path(out_root) if out_root is not None else REPO_ROOT
        self.fig_dir = self.root / "reports" / "manuscript_figures"
        self.tab_dir = self.root / "reports" / "manuscript_tables"
        self.artifacts: list[Artifact] = []
        self._read: dict[str, str] = {}
        self.plt = _style()

    def rel(self, path: Path) -> str:
        return Path(path).relative_to(self.root).as_posix()

    # -- reading -------------------------------------------------------------------
    def table(self, name: str) -> pd.DataFrame:
        """A committed experiment table, read EXACTLY (float_precision="round_trip").

        The default pandas parser can return a 17-digit float one ULP away from the value
        written (DECISIONS.md Observations Log, 2026-09-21); the manuscript must print the
        numbers the experiments computed, not a neighbouring double. The circular E17 H3
        tables are refused outright, so no builder can reach them.
        """
        if name.startswith(FORBIDDEN_SOURCE_PREFIXES):
            raise PermissionError(f"{name}: E17 H3 statistics are circular by construction and never enter "
                                  "the manuscript (DECISIONS.md 2026-09-21, E17 CLOSED, item 1)")
        path = self.tables / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"manuscript source table missing: {path}")
        self._read[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        df = pd.read_csv(path, index_col=0, float_precision="round_trip")
        return df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")])

    def _claim_sources(self, art: Artifact, names) -> None:
        for n in names:
            art.sources[n] = self._read[n]

    # -- writing -------------------------------------------------------------------
    def save_figure(self, art: Artifact, fig) -> None:
        self.fig_dir.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            out = self.fig_dir / f"{art.ident}.{ext}"
            tmp = out.with_name(f"{art.ident}.tmp.{ext}")
            # No timestamps in the files, so an unchanged figure rebuilds to identical bytes.
            meta = {"CreationDate": None} if ext == "pdf" else {"Software": None}
            fig.savefig(tmp, bbox_inches="tight", metadata=meta)
            tmp.replace(out)
            art.files.append(self.rel(out))
        self.plt.close(fig)

    def save_table(self, art: Artifact, df: pd.DataFrame, suffix: str = "") -> None:
        from .reporting import write_table_atomic

        self.tab_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{art.ident}{suffix}"
        write_table_atomic(df, self.tab_dir / f"{stem}.csv", index=False)
        _write_text(self.tab_dir / f"{stem}.md",
                    to_markdown(df, title=art.title + (f" ({suffix.strip('_')})" if suffix else ""), caption=art.caption))
        art.files += [self.rel(self.tab_dir / f"{stem}.csv"), self.rel(self.tab_dir / f"{stem}.md")]

    def register(self, art: Artifact) -> None:
        if any(a.ident == art.ident for a in self.artifacts):
            raise ValueError(f"duplicate manuscript artifact id {art.ident!r}")
        self.artifacts.append(art)


def to_markdown(df: pd.DataFrame, *, title: str = "", caption: str = "") -> str:
    """A GitHub-flavoured Markdown table, without adding a dependency (``tabulate``)."""
    def cell(v) -> str:
        if isinstance(v, float):
            if not np.isfinite(v):
                return "—" if np.isnan(v) else ("∞" if v > 0 else "−∞")
            return f"{v:.4g}" if abs(v) >= 1e-3 or v == 0 else f"{v:.3g}"
        return str(v).replace("|", "\\|").replace("\n", " ")

    cols = [cell(str(c)) for c in df.columns]
    lines = []
    if title:
        lines += [f"### {title}", ""]
    lines += ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    if caption:
        lines += ["", caption]
    return "\n".join(lines) + "\n"


def _cp_interval(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Clopper–Pearson interval for k successes in n (Clopper & Pearson 1934).

    The same construction ``conformal_runner.coverage_with_ci`` uses. Applied here only
    to E8, which recorded coverage and n but no interval.
    """
    from scipy import stats

    a = 1.0 - level
    lo = 0.0 if k == 0 else float(stats.beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - a / 2, k + 1, n - k))
    return lo, hi


def _fmt_ci(v: float, lo: float, hi: float, d: int = 3) -> str:
    return f"{v:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


# =====================================================================================
# Builders. One per manuscript artifact: read committed tables, derive the caption from
# the data (every directional claim a caption makes is checked by ``_require`` first, so
# a caption cannot assert what the data does not show), save, register. None recomputes.
# =====================================================================================


def _require(cond: bool, claim: str) -> None:
    if not cond:
        raise ValueError(f"caption claim not supported by the data: {claim}")


def _row(df: pd.DataFrame, **kv) -> pd.Series:
    """The single row matching every key; float keys compared with ``np.isclose``."""
    m = np.ones(len(df), dtype=bool)
    for k, v in kv.items():
        m &= np.isclose(df[k].astype(float), v) if isinstance(v, float) else (df[k] == v).to_numpy()
    out = df[m]
    if len(out) != 1:
        raise ValueError(f"expected exactly one row for {kv}, found {len(out)}")
    return out.iloc[0]


def _lvl(x: float) -> str:
    return f"{int(round(100 * x))}%"


def _gap_errorbar(ax, x, cov, lo, hi, nominal, *, colour, marker, label, hollow=False):
    """Coverage minus nominal, in pp, with its interval."""
    y, ylo, yhi = (100 * (np.asarray(v, float) - nominal) for v in (cov, lo, hi))
    ax.errorbar(x, y, yerr=[y - ylo, yhi - y], fmt=marker, color=colour, ms=5, capsize=2, lw=1.2,
                mfc=SURFACE if hollow else colour, label=label, zorder=3)


def build_f01_selection_bias(b: Builder) -> None:
    """E1 — the official test set is selected, not sampled (Figure 1 candidate)."""
    from .data import event_level_frame, load_events

    cfg, plt = b.cfg, b.plt
    art = Artifact("F01_selection_bias", "figure", "Selection bias: training pool vs official test set", ("E1",))
    prev, tests = b.table("e1_high_risk_prevalence"), b.table("e1_two_sample_tests")
    rules = b.table("e1_cutoff_rule_verification")
    thr, rec = cfg.high_risk_threshold, cfg.cutoff.test_recency_filter_days
    ev = event_level_frame(load_events(cfg))
    tr, te = ev[ev["split"] == "train"], ev[ev["split"] == "test"]
    # The events must reproduce E1's own numbers, or the histograms would be drawn from other data.
    for d, s in ((tr, "train"), (te, "test")):
        got = (len(d), int((d["target_log_risk"] >= thr).sum()))
        if got != (int(prev.loc[s, "events"]), int(prev.loc[s, "high-risk events"])):
            raise ValueError(f"processed events do not reproduce E1's recorded {s} counts: {got}")
    rec_tr = float((tr["target_time_to_tca"] <= rec).mean())
    rec_te = float((te["target_time_to_tca"] <= rec).mean())
    recorded = re.findall(r"only ([\d.]+)% of train", " ".join(rules["observed"].astype(str)))
    if len(recorded) != 1 or abs(100 * rec_tr - float(recorded[0])) > 0.05 or rec_te != 1.0:
        raise ValueError(f"recency shares ({rec_tr:.4f}, {rec_te:.4f}) do not reproduce E1's record {recorded}")
    if ev["target_log_risk"].max() > 0:
        raise ValueError("a log10 Pc above 0 would fall outside the histogram")

    risk_edges = np.linspace(np.floor(ev["target_log_risk"].min()), 0.0, 61)
    t, step = ev["target_time_to_tca"], 0.1
    t_edges = np.arange(np.floor(t.min() / step) * step, np.ceil(t.max() / step) * step + step / 2, step)
    fig, (a, c) = plt.subplots(1, 2, figsize=(DOUBLE_COL_IN, 2.6))
    for d, colour, label in ((tr, S1, "train"), (te, S2, "official test")):
        kw = {"density": True, "histtype": "step", "lw": 1.4, "color": colour, "label": f"{label} (n = {len(d):,})"}
        a.hist(d["target_log_risk"], bins=risk_edges, **kw)
        c.hist(d["target_time_to_tca"], bins=t_edges, **kw)
    a.set_yscale("log")
    _nominal_line(a, thr, horizontal=False)
    a.set(xlabel="final-CDM risk  [log$_{10}$ Pc]", ylabel="density (log scale)",
          title=f"(a) Final risk (high-risk threshold {thr:g} dashed)")
    _nominal_line(c, rec, horizontal=False)
    c.set(xlabel="time to TCA of the latest CDM  [days]", ylabel="density",
          title=f"(b) Recency (the {rec:g}-day test filter dashed)")
    a.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.07, 1.0))
    c.legend(frameon=False, loc="upper right")
    fig.tight_layout()

    p_tr, p_te = float(prev.loc["train", "prevalence"]), float(prev.loc["test", "prevalence"])
    ks = tests["KS p"]
    art.caption = (
        f"**Figure 1.** The official test set is selected, not sampled. (a) Final-CDM risk per event: high-risk "
        f"prevalence is {p_tr:.2%} in the training pool and {p_te:.2%} in the official test set, a "
        f"{float(prev.loc['test', 'enrichment vs train']):.2f}-fold enrichment (two-sample KS p = {ks.iloc[0]:.1e}). "
        f"(b) Time to TCA of each event's latest CDM: every test event ({rec_te:.0%}) has its latest CDM within "
        f"{rec:g} day of TCA, the organisers' documented recency filter, against {rec_tr:.1%} of training events "
        f"(KS p = {ks.iloc[1]:.1e}). Step histograms, density-normalised; n = {len(tr):,} training and "
        f"{len(te):,} test events.")
    b.save_figure(art, fig)
    t_out = pd.DataFrame([{
        "split": s, "events": int(prev.loc[s, "events"]), "high-risk events": int(prev.loc[s, "high-risk events"]),
        "high-risk prevalence [95% CI]": _fmt_ci(prev.loc[s, "prevalence"], prev.loc[s, "95% CI lo"],
                                                 prev.loc[s, "95% CI hi"], 4),
        "enrichment vs train": round(float(prev.loc[s, "enrichment vs train"]), 3),
        f"latest CDM within {rec:g} d of TCA": round(r, 4)} for s, r in (("train", rec_tr), ("test", rec_te))])
    b.save_table(art, t_out)
    b.save_table(art, tests.reset_index(), suffix="_two_sample_tests")
    art.notes.append("The histograms and recency shares are drawn from data/processed (read-only), after checking "
                     "that the events reproduce E1's recorded counts, high-risk counts and train recency share.")
    b._claim_sources(art, ["e1_high_risk_prevalence", "e1_two_sample_tests", "e1_cutoff_rule_verification"])
    b.register(art)


def build_f02_bayesian(b: Builder) -> None:
    """E8 — the steelmanned Bayesian baseline under-covers (reliability) + its PIT figure."""
    plt = b.plt
    art = Artifact("F02_bayesian_coverage", "figure", "Bayesian baseline (E8): reliability on the official test set",
                   ("E8",))
    cov, summ, pit = b.table("e8_coverage_all"), b.table("e8_coverage_summary"), b.table("e8_pit_ks")
    n = int(b.table("e1_high_risk_prevalence").loc["test", "events"])
    rows = []
    for _, r in cov.iterrows():
        k = r["empirical"] * n
        if abs(k - round(k)) > 1e-6:
            raise ValueError(f"E8 coverage {r['empirical']} is not k/{n}: the denominator assumption fails")
        lo, hi = _cp_interval(int(round(k)), n)
        rows.append({**r.to_dict(), "cp_lo": lo, "cp_hi": hi})
    agg = (pd.DataFrame(rows).groupby(["method", "nominal"])
           .agg(empirical=("empirical", "mean"), cp_lo=("cp_lo", "mean"), cp_hi=("cp_hi", "mean"),
                sd=("empirical", "std"), width=("mean width", "mean"), n_runs=("seed", "nunique"))
           .reset_index())
    _require(bool((agg["cp_hi"] < agg["nominal"]).sum() >= 4), "E8 under-coverage established at 90% and 95%")

    fig, ax = plt.subplots(figsize=(SINGLE_COL_IN, 3.0))
    lv = sorted(agg["nominal"].unique())
    ax.plot([0.75, 1.0], [0.75, 1.0], color=INK, lw=0.9, ls=(0, (4, 3)), label="empirical = nominal")
    for m, colour, mk, dx in (("MC-dropout", S1, MARK[0], -0.003), ("deep ensemble", S2, MARK[1], 0.003)):
        g = agg[agg["method"] == m].sort_values("nominal")
        ax.errorbar(g["nominal"] + dx, g["empirical"], yerr=[g["empirical"] - g["cp_lo"], g["cp_hi"] - g["empirical"]],
                    fmt=mk + "-", color=colour, ms=5, capsize=2, lw=1.4,
                    label=f"{m} ({int(g['n_runs'].iloc[0])} run{'s' if g['n_runs'].iloc[0] > 1 else ''})")
    ax.set(xlabel="nominal coverage", ylabel="empirical coverage", xticks=lv, xlim=(0.77, 0.98), ylim=(0.77, 0.98),
           title="Reliability, official test set")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()

    gap = summ["gap_pp_mean"]
    art.caption = (
        f"**Figure 2.** The Bayesian baseline under-covers on the official test set, increasingly with the "
        f"nominal level: MC-dropout (steelmanned — its hyperparameters were selected on validation coverage error) "
        f"misses nominal by {gap.loc[0.8]:+.2f}, {gap.loc[0.9]:+.2f} and {gap.loc[0.95]:+.2f} pp at 80/90/95% "
        f"(3-seed mean), with mean 90% interval width {summ.loc[0.9, 'mean_width']:.1f} log-units; the deep ensemble "
        f"behaves alike. PIT uniformity is rejected for every MC-dropout seed and for the ensemble (KS p between "
        f"{pit['KS p'].min():.0e} and {pit['KS p'].max():.0e}). Error bars: 95% Clopper–Pearson intervals "
        f"(seed-averaged), n = {n:,} events. Figure 2b reproduces the E8 run's calibration audit as rendered.")
    b.save_figure(art, fig)
    b.save_table(art, pd.DataFrame([{
        "method": g.method, "nominal": g.nominal, "runs": int(g.n_runs),
        "empirical coverage [95% CP CI]": _fmt_ci(g.empirical, g.cp_lo, g.cp_hi, 4),
        "gap (pp)": round(100 * (g.empirical - g.nominal), 2),
        "sd across seeds": round(float(g.sd), 4) if np.isfinite(g.sd) else np.nan,
        "mean width (log10)": round(float(g.width), 2), "n events": n,
    } for g in agg.sort_values(["method", "nominal"]).itertuples()]))
    b.save_table(art, pit.reset_index(), suffix="_pit_ks")
    art.notes.append("E8 recorded coverage and n but no interval; the Clopper–Pearson intervals are computed here "
                     "from the recorded k/n, each k verified integral.")
    b._claim_sources(art, ["e8_coverage_all", "e8_coverage_summary", "e8_pit_ks", "e1_high_risk_prevalence"])
    b.register(art)

    # 2b: the E8 run's own figure, carried verbatim. Its per-event predictive distributions were
    # never persisted, so it cannot be rebuilt from tables; refitting MC-dropout under the
    # current config hash would need a fresh 24-trial search. Disclosed, not hidden.
    art2 = Artifact("F02b_bayesian_calibration_audit_as_rendered", "figure",
                    "E8 calibration audit (reliability, PIT, widths) as rendered by the E8 run", ("E8",))
    b.fig_dir.mkdir(parents=True, exist_ok=True)
    src = Path(b.cfg.path("figures_dir"))
    for ext in ("png", "pdf"):
        f = src / f"e8_calibration_audit.{ext}"
        if not f.exists():
            raise FileNotFoundError(f"E8's rendered figure is missing: {f}")
        out = b.fig_dir / f"{art2.ident}.{ext}"
        shutil.copyfile(f, out)
        art2.files.append(f"{b.rel(out)}")
        art2.sources[f"figures/e8_calibration_audit.{ext}"] = hashlib.sha256(f.read_bytes()).hexdigest()
    art2.caption = ("**Figure 2b.** The E8 run's calibration audit, reproduced as rendered: reliability, the PIT "
                    "histogram (non-uniform) and interval widths. Carried verbatim from the E8 run, not rebuilt, "
                    "and not restyled.")
    art2.notes.append("NOT regenerable from tables: E8's per-event predictive distributions were never persisted. "
                      "Rebuilding needs an MC-dropout refit, which under the current config hash requires a fresh "
                      "24-trial search (no cache). Traceable to the E8 run through its provenance sidecar.")
    b.register(art2)


def build_f03_e9_machinery(b: Builder) -> None:
    """E9 — the conformal machinery tracks nominal where its assumptions hold, both sidednesses."""
    plt = b.plt
    art = Artifact("F03_machinery_validation", "figure",
                   "Machinery validation on the exchangeable self-split (E9), both sidednesses", ("E9",))
    c = b.table("e9e11_coverage")
    e9 = c[c["method"] == "E9_selftest"].copy()
    e9["ci_contains_nominal"] = [consistent_with_exact_coverage(r.cp_lo_mean, r.cp_hi_mean, r.nominal)
                                 for r in e9.itertuples()]
    two, up = e9[e9["sided"] == "two"], e9[e9["sided"] == "upper"]
    up_l = up[up["learner"] != "persistence"]
    pers_up = up[up["learner"] == "persistence"]
    lv = sorted(e9["nominal"].unique())

    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE_COL_IN, 2.7), sharey=True,
                             gridspec_kw={"width_ratios": [4, 3]})
    for ax, d, learners, title in ((axes[0], two, LEARNERS, "(a) Two-sided intervals"),
                                   (axes[1], up_l, LEARNERS[1:], "(b) One-sided upper bounds, learned models")):
        for i, (l_, col, mk) in enumerate(zip(lv, (S1, S2, S3), MARK[:3], strict=True)):
            g = d[np.isclose(d["nominal"], l_)].set_index("learner").reindex(learners)
            x = np.arange(len(learners)) + (i - 1) * 0.22
            _gap_errorbar(ax, x, g["coverage_mean"], g["cp_lo_mean"], g["cp_hi_mean"], l_, colour=col, marker=mk,
                          label=f"nominal {_lvl(l_)}")
        _nominal_line(ax)
        ax.set_xticks(np.arange(len(learners)))
        ax.set_xticklabels([LEARNER_LABEL[x] for x in learners])
        ax.set_title(title)
    axes[0].set_ylabel("coverage − nominal  [pp]")
    axes[0].legend(frameon=False, loc="lower left", ncol=3)
    fig.tight_layout()

    def summary(d):
        w = d.loc[d["gap_pp"].abs().idxmax()]
        exc = d[~d["ci_contains_nominal"]]
        s = (f"largest |gap| {abs(w.gap_pp):.2f} pp ({LEARNER_LABEL[w.learner]} at {_lvl(w.nominal)}); the 95% "
             f"Clopper–Pearson interval contains nominal in {int(d['ci_contains_nominal'].sum())} of {len(d)} cells")
        if len(exc):
            s += " — the exception" + ("s" if len(exc) > 1 else "") + ", " + "; ".join(
                f"{LEARNER_LABEL[r.learner]} at {_lvl(r.nominal)}, {'over' if r.gap_pp > 0 else 'under'}-covers by "
                f"{abs(r.gap_pp):.2f} pp" for r in exc.itertuples())
        return s

    pc = pers_up.set_index("nominal")["coverage_mean"]
    _require(bool(np.isclose(pc.loc[0.8], pc.loc[0.9])), "persistence one-sided coverage identical at 80% and 90%")
    art.caption = (
        f"**Figure 3.** Machinery validation (E9) on the exchangeable self-split (n = {int(e9['n'].iloc[0]):,} events, "
        f"3 seeds), where unweighted split conformal should cover at nominal. (a) Two-sided: {summary(two)}. "
        f"(b) One-sided, learned models: {summary(up_l)}. Persistence's one-sided bound is degenerate even here — "
        f"coverage {pc.loc[0.8]:.4f} at both 80% and 90% — because a large share of its signed residuals are exactly "
        f"zero (Gate 2 diagnosis); its one-sided bounds are excluded from every coverage claim. On exchangeable data "
        f"a deviation in either direction indicates a defect, so exactness is a two-sided question (Figure 12). "
        f"Error bars: 95% Clopper–Pearson intervals (seed-averaged).")
    b.save_figure(art, fig)
    b.save_table(art, pd.DataFrame([{
        "learner": LEARNER_LABEL[r.learner], "sided": r.sided, "nominal": r.nominal, "n": int(r.n),
        "coverage [95% CP CI]": _fmt_ci(r.coverage_mean, r.cp_lo_mean, r.cp_hi_mean, 4),
        "gap (pp)": round(r.gap_pp, 2), "CI contains nominal": bool(r.ci_contains_nominal),
    } for r in e9.sort_values(["sided", "learner", "nominal"]).itertuples()]))
    art.notes.append("E9's recorded pass criterion was coverage tracking nominal (largest |gap| 1.18 pp in its report). "
                     "The CI-contains-nominal column applies the project's exactness definition "
                     "(robustness.consistent_with_exact_coverage) to the same table.")
    b._claim_sources(art, ["e9e11_coverage"])
    b.register(art)


def build_f04_gate2_headline(b: Builder) -> None:
    """E11 — rule-derived weighting restores two-sided coverage; robust to mission clustering (E17)."""
    plt = b.plt
    art = Artifact("F04_gate2_headline", "figure",
                   "Gate 2 headline: naive vs rule-weighted two-sided coverage, and its robustness to clustering",
                   ("E10", "E11", "E17"))
    c = b.table("e9e11_coverage")
    cb, verdict = b.table("e17_h1_cluster_bootstrap"), b.table("e17_h1_gate2_verdict")
    mcn = b.table("e11_primary_mcnemar")
    prim = b.cfg.power.nominal_coverage_primary
    two = c[(c["sided"] == "two") & c["method"].isin(["E10_naive_official", "E11_weighted_rule"])]

    # E17 re-derived these coverages from fresh fits; they must count exactly E11's covered
    # events. Compared as integer counts over (events x seeds): the two runs average the same
    # per-seed counts in a different order, which can differ by one ULP (1.1e-16) in the float.
    for r in cb[cb["sided"] == "two"].itertuples():
        e = _row(two, learner=r.learner, method=r.method, nominal=float(r.nominal))
        tot = int(r.n_events) * int(e["n_seeds"])
        k11, k17 = e["coverage_mean"] * tot, r.coverage * tot
        if max(abs(k11 - round(k11)), abs(k17 - round(k17))) > 1e-6 or round(k11) != round(k17):
            raise ValueError(f"E17 and E11 disagree on {r.learner} {r.method} @ {r.nominal}: would mix runs")

    rows, verdicts = [], {}
    for lrn in LEARNERS:
        for lv in sorted(two["nominal"].unique()):
            nv = _row(two, learner=lrn, method="E10_naive_official", nominal=float(lv))
            wv = _row(two, learner=lrn, method="E11_weighted_rule", nominal=float(lv))
            v = restoration_verdict(nv.cp_lo_mean, nv.cp_hi_mean, wv.cp_lo_mean, wv.cp_hi_mean, lv)
            verdicts[(lrn, lv)] = v["verdict"]
            rows.append({"learner": LEARNER_LABEL[lrn], "nominal": lv, "n": int(nv["n"]),
                         "naive coverage [95% CP CI]": _fmt_ci(nv.coverage_mean, nv.cp_lo_mean, nv.cp_hi_mean, 4),
                         "weighted coverage [95% CP CI]": _fmt_ci(wv.coverage_mean, wv.cp_lo_mean, wv.cp_hi_mean, 4),
                         "naive median width": round(nv.median_width_mean, 1),
                         "weighted median width": round(wv.median_width_mean, 1),
                         "verdict (coverage ≥ nominal)": v["verdict"]})
    _require(all(verdicts[(lrn, prim)] == RESTORED for lrn in LEARNERS), f"RESTORED for every learner at {prim}")

    fig, (a, bb) = plt.subplots(1, 2, figsize=(DOUBLE_COL_IN, 2.8), gridspec_kw={"width_ratios": [1.2, 1]})
    p = two[np.isclose(two["nominal"], prim)]
    for j, (meth, colour, mk, lab) in enumerate((("E10_naive_official", S1, MARK[0], "naive split conformal (E10)"),
                                                 ("E11_weighted_rule", S2, MARK[1], "rule-weighted (E11)"))):
        g = p[p["method"] == meth].set_index("learner").reindex(LEARNERS)
        x = np.arange(len(LEARNERS)) + (j - 0.5) * 0.28
        a.errorbar(x, g["coverage_mean"], yerr=[g["coverage_mean"] - g["cp_lo_mean"], g["cp_hi_mean"] - g["coverage_mean"]],
                   fmt=mk, color=colour, ms=5, capsize=2, lw=1.2, label=lab)
    _nominal_line(a, prim)
    a.set_xticks(np.arange(len(LEARNERS)))
    a.set_xticklabels([LEARNER_LABEL[x] for x in LEARNERS])
    a.set(ylabel="empirical coverage", title=f"(a) Official test set, nominal {_lvl(prim)}, 95% CP intervals")
    a.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)

    rb = cb[(cb["sided"] == "two") & np.isclose(cb["nominal"], prim)]
    lrn_b = [x for x in LEARNERS if x in set(rb["learner"])]
    for j, (meth, colour) in enumerate((("E10_naive_official", S1), ("E11_weighted_rule", S2))):
        g = rb[rb["method"] == meth].set_index("learner").reindex(lrn_b)
        for k, (scheme, mk) in enumerate((("iid", MARK[0] if j == 0 else MARK[1]), ("cluster", MARK[2]))):
            x = np.arange(len(lrn_b)) + (j - 0.5) * 0.4 + (k - 0.5) * 0.15
            lo, hi = g[f"{scheme}_lo"], g[f"{scheme}_hi"]
            bb.errorbar(x, g["coverage"], yerr=[g["coverage"] - lo, hi - g["coverage"]], fmt=mk, color=colour, ms=4.5,
                        capsize=2, lw=1.2, mfc=colour if scheme == "iid" else SURFACE,
                        label=f"{'naive' if j == 0 else 'weighted'}, {scheme} bootstrap")
    _nominal_line(bb, prim)
    bb.set_xticks(np.arange(len(lrn_b)))
    bb.set_xticklabels([LEARNER_LABEL[x] for x in lrn_b])
    bb.set(title=f"(b) iid vs mission-cluster bootstrap (E17), {_lvl(prim)}")
    bb.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=6.2)
    fig.tight_layout()

    head = verdict[(verdict["learner"] == "persistence") & np.isclose(verdict["nominal"], prim)].set_index("scheme")
    _require(bool((head["verdict"] == RESTORED).all() and (head["weighted_lo"] > prim).all()),
             "persistence RESTORED under both schemes with the weighted CI wholly above nominal")
    agree = verdict.pivot_table(index=["learner", "nominal"], columns="scheme", values="verdict", aggfunc="first")
    same = agree["iid"] == agree["cluster"]
    fragile = list(agree.index[~same])
    for lrn, lv in fragile:
        w = verdict[(verdict["learner"] == lrn) & np.isclose(verdict["nominal"], lv)]
        _require(bool((w["weighted_coverage"] < lv).all()), f"{lrn}@{lv}: weighted point estimate below nominal")
    m = mcn.iloc[0]
    n_clusters = int(cb["n_clusters"].iloc[0])
    art.caption = (
        f"**Figure 4.** Rule-derived weighting restores two-sided marginal coverage on the selection-biased official "
        f"test set (n = {int(p['n'].iloc[0]):,}). (a) At nominal {_lvl(prim)}, naive split conformal's under-coverage is "
        f"established for every base learner (interval wholly below nominal) and the rule-weighted version's is not. "
        f"The pre-registered primary contrast "
        f"(persistence) moves from {m.E10_coverage:.3f} to {m.E11_coverage:.3f} (McNemar exact p = {m.mcnemar_p:.1e}; "
        f"{int(m.weighted_only)} events uncovered → covered, {int(m.naive_only)} the reverse). (b) The headline is robust "
        f"to clustering events by mission ({n_clusters} missions): under both the iid and the mission-level cluster "
        f"bootstrap, persistence's weighted interval lies wholly above nominal (lower bounds "
        f"{head.loc['iid', 'weighted_lo']:.4f} and {head.loc['cluster', 'weighted_lo']:.4f}) and its naive interval "
        f"wholly below. Across the {len(agree)} learner × level cells the two schemes agree in {int(same.sum())}"
        + ("; the exception — " + "; ".join(f"{LEARNER_LABEL[lrn]} at {_lvl(lv)}" for lrn, lv in fragile)
           + " — is not an improvement in coverage: the weighted point estimate is below nominal under both schemes, "
             "and the cluster verdict passes only because its wider interval can no longer establish under-coverage"
           if fragile else "")
        + ". Verdict: RESTORED iff the naive interval's upper bound is below nominal and the weighted one's is not — "
          "the one-sided guarantee, coverage ≥ 1 − α, so over-coverage satisfies it. MC-dropout was not refit for "
          "E17's robustness check and is absent from (b).")
    b.save_figure(art, fig)
    b.save_table(art, pd.DataFrame(rows))
    rv = verdict.copy()
    rv["learner"] = rv["learner"].map(LEARNER_LABEL)
    b.save_table(art, rv[["learner", "nominal", "scheme", "naive_coverage", "weighted_coverage", "naive_lo", "naive_hi",
                          "weighted_lo", "weighted_hi", "verdict"]].rename(
        columns={"verdict": "verdict (coverage ≥ nominal)"}), suffix="_robustness")
    b.save_table(art, mcn, suffix="_primary_contrast")
    art.notes.append("Panel (a) and the main table use E11's Clopper–Pearson intervals; panel (b) and the robustness "
                     "table use E17's bootstrap intervals. E17's covered-event counts are checked to equal E11's exactly first (the floats can differ by one ULP from seed-averaging order). "
                     "The superseded CI-containment verdict is deliberately not reproduced in the manuscript table.")
    b._claim_sources(art, ["e9e11_coverage", "e17_h1_cluster_bootstrap", "e17_h1_gate2_verdict", "e11_primary_mcnemar"])
    b.register(art)


def build_f05_one_sided(b: Builder) -> None:
    """E11 — one-sided upper bounds: rule-derived weighting does not restore them."""
    plt = b.plt
    art = Artifact("F05_one_sided_non_restoration", "figure",
                   "One-sided upper bounds: naive vs rule-weighted split conformal (learned models)", ("E10", "E11", "E9"))
    c = b.table("e9e11_coverage")
    up = c[(c["sided"] == "upper") & c["method"].isin(["E10_naive_official", "E11_weighted_rule"])]
    learners = LEARNERS[1:]           # persistence's one-sided bound is degenerate (Figure 3); excluded
    lv = sorted(up["nominal"].unique())
    cells = []
    for lrn in learners:
        for l_ in lv:
            nv = _row(up, learner=lrn, method="E10_naive_official", nominal=float(l_))
            wv = _row(up, learner=lrn, method="E11_weighted_rule", nominal=float(l_))
            v = restoration_verdict(nv.cp_lo_mean, nv.cp_hi_mean, wv.cp_lo_mean, wv.cp_hi_mean, l_)
            cells.append({"lrn": lrn, "nominal": l_, "nv": nv, "wv": wv, **v,
                          "weighted_meets": meets_coverage_guarantee(wv.cp_lo_mean, wv.cp_hi_mean, l_)})
    _require(not any(x["verdict"] == RESTORED for x in cells), "no one-sided cell is RESTORED")
    created = [x for x in cells if x["verdict"] == NO_DEFICIT and not x["weighted_meets"]]
    not_rest = [x for x in cells if x["verdict"] == NOT_RESTORED]

    fig, axes = plt.subplots(1, len(learners), figsize=(DOUBLE_COL_IN, 2.5), sharey=True)
    for ax, lrn in zip(axes, learners, strict=True):
        for j, (meth, colour, mk, lab) in enumerate((("E10_naive_official", S1, MARK[0], "naive (E10)"),
                                                     ("E11_weighted_rule", S2, MARK[1], "rule-weighted (E11)"))):
            g = up[(up["learner"] == lrn) & (up["method"] == meth)].sort_values("nominal")
            _gap_errorbar(ax, np.arange(len(lv)) + (j - 0.5) * 0.25, g["coverage_mean"], g["cp_lo_mean"],
                          g["cp_hi_mean"], g["nominal"].to_numpy(), colour=colour, marker=mk, label=lab)
        _nominal_line(ax)
        ax.set_xticks(np.arange(len(lv)))
        ax.set_xticklabels([f"nominal {_lvl(x)}" for x in lv])
        ax.set_title(LEARNER_LABEL[lrn])
    axes[0].set_ylabel("coverage − nominal  [pp]")
    axes[0].legend(frameon=False, loc="upper right")
    fig.tight_layout()

    def cellstr(x):
        return (f"{LEARNER_LABEL[x['lrn']]} {x['nv'].coverage_mean:.3f} → {x['wv'].coverage_mean:.3f}")

    lv_nr = sorted({x["nominal"] for x in not_rest})
    lv_cr = sorted({x["nominal"] for x in created})
    art.caption = (
        f"**Figure 5.** Rule-derived weighting does not restore one-sided upper-bound coverage for any learned model "
        f"(official test set, n = {int(up['n'].iloc[0]):,}). Under the same criterion as Figure 4: at "
        + " and ".join(_lvl(x) for x in lv_nr)
        + f" the naive bound under-covers and the weighted bound still does ({len(not_rest)} of {len(cells)} cells: "
        + "; ".join(cellstr(x) for x in not_rest) + ")"
        + ((f". At {' and '.join(_lvl(x) for x in lv_cr)} the naive bound shows no deficit, and the weighted bound's "
            f"interval lies wholly below nominal ({'; '.join(cellstr(x) for x in created)}): there, weighting creates "
            f"a one-sided deficit where there was none") if created else "")
        + ". The same one-sided code path covers at nominal on the exchangeable self-split (Figure 3b), so this is "
          "an effect of the shift, not of the implementation. Persistence is excluded: its one-sided bound is "
          "degenerate (Figure 3). 95% Clopper–Pearson intervals, 3 seeds.")
    b.save_figure(art, fig)
    b.save_table(art, pd.DataFrame([{
        "learner": LEARNER_LABEL[x["lrn"]], "nominal": x["nominal"], "n": int(x["nv"]["n"]),
        "naive coverage [95% CP CI]": _fmt_ci(x["nv"].coverage_mean, x["nv"].cp_lo_mean, x["nv"].cp_hi_mean, 4),
        "weighted coverage [95% CP CI]": _fmt_ci(x["wv"].coverage_mean, x["wv"].cp_lo_mean, x["wv"].cp_hi_mean, 4),
        "change (pp)": round(100 * (x["wv"].coverage_mean - x["nv"].coverage_mean), 2),
        "verdict (coverage ≥ nominal)": x["verdict"],
        "weighted arm meets coverage ≥ nominal": bool(x["weighted_meets"]),
    } for x in cells]))
    art.notes.append("Verdicts from robustness.restoration_verdict (the final one-sided criterion) applied per level. "
                     "The Gate 2 record describes the one-sided result as non-restoration without a per-level "
                     "breakdown; at 80% the final criterion gives 'no deficit to restore' for the naive arm while the "
                     "weighted arm fails — reported in the E18 checkpoint (Part D), not silently reconciled.")
    b._claim_sources(art, ["e9e11_coverage"])
    b.register(art)


def build_f06_cqr(b: Builder) -> None:
    """E12 (+ E17 H2) — CQR adapts its width, and rule-weighting lowers its coverage in both arms."""
    plt = b.plt
    art = Artifact("F06_cqr_adaptivity_and_weighting", "figure",
                   "CQR: adaptive widths, and the effect of rule-weighting on two- and one-sided coverage",
                   ("E12", "E17"))
    ad, widths = b.table("e12_adaptivity"), b.table("e12_widths")
    two, one, per_seed = b.table("e12_coverage"), b.table("e17_h2_coverage"), b.table("e17_h2_per_seed")
    prim = b.cfg.power.nominal_coverage_primary
    lv = sorted(two["nominal"].unique())
    arms = {  # sidedness -> (table, naive, weighted, self-test)
        "two": (two, "E12_cqr_naive", "E12_cqr_weighted_rule", "E12_cqr_selftest"),
        "upper": (one, "E17_cqr_upper_naive", "E17_cqr_upper_weighted_rule", "E17_cqr_upper_selftest"),
    }
    d = {s: {l_: {k: _row(t, method=m, nominal=float(l_)) for k, m in zip(("naive", "weighted", "self"), ms, strict=True)}
             for l_ in lv} for s, (t, *ms) in arms.items()}
    change = {s: [100 * (d[s][l_]["weighted"].coverage_mean - d[s][l_]["naive"].coverage_mean) for l_ in lv] for s in d}
    _require(all(x < 0 for s in change for x in change[s]), "weighting lowers CQR coverage in both arms at every level")
    _require(all(o < t for o, t in zip(change["upper"], change["two"], strict=True)), "the one-sided decrease is larger at every level")
    new_def = [l_ for l_ in lv
               if meets_coverage_guarantee(d["upper"][l_]["naive"].cp_lo_mean, d["upper"][l_]["naive"].cp_hi_mean, l_)
               and not meets_coverage_guarantee(d["upper"][l_]["weighted"].cp_lo_mean,
                                                d["upper"][l_]["weighted"].cp_hi_mean, l_)]
    two_new = [l_ for l_ in lv
               if meets_coverage_guarantee(d["two"][l_]["naive"].cp_lo_mean, d["two"][l_]["naive"].cp_hi_mean, l_)
               and not meets_coverage_guarantee(d["two"][l_]["weighted"].cp_lo_mean,
                                                d["two"][l_]["weighted"].cp_hi_mean, l_)]
    _require(len(new_def) >= 1 and not two_new, "only one-sided CQR gains a deficit it did not have")
    self_exact = all(consistent_with_exact_coverage(d[s][l_]["self"].cp_lo_mean, d[s][l_]["self"].cp_hi_mean, l_)
                     for s in d for l_ in lv)
    _require(self_exact, "the CQR self-test covers at nominal in both sidednesses")
    ps = per_seed[per_seed["sided"] == "upper"].pivot_table(index=["nominal", "seed"], columns="method", values="coverage")
    lower_cells = int((ps["E17_cqr_upper_weighted_rule"] < ps["E17_cqr_upper_naive"]).sum())
    wrow = _row(widths, nominal=float(prim))
    _require(bool(wrow.split_width_sd < 1e-9 < wrow.cqr_width_sd), "split widths constant, CQR widths vary")

    fig, axes = plt.subplots(1, 3, figsize=(DOUBLE_COL_IN, 2.6), gridspec_kw={"width_ratios": [1.15, 1, 1]})
    a = axes[0]
    a.scatter(ad["risk_last"], ad["cqr_width"], s=4, color=S1, alpha=0.35, lw=0, label="CQR (per event)", zorder=2)
    a.plot(np.sort(ad["risk_last"]), np.full(len(ad), float(ad["split_width"].median())), color=S2, lw=1.6,
           label="split conformal (constant)", zorder=3)
    a.set(xlabel="last pre-cutoff risk  [log$_{10}$ Pc]", ylabel="interval width  [log$_{10}$ units]",
          title=f"(a) Width vs input risk, {_lvl(prim)}")
    a.legend(frameon=False, loc="lower right", markerscale=3)
    for ax, s, title in ((axes[1], "two", "(b) Two-sided CQR"), (axes[2], "upper", "(c) One-sided CQR")):
        for j, (k, colour, mk, lab) in enumerate((("naive", S1, MARK[0], "naive"),
                                                  ("weighted", S2, MARK[1], "rule-weighted"),
                                                  ("self", S3, MARK[2], "self-test (exchangeable)"))):
            rows = [d[s][l_][k] for l_ in lv]
            _gap_errorbar(ax, np.arange(len(lv)) + (j - 1) * 0.22, [r.coverage_mean for r in rows],
                          [r.cp_lo_mean for r in rows], [r.cp_hi_mean for r in rows], np.array(lv),
                          colour=colour, marker=mk, label=lab)
        _nominal_line(ax)
        ax.set_xticks(np.arange(len(lv)))
        ax.set_xticklabels([_lvl(x) for x in lv])
        ax.set(xlabel="nominal", title=title)
    axes[1].set_ylabel("coverage − nominal  [pp]")
    axes[1].sharey(axes[2])
    h, lab = axes[2].get_legend_handles_labels()
    fig.legend(h, lab, frameon=False, loc="lower center", ncol=3, fontsize=6.6, bbox_to_anchor=(0.62, -0.06))
    fig.tight_layout()

    fmt = lambda xs: "/".join(f"{x:+.2f}" for x in xs)   # noqa: E731
    nd = d["upper"][new_def[0]]
    art.caption = (
        f"**Figure 6.** Conformalized quantile regression (E12; GBM quantile heads). (a) CQR adapts: its widths vary "
        f"from event to event (per-event sd {wrow.cqr_width_sd:.1f} log-units at {_lvl(prim)}) where split-conformal "
        f"widths are constant, and are {1 / wrow.width_ratio_cqr_over_split:.1f}× narrower in the median "
        f"({wrow.cqr_median_width:.1f} vs {wrow.split_median_width:.1f} log-units, rule-weighted; 3-seed means; "
        f"the scatter shows the median seed). "
        f"(b, c) Rule-derived weighting lowers CQR coverage in both arms at every level — two-sided {fmt(change['two'])} "
        f"pp, one-sided {fmt(change['upper'])} pp at {'/'.join(_lvl(x) for x in lv)} — and the one-sided decrease is "
        f"larger at every level (one-sided: lower in {lower_cells} of {len(ps)} level × seed cells). Among the CQR arms, "
        f"only one-sided CQR gains a deficit it did not have: at {_lvl(new_def[0])} its naive interval "
        f"[{nd['naive'].cp_lo_mean:.4f}, {nd['naive'].cp_hi_mean:.4f}] shows none and its weighted interval "
        f"[{nd['weighted'].cp_lo_mean:.4f}, {nd['weighted'].cp_hi_mean:.4f}] lies wholly below nominal; two-sided naive "
        f"CQR already under-covers there, so weighting deepens an existing deficit. Both arms share one quantile head "
        f"and differ only in the calibration quantile, and coverage is monotone in it, so lower coverage implies a lower "
        f"weighted quantile; why the rule weights lower it is not claimed. The unweighted self-test covers at nominal "
        f"in both sidednesses, so the machinery is not at fault. 95% Clopper–Pearson intervals, 3 seeds, "
        f"n = {int(d['two'][prim]['naive']['n']):,} official-test events.")
    b.save_figure(art, fig)
    rows = []
    for s in d:
        for l_ in lv:
            r = d[s][l_]
            rows.append({"sided": s, "nominal": l_,
                         **{f"{k} coverage [95% CP CI]": _fmt_ci(r[k].coverage_mean, r[k].cp_lo_mean, r[k].cp_hi_mean, 4)
                            for k in ("naive", "weighted", "self")},
                         "weighting change (pp)": round(100 * (r["weighted"].coverage_mean - r["naive"].coverage_mean), 2),
                         "naive meets coverage ≥ nominal": meets_coverage_guarantee(r["naive"].cp_lo_mean,
                                                                                   r["naive"].cp_hi_mean, l_),
                         "weighted meets coverage ≥ nominal": meets_coverage_guarantee(r["weighted"].cp_lo_mean,
                                                                                      r["weighted"].cp_hi_mean, l_),
                         "n (official / self-test)": f"{int(r['naive']['n'])} / {int(r['self']['n'])}"})
    b.save_table(art, pd.DataFrame(rows))
    b.save_table(art, widths, suffix="_widths")
    art.notes.append("Two-sided CQR from E12 (re-rendered and snapshot-verified bit-for-bit in E18 Part A); one-sided "
                     "CQR from E17 H2. Panel (a) is the E12 median seed at the primary level (e12_adaptivity).")
    b._claim_sources(art, ["e12_adaptivity", "e12_widths", "e12_coverage", "e17_h2_coverage", "e17_h2_per_seed"])
    b.register(art)


def build_f07_labelnoise(b: Builder) -> None:
    """E14 — label-noise sensitivity; the flat primary curve is width-driven (caveat in the caption)."""
    plt = b.plt
    art = Artifact("F07_label_noise_sensitivity", "figure", "Label-noise sensitivity (E14)", ("E14",))
    cov, trend = b.table("e14_coverage"), b.table("e14_trend")
    prim = b.cfg.power.nominal_coverage_primary
    c9 = cov[np.isclose(cov["nominal"], prim)]
    prim_curve = c9[(c9["population"] == "m7_high_risk") & (c9["method"] == "E11_weighted_rule")
                    & (c9["learner"] == "persistence")]
    flat = prim_curve.groupby("arm")["coverage_mean"].agg(["min", "max"])
    _require(bool((flat["min"] == flat["max"]).all() and flat["min"].nunique() == 1),
             "the primary curve is flat and identical in both label arms")
    flat_value = float(flat["min"].iloc[0])
    w_all = c9[(c9["arm"] == "direct") & (c9["population"] == "m7_all")]
    width = float(_row(w_all, method="E11_weighted_rule", learner="persistence", scale=1.0)["median_width_mean"])
    width_gbm = float(_row(w_all, method="E11_weighted_rule", learner="gbm", scale=1.0)["median_width_mean"])
    width_cqr = float(_row(w_all, method="E12_cqr_weighted_rule", learner="gbm", scale=1.0)["median_width_mean"])
    _require(width > width_gbm > width_cqr, "persistence's intervals are the widest")
    series = [("E11_weighted_rule", "persistence", "rule-weighted, persistence", S1, MARK[0]),
              ("E11_weighted_rule", "gbm", "rule-weighted, GBM", S2, MARK[1]),
              ("E12_cqr_weighted_rule", "gbm", "rule-weighted CQR, GBM", S3, MARK[2]),
              ("E10_naive_official", "gbm", "naive, GBM", S4, MARK[3])]
    whole = c9[(c9["arm"] == "direct") & (c9["population"] == "m7_all")]
    tr = trend[(trend["arm"] == "direct") & (trend["population"] == "m7_all") & np.isclose(trend["nominal"], prim)]

    fig, (a, c) = plt.subplots(1, 2, figsize=(DOUBLE_COL_IN, 2.7), gridspec_kw={"width_ratios": [1, 1.35]})
    for j, (arm, colour, mk) in enumerate((("direct", S1, MARK[0]), ("anchored", S2, MARK[1]))):
        g = prim_curve[prim_curve["arm"] == arm].sort_values("scale")
        x = g["scale"] + (j - 0.5) * 0.03
        a.errorbar(x, g["coverage_mean"], yerr=[g["coverage_mean"] - g["cp_lo_mean"], g["cp_hi_mean"] - g["coverage_mean"]],
                   fmt=mk + "-", color=colour, ms=4.5, capsize=2, lw=1.2, label=f"{arm} labels")
    _nominal_line(a, prim)
    a.set(xlabel="covariance scale s", ylabel="coverage",
          title=f"(a) Primary: high-risk stratum (n = {int(prim_curve['n'].iloc[0])}), persistence")
    a.legend(frameon=False, loc="lower right")
    for meth, lrn, lab, colour, mk in series:
        g = whole[(whole["method"] == meth) & (whole["learner"] == lrn)].sort_values("scale")
        c.errorbar(g["scale"], g["coverage_mean"], yerr=[g["coverage_mean"] - g["cp_lo_mean"],
                                                        g["cp_hi_mean"] - g["coverage_mean"]],
                   fmt=mk + "-", color=colour, ms=4.5, capsize=2, lw=1.2, label=lab)
    _nominal_line(c, prim)
    c.set(xlabel="covariance scale s", ylabel="coverage",
          title=f"(b) All events (n = {int(whole['n'].iloc[0]):,}), direct labels")
    c.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=6.4)
    fig.tight_layout()

    def trend_str(meth, lrn, lab):
        g = whole[(whole["method"] == meth) & (whole["learner"] == lrn)].sort_values("scale")
        t = _row(tr, method=meth, learner=lrn)
        return (f"{lab} {g['coverage_mean'].iloc[0]:.4f} → {g['coverage_mean'].iloc[-1]:.4f} (slope "
                f"{t.slope_per_unit_scale:+.3f} per unit s, 95% CI [{t.slope_lo:+.3f}, {t.slope_hi:+.3f}], "
                f"Spearman ρ = {t.spearman_rho:+.2f})")

    for meth, lrn, *_ in series[1:]:
        _require(float(_row(tr, method=meth, learner=lrn).spearman_rho) == -1.0, f"{meth}/{lrn} monotone decreasing")
    smin, smax = cov["scale"].min(), cov["scale"].max()
    art.caption = (
        f"**Figure 7.** Label-noise sensitivity (E14): coverage when the covariance behind each reported risk is "
        f"rescaled by s ∈ [{smin:g}, {smax:g}] and the labels recomputed (s = 1 reproduces the reported labels). "
        f"(a) The pre-registered primary curve — rule-weighted conformal on persistence, truly high-risk events, "
        f"nominal {_lvl(prim)} — is flat at {flat_value:.4f} at all {prim_curve['scale'].nunique()} scales, in both "
        f"label arms. **This flatness reflects interval width, not robustness to label noise:** persistence's "
        f"{_lvl(prim)} intervals have median width {width:.1f} log-units (rule-weighted GBM {width_gbm:.1f}, CQR "
        f"{width_cqr:.1f}), and (b) the methods with narrower intervals degrade monotonically under the same "
        f"perturbation — "
        + "; ".join(trend_str(m, l_, lab) for m, l_, lab, *_ in series[1:])
        + f"; persistence itself drifts slightly upward: {trend_str(*series[0][:2], '').strip()}. "
          "Error bars: 95% Clopper–Pearson intervals, 3 seeds; descriptive, no confirmatory test.")
    b.save_figure(art, fig)
    keep = cov[np.isclose(cov["nominal"], prim)
               & (((cov["population"] == "m7_high_risk") & (cov["method"] == "E11_weighted_rule")
                   & (cov["learner"] == "persistence"))
                  | ((cov["population"] == "m7_all") & (cov["arm"] == "direct")))]
    b.save_table(art, pd.DataFrame([{
        "population": r.population, "arm": r.arm, "method": r.method, "learner": LEARNER_LABEL[r.learner],
        "scale s": r.scale, "n": int(r.n), "coverage [95% CP CI]": _fmt_ci(r.coverage_mean, r.cp_lo_mean, r.cp_hi_mean, 4),
        "median width": round(r.median_width_mean, 1),
    } for r in keep.sort_values(["population", "arm", "method", "learner", "scale"]).itertuples()]))
    b.save_table(art, tr.drop(columns=["population", "arm"]).assign(learner=lambda x: x["learner"].map(LEARNER_LABEL)),
                 suffix="_trends")
    art.notes.append("The size of the label shift the rescaling induces in the high-risk stratum (median |Δ| ≤ 0.12, "
                     "95th percentile ≤ 1.9 log-units; DECISIONS.md, E14 finding 3) was printed by the E14 run but never "
                     "persisted as a table, so the caption states the caveat through table-backed quantities (the "
                     "interval width, and the narrower methods' degradation) instead of quoting it.")
    b._claim_sources(art, ["e14_coverage", "e14_trend"])
    b.register(art)


def build_f08_conditional(b: Builder) -> None:
    """E14 — marginal coverage hides high-risk-conditional failure (disclosed, characterised)."""
    plt = b.plt
    art = Artifact("F08_high_risk_conditional_coverage", "figure",
                   "Marginal vs high-risk-conditional coverage (E14, s = 1)", ("E14",))
    cc, cov = b.table("e14_conditional_coverage_anomaly_ci"), b.table("e14_coverage")
    prim = b.cfg.power.nominal_coverage_primary
    methods = [("E11_weighted_rule", "persistence", "rule-weighted\npersistence"),
               ("E11_weighted_rule", "gbm", "rule-weighted\nGBM"),
               ("E12_cqr_weighted_rule", "gbm", "rule-weighted\nCQR (GBM)")]
    marg = {(m, l_): _row(cov, arm="direct", population="m7_all", method=m, learner=l_, nominal=float(prim), scale=1.0)
            for m, l_, _ in methods}
    fig, ax = plt.subplots(figsize=(DOUBLE_COL_IN * 0.62, 2.6))
    y = np.arange(len(methods))[::-1]
    series = [("all events, direct labels", S3, MARK[2], lambda m, l_: marg[(m, l_)]),
              ("high-risk, anchored labels", S1, MARK[0], lambda m, l_: _row(cc, arm="anchored", method=m, learner=l_)),
              ("high-risk, direct labels", S2, MARK[1], lambda m, l_: _row(cc, arm="direct", method=m, learner=l_))]
    for j, (lab, colour, mk, get) in enumerate(series):
        rs = [get(m, l_) for m, l_, _ in methods]
        v = np.array([r.coverage_mean for r in rs])
        lo, hi = np.array([r.boot_lo_mean for r in rs]), np.array([r.boot_hi_mean for r in rs])
        ax.errorbar(v, y + (1 - j) * 0.2, xerr=[v - lo, hi - v], fmt=mk, color=colour, ms=5, capsize=2, lw=1.2, label=lab)
    _nominal_line(ax, prim, horizontal=False)
    ax.set_yticks(y)
    ax.set_yticklabels([m[2] for m in methods])
    ax.set(xlabel=f"coverage at nominal {_lvl(prim)} (dashed)", xlim=(0, 1.02))
    ax.legend(frameon=False, loc="upper left", fontsize=6.4)
    fig.tight_layout()

    g_a, q_a = _row(cc, arm="anchored", method="E11_weighted_rule", learner="gbm"), \
        _row(cc, arm="anchored", method="E12_cqr_weighted_rule", learner="gbm")
    g_d, q_d = _row(cc, arm="direct", method="E11_weighted_rule", learner="gbm"), \
        _row(cc, arm="direct", method="E12_cqr_weighted_rule", learner="gbm")
    p_ = _row(cc, arm="anchored", method="E11_weighted_rule", learner="persistence")
    _require(bool(g_a.boot_hi_mean < prim and q_a.boot_hi_mean < prim and g_d.boot_hi_mean < prim
                  and q_d.boot_hi_mean < prim), "the learned models' conditional intervals lie below nominal")
    _require(bool(max(g_a.boot_hi_mean, q_a.boot_hi_mean) < p_.boot_lo_mean), "both lie below persistence's interval")
    ci = lambda r: f"{r.coverage_mean:.3f} [{r.boot_lo_mean:.3f}, {r.boot_hi_mean:.3f}]"   # noqa: E731
    art.caption = (
        f"**Figure 8.** Marginal coverage can hide subgroup failure, and here it does. At nominal {_lvl(prim)} "
        f"(s = 1, 3 seeds), coverage over all {int(marg[methods[0][:2]]['n']):,} official-test events is "
        + ", ".join(f"{marg[(m, l_)].coverage_mean:.3f}" for m, l_, _ in methods)
        + f" for rule-weighted persistence, GBM and CQR respectively; conditional on the {int(g_a['n'])} truly "
          f"high-risk events it is {ci(g_a)} for GBM and {ci(q_a)} for CQR (anchored labels; direct: {ci(g_d)} and "
          f"{ci(q_d)}), against {ci(p_)} for persistence's far wider intervals. Conformal prediction guarantees "
          "marginal, not conditional, coverage, and group-conditional claims were dropped at Gate 1 for lack of power, "
          "so the conditional shortfall is a disclosed and characterised limitation of the narrow, informative "
          "methods — a separate question from whether their marginal guarantee holds (it does for rule-weighted split "
          "conformal, Figure 4; it does not for rule-weighted CQR, Figures 6 and 11). 95% event-level "
          "percentile-bootstrap intervals (seed-averaged); descriptive, not tested against nominal.")
    b.save_figure(art, fig)
    t = cc.copy()
    t["learner"] = t["learner"].map(LEARNER_LABEL)
    t["coverage [95% bootstrap CI]"] = [_fmt_ci(r.coverage_mean, r.boot_lo_mean, r.boot_hi_mean, 3) for r in cc.itertuples()]
    t["95% CP CI"] = [f"[{r.cp_lo_mean:.3f}, {r.cp_hi_mean:.3f}]" for r in cc.itertuples()]
    t["population"] = "high-risk"
    m_rows = pd.DataFrame([{"arm": "direct", "method": m, "learner": LEARNER_LABEL[l_], "population": "all events",
                            "n": int(marg[(m, l_)]["n"]), "n_seeds": int(marg[(m, l_)]["n_seeds"]),
                            "coverage [95% bootstrap CI]": _fmt_ci(marg[(m, l_)].coverage_mean,
                                                                   marg[(m, l_)].boot_lo_mean,
                                                                   marg[(m, l_)].boot_hi_mean, 3),
                            "95% CP CI": f"[{marg[(m, l_)].cp_lo_mean:.3f}, {marg[(m, l_)].cp_hi_mean:.3f}]"}
                           for m, l_, _ in methods])
    b.save_table(art, pd.concat([t[["population", "arm", "method", "learner", "n", "n_seeds",
                                    "coverage [95% bootstrap CI]", "95% CP CI"]], m_rows], ignore_index=True))
    b._claim_sources(art, ["e14_conditional_coverage_anomaly_ci", "e14_coverage"])
    b.register(art)


def build_f09_rank_invariance(b: Builder) -> None:
    """E15 — Proposition 1 (rank invariance), confirmed empirically across the 20-method classification."""
    plt = b.plt
    art = Artifact("F09_rank_invariance", "figure", "Rank invariance at a matched alert budget (E15)",
                   ("E15", "E15b"))
    summ, cls, alerts = b.table("e15_decision_cost_summary"), b.table("e15b_classification_verdicts"), b.table("e15b_alerts")
    budgets = b.table("e15b_budgets")
    prim = b.cfg.power.nominal_coverage_primary
    K = int(budgets.loc[budgets["primary"], "K"].iloc[0])
    s = summ[(summ["budget"] == "prevalence_matched") & np.isclose(summ["nominal"], prim)]
    trans = cls[cls["structural_class"] == "translation_of_point"]
    _require(bool(trans["verdict"].str.startswith("CONFIRMED").all()), "every translation-class arm confirmed")
    _require(not cls["verdict"].str.contains("CONTRADICT", case=False).any(), "no method contradicts Proposition 1")
    ta = alerts[alerts["method"].isin(set(trans["method"]))]
    _require(bool((ta["max_abs_alert_difference_vs_point"] == 0).all()), "translation arms alert-identical to point")
    klass = {"point": ("point prediction", S1, MARK[0], False),
             "E10_naive_upper": ("split conformal bound (E10)", S1, "o", True),
             "E11_weighted_rule_upper": ("rule-weighted bound (E11)", S1, "s", True),
             "E12_cqr_weighted_rule_upper": ("CQR bound (quantile head)", S2, MARK[1], False),
             "E8_bayes_upper": ("Bayesian bound (E8, event-specific σ)", S3, MARK[2], False)}
    fig, ax = plt.subplots(figsize=(SINGLE_COL_IN * 1.25, 2.9))
    seen = set()
    for i, lrn in enumerate(LEARNERS):
        g = s[s["learner"] == lrn]
        for j, (meth, (lab, colour, mk, hollow)) in enumerate(klass.items()):
            r = g[g["method"] == meth]
            if r.empty:
                continue
            r = r.iloc[0]
            yy = len(LEARNERS) - 1 - i + {"point": 0.0, "E10_naive_upper": 0.0, "E11_weighted_rule_upper": 0.0,
                                          "E12_cqr_weighted_rule_upper": -0.3, "E8_bayes_upper": -0.3}[meth]
            ax.errorbar(r.missed_high_risk, yy, xerr=[[r.missed_high_risk - r.missed_high_risk_lo],
                                                      [r.missed_high_risk_hi - r.missed_high_risk]],
                        fmt=mk, color=colour, mfc=SURFACE if hollow else colour,
                        ms={"E10_naive_upper": 9, "E11_weighted_rule_upper": 12}.get(meth, 5),
                        capsize=2, lw=1.0 if not hollow else 0, label=None if lab in seen else lab, zorder=4 - j)
            seen.add(lab)
    ax.set_yticks(np.arange(len(LEARNERS))[::-1])
    ax.set_yticklabels([LEARNER_LABEL[x] for x in LEARNERS])
    nhr = int(s["n_high_risk"].iloc[0])
    ax.set(xlabel=f"missed high-risk events at K = {K} alerts (of {nhr})", xlim=(0, nhr))
    ax.legend(frameon=False, loc="lower left", fontsize=6, bbox_to_anchor=(0, 1.0), ncol=1)
    fig.tight_layout()

    m = s.set_index(["learner", "method"])["missed_high_risk"]
    _require(bool(m.loc["persistence"].min() == m.min()), "persistence's ranking misses the fewest")
    art.caption = (
        f"**Figure 9.** Rank invariance (Proposition 1). At a matched alert budget, a bound that is a strictly "
        f"increasing function of the point prediction — here, the point plus one shared conformal quantile — raises "
        f"exactly the point prediction's alerts, so calibrating it cannot change the decision. Empirically, all "
        f"{len(trans)} translation-class arms (split and rule-weighted conformal, one-sided and two-sided, four learners) "
        f"reproduce their point prediction's alert set exactly in all {len(ta)} budget × level comparisons (hollow "
        f"markers sit on the solid point markers). Only constructions that re-rank events change the decision: CQR's "
        f"quantile head (GBM: {m.loc[('gbm', 'E12_cqr_weighted_rule_upper')]:.1f} vs {m.loc[('gbm', 'point')]:.1f} "
        f"missed) and E8's event-specific dispersion (MC-dropout: {m.loc[('mc_dropout', 'E8_bayes_upper')]:.1f} vs "
        f"{m.loc[('mc_dropout', 'point')]:.1f}). Persistence's ranking misses the fewest "
        f"({m.loc[('persistence', 'point')]:.1f} of {nhr}): the ranking score decides, not the calibration. Of the "
        f"{len(cls)} classified methods none contradicts Proposition 1. K = {K} alerts (the official high-risk count), "
        f"nominal {_lvl(prim)}, one-sided bounds, 3 seeds, 95% event-level bootstrap intervals.")
    b.save_figure(art, fig)
    t = cls[["method", "learner", "sided", "structural_class", "strictly_increasing_in_point_all",
             "order_violations_vs_point_max", "kendall_tau_vs_point_min", "verdict"]].copy()
    a90 = alerts[(alerts["budget"] == "prevalence_matched") & np.isclose(alerts["nominal"], prim)]
    t = t.merge(a90[["method", "learner", "missed_high_risk", "missed_high_risk_point",
                     "max_abs_alert_difference_vs_point"]], on=["method", "learner"], how="left")
    t["learner"] = t["learner"].map(LEARNER_LABEL)
    b.save_table(art, t)
    b.save_table(art, s[["method", "learner", "K", "missed_high_risk", "missed_high_risk_lo",
                         "missed_high_risk_hi"]].assign(learner=lambda x: x["learner"].map(LEARNER_LABEL)),
                 suffix="_matched_budget")
    b._claim_sources(art, ["e15_decision_cost_summary", "e15b_classification_verdicts", "e15b_alerts", "e15b_budgets"])
    b.register(art)


def build_f10_operating_curves(b: Builder) -> None:
    """E15 (expanded, E16 merged) — threshold-rule operating curves, extended grid, both lead times."""
    plt = b.plt
    art = Artifact("F10_threshold_operating_curves", "figure",
                   "Threshold-rule operating curves on the extended grid, 2- and 3-day lead times", ("E15c",))
    cur, dec, sel = b.table("e15c_operating_curves"), b.table("e15c_decisions"), b.table("e15c_selection")
    grid, pops, p1 = b.table("e15c_grid"), b.table("e15c_populations"), b.table("e15c_p1_checks")
    prim = b.cfg.power.nominal_coverage_primary
    op_t = float(b.cfg.threshold_analysis.operational_thresholds[0])
    common = "common_across_horizons"
    horizons = sorted(grid["horizon_days"].unique())
    arms = [("point", "point", "point prediction", S1, MARK[0]),
            ("E11_weighted_rule_two_sided_upper_edge", "two", "rule-weighted bound (two-sided upper edge)", S2, MARK[1]),
            ("E12_cqr_weighted_rule_two_sided_upper_edge", "two", "CQR bound (two-sided upper edge)", S3, MARK[2]),
            ("E8_bayes_two_sided_upper_edge", "two", "Bayesian bound (E8, two-sided upper edge)", S4, MARK[3])]
    on_point_locus = {"point", "E11_weighted_rule_two_sided_upper_edge"}

    # --- the claims, checked before anything is drawn -----------------------------
    g = grid.groupby("horizon_days")
    n_thr, n_above = g["threshold"].size(), g["threshold"].agg(lambda x: int((x > op_t).sum()))
    orig_max = grid[grid["from_point_percentiles"] | grid["operational"]].groupby("horizon_days")["threshold"].max()
    _require(bool((orig_max == op_t).all()), "the original (point-percentile) grid topped out at the operational threshold")
    tr = p1[p1["structural_class"] == "translation_of_point"]
    p1_cols = [c for c in tr.columns if c.startswith(("p1a_", "p1b_", "p1c_"))]
    _require(bool((tr[p1_cols].abs().to_numpy() == 0).all()), "P1a = P1b = P1c = 0 on every translation-class row")
    s9 = sel[(sel["population"] == common) & np.isclose(sel["nominal"], prim)]
    for ro in ("selected_on_self_test", "unrestricted_oracle_on_official_test"):
        best = s9[s9["readout"] == ro].loc[lambda x: x.groupby(["horizon_days", "ratio"])["cost"].idxmin()]
        _require(bool((best["learner"] == "persistence").all()), f"persistence cheapest on {ro} at every horizon and ratio")
    un = s9[(s9["readout"] == "unrestricted_oracle_on_official_test") & (s9["method"] == "point")]
    un = un.pivot_table(index=["learner", "ratio"], columns="horizon_days", values="cost")
    _require(bool((un[horizons[-1]] > un[horizons[0]]).all()), "every point-arm cost is higher at the longer lead time")
    dep10 = s9[(s9["readout"] == "selected_on_self_test") & (s9["ratio"] == 10)]
    lowest = dep10.loc[dep10.groupby("horizon_days")["cost"].idxmin()].set_index("horizon_days")
    gmax = grid.groupby("horizon_days")["threshold"].max()
    selb = sel.assign(pinned=np.isclose(sel["threshold"], sel["horizon_days"].map(gmax)), bound=sel["method"] != "point")
    pin = selb[selb["bound"]].groupby("readout")["pinned"].mean()
    gbm_op = _row(dec, horizon_days=float(horizons[0]), population=common, method="point", learner="gbm",
                  nominal=float(prim), threshold=op_t)
    npop = pops.set_index(["horizon_days", "population"])

    fig, axes = plt.subplots(len(horizons), len(LEARNERS), figsize=(DOUBLE_COL_IN, 4.6), sharey=True)
    for r_, h in enumerate(horizons):
        n_hr = int(npop.loc[(h, common), "n_high_risk"])
        c_h = cur[(cur["horizon_days"] == h) & (cur["population"] == common)]
        d_h = dec[(dec["horizon_days"] == h) & (dec["population"] == common) & np.isclose(dec["nominal"], prim)]
        for c_, lrn in enumerate(LEARNERS):
            ax = axes[r_, c_]
            for meth, sided, lab, colour, mk in arms:
                m = d_h[(d_h["learner"] == lrn) & (d_h["method"] == meth) & (d_h["sided"] == sided)]
                if m.empty:
                    continue
                if meth not in on_point_locus or meth == "point":
                    k = c_h[(c_h["learner"] == lrn) & (c_h["method"] == meth) & (c_h["sided"] == sided)]
                    ax.plot(k["unnecessary_maneuvers"], k["missed_high_risk"], color=colour, lw=1.3, zorder=2)
                ax.plot(m["unnecessary_maneuvers"], m["missed_high_risk"], mk, ms=3.2, color=colour, mec=SURFACE,
                        mew=0.5, zorder=4, label=lab)
                op = m[np.isclose(m["threshold"], op_t)]
                ax.plot(op["unnecessary_maneuvers"], op["missed_high_risk"], "D", ms=6, color=colour, mec=INK,
                        mew=0.7, zorder=5)
            ax.set_xscale("symlog", linthresh=10)
            ax.set_xlim(left=0)
            if r_ == 0:
                ax.set_title(LEARNER_LABEL[lrn])
            if c_ == 0:
                ax.set_ylabel(f"{h:g}-day lead time\nmissed high-risk (of {n_hr})")
            if r_ == len(horizons) - 1:
                ax.set_xlabel("unnecessary maneuvers")
    handles = {}
    for ax in axes.ravel():
        for hnd, lab in zip(*ax.get_legend_handles_labels(), strict=True):
            handles.setdefault(lab, hnd)
    fig.legend(handles.values(), handles.keys(), frameon=False, loc="lower center", ncol=2, fontsize=6.6,
               bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()

    lw = lambda h: lowest.loc[h]   # noqa: E731
    art.caption = (
        f"**Figure 10.** The threshold rule (alert when the score exceeds t) on the extended grid, at 2- and 3-day lead "
        f"times, common population (n = {int(npop.loc[(horizons[0], common), 'n_events']):,} events, "
        f"{int(npop.loc[(horizons[0], common), 'n_high_risk'])} high-risk), nominal {_lvl(prim)}. Lines: each ranking "
        f"score's full operating curve; markers: the grid thresholds ({int(n_thr.loc[horizons[0]])} and "
        f"{int(n_thr.loc[horizons[-1]])} per horizon, {int(n_above.loc[horizons[0]])} and "
        f"{int(n_above.loc[horizons[-1]])} above t = {op_t:g}); diamonds: the operational t = {op_t:g}. A conformal "
        f"bound that translates the point prediction moves along the point prediction's own curve (Proposition 1: "
        f"P1a = P1b = P1c = 0 on all {len(tr)} translation-class rows) — calibration changes the operating point, not "
        f"the curve — while CQR and the Bayesian bound trace curves of their own. Persistence is cheapest at both lead "
        f"times and every cost ratio, deployable and oracle alike; the lowest deployable cost at 10:1 is persistence's "
        f"point prediction at t = {lw(horizons[0]).threshold:g}, {lw(horizons[0]).cost:.0f} "
        f"[{lw(horizons[0]).cost_lo:.0f}, {lw(horizons[0]).cost_hi:.0f}] at {horizons[0]:g} d and "
        f"{lw(horizons[-1]).cost:.0f} [{lw(horizons[-1]).cost_lo:.0f}, {lw(horizons[-1]).cost_hi:.0f}] at "
        f"{horizons[-1]:g} d; every learner's best achievable (oracle) point-arm cost is higher at the longer lead "
        f"time. The learned point predictions "
        f"sit below the operational threshold (GBM at {horizons[0]:g} d: {gbm_op.n_alerts:.1f} alerts at t = {op_t:g}, "
        f"missing {gbm_op.missed_high_risk:.1f} of {int(gbm_op.n_high_risk)}), which is why the original grid, built "
        f"from them, topped out at t = {op_t:g}. Extending it with the bounds' own percentiles un-pinned the primary "
        f"self-test read-out ({pin.loc['selected_on_self_test']:.1%} of bound selections now at the grid maximum), but "
        f"{pin.loc['selected_on_self_test_rule_weighted']:.1%} of the rule-weighted read-out's bound selections still "
        f"sit there: residual censoring, disclosed as a finding. Costs: 95% event-level bootstrap intervals, 3 seeds.")
    b.save_figure(art, fig)
    op_rows = dec[(dec["population"] == common) & np.isclose(dec["nominal"], prim) & np.isclose(dec["threshold"], op_t)]
    t = op_rows[["horizon_days", "learner", "method", "sided", "n_alerts", "missed_high_risk", "missed_high_risk_lo",
                 "missed_high_risk_hi", "unnecessary_maneuvers", "unnecessary_maneuvers_lo", "unnecessary_maneuvers_hi",
                 "n_high_risk"]].copy()
    d10 = dep10[["horizon_days", "learner", "method", "sided", "threshold", "cost", "cost_lo", "cost_hi"]].rename(
        columns={"threshold": "deployable t (10:1)", "cost": "deployable cost (10:1)", "cost_lo": "deployable cost lo",
                 "cost_hi": "deployable cost hi"})
    t = t.merge(d10, on=["horizon_days", "learner", "method", "sided"], how="left")
    t["learner"] = t["learner"].map(LEARNER_LABEL)
    b.save_table(art, t.sort_values(["horizon_days", "learner", "method"]))
    b.save_table(art, grid.groupby("horizon_days").agg(
        thresholds=("threshold", "size"), minimum=("threshold", "min"), maximum=("threshold", "max"),
        above_operational=("threshold", lambda x: int((x > op_t).sum())),
        bound_percentiles_only=("source", lambda x: int((x == "bound").sum()))).reset_index(), suffix="_grid")
    b.save_table(art, pin.rename("bound selections at the grid maximum").reset_index(), suffix="_ceiling")
    art.notes += [
        "Pinning fractions are recomputed here from e15c_selection + e15c_grid (bound arms; selected threshold equal to "
        "the horizon's grid maximum); they reproduce the recorded 26.9% / 69.4% / 10.2% / 0.0% exactly.",
        "The ORIGINAL grid's pinning (62.3% pooled; 62.7% primary read-out) is not regenerable from current tables: the "
        "extended-grid run overwrote e15c_selection. It is regenerable only by re-running E15 at c9f423f.",
    ]
    b._claim_sources(art, ["e15c_operating_curves", "e15c_decisions", "e15c_selection", "e15c_grid",
                           "e15c_populations", "e15c_p1_checks"])
    b.register(art)


def build_f11_matrix(b: Builder) -> None:
    """E17 H2 — the completed 2x2 coverage-restoration matrix under the final criterion."""
    plt = b.plt
    art = Artifact("F11_restoration_matrix", "figure",
                   "Where the selection-bias correction works: {split, CQR} × {two-sided, one-sided}", ("E17", "E11", "E12"))
    mx = b.table("e17_coverage_restoration_matrix")
    lvl = float(mx["nominal"].iloc[0])
    _require(bool(np.isclose(mx["nominal"], lvl).all()), "the matrix is at one nominal level")
    for r in mx.itertuples():
        v = restoration_verdict(r.naive_lo, r.naive_hi, r.weighted_lo, r.weighted_hi, r.nominal)["verdict"]
        if v != r.verdict:
            raise ValueError(f"matrix verdict for {r.family}/{r.sided} does not re-derive: {r.verdict} vs {v}")
    fams, sides = ["split conformal", "CQR"], ["two", "upper"]
    lo_all = min(mx["naive_lo"].min(), mx["weighted_lo"].min())
    hi_all = max(mx["naive_hi"].max(), mx["weighted_hi"].max(), lvl)
    fig, axes = plt.subplots(2, 2, figsize=(DOUBLE_COL_IN * 0.8, 3.0), sharex=True)
    for i, f in enumerate(fams):
        for j, s in enumerate(sides):
            ax, r = axes[i, j], _row(mx, family=f, sided=s)
            for k, (arm, colour, mk) in enumerate((("naive", S1, MARK[0]), ("weighted", S2, MARK[1]))):
                v, lo, hi = r[f"{arm}_coverage"], r[f"{arm}_lo"], r[f"{arm}_hi"]
                ax.errorbar(v, 1 - k, xerr=[[v - lo], [hi - v]], fmt=mk, color=colour, ms=5, capsize=2.5, lw=1.4)
            _nominal_line(ax, lvl, horizontal=False)
            ax.set_yticks([1, 0])
            ax.set_yticklabels(["naive", "rule-weighted"] if j == 0 else ["", ""])
            ax.set_ylim(-0.7, 1.9)
            ax.grid(axis="y", visible=False)
            ok = r.verdict == RESTORED
            ax.text(0.02, 0.97, ("✓ " if ok else "✗ ") + r.verdict, transform=ax.transAxes, va="top", ha="left",
                    fontsize=7.5, color=GOOD if ok else CRITICAL, fontweight="bold")
            ax.text(0.02, 0.03, f"source: {r.source}", transform=ax.transAxes, va="bottom", ha="left",
                    fontsize=6, color=MUTED)
            if i == 0:
                ax.set_title("two-sided" if s == "two" else "one-sided (upper bound)")
            if j == 0:
                ax.set_ylabel(f, rotation=90, labelpad=2)
    pad = 0.01
    axes[1, 0].set_xlim(lo_all - pad, hi_all + pad)
    fig.supxlabel(f"coverage, official test set (nominal {_lvl(lvl)} dashed)", fontsize=8, color=INK2)
    fig.tight_layout()

    n_rest = int((mx["verdict"] == RESTORED).sum())
    cq = mx[mx["family"] == "CQR"]
    _require(bool((cq["weighted_coverage"] < cq["naive_coverage"]).all()), "weighting lowers CQR coverage in both cells")
    cell = lambda f, s: _row(mx, family=f, sided=s)   # noqa: E731
    art.caption = (
        f"**Figure 11.** Where the selection-bias correction works, nominal {_lvl(lvl)}, official test set "
        f"(n = {int(mx['n'].iloc[0]):,}, GBM base learner). Rule-derived weighting restores coverage in "
        f"{n_rest} of {len(mx)} cells: two-sided split conformal "
        f"({cell('split conformal', 'two').naive_coverage:.3f} → {cell('split conformal', 'two').weighted_coverage:.3f}). "
        f"It does not restore one-sided split conformal ({cell('split conformal', 'upper').naive_coverage:.3f} → "
        f"{cell('split conformal', 'upper').weighted_coverage:.3f}), and it lowers CQR coverage in both sidednesses "
        f"(two-sided {cell('CQR', 'two').naive_coverage:.3f} → {cell('CQR', 'two').weighted_coverage:.3f}; one-sided "
        f"{cell('CQR', 'upper').naive_coverage:.3f} → {cell('CQR', 'upper').weighted_coverage:.3f}). Verdict: RESTORED "
        f"iff the naive interval's upper bound is below nominal and the weighted one's is not (the one-sided guarantee "
        f"coverage ≥ 1 − α). 95% Clopper–Pearson intervals, 3 seeds. Sources: split conformal E10/E11, two-sided CQR "
        f"E12, one-sided CQR E17 (H2).")
    b.save_figure(art, fig)
    b.save_table(art, mx[["family", "sided", "nominal", "n", "naive_coverage", "naive_lo", "naive_hi",
                          "weighted_coverage", "weighted_lo", "weighted_hi", "change_pp", "verdict", "source"]].rename(
        columns={"verdict": "verdict (coverage ≥ nominal)"}))
    b._claim_sources(art, ["e17_coverage_restoration_matrix"])
    b.register(art)


def build_f12_validity_vs_exactness(b: Builder) -> None:
    """E17 — the validity-vs-exactness distinction, on real cases (explanatory figure/box)."""
    plt = b.plt
    art = Artifact("F12_validity_vs_exactness", "figure",
                   "Two questions, two forms: validity under shift vs exactness on exchangeable data", ("E9", "E10", "E11"))
    c = b.table("e9e11_coverage")
    n_cal = int(b.table("e9e11_diagnostics")["n_calibration"].iloc[0])
    prim = b.cfg.power.nominal_coverage_primary
    cases = [  # panel, label, method, learner, sided, nominal
        ("validity", "weighted · persistence · 2-sided", "E11_weighted_rule", "persistence", "two", prim),
        ("validity", "weighted · GBM · 2-sided", "E11_weighted_rule", "gbm", "two", prim),
        ("validity", "naive · GBM · 2-sided", "E10_naive_official", "gbm", "two", prim),
        ("exactness", "self-split · GBM · 2-sided", "E9_selftest", "gbm", "two", prim),
        ("exactness", "self-split · persistence · 1-sided", "E9_selftest", "persistence", "upper", 0.8),
    ]
    rows = []
    for panel, lab, meth, lrn, sided, lv in cases:
        r = _row(c, method=meth, learner=lrn, sided=sided, nominal=float(lv))
        val = meets_coverage_guarantee(r.cp_lo_mean, r.cp_hi_mean, lv)
        ex = consistent_with_exact_coverage(r.cp_lo_mean, r.cp_hi_mean, lv)
        rows.append({"question": "validity under shift" if panel == "validity" else "exactness (exchangeable)",
                     "case": lab, "nominal": lv, "n": int(r.n), "coverage": r.coverage_mean, "ci_lo": r.cp_lo_mean,
                     "ci_hi": r.cp_hi_mean, "one-sided form (CI upper ≥ nominal)": val,
                     "containment form (CI contains nominal)": ex,
                     "correct form for the question": "one-sided" if panel == "validity" else "containment",
                     "forms disagree": val != ex, "CI wholly above nominal": bool(r.cp_lo_mean > lv)})
    t = pd.DataFrame(rows)
    _require(bool((t["forms disagree"] == t["CI wholly above nominal"]).all()),
             "the forms disagree exactly when the CI lies wholly above nominal")
    _require(bool(t.loc[0, "forms disagree"] and t.loc[4, "forms disagree"]), "rows 1 and 5 are the disagreement cases")

    fig, axes = plt.subplots(2, 1, figsize=(DOUBLE_COL_IN * 0.92, 3.1), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2]})
    for ax, q, title in ((axes[0], "validity under shift", "(a) Validity under shift (official test): "
                          "coverage ≥ 1 − α?  Form: CI upper ≥ nominal"),
                         (axes[1], "exactness (exchangeable)", "(b) Exactness (exchangeable self-split): "
                          "implementation right?  Form: CI contains nominal")):
        d = t[t["question"] == q].reset_index(drop=True)
        yy = np.arange(len(d))[::-1]
        g = 100 * (d["coverage"] - d["nominal"])
        ax.errorbar(g, yy, xerr=[g - 100 * (d["ci_lo"] - d["nominal"]), 100 * (d["ci_hi"] - d["nominal"]) - g],
                    fmt="o", color=INK2, ms=4.5, capsize=2.5, lw=1.4)
        _nominal_line(ax, 0.0, horizontal=False)
        ax.set_yticks(yy)
        ax.set_yticklabels([f"{r.case} ({_lvl(r.nominal)})" for r in d.itertuples()])
        ax.set_ylim(-0.6, len(d) - 0.4)
        ax.grid(axis="y", visible=False)
        ax.set_title(title, loc="left", fontsize=7.4)
        correct = "one-sided form (CI upper ≥ nominal)" if q.startswith("validity") else \
            "containment form (CI contains nominal)"
        wrong = "containment form (CI contains nominal)" if q.startswith("validity") else \
            "one-sided form (CI upper ≥ nominal)"
        for y_, r in zip(yy, d.to_dict("records"), strict=True):
            ok = r[correct]
            txt = (("meets guarantee" if ok else "under-coverage established") if q.startswith("validity")
                   else ("exact" if ok else "defect: not exact"))
            ax.annotate(("✓ " if ok else "✗ ") + txt, xy=(1.005, y_), xycoords=("axes fraction", "data"), va="center",
                        fontsize=6.8, color=GOOD if ok else CRITICAL, fontweight="bold")
            if r["forms disagree"]:
                ax.annotate(f"(the {'containment' if q.startswith('validity') else 'one-sided'} form would say "
                            f"{'pass' if r[wrong] else 'fail'})", xy=(1.005, y_ - 0.38),
                            xycoords=("axes fraction", "data"), va="center", fontsize=6, color=MUTED)
    axes[1].set_xlabel("coverage − nominal  [pp], 95% Clopper–Pearson interval")
    fig.tight_layout(rect=(0, 0, 0.8, 1))

    slack_pp = 100.0 / (n_cal + 1)
    art.caption = (
        f"**Figure 12.** Two questions, two forms. *Validity under shift* asks whether a method meets its guarantee, "
        f"coverage ≥ 1 − α — a one-sided bound for one-sided bounds and two-sided intervals alike — so it is tested "
        f"as CI upper bound ≥ nominal, and over-coverage passes. *Exactness on exchangeable data* asks whether the "
        f"implementation is right: unweighted split-conformal coverage lies in [1 − α, 1 − α + 1/(n + 1)] "
        f"(n = {n_cal:,}: slack {slack_pp:.3f} pp), so a deviation in either direction signals a defect, and it is "
        f"tested as CI contains nominal. The two forms can disagree only when the interval lies wholly above nominal "
        f"(first and last rows). In the first, the containment form would fail a valid, conservative method — the "
        f"error found and corrected in E17's restoration criterion. In the last, the containment form correctly flags "
        f"a defect (persistence's degenerate one-sided scores) that the one-sided form would pass.")
    b.save_figure(art, fig)
    b.save_table(art, t.assign(coverage=lambda x: [_fmt_ci(r.coverage, r.ci_lo, r.ci_hi, 4) for r in x.itertuples()])
                 .drop(columns=["ci_lo", "ci_hi"]).rename(columns={"coverage": "coverage [95% CP CI]"}))
    b._claim_sources(art, ["e9e11_coverage", "e9e11_diagnostics"])
    b.register(art)


# Tables whose statistics must never reach the manuscript: E17 H3's association and overlap
# numbers are circular by construction (DECISIONS.md 2026-09-21, E17 CLOSED, item 1).
FORBIDDEN_SOURCE_PREFIXES: tuple[str, ...] = ("e17_h3_",)


def build_t13_five_manifestations(b: Builder) -> None:
    """E17 — the five-manifestation narrative as a QUALITATIVE table (H3 honest null).

    Each row is evidenced only by its own experiment's table. No association, correlation,
    overlap or lift statistic across rows is computed or read: the attempted quantitative
    link (E17 H3) was circular by construction and was closed as an honest null.
    """
    art = Artifact("T13_five_manifestations", "table",
                   "One dataset property, five independently measured consequences (qualitative)",
                   ("E1", "E6", "E7", "E14", "E15", "E15c"))
    prev = b.table("e1_high_risk_prevalence")
    perf = b.table("e678_final_comparison")
    cc = b.table("e14_conditional_coverage_anomaly_ci")
    summ = b.table("e15_decision_cost_summary")
    grid, sel = b.table("e15c_grid"), b.table("e15c_selection")
    prim = b.cfg.power.nominal_coverage_primary
    op_t = float(b.cfg.threshold_analysis.operational_thresholds[0])

    L = perf["L mean"]
    pers, gbm, gru = (perf.index[perf.index.str.startswith(p)][0] for p in ("E5 persistence", "E6 GBM", "E7 sequence"))
    ccr = lambda m, l_: _row(cc, arm="anchored", method=m, learner=l_)   # noqa: E731
    k150 = summ[(summ["budget"] == "prevalence_matched") & np.isclose(summ["nominal"], prim) & (summ["method"] == "point")]
    miss = k150.set_index("learner")["missed_high_risk"]
    orig_max = grid[grid["from_point_percentiles"] | grid["operational"]].groupby("horizon_days")["threshold"].max()
    gmax = grid.groupby("horizon_days")["threshold"].max()
    pin = (sel.assign(pinned=np.isclose(sel["threshold"], sel["horizon_days"].map(gmax)))
           .loc[lambda x: x["method"] != "point"].groupby("readout")["pinned"].mean())
    rows = [
        {"#": "—", "what": "The property: the official test set is enriched for high-risk events, by construction",
         "experiment": "E1 (Phase 0)", "measured by": "event-level prevalence, two-sample tests",
         "evidence (from that experiment's own table)":
             f"high-risk prevalence {prev.loc['train', 'prevalence']:.2%} (train) vs {prev.loc['test', 'prevalence']:.2%} "
             f"(test), {prev.loc['test', 'enrichment vs train']:.2f}×", "source table": "e1_high_risk_prevalence"},
        {"#": 1, "what": "Point-prediction collapse: learned models regress toward the low-risk mass",
         "experiment": "E6/E7 (Phase 2)", "measured by": "official-test challenge loss L, 3 seeds",
         "evidence (from that experiment's own table)":
             f"L: GBM {L.loc[gbm]:.2f} ± {perf.loc[gbm, 'L sd']:.2f}, GRU {L.loc[gru]:.2f} ± {perf.loc[gru, 'L sd']:.2f}, "
             f"vs persistence {L.loc[pers]:.3f}", "source table": "e678_final_comparison"},
        {"#": 2, "what": "Conditional-coverage collapse on the high-risk stratum, far below the same methods' "
                         "marginal coverage",
         "experiment": "E14 (Phase 4)", "measured by": "coverage on truly high-risk events, bootstrap CIs",
         "evidence (from that experiment's own table)":
             f"at {_lvl(prim)}: GBM {ccr('E11_weighted_rule', 'gbm').coverage_mean:.3f}, CQR "
             f"{ccr('E12_cqr_weighted_rule', 'gbm').coverage_mean:.3f}, persistence "
             f"{ccr('E11_weighted_rule', 'persistence').coverage_mean:.3f} (n = {int(cc['n'].iloc[0])})",
         "source table": "e14_conditional_coverage_anomaly_ci"},
        {"#": 3, "what": "Ranking-quality collapse: at a matched budget the ranking decides, and persistence ranks best",
         "experiment": "E15 (Phase 5)", "measured by": "missed high-risk events at K = 150 alerts",
         "evidence (from that experiment's own table)":
             "missed of 150: " + ", ".join(f"{LEARNER_LABEL[x]} {miss.loc[x]:.1f}" for x in LEARNERS),
         "source table": "e15_decision_cost_summary"},
        {"#": 4, "what": "Instrument distortion: a threshold grid built from the learned predictions has no resolution "
                         "above the operational threshold",
         "experiment": "E15 expanded (Phase 5)", "measured by": "the threshold grid's construction",
         "evidence (from that experiment's own table)":
             "original (point-percentile) grid maximum = " + ", ".join(f"{v:g} at {h:g} d" for h, v in orig_max.items())
             + f" — the operational t = {op_t:g} itself", "source table": "e15c_grid"},
        {"#": 5, "what": "The fix is only partly available: extending the grid repairs one read-out, not the other",
         "experiment": "E15 extended grid (Phase 5)", "measured by": "share of bound selections at the grid maximum",
         "evidence (from that experiment's own table)":
             f"primary self-test read-out {pin.loc['selected_on_self_test']:.1%}; rule-weighted read-out "
             f"{pin.loc['selected_on_self_test_rule_weighted']:.1%}", "source table": "e15c_selection, e15c_grid"},
    ]
    art.caption = (
        "**Table 13.** One dataset property, five consequences. Each row is measured by a different experiment with "
        "its own method, and each stands on its own evidence. The rows are deliberately not linked by a shared "
        "per-event statistic: the attempted quantitative link (E17, H3) was circular by construction — its "
        "diagnostic was definitionally tied to the memberships it was meant to predict — and was closed as an honest "
        "null, so no association, overlap or correlation figure is reported. The pattern is a qualitative synthesis.")
    b.save_table(art, pd.DataFrame(rows))
    art.notes.append("Row 4's original pinning magnitude (62.3% of bound selections) is recorded in DECISIONS.md but "
                     "not regenerable from current tables (the extended-grid run overwrote them), so it is not printed.")
    b._claim_sources(art, ["e1_high_risk_prevalence", "e678_final_comparison", "e14_conditional_coverage_anomaly_ci",
                           "e15_decision_cost_summary", "e15c_grid", "e15c_selection"])
    b.register(art)


BUILDERS = (
    build_f01_selection_bias, build_f02_bayesian, build_f03_e9_machinery, build_f04_gate2_headline,
    build_f05_one_sided, build_f06_cqr, build_f07_labelnoise, build_f08_conditional, build_f09_rank_invariance,
    build_f10_operating_curves, build_f11_matrix, build_f12_validity_vs_exactness, build_t13_five_manifestations,
)


def build_all(cfg: Config, out_root: Path | None = None) -> list[Artifact]:
    """Build every manuscript artifact, then the manifest and the captions file.

    Fails loud if any artifact is untraceable: no experiment, no source, a missing output
    file, or an experiment whose computing commit cannot be established.
    """
    b = Builder(cfg, out_root=out_root)
    for build in BUILDERS:
        build(b)
    exps = sorted({e for a in b.artifacts for e in a.experiments}, key=lambda e: (len(e), e))
    prov = {e: _provenance(b.reports, e) for e in exps}
    for a in b.artifacts:
        if not a.experiments or not a.sources or not a.files or not a.caption:
            raise ValueError(f"{a.ident}: untraceable (experiments, sources, files and caption are all required)")
        for f in a.files:
            if not (b.root / f).exists():
                raise FileNotFoundError(f"{a.ident}: output {f} was not written")
        if any(s.startswith(FORBIDDEN_SOURCE_PREFIXES) for s in a.sources):
            raise ValueError(f"{a.ident}: reads a forbidden (circular H3) table")
    for e, p in prov.items():
        if not re.fullmatch(r"[0-9a-f]{40}", str(p["git_commit_sha"])):
            raise ValueError(f"{e}: computing commit not established ({p['git_commit_sha']})")
    manifest = {
        "experiment": "E18 Part B — manuscript figures and tables",
        "command": "kc manuscript",
        "builder_git_commit": _git("rev-parse", "HEAD"),
        "builder_tree_clean": _git("status", "--porcelain", "--untracked-files=no") == "",
        "config_hash": cfg.config_hash,
        "experiments": prov,
        "artifacts": [{"id": a.ident, "kind": a.kind, "title": a.title, "experiments": list(a.experiments),
                       "files": a.files, "source_sha256": a.sources, "notes": a.notes} for a in b.artifacts],
    }
    _write_text(b.root / "reports" / "manuscript_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    lines = ["# Manuscript figure and table captions (generated by `kc manuscript` — do not edit by hand)", "",
             f"Built at `{manifest['builder_git_commit'][:12]}` (tree clean: {manifest['builder_tree_clean']}), "
             f"config `{cfg.config_hash[:12]}`. Every number below is read from a committed experiment table; "
             "sources and computing commits are in `reports/manuscript_manifest.json`.", ""]
    for a in b.artifacts:
        lines += [f"## {a.ident} — {a.title}", "", a.caption, "",
                  "Computed by: " + "; ".join(f"{e} @ `{prov[e]['git_commit_sha'][:10]}`" for e in a.experiments),
                  "Files: " + ", ".join(f"`{f}`" for f in a.files)]
        lines += [f"Note: {n}" for n in a.notes] + [""]
    _write_text(b.root / "reports" / "manuscript_captions.md", "\n".join(lines))
    return b.artifacts
