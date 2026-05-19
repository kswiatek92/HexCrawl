"""Tests for ``src.domain.services.enemy_ai.decide_action``.

Coverage targets the load-bearing behaviours called out in the task 1.15
quiz (``QUIZZES.md``) and the design decisions in ``QUESTIONS.md`` task
1.15: pure-function shape, Manhattan-distance pathfinding, LOS-gated
wake, sticky aggro, deterministic tie-breaking, and the no-path branch.
"""

from uuid import uuid4

import pytest

from src.domain.models import (
    BehaviourType,
    Direction,
    Enemy,
    Floor,
    Move,
    Player,
    TileType,
    Wait,
)
from src.domain.services.enemy_ai import WAKE_RADIUS, decide_action


def _floor_from_grid(rows: list[str]) -> Floor:
    """Build a ``Floor`` whose tile grid mirrors ``rows``.

    ``'#'`` → ``WALL``, ``'.'`` → ``FLOOR``, ``'>'`` → ``STAIRS``,
    ``'+'`` → ``DOOR``. The grid is row-major (``tiles[y][x]``), matching
    the ``Floor`` coordinate convention.
    """
    mapping = {
        "#": TileType.WALL,
        ".": TileType.FLOOR,
        ">": TileType.STAIRS,
        "+": TileType.DOOR,
    }
    height = len(rows)
    width = len(rows[0]) if height > 0 else 0
    tiles: list[list[TileType]] = [
        [mapping[rows[y][x]] for x in range(width)] for y in range(height)
    ]
    # Stairs position isn't load-bearing for AI tests; default off-grid
    # if no '>' is present so callers don't need to specify one.
    stairs: tuple[int, int] = (0, 0)
    for y in range(height):
        for x in range(width):
            if tiles[y][x] is TileType.STAIRS:
                stairs = (x, y)
    return Floor(
        floor_id=uuid4(),
        tiles=tiles,
        enemies=[],
        items={},
        stairs_down=stairs,
    )


def _enemy(position: tuple[int, int], behaviour: BehaviourType = BehaviourType.MELEE) -> Enemy:
    return Enemy(
        enemy_id=uuid4(),
        name="Goblin",
        position=position,
        behaviour=behaviour,
        hp=5,
        max_hp=5,
        attack=1,
        defense=0,
    )


def _player(position: tuple[int, int]) -> Player:
    return Player(user_id=uuid4(), name="Hero", position=position)


# --- Wake predicate --------------------------------------------------------


def test_asleep_enemy_out_of_chebyshev_radius_stays_asleep() -> None:
    # Empty 20-wide room; enemy at (0,0), player at (WAKE_RADIUS+1, 0).
    floor = _floor_from_grid(["." * 20] * 3)
    enemy = _enemy((0, 0))
    player = _player((WAKE_RADIUS + 1, 0))

    action, awake_after = decide_action(enemy, player, floor, awake=False)

    assert action == Wait()
    assert awake_after is False


def test_asleep_enemy_in_range_but_blocked_by_wall_stays_asleep() -> None:
    # Wall column at x=3 between enemy and player; both within radius.
    floor = _floor_from_grid(
        [
            "...#...",
            "...#...",
            "...#...",
        ]
    )
    enemy = _enemy((1, 1))
    player = _player((5, 1))

    action, awake_after = decide_action(enemy, player, floor, awake=False)

    assert action == Wait()
    assert awake_after is False


def test_asleep_enemy_in_range_with_los_wakes_and_acts_same_turn() -> None:
    floor = _floor_from_grid(["." * 10] * 3)
    enemy = _enemy((0, 1))
    player = _player((4, 1))

    action, awake_after = decide_action(enemy, player, floor, awake=False)

    # Wakes (awake_after=True) and immediately steps toward the player.
    assert awake_after is True
    assert action == Move(direction=Direction.EAST)


def test_asleep_enemy_exactly_at_chebyshev_radius_can_still_wake() -> None:
    # Place the player at the very edge of the wake range, clear LOS.
    floor = _floor_from_grid(["." * (WAKE_RADIUS + 2)] * 3)
    enemy = _enemy((0, 1))
    player = _player((WAKE_RADIUS, 1))

    action, awake_after = decide_action(enemy, player, floor, awake=False)

    assert awake_after is True
    assert isinstance(action, Move)


# --- Sticky aggro ----------------------------------------------------------


def test_awake_enemy_chases_even_when_wall_now_blocks_los() -> None:
    # Awake=True bypasses the wake predicate. The wall blocks LOS but A*
    # still finds a path around — the enemy chases regardless.
    floor = _floor_from_grid(
        [
            ".........",
            "....#....",
            ".........",
        ]
    )
    enemy = _enemy((1, 1))
    player = _player((7, 1))

    action, awake_after = decide_action(enemy, player, floor, awake=True)

    assert awake_after is True
    assert isinstance(action, Move)


def test_awake_enemy_out_of_range_still_chases() -> None:
    # Far apart, no LOS even checked when awake=True.
    rows = ["." * 30] * 3
    floor = _floor_from_grid(rows)
    enemy = _enemy((0, 1))
    player = _player((20, 1))

    action, awake_after = decide_action(enemy, player, floor, awake=True)

    assert awake_after is True
    assert action == Move(direction=Direction.EAST)


# --- Pathfinding: melee chase + attack -------------------------------------


def test_adjacent_player_yields_move_into_player_tile() -> None:
    # Player directly north of enemy; Move(NORTH) into player tile
    # resolves to attack via the Action contract (1.9).
    floor = _floor_from_grid(["...", "...", "..."])
    enemy = _enemy((1, 2))
    player = _player((1, 1))

    action, _ = decide_action(enemy, player, floor, awake=True)

    assert action == Move(direction=Direction.NORTH)


def test_a_star_routes_around_a_wall() -> None:
    # Vertical wall segment between enemy and player; direct east path
    # blocked, must detour north or south. Either is a valid first step;
    # we accept both — what matters is that it is not Wait and not WEST.
    floor = _floor_from_grid(
        [
            ".........",
            "....#....",
            "...#####.",
            "....#....",
            ".........",
        ]
    )
    enemy = _enemy((2, 2))
    player = _player((6, 2))

    action, awake_after = decide_action(enemy, player, floor, awake=True)

    assert awake_after is True
    assert isinstance(action, Move)
    assert action.direction in (Direction.NORTH, Direction.SOUTH)


def test_no_path_yields_wait_but_keeps_awake() -> None:
    # Player fully walled off; A* finds no path.
    floor = _floor_from_grid(
        [
            "#######",
            "#.....#",
            "#.###.#",
            "#.#.#.#",  # player inside the inner box
            "#.###.#",
            "#.....#",
            "#######",
        ]
    )
    enemy = _enemy((1, 1))
    player = _player((3, 3))

    action, awake_after = decide_action(enemy, player, floor, awake=True)

    assert action == Wait()
    # Awake flag should be preserved across the no-path branch — losing
    # aggro because of a temporary topological obstacle would be wrong.
    assert awake_after is True


def test_enemy_at_player_position_yields_wait() -> None:
    # Should never happen by game rules, but the defensive branch must
    # not crash or step in a random direction.
    floor = _floor_from_grid(["..."])
    enemy = _enemy((1, 0))
    player = _player((1, 0))

    action, awake_after = decide_action(enemy, player, floor, awake=True)

    assert action == Wait()
    assert awake_after is True


# --- Determinism / tie-breaking --------------------------------------------


def test_identical_inputs_yield_identical_outputs_across_repeated_calls() -> None:
    # 10 repeats; if anything in the search depends on dict iteration or
    # set hashing without a stable tie-break, this catches it.
    floor = _floor_from_grid(
        [
            "..........",
            "..........",
            "....#.....",
            "..........",
            "..........",
        ]
    )
    enemy = _enemy((1, 2))
    player = _player((8, 2))

    first = decide_action(enemy, player, floor, awake=True)
    for _ in range(9):
        assert decide_action(enemy, player, floor, awake=True) == first


def test_tie_break_prefers_north_over_east_over_south_over_west() -> None:
    # Player at (1, 0) means both NORTH and "no other equally short
    # step" — only one minimum step. Construct a true tie: player at
    # (2, 2) and enemy at (1, 1) — Manhattan-equal first steps are
    # NORTH→(1,0) (then EAST,EAST,SOUTH,SOUTH) vs EAST→(2,1)
    # (then SOUTH,SOUTH) — actually the EAST first is shorter overall.
    # Use a symmetric setup: enemy (0,0), player (2,2) on open ground,
    # path length 4, first step can be EAST or SOUTH. Order says EAST.
    floor = _floor_from_grid(
        [
            "....",
            "....",
            "....",
            "....",
        ]
    )
    enemy = _enemy((0, 0))
    player = _player((2, 2))

    action, _ = decide_action(enemy, player, floor, awake=True)

    # _DIRECTION_ORDER is (N, E, S, W); with equal-cost first steps
    # NORTH leaves the grid, so the deterministic tie-break selects EAST
    # (the first in-grid option).
    assert action == Move(direction=Direction.EAST)


# --- Pure-function shape ---------------------------------------------------


def test_decide_action_does_not_mutate_inputs() -> None:
    floor = _floor_from_grid(["....."] * 5)
    enemy = _enemy((0, 2))
    player = _player((4, 2))
    snapshot_enemy = (enemy.position, enemy.hp)
    snapshot_player = (player.position, player.hp)
    snapshot_tiles = [row.copy() for row in floor.tiles]

    decide_action(enemy, player, floor, awake=False)

    assert (enemy.position, enemy.hp) == snapshot_enemy
    assert (player.position, player.hp) == snapshot_player
    assert floor.tiles == snapshot_tiles


@pytest.mark.parametrize(
    "behaviour", [BehaviourType.MELEE, BehaviourType.RANGED, BehaviourType.BOSS]
)
def test_v1_falls_through_to_melee_logic_for_every_behaviour(
    behaviour: BehaviourType,
) -> None:
    # RANGED and BOSS share the melee implementation for v1 — verify the
    # function does not crash and produces a Move action. A future task
    # will specialise these branches and this test will be updated.
    floor = _floor_from_grid(["." * 6] * 3)
    enemy = _enemy((0, 1), behaviour=behaviour)
    player = _player((4, 1))

    action, awake_after = decide_action(enemy, player, floor, awake=True)

    assert awake_after is True
    assert isinstance(action, Move)
