from dataclasses import FrozenInstanceError, fields, is_dataclass
from uuid import UUID, uuid4

import pytest

from src.domain.models import (
    Abandon,
    Action,
    Attack,
    Descend,
    Direction,
    Move,
    Open,
    PickUp,
    UseItem,
    Wait,
)

ZERO_ARG_ACTIONS: tuple[type, ...] = (Wait, PickUp, Descend, Abandon)
DIRECTION_ACTIONS: tuple[type, ...] = (Move, Attack, Open)
ALL_ACTION_TYPES: tuple[type, ...] = (
    Move,
    Attack,
    Wait,
    PickUp,
    UseItem,
    Open,
    Descend,
    Abandon,
)


def test_direction_members() -> None:
    assert set(Direction) == {
        Direction.NORTH,
        Direction.SOUTH,
        Direction.EAST,
        Direction.WEST,
    }


def test_direction_values_are_uppercase_strings() -> None:
    for variant in Direction:
        assert variant.value == variant.name
        assert variant.value.isupper()


def test_direction_is_str_enum() -> None:
    assert isinstance(Direction.NORTH, str)
    assert Direction.NORTH == "NORTH"
    assert Direction.SOUTH == "SOUTH"
    assert Direction.EAST == "EAST"
    assert Direction.WEST == "WEST"


def test_direction_variants_are_singletons() -> None:
    assert Direction.NORTH is Direction.NORTH
    assert Direction("NORTH") is Direction.NORTH
    assert Direction.NORTH is not Direction.SOUTH


@pytest.mark.parametrize("variant_cls", ALL_ACTION_TYPES)
def test_action_variant_is_dataclass(variant_cls: type) -> None:
    assert is_dataclass(variant_cls)


@pytest.mark.parametrize("variant_cls", ZERO_ARG_ACTIONS)
def test_zero_arg_action_takes_no_fields(variant_cls: type) -> None:
    assert {f.name for f in fields(variant_cls)} == set()
    # Constructible with no args.
    variant_cls()


@pytest.mark.parametrize("variant_cls", ZERO_ARG_ACTIONS)
def test_zero_arg_action_is_frozen(variant_cls: type) -> None:
    instance = variant_cls()
    with pytest.raises(FrozenInstanceError):
        instance.some_attr = "x"  # type: ignore[misc]


@pytest.mark.parametrize("variant_cls", DIRECTION_ACTIONS)
def test_direction_action_exposes_direction_field(variant_cls: type) -> None:
    assert {f.name for f in fields(variant_cls)} == {"direction"}


@pytest.mark.parametrize("variant_cls", DIRECTION_ACTIONS)
@pytest.mark.parametrize("direction", list(Direction))
def test_direction_action_carries_direction(variant_cls: type, direction: Direction) -> None:
    instance = variant_cls(direction=direction)
    assert instance.direction is direction


@pytest.mark.parametrize("variant_cls", DIRECTION_ACTIONS)
def test_direction_action_is_frozen(variant_cls: type) -> None:
    instance = variant_cls(direction=Direction.NORTH)
    with pytest.raises(FrozenInstanceError):
        instance.direction = Direction.SOUTH


def test_use_item_exposes_item_id_field() -> None:
    assert {f.name for f in fields(UseItem)} == {"item_id"}


def test_use_item_carries_uuid() -> None:
    item_id = uuid4()
    action = UseItem(item_id=item_id)

    assert action.item_id == item_id
    assert isinstance(action.item_id, UUID)


def test_use_item_is_frozen() -> None:
    action = UseItem(item_id=uuid4())
    with pytest.raises(FrozenInstanceError):
        action.item_id = uuid4()


def _dispatch(action: Action) -> str:
    """Reference match-dispatch over the Action union.

    Each branch returns a sentinel naming the variant. Failure modes:
      - missing branch → mypy-strict exhaustiveness fails AND the
        runtime test asserts the sentinel for that variant.
      - branch typo → sentinel mismatch in the test.
    """
    match action:
        case Move(direction=_):
            return "MOVE"
        case Attack(direction=_):
            return "ATTACK"
        case Wait():
            return "WAIT"
        case PickUp():
            return "PICKUP"
        case UseItem(item_id=_):
            return "USE_ITEM"
        case Open(direction=_):
            return "OPEN"
        case Descend():
            return "DESCEND"
        case Abandon():
            return "ABANDON"


def test_action_match_dispatch_covers_every_variant() -> None:
    cases: list[tuple[Action, str]] = [
        (Move(direction=Direction.NORTH), "MOVE"),
        (Attack(direction=Direction.EAST), "ATTACK"),
        (Wait(), "WAIT"),
        (PickUp(), "PICKUP"),
        (UseItem(item_id=uuid4()), "USE_ITEM"),
        (Open(direction=Direction.SOUTH), "OPEN"),
        (Descend(), "DESCEND"),
        (Abandon(), "ABANDON"),
    ]

    seen = {sentinel for _, sentinel in cases}
    assert len(seen) == 8, "sentinels must be unique to detect branch crossover"

    for action, expected in cases:
        assert _dispatch(action) == expected


def test_action_unknown_object_falls_through_match() -> None:
    # Q5 of QUIZZES.md task 1.9: anything outside the union must be
    # caught explicitly (here as the wildcard). GameService relies on the
    # union typing for this guarantee; the entrypoint is responsible for
    # rejecting raw / malformed inputs before they reach the domain.
    def dispatch_with_default(value: object) -> str:
        match value:
            case Move() | Attack() | Wait() | PickUp() | UseItem() | Open() | Descend() | Abandon():
                return "ACTION"
            case _:
                return "UNKNOWN"

    assert dispatch_with_default(42) == "UNKNOWN"
    assert dispatch_with_default("MOVE") == "UNKNOWN"
    assert dispatch_with_default(None) == "UNKNOWN"
    assert dispatch_with_default(Move(direction=Direction.NORTH)) == "ACTION"


def test_actions_are_hashable() -> None:
    # Frozen dataclasses with default eq are hashable. Equal actions
    # must hash equal — required for any future turn-log keyed on actions.
    a1 = Move(direction=Direction.NORTH)
    a2 = Move(direction=Direction.NORTH)

    assert hash(a1) == hash(a2)
    assert a1 == a2

    item_id = uuid4()
    u1 = UseItem(item_id=item_id)
    u2 = UseItem(item_id=item_id)
    assert hash(u1) == hash(u2)


def test_actions_are_distinct_types_even_when_field_shape_matches() -> None:
    # Move and Attack have the same field shape (direction: Direction),
    # but they are different variants and must compare unequal — frozen
    # dataclass equality is type-aware.
    assert Move(direction=Direction.NORTH) != Attack(direction=Direction.NORTH)
    # And different from a zero-arg variant for good measure.
    assert Wait() != PickUp()
