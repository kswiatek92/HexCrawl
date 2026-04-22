from dataclasses import fields, is_dataclass
from uuid import UUID, uuid4

from src.domain.models import (
    TOTAL_FLOORS,
    Dungeon,
    Floor,
    TileType,
)


def _make_floor(*, stairs_down: tuple[int, int] = (1, 1)) -> Floor:
    return Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR]],
        enemies=[],
        items={},
        stairs_down=stairs_down,
    )


def _make_dungeon(
    *,
    dungeon_id: UUID | None = None,
    seed: int = 42,
    floors: list[Floor] | None = None,
    current_floor_index: int = 0,
) -> Dungeon:
    return Dungeon(
        dungeon_id=dungeon_id or uuid4(),
        seed=seed,
        floors=floors if floors is not None else [_make_floor()],
        current_floor_index=current_floor_index,
    )


def test_dungeon_is_dataclass() -> None:
    assert is_dataclass(Dungeon)


def test_dungeon_accepts_all_fields() -> None:
    did = uuid4()
    floor_a = _make_floor(stairs_down=(1, 1))
    floor_b = _make_floor(stairs_down=(2, 2))
    dungeon = Dungeon(
        dungeon_id=did,
        seed=12345,
        floors=[floor_a, floor_b],
        current_floor_index=1,
    )

    assert dungeon.dungeon_id == did
    assert isinstance(dungeon.dungeon_id, UUID)
    assert dungeon.seed == 12345
    assert dungeon.floors == [floor_a, floor_b]
    assert dungeon.current_floor_index == 1


def test_dungeon_exposes_expected_fields() -> None:
    # Locks the Option B decision: adding a `player` field here would
    # fail this assertion and force a conscious design conversation.
    field_names = {f.name for f in fields(Dungeon)}

    assert field_names == {
        "dungeon_id",
        "seed",
        "floors",
        "current_floor_index",
    }


def test_dungeon_is_mutable() -> None:
    dungeon = _make_dungeon()
    new_floor = _make_floor(stairs_down=(9, 9))

    dungeon.floors.append(new_floor)
    dungeon.current_floor_index = 1

    assert dungeon.floors[-1] is new_floor
    assert dungeon.current_floor_index == 1


def test_dungeon_current_floor_index_addresses_floors_list() -> None:
    floor_a = _make_floor(stairs_down=(1, 1))
    floor_b = _make_floor(stairs_down=(2, 2))
    dungeon = _make_dungeon(floors=[floor_a, floor_b], current_floor_index=0)

    # Index is the addressing mechanism — no separate `current_floor` reference.
    assert dungeon.floors[dungeon.current_floor_index] is floor_a

    dungeon.current_floor_index = 1
    assert dungeon.floors[dungeon.current_floor_index] is floor_b


def test_dungeon_floors_list_can_grow_progressively() -> None:
    # Simulates descent: StartGame seeds floor 0, descent appends the next floor.
    dungeon = _make_dungeon(floors=[_make_floor()], current_floor_index=0)
    assert len(dungeon.floors) == 1

    dungeon.floors.append(_make_floor())
    dungeon.current_floor_index = 1

    assert len(dungeon.floors) == 2
    assert dungeon.current_floor_index == 1


def test_total_floors_constant() -> None:
    assert TOTAL_FLOORS == 100
