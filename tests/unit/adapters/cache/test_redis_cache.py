"""Unit tests for :class:`RedisCache` — the pure adapter logic, no live Redis.

These lock the behaviour `RedisCache` owns *itself*: the ``ttl > 0`` guard, the
``str``<->utf-8 round-trip, the cache-miss contract, and that ``set`` issues an
atomic SET-with-expiry (``ex=ttl``) rather than a bare ``SET``. The real wire
round-trip and genuine TTL expiry against a live server are task 2.8's
integration suite (a real Redis container) — exactly the 2.4/2.5 unit vs 2.6
integration split.

The client is replaced with a hand-written async fake (no ``fakeredis`` dep, no
container) that mimics the two behaviours the adapter depends on: ``get``
returns stored values as **bytes** (so the decode path is exercised), and
``set`` records its arguments so the test can assert the ``ex`` kwarg.
"""

import pytest

from src.adapters.cache.redis_cache import RedisCache
from src.domain.ports.cache_port import ICachePort


class FakeRedis:
    """Minimal async stand-in for ``redis.asyncio.Redis``.

    Records every ``set`` call so tests can inspect the TTL argument. ``get``
    returns values as **bytes** by default (matching a default-configured real
    client); with ``decode_responses=True`` it returns **str**, mirroring a
    client configured that way — both paths the adapter must round-trip.
    """

    def __init__(self, *, decode_responses: bool = False) -> None:
        self._store: dict[str, str] = {}
        self._decode_responses = decode_responses
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str) -> bytes | str | None:
        value = self._store.get(key)
        if value is None:
            return None
        return value if self._decode_responses else value.encode("utf-8")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls.append((key, value, ex))
        self._store[key] = value


def _cache() -> tuple[RedisCache, FakeRedis]:
    fake = FakeRedis()
    return RedisCache(fake), fake  # type: ignore[arg-type]


def test_redis_cache_satisfies_port() -> None:
    # Structural conformance: a RedisCache is usable wherever ICachePort is
    # expected. If the method surface drifted, mypy would already fail, but this
    # documents the contract at runtime too.
    cache: ICachePort = _cache()[0]
    assert cache is not None


async def test_set_issues_atomic_set_with_expiry() -> None:
    cache, fake = _cache()

    await cache.set("session:abc", "blob", ttl=60)

    # Exactly one call, carrying the value and the TTL as the ex= kwarg — proves
    # the atomic SET-with-EX path, not a bare SET (which would record ex=None).
    assert fake.set_calls == [("session:abc", "blob", 60)]


async def test_get_round_trips_value_as_str() -> None:
    cache, fake = _cache()
    await cache.set("k", "value", ttl=60)

    result = await cache.get("k")

    # bytes in the store come back decoded to str (not the raw b"value").
    assert result == "value"
    assert isinstance(result, str)


async def test_get_round_trips_str_when_client_decodes_responses() -> None:
    # A client built with decode_responses=True returns str, not bytes. The
    # adapter must pass it through unchanged rather than crash on a missing
    # .decode() — this is the case Copilot flagged and the docstring promises.
    fake = FakeRedis(decode_responses=True)
    cache = RedisCache(fake)  # type: ignore[arg-type]
    await cache.set("k", "value", ttl=60)

    result = await cache.get("k")

    assert result == "value"
    assert isinstance(result, str)


async def test_get_miss_returns_none() -> None:
    cache, _ = _cache()

    assert await cache.get("never-set") is None


async def test_value_round_trips_non_ascii_exactly() -> None:
    # Proves the adapter owns utf-8 encode/decode and does not normalise: a
    # multibyte payload survives the set/get cycle byte-for-byte.
    cache, _ = _cache()
    payload = "dагеон—💀"

    await cache.set("k", payload, ttl=60)

    assert await cache.get("k") == payload


@pytest.mark.parametrize("bad_ttl", [0, -1, -3600])
async def test_set_rejects_non_positive_ttl(bad_ttl: int) -> None:
    cache, fake = _cache()

    with pytest.raises(ValueError, match="ttl must be > 0"):
        await cache.set("k", "v", ttl=bad_ttl)

    # The guard fires *before* Redis is touched: no call leaked through. Remove
    # the guard and this assertion fails (the set would be recorded).
    assert fake.set_calls == []
