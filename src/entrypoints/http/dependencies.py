"""FastAPI dependency providers for the HTTP entrypoint.

Three per-request (or per-app) resources are wired here so routes and use cases
can declare them via ``Depends()`` without knowing where they come from:

* ``get_session`` — an ``AsyncSession`` scoped to the request, wrapped in
  ``session.begin()`` so the Unit of Work commits on handler success and rolls
  back on any exception (ADR-0006: repos flush but do not commit; the session
  context manager owns the transaction boundary).
* ``get_redis`` — the process-wide Redis async client (connection pool shared
  across every request); created once in the lifespan.
* ``get_settings`` — the ``Settings`` singleton stored on ``app.state`` so tests
  can override it via ``app.dependency_overrides[get_settings]`` without
  patching the process environment.

All three read from ``request.app.state`` rather than global variables so the
resources stay bound to the app instance — which matters for test isolation
(each test that creates a fresh ``TestClient`` gets its own ``app.state``).
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.cache.redis_cache import RedisCache
from src.adapters.db.game_repository import PostgresGameRepository
from src.application.start_game import StartGame
from src.config import Settings


def get_settings(request: Request) -> Settings:
    """Return the process-wide ``Settings`` from ``app.state``."""
    return request.app.state.settings  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` wrapped in a transaction for the request.

    The ``session.begin()`` context manager commits on a clean exit and rolls
    back on any exception, giving the per-request Unit of Work the use cases
    expect (``StartGame``, ``ProcessTurn``, ``SubmitScore`` all flush but never
    commit — this is the only place the transaction is committed).
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.async_session_maker
    async with factory() as session:
        async with session.begin():
            yield session


def get_redis(request: Request) -> Redis:
    """Return the process-wide Redis async client from ``app.state``."""
    return request.app.state.redis_client  # type: ignore[no-any-return]


# --- Use-case wiring ------------------------------------------------------
#
# The chain below assembles the application use case from its adapters, one
# ``Depends`` layer per port: the request-scoped session/Redis (above) build the
# concrete repo/cache, which build the use case. This is the **composition
# root** — the one place that deliberately names concrete adapters
# (``PostgresGameRepository`` / ``RedisCache``), so these providers are typed
# against the concrete types on purpose. The decoupling lives one level in:
# ``StartGame``'s constructor is typed against the ``IGameRepository`` /
# ``ICachePort`` Protocols, so swapping an adapter is a one-line change *here*
# and nowhere else. Tests override ``get_start_game`` directly with a use case
# wired to fakes, so no DB or Redis is touched. Tasks 3.7/3.8 follow this
# pattern for their own use cases.


def get_game_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostgresGameRepository:
    """Build the Postgres game repository on the request-scoped session."""
    return PostgresGameRepository(session)


def get_cache(redis: Annotated[Redis, Depends(get_redis)]) -> RedisCache:
    """Build the Redis cache adapter on the process-wide client."""
    return RedisCache(redis)


def get_start_game(
    games: Annotated[PostgresGameRepository, Depends(get_game_repository)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> StartGame:
    """Assemble the ``StartGame`` use case from its injected ports."""
    return StartGame(games, cache)
