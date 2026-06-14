"""Live-Postgres fixtures for the task 2.6 DB-repo integration tests.

The unit tests for the repositories (``tests/unit/adapters/db/``) lock the pure
domain<->ORM mappers in-memory. These integration tests cover the half a mapper
test *cannot*: the real SQL behaviour — JSONB round-trips, ``selectin`` eager
loads, the ``ON CONFLICT DO NOTHING`` upsert, leaderboard ordering / the weekly
window, and the no-commit Unit-of-Work contract. They need a real database, so a
throwaway Postgres is spun up with ``testcontainers`` (QUESTIONS.md Phase 2: the
chosen runner — programmatic per-session container, auto cleanup, no compose
file).

Fixture strategy:

* ``postgres_container`` — **session-scoped, sync.** Pulling the image and
  booting Postgres is the expensive step, so it happens once for the whole run.
  ``driver="asyncpg"`` makes ``get_connection_url()`` hand back a
  ``postgresql+asyncpg://`` URL matching the production stack.
* ``sessionmaker`` — **function-scoped, async.** Builds a fresh engine
  (``NullPool`` — no pooling games across event loops), creates the schema from
  the shared ORM ``Base.metadata`` (not Alembic: migrations are covered
  separately by ``test_migrations.py``; here the schema is single-sourced from
  the same metadata the repos map to), yields an ``async_sessionmaker``, then
  drops every table and disposes the engine. Per-test create/drop gives total
  isolation without juggling event-loop scopes, and an ``async_sessionmaker``
  (rather than one session) lets a test open *two independent* sessions — which
  the no-commit test needs to prove writes aren't visible across transactions.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from src.adapters.db.base import Base


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture
async def sessionmaker(
    postgres_container: PostgresContainer,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        postgres_container.get_connection_url(),
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
