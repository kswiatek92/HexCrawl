"""``StartGame`` — the use case for creating a new dungeon run.

This is the first occupant of the **application layer** and sets the pattern
the later use cases (``ProcessTurn``, ``SubmitScore``) follow. A use case is
*orchestration*: it holds no game rule of its own — it wires the domain
services (here: ``DungeonGenerator``, ``spawn_position``) to the persistence
ports (``IGameRepository``, ``ICachePort``) in the right order to accomplish
one user action.

``StartGame`` is the write-side command for "player starts a new game":

1. pick a ``seed`` (server-random by default; client-supplied for daily /
   shared-seed modes per QUESTIONS.md 1.6),
2. generate floor 0 from it,
3. build the ``(Dungeon, Player)`` pair,
4. persist it durably (Postgres, via :class:`IGameRepository`),
5. seed the hot active-game-state into the cache (Redis, via
   :class:`ICachePort`) so the turn loop reads mid-game state without a DB
   round-trip,
6. return the canonical post-write pair.

Bound by the hexagonal golden rule: this module imports domain models, the
domain ``Protocol`` ports, and the ``DungeonGenerator`` service only — never
an adapter, never ``fastapi`` / ``sqlalchemy`` / ``redis`` / ``celery``.

**Two boundary behaviours worth calling out:**

* **The use case does not commit.** ``IGameRepository.save`` merges + flushes
  but leaves the transaction boundary to the caller (DECISIONS.md ADR-0006;
  ``game_repository.py``). The SQLAlchemy ``Session`` is the per-request Unit
  of Work, committed by the ambient request scope wired in task 3.4 — not
  here. The use case cannot reach a session and must not try to.
* **The cache write is best-effort.** The durable copy is the Postgres write;
  the Redis entry is *rebuildable derived state*. If the cache write fails
  (Redis down, timeout), we log and carry on rather than failing the whole
  command — losing a cache entry is harmless, failing "new game" over a cache
  hiccup is not (QUIZZES.md task 3.1 Q4).
"""

import random
from typing import Final
from uuid import UUID, uuid4

import structlog

from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    game_state_cache_key,
    serialize_game_state,
)
from src.domain.models import Dungeon, Player
from src.domain.ports import ICachePort, IGameRepository
from src.domain.services import dungeon_generator
from src.domain.services.spawn import spawn_position

logger = structlog.get_logger(__name__)

# Seeds are unpredictable run identifiers, not cryptographic secrets; 63 bits
# keeps the value a non-negative signed-64-bit int (comfortably within the
# Postgres BIGINT the seed column uses).
_SEED_BITS: Final[int] = 63


class StartGame:
    """Use case: create and persist a new dungeon run.

    Ports are constructor-injected (mirroring how the adapters take their
    session / client), so the use case is unit-testable against simple
    hand-written fakes with no database or Redis.
    """

    def __init__(self, games: IGameRepository, cache: ICachePort) -> None:
        self._games = games
        self._cache = cache

    async def execute(
        self,
        user_id: UUID,
        player_name: str,
        seed: int | None = None,
    ) -> tuple[Dungeon, Player]:
        """Create a new run for ``user_id`` and return the ``(Dungeon, Player)``.

        Takes primitive identifiers (``user_id``, ``player_name``) rather than
        a built ``Player`` so the use case stays decoupled from the transport
        layer — the HTTP route (task 3.6) maps a request body to these args
        without the domain leaking outward (QUIZZES.md task 3.1 Q3).

        ``seed`` defaults to a fresh server-random value; callers pass an
        explicit seed for daily / shared-seed leaderboard modes.
        """
        resolved_seed = seed if seed is not None else random.getrandbits(_SEED_BITS)
        dungeon_id = uuid4()

        floor0 = dungeon_generator.generate(resolved_seed, 0)
        dungeon = Dungeon(
            dungeon_id=dungeon_id,
            seed=resolved_seed,
            floors=[floor0],
            current_floor_index=0,
        )
        player = Player(
            user_id=user_id,
            name=player_name,
            position=spawn_position(floor0),
        )

        # Durable write first: this is the authoritative copy. The repo flushes
        # but does not commit — the ambient request transaction (task 3.4) does.
        saved_dungeon, saved_player = await self._games.save(dungeon, player)

        # Serialise outside the try: this is pure, in-process work that should
        # never fail. If it ever does (e.g. a model field the codec forgot), we
        # want that bug to surface loudly, not be swallowed as a "cache failure".
        blob = serialize_game_state(saved_dungeon, saved_player)

        # Best-effort cache seed: Redis holds a rebuildable copy, so a failure
        # here must not fail the command. We deliberately catch broadly — the
        # cache port's contract is that infra faults *propagate*, and swallowing
        # them is precisely this use case's call (QUIZZES.md task 3.1 Q4).
        try:
            await self._cache.set(game_state_cache_key(dungeon_id), blob, GAME_STATE_TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001 — intentional: cache is rebuildable derived state
            logger.warning(
                "start_game_cache_seed_failed",
                dungeon_id=str(dungeon_id),
                error=type(exc).__name__,
            )

        return saved_dungeon, saved_player
