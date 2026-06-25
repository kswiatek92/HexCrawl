"""``GenerateFloor`` — the work behind the ``map_generation`` task.

The application half of Phase 4's ``map_generation`` job (CLAUDE.md → Celery task
table: "Offload heavy BSP gen for floors 10+"). Where the turn loop refuses to
generate the next floor inline — deep-floor BSP is CPU-bound and would block the
async event loop (``game_service._player_descend``: "Pre-generation … is
StartGame/Celery's job") — this use case *runs* that generation off-loop and
caches the result for the descent path to pick up.

It is the ``map_generation`` counterpart of :class:`RebuildLeaderboard`: the
Celery task (``adapters/tasks/map_generation.py``) is the thin adapter that
stands up the concrete cache; this use case holds the orchestration. Bound by the
hexagonal golden rule — it imports the domain generator, the cache port, and the
sibling ``floor_cache`` codec only; never an adapter, never Celery.

**Idempotent by construction.** ``dungeon_generator.generate`` is a pure
deterministic function of ``(seed, floor_index)`` and the floor is written to the
cache as a full overwrite, so running this twice — as at-least-once delivery can
cause — lands the identical bytes. No read-modify-write, nothing to double-count.
That is what makes "effectively once via idempotency" the real guarantee even
though the queue cannot promise exactly-once (QUIZZES.md 4.3 Q2).
"""

from uuid import UUID

import structlog

from src.application.floor_cache import (
    PREGEN_FLOOR_TTL_SECONDS,
    pregenerated_floor_cache_key,
    serialize_floor,
)
from src.domain.ports import ICachePort
from src.domain.services import generate

logger = structlog.get_logger(__name__)


class GenerateFloor:
    """Use case: pre-generate a deep floor's geometry and cache it.

    The cache port is constructor-injected (mirroring :class:`RebuildLeaderboard`),
    so the use case is unit-testable against a simple hand-written fake with no
    Redis.
    """

    def __init__(self, cache: ICachePort) -> None:
        self._cache = cache

    async def execute(self, game_id: UUID, seed: int, floor_index: int, floor_id: UUID) -> None:
        """Generate floor ``floor_index`` from ``(seed, floor_index)`` and cache it.

        Runs the pure domain BSP generator, stamps the supplied ``floor_id`` onto
        the produced ``Floor`` (so a retried job lands a stable row id rather than
        a fresh ``uuid4`` each time), serialises it via the shared ``floor_cache``
        codec, and overwrites the per-``(game_id, floor_index)`` cache entry with a
        bounded TTL. The descent path polls that key for readiness; an orphaned
        entry (player dies before descending) expires by the TTL.
        """
        floor = generate(seed, floor_index, floor_id)
        await self._cache.set(
            pregenerated_floor_cache_key(game_id, floor_index),
            serialize_floor(floor),
            PREGEN_FLOOR_TTL_SECONDS,
        )
        logger.debug(
            "floor_pregenerated",
            game_id=str(game_id),
            floor_index=floor_index,
            floor_id=str(floor_id),
        )
