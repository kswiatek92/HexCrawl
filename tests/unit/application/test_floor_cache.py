"""Tests for ``src.application.floor_cache`` — the pre-gen cache contract + codec.

Covers the per-``(game_id, floor_index)`` key, the TTL constant, and the
``serialize_floor`` / ``deserialize_floor`` round-trip. The serialiser is
validated by parsing its JSON output and asserting the real encoding (not just
"it returns a string"); the round-trip is asserted to depend on actual field
values, so a codec that dropped or transposed a field would fail.
"""

import json
from uuid import UUID, uuid4

from src.application.floor_cache import (
    PREGEN_FLOOR_TTL_SECONDS,
    deserialize_floor,
    pregenerated_floor_cache_key,
    serialize_floor,
)
from src.domain.models import BehaviourType, Enemy, Floor, Item, ItemType, TileType


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


def test_cache_key_is_namespaced_per_game_and_floor() -> None:
    game_id = uuid4()
    # The `floor:` prefix keeps pre-gen entries distinct from the `game:` active
    # blob; the floor index keeps each run's deep floors separate.
    assert pregenerated_floor_cache_key(game_id, 12) == f"floor:{game_id}:12"
    assert pregenerated_floor_cache_key(game_id, 12) != pregenerated_floor_cache_key(game_id, 13)


def test_ttl_is_positive_and_bounded() -> None:
    # TTL is mandatory (the cache port rejects ttl <= 0) and is what cleans up an
    # orphaned pre-gen floor the player never reaches (quiz 4.3 Q4).
    assert PREGEN_FLOOR_TTL_SECONDS == 7200
    assert PREGEN_FLOOR_TTL_SECONDS > 0


def test_serialize_encodes_the_documented_wire_shape() -> None:
    floor_id = uuid4()
    floor = _floor(floor_id)

    payload = json.loads(serialize_floor(floor))

    assert payload["floor_id"] == str(floor_id)
    # StrEnum tiles serialise to their wire strings, row-major.
    assert payload["tiles"] == [
        ["WALL", "FLOOR", "STAIRS"],
        ["DOOR", "FLOOR", "WALL"],
    ]
    # (x, y) positions become [x, y] arrays; ground items keyed "x,y".
    assert payload["stairs_down"] == [2, 0]
    assert list(payload["items"].keys()) == ["1,1"]
    assert payload["items"]["1,1"][0]["item_type"] == "POTION"
    assert payload["enemies"][0]["position"] == [1, 0]
    assert payload["enemies"][0]["awake"] is True


def test_round_trip_reconstructs_an_equal_floor() -> None:
    floor = _floor(uuid4())
    # deserialize ∘ serialize is identity over the wire format.
    assert deserialize_floor(serialize_floor(floor)) == floor


def test_round_trip_depends_on_actual_field_values() -> None:
    # Anti-false-positive: change concrete fields and assert the round-trip carries
    # the *changed* values through, so the test depends on the codec, not constants.
    floor = _floor(uuid4())
    floor.stairs_down = (0, 1)
    floor.enemies[0].awake = False
    floor.enemies[0].hp = 1

    restored = deserialize_floor(serialize_floor(floor))

    assert restored.stairs_down == (0, 1)
    assert restored.enemies[0].awake is False
    assert restored.enemies[0].hp == 1
