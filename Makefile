# Thin aliases over the `kc` CLI and dev tooling (SOFTWARE_ARCHITECTURE.md §3).
# These are conveniences only; the CLI is the source of truth for pipeline stages.

.PHONY: help install lint test test-fast audit ingest reproduce clean

help:
	@echo "Targets:"
	@echo "  install     - create the pinned uv environment (uv sync)"
	@echo "  lint        - ruff check"
	@echo "  test        - full test suite (pytest)"
	@echo "  test-fast   - unit tests only (deselect slow/full-dataset tests)"
	@echo "  ingest      - E0: download + checksum-verify + freeze raw data"
	@echo "  audit       - E1/E2/E3: render Phase 0 audit + Pc-spike reports"
	@echo "  reproduce   - full manuscript reproduction (not available until later phases)"
	@echo "  clean       - remove rendered reports and caches (never touches data/raw)"

install:
	uv sync --extra notebooks --extra dev

lint:
	uv run ruff check src tests

test:
	uv run pytest

test-fast:
	uv run pytest -m "not slow"

ingest:
	uv run kc ingest

audit:
	uv run kc audit

reproduce:
	@echo "reproduce-all is not implemented in Phase 0 (E0-E3 only). See EXPERIMENT_PLAN.md."
	@exit 1

clean:
	rm -rf reports/*.html reports/figures reports/tables
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
