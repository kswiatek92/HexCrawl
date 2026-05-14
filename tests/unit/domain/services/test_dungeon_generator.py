"""Smoke tests for `src.domain.services.dungeon_generator.generate`.

Scope: the basic invariants the generator must satisfy. The comprehensive
suite — property-based tests via Hypothesis, edge cases on tiny grids,
re-roll exhaustion, and so on — belongs to task 1.14
("Unit tests for DungeonGenerator") per `BOARD.md`. The tests here exist
so 1.13 itself isn't shipped untested, and they cover the post-conditions
that the task's design documents (`QUESTIONS.md` task 1.13, `QUIZZES.md`
task 1.13 Q2 + Q4) explicitly call out as load-bearing.
"""

from dataclasses import is_dataclass

from src.domain.models import GRID_HEIGHT, GRID_WIDTH, Floor, TileType
from src.domain.services import generate

_WALKABLE: frozenset[TileType] = frozenset({TileType.FLOOR, TileType.STAIRS, TileType.DOOR})


def _flood_fill_walkable_count(tiles: list[list[TileType]], width: int, height: int) -> int:
    """Return the size of the connected component of walkable tiles
    containing the first walkable tile found (row-major scan).

    Implemented independently of the generator's internal flood-fill
    helper so the test exercises an external observation of connectivity,
    not the generator's own bookkeeping.
    """
    start: tuple[int, int] | None = None
    for y in range(height):
        for x in range(width):
            if tiles[y][x] in _WALKABLE:
                start = (x, y)
                break
        if start is not None:
            break
    if start is None:
        return 0
    visited: set[tuple[int, int]] = set()
    stack: list[tuple[int, int]] = [start]
    while stack:
        pos = stack.pop()
        if pos in visited:
            continue
        visited.add(pos)
        x, y = pos
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                if tiles[ny][nx] in _WALKABLE:
                    stack.append((nx, ny))
    return len(visited)


def _total_walkable(tiles: list[list[TileType]]) -> int:
    return sum(1 for row in tiles for t in row if t in _WALKABLE)


def test_returns_a_floor_dataclass() -> None:
    floor = generate(seed=12345, floor_index=0)
    assert isinstance(floor, Floor)
    assert is_dataclass(floor)


def test_grid_has_expected_default_dimensions() -> None:
    floor = generate(seed=12345, floor_index=0)
    assert len(floor.tiles) == GRID_HEIGHT
    for row in floor.tiles:
        assert len(row) == GRID_WIDTH


def test_all_tiles_are_valid_tile_type_members() -> None:
    # `isinstance` (not `tile in TileType`): on Python 3.12 a `StrEnum`'s
    # `__contains__` returns True for raw values too — `"FLOOR" in TileType`
    # is True — which would hide a regression where the generator emits
    # serialised strings instead of enum members. `isinstance` rejects
    # raw strings, which is what the assertion is meant to enforce.
    floor = generate(seed=12345, floor_index=0)
    for row in floor.tiles:
        for tile in row:
            assert isinstance(tile, TileType)


def test_exactly_one_stairs_tile_and_stairs_down_matches_its_position() -> None:
    floor = generate(seed=12345, floor_index=0)
    stairs_positions = [
        (x, y)
        for y, row in enumerate(floor.tiles)
        for x, tile in enumerate(row)
        if tile is TileType.STAIRS
    ]
    assert stairs_positions == [floor.stairs_down]


def test_enemies_and_items_start_empty() -> None:
    floor = generate(seed=12345, floor_index=0)
    assert floor.enemies == []
    assert floor.items == {}


def test_same_seed_and_floor_index_produces_identical_geometry() -> None:
    # Determinism is the property `QUIZZES.md` task 1.13 Q2 hinges on:
    # if this fails, the planned replay system is impossible.
    a = generate(seed=42, floor_index=3)
    b = generate(seed=42, floor_index=3)
    assert a.tiles == b.tiles
    assert a.stairs_down == b.stairs_down


def test_different_seeds_produce_different_geometry() -> None:
    # Canned (not random) seed pair so the test itself stays
    # deterministic. If the generator ignored the seed entirely both
    # calls would return identical tiles and this would catch it.
    a = generate(seed=1, floor_index=0)
    b = generate(seed=2, floor_index=0)
    assert a.tiles != b.tiles


def test_different_floor_indices_produce_different_geometry() -> None:
    a = generate(seed=42, floor_index=0)
    b = generate(seed=42, floor_index=1)
    assert a.tiles != b.tiles


def test_all_walkable_tiles_form_one_connected_component() -> None:
    # The flood-fill reachability check is the post-condition
    # `QUESTIONS.md` task 1.13 commits the generator to enforce. Verify
    # against an independently-implemented flood-fill so a regression
    # in the generator's own check would still surface here.
    floor = generate(seed=12345, floor_index=0)
    component_size = _flood_fill_walkable_count(floor.tiles, width=GRID_WIDTH, height=GRID_HEIGHT)
    assert component_size == _total_walkable(floor.tiles)
    assert component_size > 0


def test_stairs_position_is_inside_grid_bounds() -> None:
    floor = generate(seed=12345, floor_index=0)
    sx, sy = floor.stairs_down
    assert 0 <= sx < GRID_WIDTH
    assert 0 <= sy < GRID_HEIGHT
