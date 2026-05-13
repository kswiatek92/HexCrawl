"""BSP-based ``DungeonGenerator`` — a function whose *geometry* output
(``tiles`` and ``stairs_down``) is a pure deterministic function of
``(seed, floor_index)`` plus the tunable knobs.

The returned ``Floor`` also carries a ``floor_id``, which is a row
identifier rather than geometry. When the caller omits ``floor_id`` the
generator mints a fresh ``uuid4()`` for ergonomic test use; that one
field is intentionally non-deterministic. Geometry never depends on it.

The generator is the first occupant of ``src/domain/services/``. It is the
counterpart, on the geometry side, of ``compute_score_value`` in
``src/domain/models/score.py``: a module-level pure function with module-level
constants exposed as keyword-only defaults so playtesting and tests can override
without touching the algorithm.

Design intent (locked by ``QUESTIONS.md`` Phase 1 → "DungeonGenerator (task
1.13)"):

* **Pure geometry only.** The returned ``Floor`` has tiles and a
  ``stairs_down`` position. ``enemies`` is ``[]`` and ``items`` is ``{}`` —
  populating them is a separate downstream concern, so the generator's
  contract stays narrow ("given a seed and floor index, produce a
  deterministic layout").
* **Seeded determinism.** Every call constructs a fresh
  ``random.Random(f"{seed}|{floor_index}|{attempt}")``. The string form
  is used because ``random.Random``'s tuple-seed path was removed in
  Python 3.11; string seeds are stably hashed via SHA-512 internally and
  remain deterministic across CPython versions. The global ``random``
  module is never touched. This is what makes the planned replay system
  (Backlog in ``BOARD.md``) feasible: a finished run's parent seed plus its
  action log fully reproduces the run.
* **Tunable knobs, not baked-in constants.** ``MIN_ROOM_SIZE``,
  ``MAX_BSP_DEPTH``, and ``MAX_REGEN_ATTEMPTS`` are module-level *defaults*;
  ``generate`` accepts overrides as keyword-only arguments.
* **Reachability is enforced, not trusted.** After laying out rooms and
  corridors, the generator runs a flood-fill from any walkable tile and
  requires *all* walkable tiles to form a single connected component. If
  the check fails, we re-roll with a bumped ``attempt`` counter so the
  new RNG state is unrelated to the failing one. After
  ``max_regen_attempts`` consecutive failures we raise ``RuntimeError`` —
  this is statistically near-impossible at default parameters but beats
  silently spinning forever on pathological inputs.

Coordinate convention follows ``Floor`` (see ``src/domain/models/floor.py``):
the tile grid is row-major as ``tiles[y][x]``, while every domain-facing
``(x, y)`` tuple — including ``stairs_down`` — uses Cartesian order. Internal
BSP nodes and rooms are stored as ``(x, y, w, h)`` rectangles, and the inversion
is applied only when writing to or reading from the tile grid.
"""

import random
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

from src.domain.models.floor import GRID_HEIGHT, GRID_WIDTH, Floor
from src.domain.models.tile_type import TileType

MIN_ROOM_SIZE: Final[int] = 4
MAX_BSP_DEPTH: Final[int] = 5
MAX_REGEN_ATTEMPTS: Final[int] = 8

_DEEP_SPLIT_PROBABILITY: Final[float] = 0.6
_LONG_AXIS_BIAS: Final[float] = 0.8
_WALKABLE: Final[frozenset[TileType]] = frozenset({TileType.FLOOR, TileType.STAIRS, TileType.DOOR})
_NEIGHBOUR_OFFSETS: Final[tuple[tuple[int, int], ...]] = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
)


@dataclass(frozen=True)
class _BspNode:
    """Internal BSP-tree node.

    ``(x, y, w, h)`` is the node's bounding rectangle in floor coordinates.
    A node is a *leaf* when ``room`` is set (and ``left``/``right`` are
    ``None``); it is *internal* when ``left`` and ``right`` are set (and
    ``room`` is ``None``). The two states are mutually exclusive — the
    tree-building pass enforces it.

    Frozen so the tree, once built, cannot be accidentally mutated by the
    corridor / stairs passes; only the ``tiles`` grid carries mutation
    state during generation.
    """

    x: int
    y: int
    w: int
    h: int
    left: "_BspNode | None" = None
    right: "_BspNode | None" = None
    room: tuple[int, int, int, int] | None = None


def generate(
    seed: int,
    floor_index: int,
    floor_id: UUID | None = None,
    *,
    width: int = GRID_WIDTH,
    height: int = GRID_HEIGHT,
    min_room_size: int = MIN_ROOM_SIZE,
    max_depth: int = MAX_BSP_DEPTH,
    max_regen_attempts: int = MAX_REGEN_ATTEMPTS,
) -> Floor:
    """Generate a ``Floor`` of pure BSP geometry.

    The function is deterministic in its geometry output for a given
    ``(seed, floor_index, width, height, min_room_size, max_depth)`` tuple
    — two calls with the same arguments return floors whose ``tiles`` and
    ``stairs_down`` are equal.

    ``floor_id`` is a row identifier, not a geometry identifier. It is the
    caller's responsibility to supply one (so two players sharing a daily
    seed don't collide on the leaderboard); when ``None`` we mint a fresh
    ``uuid4()`` for ergonomics in tests. Geometry never depends on this
    value.

    Raises ``RuntimeError`` if reachability cannot be satisfied within
    ``max_regen_attempts`` re-rolls. With default parameters on the
    documented 80×50 grid this should not occur in practice.
    """
    for attempt in range(max_regen_attempts):
        rng = random.Random(f"{seed}|{floor_index}|{attempt}")
        root = _build_tree(
            _BspNode(x=0, y=0, w=width, h=height),
            rng,
            depth=0,
            max_depth=max_depth,
            min_room_size=min_room_size,
        )
        tiles: list[list[TileType]] = [[TileType.WALL] * width for _ in range(height)]
        leaves = _collect_leaves(root)
        for leaf in leaves:
            _carve_room(tiles, leaf)
        _carve_corridors(tiles, root, rng)
        stairs_x, stairs_y = _place_stairs(tiles, leaves[-1])
        if _walkable_connected(tiles, width, height):
            return Floor(
                floor_id=floor_id if floor_id is not None else uuid4(),
                tiles=tiles,
                enemies=[],
                items={},
                stairs_down=(stairs_x, stairs_y),
            )
    raise RuntimeError(
        "DungeonGenerator: failed to produce a connected floor after "
        f"{max_regen_attempts} attempts "
        f"(seed={seed}, floor_index={floor_index}, "
        f"width={width}, height={height}, "
        f"min_room_size={min_room_size}, max_depth={max_depth})"
    )


def _build_tree(
    node: _BspNode,
    rng: random.Random,
    *,
    depth: int,
    max_depth: int,
    min_room_size: int,
) -> _BspNode:
    """Recursively partition ``node``; return a fully-built BSP subtree.

    Internal nodes have ``left``/``right``; leaves have ``room``.
    """
    split = _try_split(node, rng, depth=depth, max_depth=max_depth, min_room_size=min_room_size)
    if split is None:
        room = _choose_room(node, rng, min_room_size=min_room_size)
        return _BspNode(x=node.x, y=node.y, w=node.w, h=node.h, room=room)
    left_bounds, right_bounds = split
    left = _build_tree(
        left_bounds, rng, depth=depth + 1, max_depth=max_depth, min_room_size=min_room_size
    )
    right = _build_tree(
        right_bounds, rng, depth=depth + 1, max_depth=max_depth, min_room_size=min_room_size
    )
    return _BspNode(x=node.x, y=node.y, w=node.w, h=node.h, left=left, right=right)


def _try_split(
    node: _BspNode,
    rng: random.Random,
    *,
    depth: int,
    max_depth: int,
    min_room_size: int,
) -> tuple[_BspNode, _BspNode] | None:
    """Decide whether and how to split ``node``.

    Returns the two child node bounds, or ``None`` if the node should
    remain a leaf — either because we've hit ``max_depth``, because no
    axis can host two ``min_room_size+2`` halves, or because the RNG
    rolled below the split probability.
    """
    if depth >= max_depth:
        return None

    leaf_min = min_room_size + 2
    split_min = 2 * leaf_min
    can_split_v = node.w >= split_min
    can_split_h = node.h >= split_min

    if not (can_split_v or can_split_h):
        return None
    # Force-split at the root: a 25% chance of leaving an 80×50 grid as
    # a single room produces a degenerate floor. Below the root, splitting
    # is probabilistic so depth-5 trees don't always fan out to 32 leaves
    # — the target is roughly 6–10 rooms per floor at default parameters.
    if depth > 0 and rng.random() >= _DEEP_SPLIT_PROBABILITY:
        return None

    if can_split_v and can_split_h:
        # Bias toward splitting the longer axis so rooms don't degenerate
        # into long thin strips.
        if node.w > node.h:
            split_vertically = rng.random() < _LONG_AXIS_BIAS
        elif node.h > node.w:
            split_vertically = rng.random() >= _LONG_AXIS_BIAS
        else:
            split_vertically = rng.random() < 0.5
    else:
        split_vertically = can_split_v

    if split_vertically:
        split_x = rng.randint(leaf_min, node.w - leaf_min)
        left = _BspNode(x=node.x, y=node.y, w=split_x, h=node.h)
        right = _BspNode(x=node.x + split_x, y=node.y, w=node.w - split_x, h=node.h)
        return left, right

    split_y = rng.randint(leaf_min, node.h - leaf_min)
    top = _BspNode(x=node.x, y=node.y, w=node.w, h=split_y)
    bottom = _BspNode(x=node.x, y=node.y + split_y, w=node.w, h=node.h - split_y)
    return top, bottom


def _choose_room(
    node: _BspNode, rng: random.Random, *, min_room_size: int
) -> tuple[int, int, int, int]:
    """Pick a room rectangle inside leaf ``node``, with 1-tile padding.

    Returns ``(rx, ry, rw, rh)``. Requires ``node.w >= min_room_size + 2``
    and ``node.h >= min_room_size + 2``; the ``_try_split`` logic
    guarantees both for any leaf it produces.
    """
    max_rw = node.w - 2
    max_rh = node.h - 2
    rw = rng.randint(min_room_size, max_rw)
    rh = rng.randint(min_room_size, max_rh)
    rx = rng.randint(node.x + 1, node.x + node.w - 1 - rw)
    ry = rng.randint(node.y + 1, node.y + node.h - 1 - rh)
    return rx, ry, rw, rh


def _collect_leaves(node: _BspNode) -> list[_BspNode]:
    """Return all leaves of the BSP tree in pre-order.

    Pre-order means the first leaf is in the top-left of the floor and the
    last is in the bottom-right (modulo split-axis choices) — useful for
    placing stairs deterministically in a far corner.
    """
    if node.room is not None:
        return [node]
    assert node.left is not None and node.right is not None
    return _collect_leaves(node.left) + _collect_leaves(node.right)


def _carve_room(tiles: list[list[TileType]], leaf: _BspNode) -> None:
    """Carve the leaf's room into the tile grid (mark FLOOR)."""
    assert leaf.room is not None
    rx, ry, rw, rh = leaf.room
    for y in range(ry, ry + rh):
        row = tiles[y]
        for x in range(rx, rx + rw):
            row[x] = TileType.FLOOR


def _carve_corridors(tiles: list[list[TileType]], node: _BspNode, rng: random.Random) -> None:
    """Post-order walk; carve an L-corridor at each internal node.

    For an internal node we pick a representative point in some room of
    the left subtree and another in the right subtree, then carve an
    L-shape between them. The corridor will pass through whatever it
    crosses (always overwriting to FLOOR), which is safe because rooms
    are already FLOOR and walls between subtrees are exactly what we
    want to break.
    """
    if node.room is not None:
        return
    assert node.left is not None and node.right is not None
    _carve_corridors(tiles, node.left, rng)
    _carve_corridors(tiles, node.right, rng)
    left_point = _representative_point(node.left, rng)
    right_point = _representative_point(node.right, rng)
    _carve_l_corridor(tiles, left_point, right_point, rng)


def _representative_point(node: _BspNode, rng: random.Random) -> tuple[int, int]:
    """Pick a random tile inside some room reachable from ``node``.

    Recurses through internal nodes by random subtree choice. Because
    every leaf carries a room, this always returns a valid floor tile.
    """
    if node.room is not None:
        rx, ry, rw, rh = node.room
        return rng.randint(rx, rx + rw - 1), rng.randint(ry, ry + rh - 1)
    assert node.left is not None and node.right is not None
    return _representative_point(node.left if rng.random() < 0.5 else node.right, rng)


def _carve_l_corridor(
    tiles: list[list[TileType]],
    start: tuple[int, int],
    end: tuple[int, int],
    rng: random.Random,
) -> None:
    """Carve an L-shape from ``start`` to ``end``.

    The corridor is two straight segments meeting at one elbow. We pick
    the elbow randomly: 50% horizontal-first (elbow at ``(end.x, start.y)``)
    or vertical-first (elbow at ``(start.x, end.y)``). Either way, the
    segments together touch both endpoints.
    """
    ax, ay = start
    bx, by = end
    if rng.random() < 0.5:
        _carve_horizontal_segment(tiles, ay, ax, bx)
        _carve_vertical_segment(tiles, bx, ay, by)
    else:
        _carve_vertical_segment(tiles, ax, ay, by)
        _carve_horizontal_segment(tiles, by, ax, bx)


def _carve_horizontal_segment(tiles: list[list[TileType]], y: int, x_a: int, x_b: int) -> None:
    """Set ``tiles[y][x]`` to FLOOR for x between ``x_a`` and ``x_b`` inclusive."""
    row = tiles[y]
    for x in range(min(x_a, x_b), max(x_a, x_b) + 1):
        row[x] = TileType.FLOOR


def _carve_vertical_segment(tiles: list[list[TileType]], x: int, y_a: int, y_b: int) -> None:
    """Set ``tiles[y][x]`` to FLOOR for y between ``y_a`` and ``y_b`` inclusive."""
    for y in range(min(y_a, y_b), max(y_a, y_b) + 1):
        tiles[y][x] = TileType.FLOOR


def _place_stairs(tiles: list[list[TileType]], leaf: _BspNode) -> tuple[int, int]:
    """Place STAIRS at the centre of ``leaf``'s room; return its ``(x, y)``."""
    assert leaf.room is not None
    rx, ry, rw, rh = leaf.room
    sx = rx + rw // 2
    sy = ry + rh // 2
    tiles[sy][sx] = TileType.STAIRS
    return sx, sy


def _walkable_connected(tiles: list[list[TileType]], width: int, height: int) -> bool:
    """Return ``True`` iff every walkable tile is reachable from any other.

    Walkable means ``FLOOR``, ``STAIRS``, or ``DOOR`` (the v1 tile types
    that admit movement). We flood-fill (stack-based DFS) from the first
    walkable tile we find using 4-neighbour adjacency and check that the
    visited count equals the total walkable count. DFS vs BFS doesn't
    affect the result for a connectivity check, and a list-as-stack is
    cheaper than ``collections.deque`` for this grid size.
    """
    start: tuple[int, int] | None = None
    total_walkable = 0
    for y in range(height):
        row = tiles[y]
        for x in range(width):
            if row[x] in _WALKABLE:
                total_walkable += 1
                if start is None:
                    start = (x, y)
    if start is None:
        return total_walkable == 0

    visited: set[tuple[int, int]] = set()
    stack: list[tuple[int, int]] = [start]
    while stack:
        pos = stack.pop()
        if pos in visited:
            continue
        visited.add(pos)
        x, y = pos
        for dx, dy in _NEIGHBOUR_OFFSETS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                if tiles[ny][nx] in _WALKABLE:
                    stack.append((nx, ny))
    return len(visited) == total_walkable
