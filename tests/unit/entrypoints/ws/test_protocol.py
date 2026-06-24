"""Unit tests for the WebSocket wire protocol (task 3.9).

Pure and instant: ``parse_action`` (inbound JSON frame → typed domain ``Action``)
and ``serialize_event`` (domain ``TurnEvent`` → JSON-safe dict) are exercised
directly, no socket or app involved.
"""

from uuid import uuid4

import pytest

from src.domain.models import (
    Abandon,
    ActionRejected,
    Attack,
    Descend,
    Direction,
    EnemyAttacked,
    EnemyKilled,
    FloorDescended,
    Move,
    Open,
    PickUp,
    PlayerAttacked,
    PlayerDamaged,
    PlayerDied,
    PlayerMoved,
    RunAbandoned,
    UseItem,
    Wait,
)
from src.entrypoints.ws.protocol import ActionParseError, parse_action, serialize_event

# --- parse_action: happy paths --------------------------------------------


def test_parse_move_builds_typed_move_with_direction() -> None:
    assert parse_action({"action": "move", "direction": "NORTH"}) == Move(Direction.NORTH)


def test_parse_attack_builds_typed_attack_with_direction() -> None:
    assert parse_action({"action": "attack", "direction": "EAST"}) == Attack(Direction.EAST)


def test_parse_open_builds_typed_open_with_direction() -> None:
    assert parse_action({"action": "open", "direction": "SOUTH"}) == Open(Direction.SOUTH)


def test_parse_use_item_builds_typed_use_item_with_uuid() -> None:
    item_id = uuid4()
    assert parse_action({"action": "use_item", "item_id": str(item_id)}) == UseItem(item_id)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("wait", Wait()),
        ("descend", Descend()),
        ("abandon", Abandon()),
        ("pickup", PickUp()),
    ],
)
def test_parse_nullary_actions(name: str, expected: object) -> None:
    assert parse_action({"action": name}) == expected


# --- parse_action: error paths --------------------------------------------


def test_parse_non_object_frame_raises() -> None:
    # A bare JSON array/number is well-formed JSON but not an action frame.
    with pytest.raises(ActionParseError):
        parse_action([1, 2, 3])


def test_parse_missing_action_field_raises() -> None:
    with pytest.raises(ActionParseError):
        parse_action({"direction": "NORTH"})


def test_parse_non_string_action_field_raises() -> None:
    with pytest.raises(ActionParseError):
        parse_action({"action": 7})


def test_parse_unknown_action_raises() -> None:
    with pytest.raises(ActionParseError, match="unknown action"):
        parse_action({"action": "teleport"})


def test_parse_move_without_direction_raises() -> None:
    with pytest.raises(ActionParseError, match="direction"):
        parse_action({"action": "move"})


def test_parse_move_with_invalid_direction_raises() -> None:
    with pytest.raises(ActionParseError, match="invalid direction"):
        parse_action({"action": "move", "direction": "UPWARD"})


def test_parse_use_item_with_bad_uuid_raises() -> None:
    with pytest.raises(ActionParseError, match="item_id"):
        parse_action({"action": "use_item", "item_id": "not-a-uuid"})


def test_parse_use_item_without_item_id_raises() -> None:
    with pytest.raises(ActionParseError, match="item_id"):
        parse_action({"action": "use_item"})


# --- serialize_event ------------------------------------------------------


def test_serialize_player_moved_carries_positions_as_arrays() -> None:
    wire = serialize_event(PlayerMoved(from_position=(1, 2), to_position=(1, 3)))
    assert wire == {"type": "player_moved", "from": [1, 2], "to": [1, 3]}


def test_serialize_player_attacked_carries_enemy_damage_killed() -> None:
    enemy_id = uuid4()
    wire = serialize_event(PlayerAttacked(enemy_id=enemy_id, damage=4, killed=True))
    assert wire == {
        "type": "player_attacked",
        "enemy_id": str(enemy_id),
        "damage": 4,
        "killed": True,
    }


def test_serialize_enemy_attacked() -> None:
    enemy_id = uuid4()
    wire = serialize_event(EnemyAttacked(enemy_id=enemy_id, damage=2))
    assert wire == {"type": "enemy_attacked", "enemy_id": str(enemy_id), "damage": 2}


def test_serialize_player_damaged_carries_amount() -> None:
    assert serialize_event(PlayerDamaged(amount=3)) == {"type": "player_damaged", "amount": 3}


def test_serialize_enemy_killed() -> None:
    enemy_id = uuid4()
    assert serialize_event(EnemyKilled(enemy_id=enemy_id)) == {
        "type": "enemy_killed",
        "enemy_id": str(enemy_id),
    }


def test_serialize_player_died() -> None:
    assert serialize_event(PlayerDied()) == {"type": "player_died"}


def test_serialize_floor_descended_carries_new_index() -> None:
    assert serialize_event(FloorDescended(new_floor_index=2)) == {
        "type": "floor_descended",
        "new_floor_index": 2,
    }


def test_serialize_run_abandoned() -> None:
    assert serialize_event(RunAbandoned()) == {"type": "run_abandoned"}


def test_serialize_action_rejected_carries_reason() -> None:
    assert serialize_event(ActionRejected(reason="blocked_by_wall")) == {
        "type": "action_rejected",
        "reason": "blocked_by_wall",
    }
