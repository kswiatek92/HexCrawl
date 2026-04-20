from dataclasses import fields, is_dataclass
from uuid import UUID, uuid4

from src.domain.models import Player


def _make_player(
    *,
    user_id: UUID | None = None,
    name: str = "Thorin",
    position: tuple[int, int] = (0, 0),
    hp: int = 20,
    max_hp: int = 20,
    attack: int = 3,
    defense: int = 1,
) -> Player:
    return Player(
        user_id=user_id or uuid4(),
        name=name,
        position=position,
        hp=hp,
        max_hp=max_hp,
        attack=attack,
        defense=defense,
    )


def test_player_is_dataclass() -> None:
    assert is_dataclass(Player)


def test_player_defaults_match_v1_stats() -> None:
    player = Player(user_id=uuid4(), name="Thorin", position=(0, 0))

    assert player.hp == 20
    assert player.max_hp == 20
    assert player.attack == 3
    assert player.defense == 1


def test_player_accepts_required_identity_fields() -> None:
    uid = uuid4()
    player = _make_player(user_id=uid, name="Gimli", position=(4, 7))

    assert player.user_id == uid
    assert isinstance(player.user_id, UUID)
    assert player.name == "Gimli"
    assert player.position == (4, 7)


def test_player_is_mutable() -> None:
    player = _make_player()

    player.hp = 12
    player.position = (3, 5)

    assert player.hp == 12
    assert player.position == (3, 5)


def test_player_overrides_stats() -> None:
    player = _make_player(hp=15, max_hp=25, attack=5, defense=2)

    assert player.hp == 15
    assert player.max_hp == 25
    assert player.attack == 5
    assert player.defense == 2


def test_player_exposes_expected_fields() -> None:
    field_names = {f.name for f in fields(Player)}

    assert field_names == {
        "user_id",
        "name",
        "position",
        "hp",
        "max_hp",
        "attack",
        "defense",
    }
