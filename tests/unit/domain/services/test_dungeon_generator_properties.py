"""Property-based and behaviour tests for ``src.domain.services.dungeon_generator.generate``.

Companion to ``test_dungeon_generator.py`` (the 10 canned-seed smoke tests
shipped with task 1.13). This module covers what the smoke suite deferred to
task 1.14:

* **Hypothesis property tests** that exercise invariants across the input space
  (arbitrary ``seed`` × ``floor_index`` in the 100-floor `Dungeon` range), not
  just hand-picked seeds.
* **Edge cases on tunable knobs** — smallest valid grid, ``max_depth=0``
  forcing a single leaf, custom ``min_room_size`` changing geometry.
* **Re-roll exhaustion error path** — ``max_regen_attempts=0`` short-circuits
  to ``RuntimeError`` with debuggable context.
* **Behavioural contracts** the smoke suite skipped: no side effect on the
  global ``random`` module, ``floor_id`` passes through, ``floor_id`` does not
  bleed into geometry seeding.
* **Statistical sanity** on walkable area across many seeds — loose enough not
  to flake on minor tweaks but tight enough to flag "no rooms at all" or
  "everything is floor" regressions.

Hypothesis settings: ``@settings(max_examples=50, deadline=None)``.
``max_examples=50`` keeps the suite under 1s total at typical BSP generation
speed (~5 ms / call), and ``deadline=None`` defers Hypothesis's 200 ms
per-example deadline because BSP runs on 80×50 grids can spike past it on
slow CI runners — the property tests are correctness checks, not latency
budgets.
"""

import random
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.models import GRID_HEIGHT, GRID_WIDTH, TileType
from src.domain.services import MIN_ROOM_SIZE, generate

_WALKABLE: frozenset[TileType] = frozenset({TileType.FLOOR, TileType.STAIRS, TileType.DOOR})


def _flood_fill_count(tiles: list[list[TileType]], width: int, height: int) -> int:
    """Return the size of the connected component of walkable tiles
    containing the first walkable cell (row-major scan).

    Independent of the generator's internal helper so tests verify
    connectivity by external observation, not by re-running the same code.
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


def _walkable_count(tiles: list[list[TileType]]) -> int:
    return sum(1 for row in tiles for t in row if t in _WALKABLE)


# ----- Property tests (Hypothesis) -----


@given(
    seed=st.integers(min_value=-1_000_000, max_value=1_000_000),
    floor_index=st.integers(min_value=0, max_value=99),
)
@settings(max_examples=50, deadline=None)
def test_all_invariants_hold_for_arbitrary_seed_and_floor_index(
    seed: int, floor_index: int
) -> None:
    floor = generate(seed=seed, floor_index=floor_index)

    # Dimensions
    assert len(floor.tiles) == GRID_HEIGHT
    for row in floor.tiles:
        assert len(row) == GRID_WIDTH

    # Every cell is a valid TileType member
    for row in floor.tiles:
        for tile in row:
            assert tile in TileType

    # Exactly one STAIRS, matching floor.stairs_down
    stairs_positions = [
        (x, y)
        for y, row in enumerate(floor.tiles)
        for x, tile in enumerate(row)
        if tile is TileType.STAIRS
    ]
    assert stairs_positions == [floor.stairs_down]

    # stairs_down inside grid bounds
    sx, sy = floor.stairs_down
    assert 0 <= sx < GRID_WIDTH
    assert 0 <= sy < GRID_HEIGHT

    # Stairs tile is walkable
    assert floor.tiles[sy][sx] in _WALKABLE

    # Empty enemies / items — generator produces pure geometry
    assert floor.enemies == []
    assert floor.items == {}

    # floor_id is a UUID
    assert isinstance(floor.floor_id, UUID)

    # All walkable tiles form one connected component (independent flood-fill)
    component = _flood_fill_count(floor.tiles, GRID_WIDTH, GRID_HEIGHT)
    assert component == _walkable_count(floor.tiles)
    assert component > 0


@given(
    seed=st.integers(min_value=-1_000_000, max_value=1_000_000),
    floor_index=st.integers(min_value=0, max_value=99),
)
@settings(max_examples=50, deadline=None)
def test_determinism_property(seed: int, floor_index: int) -> None:
    # The replay-system property: identical inputs → identical geometry,
    # for arbitrary seed and floor_index in the valid range.
    a = generate(seed=seed, floor_index=floor_index)
    b = generate(seed=seed, floor_index=floor_index)
    assert a.tiles == b.tiles
    assert a.stairs_down == b.stairs_down


# ----- Edge cases on tunable knobs -----


def test_smallest_valid_grid_produces_single_room_floor() -> None:
    # width = height = MIN_ROOM_SIZE + 2 = 6 cannot satisfy split_min=12,
    # so the BSP stays a single leaf and the floor is a single room.
    smallest = MIN_ROOM_SIZE + 2
    floor = generate(seed=0, floor_index=0, width=smallest, height=smallest)

    assert len(floor.tiles) == smallest
    assert all(len(row) == smallest for row in floor.tiles)
    stairs_count = sum(1 for row in floor.tiles for t in row if t is TileType.STAIRS)
    assert stairs_count == 1
    component = _flood_fill_count(floor.tiles, smallest, smallest)
    assert component == _walkable_count(floor.tiles)
    assert component > 0


def test_max_depth_zero_forces_single_leaf() -> None:
    # max_depth=0 short-circuits every split decision; the floor is one room.
    floor = generate(seed=12345, floor_index=0, max_depth=0)

    stairs_count = sum(1 for row in floor.tiles for t in row if t is TileType.STAIRS)
    assert stairs_count == 1
    assert _flood_fill_count(floor.tiles, GRID_WIDTH, GRID_HEIGHT) == _walkable_count(floor.tiles)


def test_custom_min_room_size_changes_geometry() -> None:
    # If min_room_size weren't wired through, both calls would produce
    # identical tiles. They must differ — proof the knob reaches the algorithm.
    default = generate(seed=42, floor_index=0)
    larger = generate(seed=42, floor_index=0, min_room_size=10)
    assert default.tiles != larger.tiles


# ----- Re-roll exhaustion error path -----


def test_max_regen_attempts_zero_raises_runtime_error_with_debug_context() -> None:
    # range(0) yields no iterations, so generate() falls through directly to
    # the RuntimeError. The message must include the inputs so future
    # debugging doesn't require re-instrumenting the function.
    with pytest.raises(RuntimeError) as exc_info:
        generate(seed=12345, floor_index=7, max_regen_attempts=0)
    msg = str(exc_info.value)
    assert "seed=12345" in msg
    assert "floor_index=7" in msg
    assert "0 attempts" in msg


# ----- Behavioural contracts -----


def test_does_not_mutate_global_random_state() -> None:
    # The function must construct its own random.Random() and never touch
    # random.seed() or any global-module function. We assert by snapshotting
    # the global RNG state before and after a generate() call.
    before = random.getstate()
    generate(seed=12345, floor_index=0)
    after = random.getstate()
    assert before == after


def test_custom_floor_id_is_returned_unchanged() -> None:
    given_id = uuid4()
    floor = generate(seed=0, floor_index=0, floor_id=given_id)
    assert floor.floor_id == given_id


def test_default_floor_id_is_a_fresh_uuid4_each_call() -> None:
    # Two calls without an explicit floor_id must return different IDs.
    # If they were equal we'd be looking at accidental memoization, a
    # nil-UUID default, or floor_id derived from (seed, floor_index).
    a = generate(seed=0, floor_index=0)
    b = generate(seed=0, floor_index=0)
    assert a.floor_id != b.floor_id


def test_floor_id_does_not_affect_geometry() -> None:
    # Geometry purity scope: same (seed, floor_index, knobs) must produce
    # identical tiles regardless of the floor_id row identifier. If
    # floor_id leaked into the RNG seed, these tiles would differ.
    a = generate(seed=0, floor_index=0, floor_id=uuid4())
    b = generate(seed=0, floor_index=0, floor_id=uuid4())
    assert a.tiles == b.tiles
    assert a.stairs_down == b.stairs_down
    assert a.floor_id != b.floor_id


# ----- Statistical sanity -----


def test_walkable_area_falls_in_reasonable_band_over_many_seeds() -> None:
    # Catches gross regressions: a single 4×4 room is 16 walkable tiles;
    # the entire 80×50 grid is 4000. Real floors at default knobs land
    # well between these extremes (smoke tests have shown ~1100–1300).
    # The band is intentionally wide so minor algorithm tweaks don't flake.
    for seed in range(50):
        floor = generate(seed=seed, floor_index=0)
        walkable = _walkable_count(floor.tiles)
        assert 200 <= walkable <= 3000, f"seed={seed} walkable={walkable}"
