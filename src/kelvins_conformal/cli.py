"""Command-line entry points for Phase 0 (E0-E3).

Only the two stages Phase 0 needs are exposed: ``kc ingest`` (E0) and ``kc audit``
(E1/E2/E3 report rendering). Later phases add ``power``, ``train``, ``conformal``,
``evaluate``, ``reproduce-all`` (SOFTWARE_ARCHITECTURE.md §2). Keeping the surface
minimal is deliberate — no command exists ahead of the experiment that needs it
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


if __name__ == "__main__":
    app()
