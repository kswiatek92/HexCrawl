from dataclasses import fields, is_dataclass
from uuid import UUID, uuid4

import pytest

from src.domain.models import BehaviourType, Enemy


def _make_enemy(
    *,
    enemy_id: UUID | None = None,
    name: str = "Goblin",
    position: tuple[int, int] = (0, 0),
    behaviour: BehaviourType = BehaviourType.MELEE,
    hp: int = 5,
    max_hp: int = 5,
    attack: int = 1,
    defense: int = 0,
) -> Enemy:
    return Enemy(
        enemy_id=enemy_id or uuid4(),
        name=name,
        position=position,
        behaviour=behaviour,
        hp=hp,
        max_hp=max_hp,
        attack=attack,
        defense=defense,
    )


def test_enemy_is_dataclass() -> None:
    assert is_dataclass(Enemy)


def test_enemy_accepts_all_fields() -> None:
    eid = uuid4()
    enemy = Enemy(
        enemy_id=eid,
        name="Archer",
        position=(3, 4),
        behaviour=BehaviourType.RANGED,
        hp=6,
        max_hp=8,
        attack=2,
        defense=1,
    )

    assert enemy.enemy_id == eid
    assert isinstance(enemy.enemy_id, UUID)
    assert enemy.name == "Archer"
    assert enemy.position == (3, 4)
    assert enemy.behaviour is BehaviourType.RANGED
    assert enemy.hp == 6
    assert enemy.max_hp == 8
    assert enemy.attack == 2
    assert enemy.defense == 1


def test_enemy_is_mutable() -> None:
    enemy = _make_enemy(hp=5, position=(1, 1))

    enemy.hp = 2
    enemy.position = (4, 7)

    assert enemy.hp == 2
    assert enemy.position == (4, 7)


def test_enemy_exposes_expected_fields() -> None:
    field_names = {f.name for f in fields(Enemy)}

    assert field_names == {
        "enemy_id",
        "name",
        "position",
        "behaviour",
        "hp",
        "max_hp",
        "attack",
        "defense",
    }


@pytest.mark.parametrize("behaviour", list(BehaviourType))
def test_enemy_accepts_each_behaviour_variant(behaviour: BehaviourType) -> None:
    enemy = _make_enemy(behaviour=behaviour)

    assert enemy.behaviour is behaviour


def test_behaviour_type_members() -> None:
    assert set(BehaviourType) == {
        BehaviourType.MELEE,
        BehaviourType.RANGED,
        BehaviourType.BOSS,
    }


def test_behaviour_type_values_are_uppercase_strings() -> None:
    for variant in BehaviourType:
        assert variant.value == variant.name
        assert variant.value.isupper()


def test_behaviour_type_is_str_enum() -> None:
    assert isinstance(BehaviourType.MELEE, str)
    assert BehaviourType.MELEE == "MELEE"
    assert BehaviourType.RANGED == "RANGED"
    assert BehaviourType.BOSS == "BOSS"
