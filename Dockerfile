# Shared image for HexCrawl's Python processes — the Celery worker and Celery Beat
# run from this single image with different commands (see docker-compose.yml).
# "Build once, run many roles": one image, no per-role rebuild.
#
# Single-stage, dev-oriented. Phase 6 (tasks 6.1 / 6.2) will refine this into a
# multi-stage *production* build; this version exists so 4.6 can wire worker + beat
# into Compose without blocking on Phase 6.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# UV_COMPILE_BYTECODE — precompile .pyc at install time for faster cold starts.
# UV_LINK_MODE=copy — copy packages into the venv instead of hardlinking; avoids
# noisy warnings when the build cache and target live on different filesystems.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependency layer first, so it stays cached unless the lockfile changes. The
# project itself has no [build-system] in pyproject.toml, so uv treats it as a
# *virtual* project: it installs only the locked dependencies into /app/.venv and
# runs the source in-place (copied below) rather than building/installing a wheel.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# Application source. `celery -A src.adapters.tasks.celery_app` resolves because
# the worker runs with CWD /app, putting the repo root (and thus the `src`
# package) on sys.path — matching how it runs on the host.
COPY src ./src

# Put the synced venv on PATH so `celery` / `uvicorn` are invoked directly,
# without a `uv run` wrapper per container start.
ENV PATH="/app/.venv/bin:$PATH"

# No CMD: the role-specific command (worker vs beat) is supplied by Compose.
