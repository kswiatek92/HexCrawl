"""Integration tests for :class:`RedisCache` against a real Redis container.

These cover the wire behaviour the unit suite defers to task 2.8: a genuine
set/get round trip, that ``SET ... EX`` registers a real server-side TTL *and*
the key actually expires, and that a connection failure propagates as an
exception rather than a silent cache miss. Design intent is pinned by
``QUIZZES.md`` task 2.8 (Q1 round-trip must ``await get``; Q2 deterministic TTL
without ``time.sleep``; Q5 failures surface, never swallowed).

The ``cache`` fixture (see ``conftest.py``) yields ``(RedisCache, raw client)``
against a flushed, dedicated Redis DB.
"""

import asyncio

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.adapters.cache.redis_cache import RedisCache, create_redis_client


async def test_round_trips_value_through_real_redis(
    cache: tuple[RedisCache, Redis],
) -> None:
    # Q1: the broken quiz snippet asserts `cache.get(k)` (a coroutine) without
    # awaiting; the single correct assertion awaits both calls. Proves
    # serialisation symmetry against a real server, not a fake.
    redis_cache, _ = cache

    await redis_cache.set("session:abc", "blob", ttl=60)

    assert await redis_cache.get("session:abc") == "blob"


async def test_get_miss_returns_none(
    cache: tuple[RedisCache, Redis],
) -> None:
    # A key never written is a cache miss → None, against real Redis (not just
    # the fake). Remove the value and the round-trip assertion above would fail;
    # this proves the *absence* path independently.
    redis_cache, _ = cache

    assert await redis_cache.get("never-set") is None


async def test_set_replaces_existing_value(
    cache: tuple[RedisCache, Redis],
) -> None:
    # Port contract: `set` is a write-that-replaces, no upsert/insert distinction.
    redis_cache, _ = cache

    await redis_cache.set("k", "first", ttl=60)
    await redis_cache.set("k", "second", ttl=60)

    assert await redis_cache.get("k") == "second"


async def test_set_registers_server_side_ttl(
    cache: tuple[RedisCache, Redis],
) -> None:
    # Q2 (deterministic): prove the atomic SET-with-EX reached Redis by reading
    # the key's TTL server-side — no sleeping, no flakiness. A bare SET (the bug
    # the unit suite guards against) would leave TTL = -1 (no expiry).
    redis_cache, client = cache

    await redis_cache.set("k", "v", ttl=60)

    ttl = await client.ttl("k")
    assert 0 < ttl <= 60


async def test_value_actually_expires(
    cache: tuple[RedisCache, Redis],
) -> None:
    # Q2 (real expiry): a short TTL plus a *bounded poll* (not a fixed time.sleep)
    # proves end-to-end SETEX semantics — the key genuinely disappears. If the
    # adapter dropped `ex=ttl`, the key would never expire and this would time out.
    redis_cache, _ = cache
    await redis_cache.set("ephemeral", "v", ttl=1)

    assert await redis_cache.get("ephemeral") == "v"  # present before expiry

    for _ in range(50):  # up to ~5s, well past the 1s TTL
        if await redis_cache.get("ephemeral") is None:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("key did not expire within the timeout — SETEX expiry not applied")


async def test_non_ascii_round_trips_exactly(
    cache: tuple[RedisCache, Redis],
) -> None:
    # The adapter owns the utf-8 encode/decode; a multibyte payload must survive
    # the real wire byte-for-byte (no normalisation, no mojibake).
    redis_cache, _ = cache
    payload = "dагеон—💀"

    await redis_cache.set("k", payload, ttl=60)

    assert await redis_cache.get("k") == payload


async def test_failure_propagates_not_swallowed() -> None:
    # Q5 / port contract: "Redis is down" raises — it is NOT turned into a cache
    # miss. A client pointed at an unreachable port must surface a ConnectionError
    # from `get`, not return None (a silent fallback that hides the outage is the
    # anti-pattern; graceful degradation belongs in the use case, not the adapter).
    dead = create_redis_client("redis://127.0.0.1:1/0")
    redis_cache = RedisCache(dead)
    try:
        with pytest.raises(RedisConnectionError):
            await redis_cache.get("k")
    finally:
        await dead.aclose()
