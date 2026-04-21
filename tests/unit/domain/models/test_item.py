from dataclasses import fields, is_dataclass
from uuid import UUID, uuid4

import pytest

from src.domain.models import Item, ItemType


def _make_item(
    *,
    item_id: UUID | None = None,
    name: str = "Rusty Sword",
    item_type: ItemType = ItemType.WEAPON,
    effect: int = 0,
    count: int = 1,
) -> Item:
    return Item(
        item_id=item_id or uuid4(),
        name=name,
        item_type=item_type,
        effect=effect,
        count=count,
    )


def test_item_is_dataclass() -> None:
    assert is_dataclass(Item)


def test_item_accepts_all_fields() -> None:
    iid = uuid4()
    item = Item(
        item_id=iid,
        name="Iron Helm",
        item_type=ItemType.ARMOR,
        effect=2,
        count=1,
    )

    assert item.item_id == iid
    assert isinstance(item.item_id, UUID)
    assert item.name == "Iron Helm"
    assert item.item_type is ItemType.ARMOR
    assert item.effect == 2
    assert item.count == 1


def test_item_default_count_is_one() -> None:
    item = Item(
        item_id=uuid4(),
        name="Brass Key",
        item_type=ItemType.KEY,
    )

    assert item.count == 1


def test_item_default_effect_is_zero() -> None:
    item = Item(
        item_id=uuid4(),
        name="Brass Key",
        item_type=ItemType.KEY,
    )

    assert item.effect == 0


def test_item_is_mutable() -> None:
    item = _make_item(item_type=ItemType.POTION, effect=5, count=3)

    item.count = 2
    item.effect = 10

    assert item.count == 2
    assert item.effect == 10


def test_item_exposes_expected_fields() -> None:
    field_names = {f.name for f in fields(Item)}

    assert field_names == {
        "item_id",
        "name",
        "item_type",
        "effect",
        "count",
    }


@pytest.mark.parametrize("item_type", list(ItemType))
def test_item_accepts_each_item_type(item_type: ItemType) -> None:
    item = _make_item(item_type=item_type)

    assert item.item_type is item_type


def test_item_supports_stack_count() -> None:
    item = _make_item(item_type=ItemType.POTION, effect=5, count=5)

    assert item.count == 5


def test_item_type_members() -> None:
    assert set(ItemType) == {
        ItemType.WEAPON,
        ItemType.ARMOR,
        ItemType.SHIELD,
        ItemType.POTION,
        ItemType.KEY,
    }


def test_item_type_values_are_uppercase_strings() -> None:
    for variant in ItemType:
        assert variant.value == variant.name
        assert variant.value.isupper()


def test_item_type_is_str_enum() -> None:
    assert isinstance(ItemType.WEAPON, str)
    assert ItemType.WEAPON == "WEAPON"
    assert ItemType.ARMOR == "ARMOR"
    assert ItemType.SHIELD == "SHIELD"
    assert ItemType.POTION == "POTION"
    assert ItemType.KEY == "KEY"
