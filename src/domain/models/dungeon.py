from dataclasses import dataclass
from uuid import UUID

from src.domain.models.floor import Floor

TOTAL_FLOORS: int = 100


@dataclass
class Dungeon:
    """Domain model for a single dungeon run.

    Binds a procedural ``seed`` to a progression of ``floors`` and tracks
    which floor the player is currently on via ``current_floor_index``
    (0-based). Mutable by design — ``floors`` grows as the player descends
    (new floors are generated from the seed by ``DungeonGenerator``) and
    ``current_floor_index`` increments on descent.

    The ``seed`` is the source of truth for procedural content: any floor
    can be regenerated from ``(seed, index)``. On persistence only the
    seed + index need to be saved; the in-memory ``floors`` list is a
    runtime cache. For v1 a run is ``TOTAL_FLOORS`` (100) floors deep;
    reaching index ``TOTAL_FLOORS - 1`` and descending is the win state.
    Descent bounds are enforced by ``GameService``, not this dataclass —
    ``Dungeon`` is a passive container like the other domain models.

    Note on ``Player``: by design the ``Player`` instance is **not** a
    field on ``Dungeon``. Services take both: ``process_turn(dungeon,
    player, action)``. This keeps ``Player`` as "who the user is"
    (identity, future profile) and ``Dungeon`` as "this specific run",
    and makes v2 co-op additive rather than a refactor.
    """

    dungeon_id: UUID
    seed: int
    floors: list[Floor]
    current_floor_index: int
