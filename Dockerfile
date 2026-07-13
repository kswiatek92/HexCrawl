# The one production image for every HexCrawl Python process (tasks 6.1/6.2):
# the FastAPI API (default CMD), the Celery worker, Celery Beat, and the
# one-shot Alembic migration all run from this image with different commands
# ("build once, run many roles" — see docker-compose{,.prod}.yml).
#
# Multi-stage: the builder carries uv and the build toolchain; the runtime
# stage starts from a bare Python base and receives only the synced venv and
# the source. That shrinks the image AND its attack surface — no uv, no
# compilers, nothing to `pip install` with, inside the container an attacker
# could reach.
#
# Bases are pinned by tag; pinning by digest (`python:3.12-slim-bookworm@sha256:…`)
# is the stricter reproducibility/supply-chain option — Dependabot's docker
# ecosystem can maintain digests too. Deliberately not done yet to keep image
# updates readable while the deploy story stabilises (Phase 6).

# ---- builder: resolve + install locked dependencies into /app/.venv --------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# UV_COMPILE_BYTECODE — precompile .pyc at install time for faster cold starts.
# UV_LINK_MODE=copy — copy packages into the venv instead of hardlinking; avoids
# noisy warnings when the build cache and target live on different filesystems.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependency layer first, so it stays cached unless the lockfile changes. The
# project has no [build-system], so uv treats it as a *virtual* project: it
# installs only the locked dependencies into /app/.venv and the source runs
# in-place (copied in the runtime stage), never built into a wheel.
# `--frozen` = install exactly uv.lock, no re-resolution — the same closure
# CI tested is the closure that ships (reproducible builds).
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# ---- runtime: bare Python + venv + source, non-root ------------------------
FROM python:3.14-slim-bookworm

WORKDIR /app

# Run as a dedicated non-root user: a container escape or RCE lands in an
# unprivileged account, not uid 0. System account, no home, no shell login.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

# The venv is self-contained (its python is copied, not symlinked, thanks to
# UV_LINK_MODE=copy) and the runtime base provides the same 3.12 interpreter
# ABI the builder used.
COPY --from=builder /app/.venv /app/.venv

# Application source + migrations. Alembic ships in the image so the same
# artifact can run `alembic upgrade head` (the prod compose migrate one-shot,
# and later the ECS pre-deploy step) — a deploy is image + env, nothing else.
# `celery -A src.adapters.tasks.celery_app` / `src.entrypoints.http.main:app`
# resolve because every role runs with CWD /app, putting the repo root (and
# thus the `src` package) on sys.path — matching how it runs on the host.
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

# Put the synced venv on PATH so `gunicorn` / `celery` / `alembic` are invoked
# directly, without a `uv run` wrapper per container start.
ENV PATH="/app/.venv/bin:$PATH"

USER app

# Default role: the API (task 6.1). Gunicorn supervises 2 uvicorn workers
# (QUESTIONS.md Phase 6: one async event loop per worker; scale out with more
# containers/tasks, not more workers). CMD, not ENTRYPOINT: the other roles
# (worker / beat / migrate) swap the whole command in Compose (task 6.2).
CMD ["gunicorn", "src.entrypoints.http.main:app", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000"]
