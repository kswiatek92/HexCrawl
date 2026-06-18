"""``ProcessTurn`` — the use case for advancing a run by one player action.

The write-side command behind the WebSocket turn loop (CLAUDE.md → "WebSocket
turn loop"). Where ``StartGame`` (3.1) *creates* a run, ``ProcessTurn`` *advances*
one: it takes one player ``Action``, loads the run's active ``(Dungeon, Player)``
state, runs the pure domain ``process_turn`` over it, persists the result, and
hands back the ``TurnResult`` (the typed event list + game-over flag) for the
entrypoint (task 3.9) to serialise to the client.

Like every use case it is *orchestration*, not game rule: the rules live in
``GameService.process_turn``; this module only wires that service to the
persistence ports in the right order. Bound by the hexagonal golden rule — it
imports domain models, the domain ports, the domain service, and the sibling
``game_state`` codec only; never an adapter, never a framework.

**Load — cache-first, Postgres-fallback.** The hot, turn-by-turn state lives in
Redis, not Postgres (CLAUDE.md: "Active game state lives in Redis (TTL 2h)"), so
the read tries the cache first — that is the whole point of keeping it there
(QUIZZES.md task 3.2 Q1). A miss is *not* fatal: a run whose 2h TTL lapsed
mid-session is rebuilt from its last Postgres checkpoint (``game_state.py`` →
"rebuilt from the Postgres checkpoint on the next access"). Only when *neither*
holds the run is it genuinely gone — :class:`GameNotFoundError`.

**Persist — Redis every turn, Postgres on checkpoints.** Every turn refreshes the
Redis working copy. Postgres is written *only* on a checkpoint — game over or a
floor descent (CLAUDE.md: "Persisted to PostgreSQL only on: game over, floor
descent (checkpoint), explicit save") — to bound write-amplification: most turns
never touch the relational store. When both writes happen, the durable Postgres
save goes **first**, so an interrupt between the two can never lose a checkpoint
(it only loses a rebuildable cache refresh).

**Cache writes propagate — the opposite of ``StartGame``.** ``StartGame`` swallows
a cache-write failure because *its* authoritative copy is the Postgres row. Here
the cache *is* the authoritative copy of mid-game state (a normal turn writes
nowhere else), so a failed write is a real failure: swallowing it would let the
client believe the turn landed while the next turn reads stale state. We let it
propagate to the handler instead of silently diverging.
"""

from uuid import UUID

import structlog

from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    deserialize_game_state,
    game_state_cache_key,
    serialize_game_state,
)
from src.domain.models import Action, Dungeon, FloorDescended, Player
from src.domain.ports import ICachePort, IGameRepository
from src.domain.services import TurnResult, process_turn

logger = structlog.get_logger(__name__)


class GameNotFoundError(Exception):
    """No run exists for the given id — not in the cache, not in Postgres.

    A normal application outcome (the id was never started, was already
    hard-deleted, or is simply wrong), not an infrastructure fault. The
    entrypoint (task 3.9) maps it to a close/error frame; the HTTP layer
    would map it to a 404.
    """


class ProcessTurn:
    """Use case: advance a run by one player action.

    Ports are constructor-injected (mirroring ``StartGame``), so the use case
    is unit-testable against simple hand-written fakes with no Redis or
    database.
    """

    def __init__(self, games: IGameRepository, cache: ICachePort) -> None:
        self._games = games
        self._cache = cache

    async def execute(self, game_id: UUID, action: Action) -> TurnResult:
        """Resolve one turn for ``game_id`` and return its ``TurnResult``.

        Loads the active state (cache-first, Postgres-fallback), runs the
        domain turn, checkpoints to Postgres on game over / floor descent,
        and refreshes the Redis working copy. Raises
        :class:`GameNotFoundError` if no run exists for ``game_id``.
        """
        key = game_state_cache_key(game_id)
        dungeon, player = await self._load(game_id, key)

        result = process_turn(dungeon, player, action)

        # Durable checkpoint first so an interrupt before the cache write can
        # never lose a game-over/descent (QUIZZES.md task 3.3 Q4 ordering).
        if result.game_over or _is_checkpoint(result):
            await self._games.save(dungeon, player)

        # Refresh the hot working copy every turn. Errors propagate: the cache
        # is the authoritative copy of mid-game state, so a failed write must
        # not be silently swallowed (contrast StartGame).
        await self._cache.set(key, serialize_game_state(dungeon, player), GAME_STATE_TTL_SECONDS)

        return result

    async def _load(self, game_id: UUID, key: str) -> tuple[Dungeon, Player]:
        """Load active state: Redis first, Postgres checkpoint on a cache miss."""
        blob = await self._cache.get(key)
        if blob is not None:
            return deserialize_game_state(blob)

        # Cache miss — the run's TTL lapsed (or it was never cached). Rebuild
        # from the last durable checkpoint; the turn below re-seeds the cache.
        loaded = await self._games.get(game_id)
        if loaded is None:
            raise GameNotFoundError(str(game_id))
        logger.info("process_turn_cache_miss_rehydrated", game_id=str(game_id))
        return loaded


def _is_checkpoint(result: TurnResult) -> bool:
    """True when this turn descended a floor — a Postgres checkpoint trigger.

    Game over is checked separately by the caller via ``result.game_over``;
    this covers the other checkpoint case (floor descent), detected from the
    event log rather than re-deriving floor-index deltas.
    """
    return any(isinstance(event, FloorDescended) for event in result.events)
