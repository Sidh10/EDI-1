"""Command-line entry points for Phases 0-1 (E0-E5).

Exposed stages: ``kc ingest`` (E0), ``kc audit`` (E1/E2/E3), ``kc baselines`` (E5)
and ``kc power`` (E4). Later phases add ``train``, ``conformal``, ``evaluate`` and
``reproduce-all`` (SOFTWARE_ARCHITECTURE.md §2). Keeping the surface minimal is
deliberate — no command exists ahead of the experiment that needs it
(CLAUDE.md §2, §7).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from .config import REPO_ROOT, load_config

app = typer.Typer(
    add_completion=False,
    help="Kelvins-conformal research pipeline (Phase 0: ingest + audit).",
    no_args_is_help=True,
)


@app.command()
def ingest(
    source_zip: Path | None = typer.Option(
        None,
        "--source-zip",
        help="Use a pre-downloaded dataset zip instead of fetching from Zenodo "
        "(still checksum-verified). Enables offline/deterministic re-ingest.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing (immutable) raw store. Record why in DECISIONS.md."
    ),
    config: Path | None = typer.Option(None, "--config", help="Path to a config YAML."),
) -> None:
    """E0: download, checksum-verify, unpack, freeze read-only, record provenance."""
    from . import ingest as ingest_mod

    cfg = load_config(config)
    typer.echo(f"[ingest] target md5 = {cfg.dataset.md5}")
    raw = ingest_mod.run_ingest(cfg, source_zip=source_zip, force=force)
    typer.echo(f"[ingest] raw store frozen at: {raw}")
    typer.echo(f"[ingest] provenance: {raw / ingest_mod.MANIFEST_NAME}")


# --- notebook execution helpers (audit) -------------------------------------
def _ensure_kernel(name: str = "python3") -> None:
    """Register an ipykernel spec in the current environment if absent."""
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        if name in KernelSpecManager().find_kernel_specs():
            return
    except Exception:  # noqa: BLE001 - fall through to install attempt
        pass
    subprocess.run(
        [sys.executable, "-m", "ipykernel", "install", "--sys-prefix", "--name", name],
        check=True,
        capture_output=True,
    )


def _run_notebook(nb_in: Path, html_out: Path, kernel: str = "python3") -> None:
    """Execute a notebook headlessly (papermill) then export to HTML (nbconvert)."""
    import nbformat
    import papermill as pm
    from nbconvert import HTMLExporter

    html_out.parent.mkdir(parents=True, exist_ok=True)
    executed = nb_in.with_suffix(".executed.ipynb")
    typer.echo(f"[audit] executing {nb_in.name} …")
    pm.execute_notebook(
        str(nb_in),
        str(executed),
        kernel_name=kernel,
        cwd=str(REPO_ROOT),
        progress_bar=False,
    )
    nb = nbformat.read(str(executed), as_version=4)
    body, _ = HTMLExporter(exclude_input=False).from_notebook_node(nb)
    html_out.write_text(body, encoding="utf-8")
    executed.unlink(missing_ok=True)
    typer.echo(f"[audit] wrote {html_out}")


@app.command()
def audit(
    config: Path | None = typer.Option(None, "--config", help="Path to a config YAML."),
    skip_pc: bool = typer.Option(False, "--skip-pc", help="Skip the E3 Pc-spike notebook."),
) -> None:
    """E1/E2/E3: build the events table and render the Phase 0 audit reports.

    Renders ``reports/00_data_audit.html`` (E1 + E2 tally) and
    ``reports/00b_pc_spike.html`` (E3). The notebooks build
    ``data/processed/events.parquet`` from the frozen raw store on first run.
    """
    cfg = load_config(config)
    _ensure_kernel()
    nb_dir = REPO_ROOT / "notebooks"
    reports = cfg.path("reports_dir")

    _run_notebook(nb_dir / "00_data_audit.ipynb", reports / "00_data_audit.html")
    if not skip_pc:
        _run_notebook(nb_dir / "00b_pc_spike.ipynb", reports / "00b_pc_spike.html")
    typer.echo("[audit] Phase 0 reports rendered. Review, then Sidh records the checkpoint.")


@app.command()
def baselines(
    config: Path | None = typer.Option(None, "--config", help="Path to a config YAML."),
) -> None:
    """E5: validate the challenge metric against the published baseline scores.

    Renders ``reports/01b_baseline_validation.html``. This is the credibility gate
    for every later number — if it fails, nothing downstream is trustworthy.
    """
    cfg = load_config(config)
    _ensure_kernel()
    _run_notebook(
        REPO_ROOT / "notebooks" / "01b_baseline_validation.ipynb",
        cfg.path("reports_dir") / "01b_baseline_validation.html",
    )


@app.command()
def power(
    config: Path | None = typer.Option(None, "--config", help="Path to a config YAML."),
) -> None:
    """E4: statistical power analysis — produces the Gate 1 decision table.

    Renders ``reports/01_power_analysis.html``. Claude Code produces the table and
    stops; the GO/PIVOT/NO-GO call is the project owner's (CLAUDE.md §3).
    """
    cfg = load_config(config)
    _ensure_kernel()
    _run_notebook(
        REPO_ROOT / "notebooks" / "01_power_analysis.ipynb",
        cfg.path("reports_dir") / "01_power_analysis.html",
    )
    typer.echo("[power] Gate 1 table rendered. Review, then Sidh records the gate decision.")


@app.command()
def baselines_phase2(
    config: Path | None = typer.Option(None, "--config", help="Path to a config YAML."),
) -> None:
    """E6/E7/E8: train the Phase-2 baselines and audit MC-dropout coverage.

    Renders ``reports/02_baselines.html``. Slow by design — three hyperparameter
    searches plus multi-seed training on CPU (EXPERIMENT_PLAN estimates hours).
    """
    import time as _time

    from .reporting import OutputLockError, output_lock

    cfg = load_config(config)
    _ensure_kernel()
    # Run-id guard: two concurrent runs must not write reports/tables/ at once
    # (the concurrent-write hazard logged at the Phase-2 checkpoint). A unique id
    # per invocation; the lock auto-reclaims if a prior run was killed.
    run_id = f"phase2-{cfg.config_hash[:12]}-{int(_time.time())}"
    try:
        with output_lock(cfg.path("tables_dir"), run_id):
            _run_notebook(
                REPO_ROOT / "notebooks" / "02_baselines.ipynb",
                cfg.path("reports_dir") / "02_baselines.html",
            )
    except OutputLockError as exc:
        raise typer.Exit(code=1) from exc
    typer.echo("[phase2] E6/E7/E8 report rendered. Review, then Sidh records the checkpoint.")


@app.command()
def conformal(
    config: Path | None = typer.Option(None, "--config", help="Path to a config YAML."),
    only: str = typer.Option(
        "all", "--only",
        help="Which notebook(s): 'gate2' (03, E9-E11), 'cqr' (03b, E12), or 'all'.",
    ),
) -> None:
    """Phase 3 conformal experiments.

    ``--only gate2`` renders ``reports/03_conformal.html`` (E9-E11, the Gate 2 batch);
    ``--only cqr`` renders ``reports/03b_cqr.html`` (E12, post-Gate-2); ``all`` renders
    both (the reproduce-all path). Stops at each batch boundary; gate calls are Sidh's
    (CLAUDE.md §3, §13). Slow by design — multi-seed CPU training.
    """
    import time as _time

    from .reporting import OutputLockError, output_lock

    if only not in ("all", "gate2", "cqr"):
        raise typer.BadParameter("--only must be one of: all, gate2, cqr")
    cfg = load_config(config)
    _ensure_kernel()
    nb_dir = REPO_ROOT / "notebooks"
    reports = cfg.path("reports_dir")
    run_id = f"phase3-{cfg.config_hash[:12]}-{int(_time.time())}"
    try:
        with output_lock(cfg.path("tables_dir"), run_id):
            if only in ("all", "gate2"):
                _run_notebook(nb_dir / "03_conformal.ipynb", reports / "03_conformal.html")
            if only in ("all", "cqr"):
                _run_notebook(nb_dir / "03b_cqr.ipynb", reports / "03b_cqr.html")
    except OutputLockError as exc:
        raise typer.Exit(code=1) from exc
    typer.echo("[phase3] conformal report(s) rendered. Gate calls are Sidh's (CLAUDE.md §13).")


if __name__ == "__main__":
    app()
