"""Unit tests for the HTTP response-schema mappers (task 3.6).

The integration tests in ``tests/integration/entrypoints/test_game_start.py``
exercise ``GameStateResponse`` end-to-end, but a freshly started run has an
unpopulated floor (``StartGame`` generates geometry only), so the
``EnemyState`` / ``ItemState`` mappers and the ground-item ``"x,y"`` keying
never run there. These pure-mapping tests cover them directly against a
hand-built ``Floor``.
"""

from uuid import uuid4

from src.domain.models import (
    BehaviourType,
    Dungeon,
    Enemy,
    Floor,
    Item,
    ItemType,
    Player,
    TileType,
)
from src.entrypoints.http.schemas import FloorState, GameStateResponse


def _floor_with_contents() -> tuple[Floor, Enemy, Item]:
    """A 3-wide × 2-tall floor with one enemy and one ground-item stack."""
    # Row-major: tiles[y][x]; 2 rows (height) × 3 cols (width).
    tiles = [
        [TileType.WALL, TileType.FLOOR, TileType.FLOOR],
        [TileType.FLOOR, TileType.FLOOR, TileType.STAIRS],
    ]
    enemy = Enemy(
        enemy_id=uuid4(),
        name="goblin",
        position=(1, 0),
        behaviour=BehaviourType.MELEE,
        hp=5,
        max_hp=5,
        attack=2,
        defense=0,
        awake=True,
    )
    item = Item(item_id=uuid4(), name="potion", item_type=ItemType.POTION, effect=3, count=2)
    floor = Floor(
        floor_id=uuid4(),
        tiles=tiles,
        enemies=[enemy],
        items={(2, 1): [item]},
        stairs_down=(2, 1),
    )
    return floor, enemy, item


def test_floor_state_maps_dimensions_enemies_and_items() -> None:
    floor, enemy, item = _floor_with_contents()

    state = FloorState.from_domain(floor)

    # Dimensions derived from the row-major grid (outer = rows = height).
    assert state.width == 3
    assert state.height == 2

    # Enemy mapper: id preserved, enum → wire string, awake carried through.
    assert len(state.enemies) == 1
    mapped_enemy = state.enemies[0]
    assert mapped_enemy.enemy_id == enemy.enemy_id
    assert mapped_enemy.behaviour == "MELEE"
    assert mapped_enemy.awake is True

    # Item mapper: ground items keyed "x,y" (JSON-string key), stack preserved.
    assert set(state.items.keys()) == {"2,1"}
    mapped_item = state.items["2,1"][0]
    assert mapped_item.item_id == item.item_id
    assert mapped_item.item_type == "POTION"
    assert mapped_item.count == 2


def test_floor_state_serialises_to_string_keyed_items() -> None:
    # The "x,y" key is what reaches the client — confirm it survives JSON dump,
    # since a tuple key would not be a valid JSON object key.
    floor, _, _ = _floor_with_contents()

    dumped = FloorState.from_domain(floor).model_dump(mode="json")

    assert "2,1" in dumped["items"]
    assert dumped["tiles"][0][0] == "WALL"


def test_game_state_response_selects_current_floor() -> None:
    floor, _, _ = _floor_with_contents()
    other = Floor(
        floor_id=uuid4(),
        tiles=[[TileType.WALL]],
        enemies=[],
        items={},
        stairs_down=(0, 0),
    )
    dungeon = Dungeon(dungeon_id=uuid4(), seed=7, floors=[other, floor], current_floor_index=1)
    player = Player(user_id=uuid4(), name="hero", position=(0, 1))

    resp = GameStateResponse.from_domain(dungeon, player)

    # The response carries the *current* floor (index 1), not floor 0.
    assert resp.current_floor_index == 1
    assert resp.floor.width == 3
    assert resp.floor.height == 2
    assert resp.seed == 7
