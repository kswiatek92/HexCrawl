from dataclasses import dataclass
from uuid import UUID

from src.domain.models.enemy import Enemy
from src.domain.models.item import Item
from src.domain.models.tile_type import TileType

GRID_WIDTH: int = 80
GRID_HEIGHT: int = 50


@dataclass
class Floor:
    """Domain model for one level of a dungeon run.

    Mutable by design. The ``tiles`` grid is generated once by
    ``DungeonGenerator`` and treated as read-only thereafter, but
    ``enemies`` and ``items`` mutate every turn (kills, pickups, drops),
    so the dataclass cannot be ``frozen``. Mutation lives with the
    callers (``GameService``, ``EnemyAI``); ``Floor`` itself is a passive
    container.

    Coordinate convention: ``tiles[y][x]``. Y is the outer (row) index,
    X is the inner (column) index — row-major, matching the BSP /
    canvas-render direction. ``enemies[i].position`` and ``items`` keys
    use ``(x, y)`` for the domain-facing API; the indexing inversion is
    intentional and only applied when projecting an ``(x, y)`` onto the
    grid.

    ``items`` is keyed by position because ``Item`` has no intrinsic
    position field — the dict key is canonical for ground items. Multiple
    items can share a tile (e.g. a new weapon pickup drops the old one
    on the same square), so the value is a list.

    Grid dimensions for v1 are fixed at ``GRID_WIDTH`` × ``GRID_HEIGHT``
    (80×50, classic roguelike). Validation is the generator's job, not
    this dataclass's — ``Floor`` accepts whatever grid it is given.
    """

    floor_id: UUID
    tiles: list[list[TileType]]
    enemies: list[Enemy]
    items: dict[tuple[int, int], list[Item]]
    stairs_down: tuple[int, int]
