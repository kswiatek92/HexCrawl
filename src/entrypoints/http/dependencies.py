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

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
