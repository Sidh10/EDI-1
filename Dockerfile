# Reproduction container (SOFTWARE_ARCHITECTURE.md §12, Tier 3).
# Kept in sync with the pinned uv.lock; a tagged release is validated by building
# this image and running the test suite (and, in later phases, `kc reproduce-all`)
# inside it before release.
FROM python:3.11-slim-bookworm

# uv provides deterministic, hash-checked installs from the lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching) from the locked environment.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --extra notebooks --extra dev --no-editable || uv sync --extra notebooks --extra dev

# Bring in the rest of the project (configs, tests, notebooks, docs).
COPY . .

# Data is NOT baked into the image; `kc ingest` fetches + checksum-verifies it at
# run time (CLAUDE.md §5: raw data is never committed or shipped).
ENTRYPOINT ["uv", "run"]
CMD ["kc", "--help"]
