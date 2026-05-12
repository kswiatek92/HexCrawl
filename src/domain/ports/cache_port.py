"""Port: ephemeral key/value cache (Redis-backed in production).

Structural contract that any cache adapter must satisfy to serve the
short-lived, TTL-bounded state HexCrawl keeps out of the relational
store: active game sessions (CLAUDE.md → "WebSocket turn loop":
"Active game state lives in Redis (TTL 2h)") and the precomputed
leaderboard slices the `score_recalc` Celery task refreshes. Concrete
implementations live in ``src/adapters/cache/`` (Phase 2.7) — this
module never imports them, and they conform via structural typing
rather than inheritance.

Living in ``src/domain/ports/``, this module is bound by the hexagonal
golden rule (CLAUDE.md → "Architecture — Hexagonal / Ports & Adapters"):
zero framework imports. No ``redis``, no ``celery``, no ``pydantic``.
The port describes *what* the domain needs from a cache, not *how* it
is implemented.

Design choices are pinned by ``QUIZZES.md`` task 1.12:

* **Protocol over ABC** — same rationale as :mod:`game_repository` and
  :mod:`score_repository`: adapters conform structurally, the
  dependency arrow stays ``adapters → ports``, and test fakes need no
  inheritance.
* **Values are `str`, not `dict` or `Any`** (Q1) — Redis stores
  bytes-as-strings natively, and ``disallow_any_explicit`` (set on
  ``src.domain.*`` in ``pyproject.toml``) forbids ``Any`` here anyway.
  A ``dict`` value would silently tie the port to a particular
  serialisation choice and re-introduce the framework dependency the
  hexagonal layout exists to prevent. ``str`` is the narrowest type
  that satisfies every planned consumer.
* **Use cases own serialisation, not the cache adapter** (Q2) —
  ``StartGame`` / ``ProcessTurn`` (Phase 3) ``json.dumps`` their
  ``Dungeon`` blob before calling :meth:`ICachePort.set`, and
  ``json.loads`` after :meth:`ICachePort.get`. The cache adapter does
  not import :class:`Dungeon`. This keeps the adapter generic (the
  same Redis client serves session blobs and leaderboard blobs) and
  keeps domain coupling on the *use-case* side of the boundary.
* **TTL is mandatory on every write** (Q3) — the cache layer must
  never accumulate state indefinitely. ``ttl > 0`` is a docstring
  contract; runtime enforcement falls to the adapter (Redis ``SETEX``
  rejects ``ttl <= 0`` natively). There is no "store forever"
  overload — abandoned game sessions naturally expire, which is the
  whole point of putting them in Redis instead of Postgres.
* **`get` returns `None` for both "never set" and "expired"** (Q4) —
  callers MUST treat both flavours of cache miss identically: fall
  through to the authoritative source (Postgres) or start fresh.
  Adapters MUST NOT expose an "expired vs never-set" signal — there
  is no `get_with_metadata()` method and there will not be one.
* **Two-method surface, no `delete`** — quiz Q5 caps the
  ``FakeCachePort`` budget at 5–10 lines, which is the deliberate
  signal that the surface is minimal. v1 consumers
  (``StartGame``, ``ProcessTurn``, the three ``/leaderboard/*``
  endpoints, ``score_recalc``) all use ``get``/``set`` only. Active
  game-session eviction at game-over is handled by *key design*
  (each run uses a per-``session_id`` key) and TTL — not by an
  explicit ``delete``. If an admin-kick or similar use case ever
  surfaces, ``delete`` joins the port then; per ISP it is excluded
  now.
* **All methods async** — adapters use ``redis.asyncio`` per
  CLAUDE.md → "Code conventions — Async all the way down". A sync
  port would force adapters to either block the event loop or wrap
  with ``asyncio.run`` at every call site.
* **No `runtime_checkable`** — the project type-checks statically
  with mypy-strict; no ``isinstance(x, ICachePort)`` guards exist
  or are planned.
"""

from typing import Protocol


class ICachePort(Protocol):
    """Ephemeral key/value cache contract.

    Adapters implementing this Protocol own the storage details (Redis
    connection lifecycle, key namespacing, retry semantics, network
    timeouts, and the wire-level expiry mechanism). The domain only
    sees the contract below.
    """

    async def get(self, key: str) -> str | None:
        """Fetch the value stored under ``key``.

        Returns ``None`` if the key is missing **or** expired. Callers
        MUST treat both cases identically — fall through to the
        authoritative source (a Postgres read via
        :class:`IGameRepository` / :class:`IScoreRepository`, or a
        fresh computation). Adapters MUST NOT expose an "expired vs
        never-set" signal: any future "get with metadata" method would
        leak Redis internals across the port and re-introduce a
        framework coupling the domain explicitly rejects.

        Adapter-level failures (connection refused, Redis down,
        protocol error) propagate as exceptions. "Cache miss" is a
        domain outcome; "no Redis" is not. Application-layer graceful
        degradation lives in the use case, not in this port.
        """
        ...

    async def set(self, key: str, value: str, ttl: int) -> None:
        """Store ``value`` under ``key`` with a ``ttl``-second expiration.

        Overwrites any existing value at ``key`` without error — there
        is no "already exists" sentinel and no upsert vs. insert
        distinction. From the caller's point of view, ``set`` is a
        write that replaces.

        ``ttl`` is REQUIRED and must be ``> 0``. No infinite-TTL
        semantics, no ``ttl=0`` "delete now" overload — the port
        treats every entry as ephemeral by design (CLAUDE.md →
        "Active game state lives in Redis (TTL 2h)"). Enforcement of
        the positivity invariant is the adapter's job; Redis
        ``SETEX`` rejects ``ttl <= 0`` natively, which is the
        backstop.

        Values are opaque bytes-as-str: adapters MUST round-trip
        ``value`` exactly. No encoding normalisation, no whitespace
        trimming, no JSON-aware parsing. Serialisation of domain
        objects (``Dungeon``, ``list[Score]``) is the *caller's*
        responsibility — typically ``json.dumps`` in the use case
        before this call, and ``json.loads`` after the matching
        ``get``. The cache adapter never imports a domain type.

        Adapter-level failures (connection refused, write timeout)
        propagate as exceptions; same convention as :meth:`get`.
        """
        ...
