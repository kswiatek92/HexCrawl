"""Tests for ``src.domain.services.spawn.spawn_position``.

The spawn rule was extracted from ``game_service`` (task 3.1) so ``StartGame``
and descent share one source of truth. These cover the rule directly; descent
behaviour is still exercised through ``process_turn`` in ``test_game_service``.
"""

from uuid import UUID, uuid4

from src.domain.models import Floor, TileType
from src.domain.services import dungeon_generator
from src.domain.services.spawn import spawn_position


def _floor_from_grid(rows: list[str], floor_id: UUID | None = None) -> Floor:
    """``.`` → FLOOR, ``#`` → WALL, ``>`` → STAIRS, ``+`` → DOOR."""
    mapping = {
        ".": TileType.FLOOR,
        "#": TileType.WALL,
        ">": TileType.STAIRS,
        "+": TileType.DOOR,
    }
    tiles = [[mapping[ch] for ch in row] for row in rows]
    return Floor(
        floor_id=floor_id or uuid4(),
        tiles=tiles,
        enemies=[],
        items={},
        stairs_down=(0, 0),
    )


def test_returns_first_floor_tile_in_row_major_order() -> None:
    # First two rows are solid wall; the first walkable tile is the FLOOR at
    # (x=2, y=2). Row-major means we scan y outer, x inner.
    floor = _floor_from_grid(
        [
            "#####",
            "#####",
            "##..#",
            "#####",
        ]
    )
    assert spawn_position(floor) == (2, 2)


def test_stairs_count_as_walkable() -> None:
    # No FLOOR anywhere; the only walkable tile is STAIRS at (1, 1).
    floor = _floor_from_grid(
        [
            "###",
            "#>#",
            "###",
        ]
    )
    assert spawn_position(floor) == (1, 1)


def test_door_does_not_count_as_spawn() -> None:
    # A DOOR precedes the FLOOR in scan order, but spawn must land on the
    # FLOOR — a player should not start standing in a (closed) doorway.
    floor = _floor_from_grid(
        [
            "#+#",
            "#.#",
        ]
    )
    assert spawn_position(floor) == (1, 1)


def test_fully_blocked_floor_falls_back_to_origin() -> None:
    floor = _floor_from_grid(["###", "###"])
    assert spawn_position(floor) == (0, 0)


def test_generated_floor_spawns_on_a_walkable_tile() -> None:
    floor = dungeon_generator.generate(seed=42, floor_index=0)
    x, y = spawn_position(floor)
    assert floor.tiles[y][x] in (TileType.FLOOR, TileType.STAIRS)
