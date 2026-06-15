"""Redis adapter implementing :class:`ICachePort`.

Backs the ephemeral, TTL-bounded state HexCrawl keeps out of the relational
store — active game sessions (CLAUDE.md → "Active game state lives in Redis
(TTL 2h)") and the precomputed leaderboard slices. This is an *adapter*: it
imports a framework (``redis.asyncio``) and must never be imported by
``domain/`` or ``application/``. It conforms to :class:`ICachePort`
**structurally** (no inheritance) — mypy checks the match, there is no
``implements`` keyword, exactly like ``PostgresGameRepository`` vs
``IGameRepository``.

Design, pinned to ``QUIZZES.md`` task 2.7 and the :mod:`cache_port` docstring:

* **``redis.asyncio``, never the sync client** (Q3) — a blocking Redis call on
  the FastAPI event loop stalls *every* in-flight request, not just the caller;
  async keeps the loop free while the round-trip is in flight.
* **Atomic ``SET ... EX``, not ``SET`` then ``EXPIRE``** (Q2) — passing
  ``ex=ttl`` issues a single command, so there is no window where a crash
  between two commands leaves a key with no TTL accumulating forever. This is
  the runtime backstop for the port's mandatory-TTL contract.
* **Connection pool, not a connection per call** (Q4) — :func:`create_redis_client`
  goes through ``redis.asyncio.from_url``, which builds a pool. The app creates
  one client at startup (FastAPI lifespan, Phase 3) and injects it here; the
  adapter never builds the pool itself — the same "caller owns the long-lived
  resource" rule the DB repos follow for the engine/session.
* **Failures propagate** (Q5) — "Redis is down" raises, it is not a cache miss.
  Graceful degradation (fall back to Postgres, log the outage) lives in the
  use case, per the port docstring; a *silent* fallback that hides the outage
  is the anti-pattern.
* **The adapter owns the ``str`` round-trip** — the client is left on its
  default (bytes) responses and this adapter encodes/decodes utf-8 itself, so
  the port's ``str`` contract holds regardless of how the injected client was
  configured. Serialisation of domain objects (``Dungeon``, ``list[Score]``)
  stays the *caller's* job — this module imports no domain type.
"""

from redis.asyncio import Redis, from_url


def create_redis_client(url: str) -> Redis:
    """Build the shared, pooled async Redis client for one app process.

    Wraps ``redis.asyncio.from_url`` (which provisions a connection pool). Call
    once at startup and inject the result into :class:`RedisCache`; closing it
    is the caller's responsibility (FastAPI lifespan shutdown, Phase 3).
    """
    return from_url(url)


class RedisCache:
    """Async Redis implementation of :class:`ICachePort`.

    The client is injected (not created here) so the caller owns the connection
    pool and its lifecycle. Storage details — namespacing, retries, timeouts —
    live with the client; the domain only sees ``get``/``set``.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        # Redis returns nil for both a never-set key and an expired one; the
        # client surfaces both as ``None``, so callers cannot (and must not)
        # distinguish "missing" from "expired" — both are a cache miss.
        raw = await self._client.get(key)
        if raw is None:
            return None
        # Honour the str contract regardless of how the injected client was
        # configured: a default client hands back bytes, a decode_responses=True
        # client hands back str. Anything else is a misconfiguration we surface
        # loudly rather than silently mangle.
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        if isinstance(raw, str):
            return raw
        raise TypeError(f"unexpected Redis value type for key {key!r}: {type(raw).__name__}")

    async def set(self, key: str, value: str, ttl: int) -> None:
        # Enforce the port's mandatory-positive-TTL invariant before touching
        # Redis, so a misuse fails loudly at the call site rather than as an
        # opaque server-side error. SETEX is the backstop, this is the guard.
        if ttl <= 0:
            raise ValueError(f"ttl must be > 0, got {ttl}")
        # ex=ttl makes this an atomic SET-with-expiry (single command); the str
        # value is encoded to utf-8 bytes on the wire by redis-py.
        await self._client.set(key, value, ex=ttl)
