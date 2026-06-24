"""FastAPI application entry point.

Wires together lifespan (DB engine + Redis pool), CORS middleware, and the
versioned API router. ``uvicorn src.entrypoints.http.main:app`` is the prod and
dev launch target (see CLAUDE.md local dev setup).

Architecture:
* **Lifespan** owns the two long-lived connection resources (SQLAlchemy async
  engine and Redis async client). Starting them here — not at module import —
  defers the network connections until the event loop is running and ensures
  graceful teardown when the server stops (QUIZZES.md task 3.4 Q1).
* **CORS** is added last so it runs outermost in the LIFO middleware stack —
  the preflight ``OPTIONS`` response leaves before any auth middleware fires
  (QUIZZES.md task 3.4 Q3). Origins come from ``Settings.cors_origins``
  (default ``["http://localhost:5173"]``; set ``CORS_ORIGINS`` env var for prod
  — QUESTIONS.md task 3.4 decision).
* **Versioned router** — all business routes live under ``/v1/`` (QUESTIONS.md
  task 3.4 decision). The health endpoint sits outside ``/v1`` because it is a
  platform/infra concern, not a business API.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.cache.redis_cache import create_redis_client
from src.config import Settings
from src.entrypoints.http import router_auth, router_game, router_leaderboard
from src.entrypoints.ws import router_game as ws_router_game

logger = structlog.get_logger(__name__)


def _scrub_dsn(url: str) -> str:
    """Return the DSN with the password component replaced by '***'.

    Prevents credentials from appearing in structured logs when startup
    logs the configured database/Redis URLs for diagnostics.
    """
    parts = urlsplit(url)
    if parts.password:
        # netloc = [user[:password]@]host[:port] — rebuild without the secret.
        netloc = parts.hostname or ""
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        if parts.username:
            netloc = f"{parts.username}:***@{netloc}"
        parts = parts._replace(netloc=netloc)
    return urlunsplit(parts)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise and teardown the DB engine and Redis client.

    Reads ``Settings`` from ``app.state`` (populated in ``create_app`` before
    startup) so there is a single ``Settings`` instantiation per process.
    ``app.state`` is the injection point for per-request dependencies: tests can
    substitute fakes by setting ``app.state.*`` before the first request.
    """
    settings: Settings = app.state.settings

    engine = create_async_engine(settings.database_url)
    app.state.async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    redis_client = create_redis_client(settings.redis_url)
    app.state.redis_client = redis_client

    logger.info(
        "app_startup",
        database_url=_scrub_dsn(settings.database_url),
        redis_url=_scrub_dsn(settings.redis_url),
    )
    yield

    await engine.dispose()
    await redis_client.aclose()
    logger.info("app_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return the configured FastAPI application.

    Accepts an optional ``Settings`` override so tests can inject a custom
    config without patching the process environment. When ``None``, a fresh
    ``Settings()`` is loaded from env / ``.env``.
    """
    resolved = settings or Settings()

    application = FastAPI(
        title="HexCrawl API",
        description="Browser-based dungeon crawler — backend API.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Pre-populate state so lifespan and dependencies can read settings without
    # a second instantiation.
    application.state.settings = resolved

    # CORS added last → runs outermost (LIFO) → preflight resolved before auth.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = APIRouter(prefix="/v1")
    api_router.include_router(router_auth.router)
    api_router.include_router(router_game.router)
    api_router.include_router(router_leaderboard.router)
    application.include_router(api_router)

    # The WebSocket turn loop (task 3.9) is mounted at the app root — not under
    # /v1 — to match the CLAUDE.md API surface (`WS /ws/game/{session_id}`).
    # Browser WS clients build the URL directly, so the documented path is the
    # contract the frontend (Phase 5) will hardcode.
    application.include_router(ws_router_game.router)

    @application.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
