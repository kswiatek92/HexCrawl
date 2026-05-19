"""Tests for ``src.domain.services.game_service.process_turn``.

Coverage targets the task 1.16 design intent locked in ``QUESTIONS.md``
(mutate in place + return TurnResult, interleaved enemy order, per-turn
seeded RNG, sticky aggro, RNG-variance damage, domain-event narrative)
and the quiz questions in ``QUIZZES.md`` task 1.16 (mutation choice,
order of operations, RNG injection, domain events, no constructor
dependencies).
"""

from uuid import UUID, uuid4

from src.domain.models import (
    Abandon,
    ActionRejected,
    Attack,
    BehaviourType,
    Descend,
    Direction,
    Dungeon,
    Enemy,
    EnemyAttacked,
    EnemyKilled,
    Floor,
    FloorDescended,
    Move,
    Open,
    PickUp,
    Player,
    PlayerAttacked,
    PlayerDamaged,
    PlayerDied,
    PlayerMoved,
    RunAbandoned,
    TileType,
    UseItem,
    Wait,
)
from src.domain.services import process_turn

# --- Test fixture helpers --------------------------------------------------


def _floor_from_grid(rows: list[str], floor_id: UUID | None = None) -> Floor:
    """Build a ``Floor`` from a string grid (matches the AI tests' helper).

    ``.`` → FLOOR, ``#`` → WALL, ``>`` → STAIRS, ``+`` → DOOR.
    Stairs are auto-detected; defaults to (0, 0) when absent. Enemies
    and items default to empty; tests add them explicitly.
    """
    mapping = {
        ".": TileType.FLOOR,
        "#": TileType.WALL,
        ">": TileType.STAIRS,
        "+": TileType.DOOR,
    }
    height = len(rows)
    width = len(rows[0]) if height > 0 else 0
    tiles: list[list[TileType]] = [
        [mapping[rows[y][x]] for x in range(width)] for y in range(height)
    ]
    stairs: tuple[int, int] = (0, 0)
    for y in range(height):
        for x in range(width):
            if tiles[y][x] is TileType.STAIRS:
                stairs = (x, y)
    return Floor(
        floor_id=floor_id or uuid4(),
        tiles=tiles,
        enemies=[],
        items={},
        stairs_down=stairs,
    )


def _dungeon(floors: list[Floor], *, seed: int = 12345, current_floor_index: int = 0) -> Dungeon:
    return Dungeon(
        dungeon_id=uuid4(),
        seed=seed,
        floors=floors,
        current_floor_index=current_floor_index,
    )


def _player(position: tuple[int, int], *, hp: int = 20, attack: int = 3) -> Player:
    return Player(user_id=uuid4(), name="Hero", position=position, hp=hp, attack=attack)


def _enemy(
    position: tuple[int, int],
    *,
    hp: int = 5,
    attack: int = 1,
    defense: int = 0,
    awake: bool = False,
    enemy_id: UUID | None = None,
) -> Enemy:
    return Enemy(
        enemy_id=enemy_id or uuid4(),
        name="Goblin",
        position=position,
        behaviour=BehaviourType.MELEE,
        hp=hp,
        max_hp=hp,
        attack=attack,
        defense=defense,
        awake=awake,
    )


def _stable_id(suffix: int) -> UUID:
    # Stable across runs so enemy-id-sort-order tests stay deterministic.
    return UUID(f"00000000-0000-0000-0000-{suffix:012d}")


# --- Move ------------------------------------------------------------------


def test_move_into_floor_updates_position_and_emits_player_moved() -> None:
    floor = _floor_from_grid(["...", "...", "..."])
    dungeon = _dungeon([floor])
    player = _player((1, 1))

    result = process_turn(dungeon, player, Move(direction=Direction.EAST))

    assert player.position == (2, 1)
    assert PlayerMoved(from_position=(1, 1), to_position=(2, 1)) in result.events
    assert result.game_over is False


def test_move_into_wall_emits_action_rejected_and_does_not_move() -> None:
    floor = _floor_from_grid(["###", ".#.", "..."])
    dungeon = _dungeon([floor])
    player = _player((0, 1))

    result = process_turn(dungeon, player, Move(direction=Direction.NORTH))

    assert player.position == (0, 1)  # unchanged
    assert ActionRejected(reason="blocked_by_wall") in result.events


def test_move_out_of_bounds_emits_action_rejected() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    result = process_turn(dungeon, player, Move(direction=Direction.WEST))

    assert player.position == (0, 0)
    assert ActionRejected(reason="out_of_bounds") in result.events


def test_move_into_door_blocks_until_open_is_implemented() -> None:
    # DOOR is sight + movement blocker until task that ships
    # "open door" tile state — process_turn must reject the move
    # rather than letting the player walk through a closed door.
    floor = _floor_from_grid(["+.", ".."])
    dungeon = _dungeon([floor])
    player = _player((1, 0))

    result = process_turn(dungeon, player, Move(direction=Direction.WEST))

    assert player.position == (1, 0)
    assert ActionRejected(reason="blocked_by_door") in result.events


# --- Move-into-enemy → attack ----------------------------------------------


def test_move_into_enemy_resolves_as_attack_not_movement() -> None:
    floor = _floor_from_grid(["..."])
    enemy = _enemy((1, 0), hp=10)
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0), attack=3)

    result = process_turn(dungeon, player, Move(direction=Direction.EAST))

    # Player stays put; the Move resolved to an attack.
    assert player.position == (0, 0)
    assert any(isinstance(e, PlayerAttacked) for e in result.events)
    assert not any(isinstance(e, PlayerMoved) for e in result.events)
    # Enemy took some damage (variance ± 1 around attack=3, def=0,
    # floored at 1 → range [1, 4]).
    assert enemy.hp < 10


def test_player_attack_killing_an_enemy_emits_enemy_killed_and_removes_it() -> None:
    floor = _floor_from_grid([".."])
    enemy_id = _stable_id(1)
    enemy = _enemy((1, 0), hp=1, enemy_id=enemy_id)
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0), attack=10)

    result = process_turn(dungeon, player, Move(direction=Direction.EAST))

    assert enemy not in floor.enemies
    assert EnemyKilled(enemy_id=enemy_id) in result.events
    attack_events = [e for e in result.events if isinstance(e, PlayerAttacked)]
    assert len(attack_events) == 1 and attack_events[0].killed is True


# --- Explicit Attack -------------------------------------------------------


def test_explicit_attack_on_empty_tile_is_rejected() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    player = _player((1, 0))

    result = process_turn(dungeon, player, Attack(direction=Direction.EAST))

    assert ActionRejected(reason="nothing_to_attack") in result.events


def test_explicit_attack_on_enemy_deals_damage_without_moving() -> None:
    floor = _floor_from_grid(["..."])
    enemy = _enemy((1, 0), hp=10)
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0), attack=3)

    result = process_turn(dungeon, player, Attack(direction=Direction.EAST))

    assert player.position == (0, 0)
    assert enemy.hp < 10
    assert any(isinstance(e, PlayerAttacked) for e in result.events)


# --- Wait ------------------------------------------------------------------


def test_wait_leaves_player_state_unchanged_but_still_runs_enemy_ai() -> None:
    # Enemy adjacent and awake: Wait still lets the enemy attack.
    floor = _floor_from_grid(["..."])
    enemy = _enemy((1, 0), attack=2, awake=True)
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    starting_hp = player.hp
    result = process_turn(dungeon, player, Wait())

    assert player.position == (0, 0)
    assert player.hp < starting_hp
    assert any(isinstance(e, EnemyAttacked) for e in result.events)


# --- Descend ---------------------------------------------------------------


def test_descend_off_stairs_is_rejected() -> None:
    floor = _floor_from_grid(["..>"])
    dungeon = _dungeon([floor, _floor_from_grid(["..."])])
    player = _player((0, 0))

    result = process_turn(dungeon, player, Descend())

    assert dungeon.current_floor_index == 0
    assert ActionRejected(reason="not_on_stairs") in result.events


def test_descend_without_next_floor_is_rejected() -> None:
    floor = _floor_from_grid(["..>"])
    dungeon = _dungeon([floor])  # only one floor available
    player = _player((2, 0))

    result = process_turn(dungeon, player, Descend())

    assert dungeon.current_floor_index == 0
    assert ActionRejected(reason="no_next_floor") in result.events


def test_descend_on_stairs_advances_index_and_places_player() -> None:
    floor_a = _floor_from_grid(["..>"])
    floor_b = _floor_from_grid([".....", "....."])
    dungeon = _dungeon([floor_a, floor_b])
    player = _player((2, 0))

    result = process_turn(dungeon, player, Descend())

    assert dungeon.current_floor_index == 1
    # Player landed somewhere walkable on the new floor.
    px, py = player.position
    assert floor_b.tiles[py][px] in (TileType.FLOOR, TileType.STAIRS)
    assert FloorDescended(new_floor_index=1) in result.events


# --- Abandon ---------------------------------------------------------------


def test_abandon_short_circuits_the_turn_and_sets_game_over() -> None:
    # Even with an enemy that would normally attack this turn, abandon
    # must terminate before the enemy AI loop runs — letting an enemy
    # land a hit after the player has abandoned is the wrong narrative.
    floor = _floor_from_grid(["..."])
    enemy = _enemy((1, 0), attack=2, awake=True)
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0))
    starting_hp = player.hp

    result = process_turn(dungeon, player, Abandon())

    assert result.game_over is True
    assert RunAbandoned() in result.events
    assert player.hp == starting_hp
    assert not any(isinstance(e, EnemyAttacked) for e in result.events)


# --- Not-implemented action variants ---------------------------------------


def test_pickup_is_rejected_with_not_implemented_v1() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    result = process_turn(dungeon, player, PickUp())

    assert ActionRejected(reason="not_implemented_v1") in result.events


def test_useitem_is_rejected_with_not_implemented_v1() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    result = process_turn(dungeon, player, UseItem(item_id=uuid4()))

    assert ActionRejected(reason="not_implemented_v1") in result.events


def test_open_is_rejected_with_not_implemented_v1() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    result = process_turn(dungeon, player, Open(direction=Direction.EAST))

    assert ActionRejected(reason="not_implemented_v1") in result.events


# --- Enemy AI loop ---------------------------------------------------------


def test_distant_asleep_enemy_does_nothing_after_player_wait() -> None:
    floor = _floor_from_grid(["." * 30])
    enemy = _enemy((25, 0))  # far out of wake radius
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    result = process_turn(dungeon, player, Wait())

    assert enemy.position == (25, 0)
    assert enemy.awake is False
    assert not any(isinstance(e, EnemyAttacked) for e in result.events)


def test_in_range_enemy_with_los_wakes_and_chases() -> None:
    floor = _floor_from_grid(["." * 10])
    enemy = _enemy((4, 0))
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    starting = enemy.position
    process_turn(dungeon, player, Wait())

    # The enemy moved closer (Manhattan distance to player dropped).
    assert enemy.position != starting
    assert enemy.awake is True


def test_enemy_killed_by_player_does_not_get_an_ai_turn() -> None:
    # Order by enemy_id matters: place the killable enemy first in sort
    # order, the unrelated enemy second, and verify the second still acts.
    floor = _floor_from_grid(["...."])
    killable = _enemy((1, 0), hp=1, enemy_id=_stable_id(1))
    bystander = _enemy((3, 0), attack=2, awake=True, enemy_id=_stable_id(2))
    floor.enemies.extend([killable, bystander])
    dungeon = _dungeon([floor])
    player = _player((0, 0), attack=10)

    result = process_turn(dungeon, player, Move(direction=Direction.EAST))

    # killable is dead, removed; bystander still moved/attacked.
    assert killable not in floor.enemies
    assert bystander in floor.enemies
    assert EnemyKilled(enemy_id=killable.enemy_id) in result.events
    # Bystander chased: position changed or it dealt damage.
    assert bystander.position != (3, 0) or any(isinstance(e, EnemyAttacked) for e in result.events)


def test_enemy_killing_blow_to_player_emits_player_died_and_stops_loop() -> None:
    # Player at 1 HP; first enemy hits hard; the second enemy should
    # never get a turn because game_over short-circuits.
    floor = _floor_from_grid(["....."])
    e_first = _enemy((1, 0), attack=20, defense=0, awake=True, enemy_id=_stable_id(1))
    e_second = _enemy((4, 0), attack=20, defense=0, awake=True, enemy_id=_stable_id(2))
    floor.enemies.extend([e_first, e_second])
    dungeon = _dungeon([floor])
    player = _player((0, 0), hp=1)

    result = process_turn(dungeon, player, Wait())

    assert player.hp <= 0
    assert result.game_over is True
    assert PlayerDied() in result.events
    # Exactly one EnemyAttacked — the second enemy never got to swing.
    attack_events = [e for e in result.events if isinstance(e, EnemyAttacked)]
    assert len(attack_events) == 1


def test_enemy_attack_increments_player_damage_taken() -> None:
    # The cumulative counter feeds ScoreService.compute later; it must
    # match the sum of PlayerDamaged amounts emitted this turn.
    floor = _floor_from_grid(["..."])
    enemy = _enemy((1, 0), attack=2, awake=True)
    floor.enemies.append(enemy)
    dungeon = _dungeon([floor])
    player = _player((0, 0))

    result = process_turn(dungeon, player, Wait())

    damage_events = [e for e in result.events if isinstance(e, PlayerDamaged)]
    assert player.damage_taken == sum(e.amount for e in damage_events)
    assert player.damage_taken > 0


def test_enemies_act_in_enemy_id_sort_order_not_list_order() -> None:
    # The list order is descending id; emitted events must be in
    # ascending id order, so insertion-order in the list does not
    # influence the per-turn narrative.
    floor = _floor_from_grid([".....", ".....", "....."])
    later_id = _stable_id(2)
    earlier_id = _stable_id(1)
    e_later = _enemy((3, 0), attack=2, awake=True, enemy_id=later_id)
    e_earlier = _enemy((3, 2), attack=2, awake=True, enemy_id=earlier_id)
    # Append in id-DESCENDING order to make the test meaningful.
    floor.enemies.extend([e_later, e_earlier])
    dungeon = _dungeon([floor])
    player = _player((0, 1))

    result = process_turn(dungeon, player, Wait())

    # The first EnemyAttacked / step from this turn must come from the
    # earlier id — that is the contract.
    enemy_event_ids = [e.enemy_id for e in result.events if isinstance(e, EnemyAttacked)]
    if enemy_event_ids:
        assert enemy_event_ids[0] == earlier_id


# --- RNG / determinism -----------------------------------------------------


def test_same_seed_and_turn_count_produces_identical_damage() -> None:
    # Two dungeons with the same seed, same floor index, same turn
    # count, same combatants → bit-identical damage rolls.
    def setup() -> tuple[Dungeon, Player, Enemy]:
        floor = _floor_from_grid(["..."])
        enemy = _enemy((1, 0), hp=100, enemy_id=_stable_id(1))
        floor.enemies.append(enemy)
        dungeon = _dungeon([floor], seed=99)
        player = _player((0, 0), attack=5)
        return dungeon, player, enemy

    d1, p1, e1 = setup()
    d2, p2, e2 = setup()
    r1 = process_turn(d1, p1, Attack(direction=Direction.EAST))
    r2 = process_turn(d2, p2, Attack(direction=Direction.EAST))

    [a1] = [e for e in r1.events if isinstance(e, PlayerAttacked)]
    [a2] = [e for e in r2.events if isinstance(e, PlayerAttacked)]
    assert a1.damage == a2.damage
    assert e1.hp == e2.hp


def test_different_turn_counts_can_produce_different_damage_rolls() -> None:
    # Probe a small window of turn counts and confirm the RNG actually
    # responds to turn_count — otherwise the seed isn't being threaded
    # through correctly and replay would be broken.
    damages: set[int] = set()
    for turn_count in range(20):
        floor = _floor_from_grid(["..."])
        enemy = _enemy((1, 0), hp=100, enemy_id=_stable_id(1))
        floor.enemies.append(enemy)
        dungeon = _dungeon([floor], seed=42)
        dungeon.turn_count = turn_count
        player = _player((0, 0), attack=5)
        result = process_turn(dungeon, player, Attack(direction=Direction.EAST))
        [att] = [e for e in result.events if isinstance(e, PlayerAttacked)]
        damages.add(att.damage)
    # With ±1 variance at attack=5, defense=0, damages live in [4, 6];
    # we expect to see at least 2 distinct values across 20 turns.
    assert len(damages) >= 2


def test_turn_count_increments_exactly_once_per_call() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    player = _player((1, 0))

    process_turn(dungeon, player, Wait())
    process_turn(dungeon, player, Wait())
    process_turn(dungeon, player, Wait())

    assert dungeon.turn_count == 3


def test_damage_is_floored_at_one_even_with_high_defense() -> None:
    # Defense > attack would otherwise yield zero or negative damage;
    # the min-damage floor prevents armor-stacking lockouts.
    floor = _floor_from_grid(["..."])
    tank = _enemy((1, 0), hp=100, defense=99)
    floor.enemies.append(tank)
    dungeon = _dungeon([floor])
    player = _player((0, 0), attack=1)

    result = process_turn(dungeon, player, Attack(direction=Direction.EAST))

    [att] = [e for e in result.events if isinstance(e, PlayerAttacked)]
    assert att.damage == 1


# --- Mutation invariants ---------------------------------------------------


def test_dungeon_id_and_seed_are_not_mutated_across_a_turn() -> None:
    floor = _floor_from_grid(["..."])
    dungeon = _dungeon([floor])
    original_id = dungeon.dungeon_id
    original_seed = dungeon.seed
    player = _player((1, 0))

    process_turn(dungeon, player, Wait())

    assert dungeon.dungeon_id == original_id
    assert dungeon.seed == original_seed


def test_rejected_action_does_not_increment_damage_taken_or_change_position() -> None:
    floor = _floor_from_grid(["#.", ".."])
    dungeon = _dungeon([floor])
    player = _player((0, 1))

    process_turn(dungeon, player, Move(direction=Direction.NORTH))

    assert player.position == (0, 1)
    assert player.damage_taken == 0
