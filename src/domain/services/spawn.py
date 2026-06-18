"""Shared spawn-placement rule for a fresh floor.

A single pure function, ``spawn_position``, answers "where does the player
appear when they first set foot on a floor?" — used both by ``StartGame``
(application layer, initial spawn on floor 0) and by ``GameService`` on
descent (placing the player on the newly-entered floor).

Pulled out of ``game_service`` so the two callers share one source of truth
rather than duplicating the scan. Pure geometry, no I/O, no framework
imports — it lives in ``domain/services`` like the other rule functions.
"""

from src.domain.models.floor import Floor
from src.domain.models.tile_type import TileType


def spawn_position(floor: Floor) -> tuple[int, int]:
    """Return the first FLOOR-or-STAIRS tile in row-major scan order.

    v1 placeholder for spawn placement: when ``Floor`` gains a proper
    ``spawn_position`` field (driven by ``DungeonGenerator`` once it starts
    placing up-stairs), this helper goes away. Falls back to ``(0, 0)`` only
    for the degenerate case of a fully blocked floor — which never happens
    with the generator's connectivity guarantee.
    """
    for y, row in enumerate(floor.tiles):
        for x, tile in enumerate(row):
            if tile is TileType.FLOOR or tile is TileType.STAIRS:
                return (x, y)
    return (0, 0)
