"""Live-Redis fixtures for the task 2.8 `RedisCache` integration tests.

The unit tests (``tests/unit/adapters/cache/test_redis_cache.py``) lock the pure
adapter logic against a hand-written ``FakeRedis``. These integration tests cover
the half a fake *cannot*: the real wire behaviour — that the value actually
survives a round trip through a real server, that ``SET ... EX`` registers a
real server-side TTL and the key genuinely expires, and that a dead Redis raises
rather than masquerading as a cache miss. They need a real Redis, so a throwaway
one is spun up with ``testcontainers`` (QUESTIONS.md Phase 2: the chosen runner —
programmatic per-session container, auto cleanup, no compose file). This mirrors
the 2.4/2.5 unit-mapper vs 2.6 integration split established for the DB repos.

Fixture strategy:

* ``redis_container`` — **session-scoped, sync.** Pulling the image and booting
  Redis is the expensive step, so it happens once for the whole run. If the
  Docker daemon isn't reachable, the whole suite skips (not errors) — unit tests
  still pass locally, and CI (where Docker is present) runs them in full. Same
  pattern as the DB conftest.
* ``cache`` — **function-scoped, async.** Builds the production async client via
  the adapter's own :func:`create_redis_client` (``redis.asyncio``, exercising the
  real ``from_url`` path — *not* the container's sync ``get_client()``), flushes
  the DB for per-test isolation (QUIZZES.md 2.8 Q3: a shared key across tests is
  the classic "passes alone, fails in suite" bug — FLUSHDB between tests removes
  it), then yields ``(RedisCache, raw client)``. The raw client is exposed so the
  TTL test can read ``TTL`` server-side without driving it through the adapter.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from docker.errors import DockerException
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer

from src.adapters.cache.redis_cache import RedisCache, create_redis_client

_REDIS_PORT = 6379


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    # These tests need a real Redis, which testcontainers boots via Docker. If the
    # daemon isn't reachable (no Docker locally), skip the whole cache integration
    # suite instead of erroring the run — unit tests still pass, and CI runs these
    # in full. Identical to the DB integration conftest.
    try:
        container = RedisContainer("redis:7-alpine")
        container.start()
    except DockerException as exc:
        pytest.skip(f"Docker unavailable — skipping Redis integration tests ({exc})")
    try:
        yield container
    finally:
        container.stop()


@pytest_asyncio.fixture
async def cache(
    redis_container: RedisContainer,
) -> AsyncIterator[tuple[RedisCache, Redis]]:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(_REDIS_PORT)
    client = create_redis_client(f"redis://{host}:{port}/0")
    # Per-test isolation: wipe DB 0 so no key set by an earlier test bleeds into
    # this one (QUIZZES.md 2.8 Q3). FLUSHDB is scoped to this single logical DB,
    # not the whole server — safe because the container is dedicated test infra.
    await client.flushdb()
    try:
        yield RedisCache(client), client
    finally:
        await client.aclose()
