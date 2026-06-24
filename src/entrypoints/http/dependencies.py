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
from uuid import UUID

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.cache.redis_cache import RedisCache
from src.adapters.db.game_repository import PostgresGameRepository
from src.application.abandon_game import AbandonGame
from src.application.game_state import deserialize_game_state, game_state_cache_key
from src.application.get_game import GetGame
from src.application.process_turn import ProcessTurn
from src.application.start_game import StartGame
from src.config import Settings
from src.domain.models import Action, Dungeon, Player
from src.domain.services import TurnResult


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


def get_session_maker(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the process-wide ``async_sessionmaker`` from ``app.state``.

    The WebSocket turn loop (task 3.9) needs to open a *fresh* session per turn
    rather than share the request-scoped one ``get_session`` yields — see
    :class:`GameSessionRunner` — so it takes the factory, not a session.
    """
    return request.app.state.async_session_maker  # type: ignore[no-any-return]


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


def get_get_game(
    games: Annotated[PostgresGameRepository, Depends(get_game_repository)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> GetGame:
    """Assemble the ``GetGame`` read use case from its injected ports."""
    return GetGame(games, cache)


def get_abandon_game(
    games: Annotated[PostgresGameRepository, Depends(get_game_repository)],
    cache: Annotated[RedisCache, Depends(get_cache)],
) -> AbandonGame:
    """Assemble the ``AbandonGame`` use case from its injected ports."""
    return AbandonGame(games, cache)


# --- WebSocket turn loop: per-turn Unit of Work ---------------------------
#
# The HTTP providers above each serve *one request* and lean on
# ``get_session``'s request-scoped ``session.begin()`` for their transaction.
# A WebSocket connection is long-lived and a FastAPI ``Depends`` resolves
# **once per connection**, so a single injected session/transaction would span
# every turn — checkpoints (game over, floor descent) wouldn't commit until the
# socket closed, and a mid-session crash would lose them. The turn loop needs
# the opposite: one transaction *per turn*. ``GameSessionRunner`` provides that
# — it holds the session *factory* (not a session) and opens a fresh
# ``session.begin()`` for each call. It is the composition root for the WS path:
# the one place the concrete adapters are named for the loop, mirroring the HTTP
# providers above. The handler (``entrypoints/ws/router_game.py``) depends only
# on this runner and never touches a session, repo, or cache directly.


class GameSessionRunner:
    """Runs WebSocket turn-loop operations, each in its own transaction.

    Built from the process-wide session factory and Redis client (both
    long-lived), it exposes the two operations the WS handler needs:
    :meth:`load_authorized` (connect-time authorisation + initial state) and
    :meth:`process` (one turn). Each opens a fresh ``AsyncSession`` wrapped in
    ``session.begin()`` so the per-turn Unit of Work commits independently —
    the same transaction boundary ``get_session`` gives HTTP requests, applied
    once per turn instead of once per connection.
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        redis: Redis,
    ) -> None:
        self._session_maker = session_maker
        self._redis = redis

    async def load_authorized(
        self, game_id: UUID, requester_id: UUID
    ) -> tuple[Dungeon, Player]:
        """Load ``game_id`` and confirm ``requester_id`` owns it.

        Delegates to the ``GetGame`` use case (cache-first read + ownership
        check), so the WS connect path reuses exactly the authorisation the
        ``GET /game/{id}`` route uses: it raises ``GameNotFoundError`` for an
        unknown run and ``NotGameOwnerError`` for a foreign one. Read-only, but
        still inside a transaction for a consistent session lifecycle.
        """
        async with self._session_maker() as session, session.begin():
            use_case = GetGame(PostgresGameRepository(session), RedisCache(self._redis))
            return await use_case.execute(game_id, requester_id)

    async def process(
        self, game_id: UUID, action: Action
    ) -> tuple[TurnResult, Dungeon, Player]:
        """Advance ``game_id`` by one ``action`` and return result + new state.

        Runs the ``ProcessTurn`` use case in a fresh per-turn transaction, then
        re-reads the cache entry ``ProcessTurn`` just wrote to recover the
        post-turn ``(Dungeon, Player)`` — the use case returns only a
        ``TurnResult``, but the handler needs the full state to push back to the
        client (enemy *moves* emit no event, so the event stream alone can't
        rebuild positions). The re-read is a single cheap GET of the entry the
        turn just refreshed.
        """
        async with self._session_maker() as session, session.begin():
            cache = RedisCache(self._redis)
            use_case = ProcessTurn(PostgresGameRepository(session), cache)
            result = await use_case.execute(game_id, action)
            blob = await cache.get(game_state_cache_key(game_id))

        # ProcessTurn.execute always refreshes the cache before returning, so a
        # missing blob here is an infrastructure fault, not a normal outcome.
        if blob is None:  # pragma: no cover - defensive; execute always writes it
            raise RuntimeError(f"game state vanished from cache after turn: {game_id}")
        dungeon, player = deserialize_game_state(blob)
        return result, dungeon, player


def get_game_session_runner(
    session_maker: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_maker)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> GameSessionRunner:
    """Assemble the WebSocket turn-loop runner from the long-lived resources."""
    return GameSessionRunner(session_maker, redis)
