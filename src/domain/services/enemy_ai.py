"""Per-enemy AI decision function: LOS-gated wake-up + melee A* chase.

Pure function in the domain layer. Takes the current world state plus an
``awake`` flag and returns ``(action, awake_after_this_turn)``. The
caller (``GameService`` in task 1.16) owns wake-state storage across
turns — keeping it out of the dataclass means task 1.15 doesn't need to
mutate ``Enemy``'s schema.

Design intent (see ``QUESTIONS.md`` task 1.15):

* **LOS-gated wake**, not blind Manhattan. Predicate is
  ``chebyshev_distance(enemy, player) ≤ WAKE_RADIUS AND has_los(...)``.
  ``WALL`` and ``DOOR`` block LOS (task 1.3 decision); the same predicate
  applies to ranged attacks.
* **Sticky aggro**: once awoken, an enemy stays awoken for the rest of
  the floor. Releasing aggro on LOS-break would oscillate at the LOS
  boundary and forgive sloppy play too aggressively.
* **A\\*** with Manhattan heuristic for melee pathfinding. 4-neighbour
  moves only (matches the orthogonal ``Direction`` enum). Player's tile
  is treated as passable for the search so the final step lands on it
  and resolves to an attack per the ``Action`` contract.

Tie-breaking is deterministic across machines and Python versions:
``heapq`` ordering plus a fixed clockwise ``_DIRECTION_ORDER`` (N, E, S,
W) means the same inputs always produce the same action. This matters
for reproducibility (the planned replay system in the backlog depends on
it).

For v1, ``RANGED`` and ``BOSS`` behaviours fall through to the same
melee logic — they will be specialised in a later task. The dispatch on
``enemy.behaviour`` is the seam.
"""

import heapq
from collections.abc import Callable
from typing import Final

from src.domain.models.action import Action, Direction, Move, Wait
from src.domain.models.enemy import Enemy
from src.domain.models.floor import Floor
from src.domain.models.player import Player
from src.domain.models.tile_type import TileType
from src.domain.services.fov import has_los

WAKE_RADIUS: Final[int] = 8

# Sight blockers per the task 1.3 decision: ``WALL`` and (closed) ``DOOR``.
# The current ``DungeonGenerator`` does not yet emit ``DOOR`` tiles, but
# the predicate is correct for the moment DOORs ship.
_SIGHT_BLOCKERS: Final[frozenset[TileType]] = frozenset({TileType.WALL, TileType.DOOR})

# Movement blockers: the AI cannot open doors in v1 (only the player has
# the ``Open`` action), so closed ``DOOR`` is impassable for enemies.
_MOVEMENT_BLOCKERS: Final[frozenset[TileType]] = frozenset({TileType.WALL, TileType.DOOR})

# Clockwise from north — fixed order for deterministic neighbour
# exploration and first-step direction reconstruction in A*.
_DIRECTION_ORDER: Final[tuple[tuple[Direction, int, int], ...]] = (
    (Direction.NORTH, 0, -1),
    (Direction.EAST, 1, 0),
    (Direction.SOUTH, 0, 1),
    (Direction.WEST, -1, 0),
)

_UNREACHABLE: Final[int] = 10**12


def decide_action(
    enemy: Enemy,
    player: Player,
    floor: Floor,
    *,
    awake: bool = False,
) -> tuple[Action, bool]:
    """Return ``(action, awake_after)`` for one enemy's turn.

    If ``awake`` is ``False``, evaluate the wake predicate
    (``chebyshev_distance ≤ WAKE_RADIUS`` AND symmetric LOS). Failing it
    yields ``(Wait(), False)`` — the enemy idles and the caller carries
    forward ``awake=False`` for next turn. Passing it wakes the enemy and
    the same turn it acts on its melee logic.

    Once ``awake`` is ``True``, the predicate is skipped: sticky aggro
    until the caller resets the flag (per-floor by convention).

    Melee logic:

    * If A* finds a 4-neighbour path to the player, the action is
      ``Move`` in the first-step direction; moving into the player's
      tile resolves to an attack via the ``Action`` contract.
    * If no path exists (player walled off, or enemy is on the player's
      tile — defensively handled though impossible by game rules) the
      result is ``Wait()``.
    """
    if not awake:
        if not _should_wake(enemy, player, floor):
            return Wait(), False
        awake = True

    direction = _next_step_direction(enemy.position, player.position, floor)
    if direction is None:
        return Wait(), awake
    return Move(direction=direction), awake


def _should_wake(enemy: Enemy, player: Player, floor: Floor) -> bool:
    ex, ey = enemy.position
    px, py = player.position
    chebyshev = max(abs(ex - px), abs(ey - py))
    if chebyshev > WAKE_RADIUS:
        return False
    height = len(floor.tiles)
    width = len(floor.tiles[0]) if height > 0 else 0
    return has_los(
        enemy.position,
        player.position,
        blocks_sight=_make_sight_blocker(floor),
        width=width,
        height=height,
        max_radius=WAKE_RADIUS,
    )


def _make_sight_blocker(floor: Floor) -> Callable[[int, int], bool]:
    tiles = floor.tiles

    def blocks(x: int, y: int) -> bool:
        return tiles[y][x] in _SIGHT_BLOCKERS

    return blocks


def _next_step_direction(
    start: tuple[int, int],
    goal: tuple[int, int],
    floor: Floor,
) -> Direction | None:
    """A* on the floor grid; return the ``Direction`` of the first step.

    Returns ``None`` if ``start == goal`` or no path exists. The
    destination tile (``goal``) is treated as passable for the search so
    the move-into-player step is allowed (it resolves to an attack at
    apply-time); every other tile honours ``_MOVEMENT_BLOCKERS``.

    Determinism: heap entries are ``(f_score, push_order, position)``.
    ``push_order`` is monotonically increasing, so ``heappop`` is FIFO
    within an f-tie; neighbour exploration follows ``_DIRECTION_ORDER``.
    Together these make the same input always yield the same first step.
    """
    if start == goal:
        return None

    height = len(floor.tiles)
    width = len(floor.tiles[0]) if height > 0 else 0
    tiles = floor.tiles

    def passable(x: int, y: int) -> bool:
        if (x, y) == goal:
            return True
        if not (0 <= x < width and 0 <= y < height):
            return False
        return tiles[y][x] not in _MOVEMENT_BLOCKERS

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start: 0}
    counter = 0
    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (_manhattan(start, goal), counter, start))

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            return _first_step_direction(came_from, start, goal)
        cx, cy = current
        for _direction, dx, dy in _DIRECTION_ORDER:
            nx, ny = cx + dx, cy + dy
            if not passable(nx, ny):
                continue
            tentative_g = g_score[current] + 1
            neighbour = (nx, ny)
            if tentative_g < g_score.get(neighbour, _UNREACHABLE):
                g_score[neighbour] = tentative_g
                came_from[neighbour] = current
                f = tentative_g + _manhattan(neighbour, goal)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbour))

    return None


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _first_step_direction(
    came_from: dict[tuple[int, int], tuple[int, int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> Direction:
    """Trace ``came_from`` back from ``goal`` to the tile adjacent to
    ``start``; return the ``Direction`` of that hop.

    Precondition: ``start != goal`` and a path exists from start to goal
    (the caller checks both). A* uses 4-neighbour moves exclusively, so
    the first step is always a cardinal direction.
    """
    cursor = goal
    while came_from[cursor] != start:
        cursor = came_from[cursor]
    sx, sy = start
    cx, cy = cursor
    dx, dy = cx - sx, cy - sy
    for direction, ox, oy in _DIRECTION_ORDER:
        if (ox, oy) == (dx, dy):
            return direction
    raise AssertionError(f"A* produced non-cardinal first step: ({dx}, {dy})")
