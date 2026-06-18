"""Tests for ``src.application.game_state`` — the active-state cache contract.

Covers the cache key, the TTL constant, and ``serialize_game_state``. The
serialiser is validated by parsing its JSON output and asserting every field,
so the test depends on the actual encoding (not just "it returns a string").
The inverse (``deserialize_game_state``) lands with ProcessTurn (3.2); its
round-trip is that task's to prove.
"""

import json
from uuid import UUID, uuid4

from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    game_state_cache_key,
    serialize_game_state,
)
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


def _floor(floor_id: UUID) -> Floor:
    # 2x3 grid (height 2, width 3) with a STAIRS, plus one enemy and one
    # ground-item stack so every encoder branch is exercised.
    tiles = [
        [TileType.WALL, TileType.FLOOR, TileType.STAIRS],
        [TileType.DOOR, TileType.FLOOR, TileType.WALL],
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
    item = Item(item_id=uuid4(), name="potion", item_type=ItemType.POTION, effect=8, count=3)
    return Floor(
        floor_id=floor_id,
        tiles=tiles,
        enemies=[enemy],
        items={(1, 1): [item]},
        stairs_down=(2, 0),
    )


def _dungeon_and_player() -> tuple[Dungeon, Player]:
    floor_id = uuid4()
    dungeon = Dungeon(
        dungeon_id=uuid4(),
        seed=98765,
        floors=[_floor(floor_id)],
        current_floor_index=0,
        turn_count=7,
    )
    player = Player(
        user_id=uuid4(),
        name="hero",
        position=(1, 1),
        hp=15,
        max_hp=20,
        attack=4,
        defense=2,
        damage_taken=5,
    )
    return dungeon, player


def test_cache_key_format() -> None:
    game_id = UUID("12345678-1234-5678-1234-567812345678")
    assert game_state_cache_key(game_id) == "game:12345678-1234-5678-1234-567812345678"


def test_ttl_is_two_hours() -> None:
    assert GAME_STATE_TTL_SECONDS == 7200


def test_serialize_produces_parseable_json() -> None:
    dungeon, player = _dungeon_and_player()
    parsed = json.loads(serialize_game_state(dungeon, player))
    assert set(parsed) == {"dungeon", "player"}


def test_serialize_dungeon_scalar_fields() -> None:
    dungeon, player = _dungeon_and_player()
    parsed = json.loads(serialize_game_state(dungeon, player))
    d = parsed["dungeon"]
    assert d["dungeon_id"] == str(dungeon.dungeon_id)
    assert d["seed"] == 98765
    assert d["current_floor_index"] == 0
    assert d["turn_count"] == 7
    assert len(d["floors"]) == 1


def test_serialize_floor_tiles_and_stairs() -> None:
    dungeon, player = _dungeon_and_player()
    parsed = json.loads(serialize_game_state(dungeon, player))
    floor = parsed["dungeon"]["floors"][0]
    # Tiles encode as nested wire-strings (TileType is a StrEnum).
    assert floor["tiles"] == [
        ["WALL", "FLOOR", "STAIRS"],
        ["DOOR", "FLOOR", "WALL"],
    ]
    assert floor["stairs_down"] == [2, 0]
    assert floor["floor_id"] == str(dungeon.floors[0].floor_id)


def test_serialize_enemy_fields() -> None:
    dungeon, player = _dungeon_and_player()
    parsed = json.loads(serialize_game_state(dungeon, player))
    enemy = parsed["dungeon"]["floors"][0]["enemies"][0]
    source = dungeon.floors[0].enemies[0]
    assert enemy == {
        "enemy_id": str(source.enemy_id),
        "name": "goblin",
        "position": [1, 0],
        "behaviour": "MELEE",
        "hp": 5,
        "max_hp": 5,
        "attack": 2,
        "defense": 0,
        "awake": True,
    }


def test_serialize_ground_items_keyed_by_position() -> None:
    dungeon, player = _dungeon_and_player()
    parsed = json.loads(serialize_game_state(dungeon, player))
    items = parsed["dungeon"]["floors"][0]["items"]
    source = dungeon.floors[0].items[(1, 1)][0]
    # JSON object keys must be strings: the (x, y) tuple becomes "x,y".
    assert set(items) == {"1,1"}
    assert items["1,1"] == [
        {
            "item_id": str(source.item_id),
            "name": "potion",
            "item_type": "POTION",
            "effect": 8,
            "count": 3,
        }
    ]


def test_serialize_player_fields() -> None:
    dungeon, player = _dungeon_and_player()
    parsed = json.loads(serialize_game_state(dungeon, player))
    assert parsed["player"] == {
        "user_id": str(player.user_id),
        "name": "hero",
        "position": [1, 1],
        "hp": 15,
        "max_hp": 20,
        "attack": 4,
        "defense": 2,
        "damage_taken": 5,
    }
