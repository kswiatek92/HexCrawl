from dataclasses import fields, is_dataclass
from uuid import UUID, uuid4

from src.domain.models import (
    GRID_HEIGHT,
    GRID_WIDTH,
    BehaviourType,
    Enemy,
    Floor,
    Item,
    ItemType,
    TileType,
)


def _make_floor(
    *,
    floor_id: UUID | None = None,
    tiles: list[list[TileType]] | None = None,
    enemies: list[Enemy] | None = None,
    items: dict[tuple[int, int], list[Item]] | None = None,
    stairs_down: tuple[int, int] = (1, 1),
) -> Floor:
    return Floor(
        floor_id=floor_id or uuid4(),
        tiles=tiles if tiles is not None else [[TileType.FLOOR]],
        enemies=enemies if enemies is not None else [],
        items=items if items is not None else {},
        stairs_down=stairs_down,
    )


def _make_enemy(position: tuple[int, int] = (0, 0)) -> Enemy:
    return Enemy(
        enemy_id=uuid4(),
        name="Goblin",
        position=position,
        behaviour=BehaviourType.MELEE,
        hp=5,
        max_hp=5,
        attack=1,
        defense=0,
    )


def _make_item(item_type: ItemType = ItemType.POTION) -> Item:
    return Item(item_id=uuid4(), name="Healing potion", item_type=item_type)


def test_floor_is_dataclass() -> None:
    assert is_dataclass(Floor)


def test_floor_accepts_all_fields() -> None:
    fid = uuid4()
    tiles = [
        [TileType.WALL, TileType.FLOOR, TileType.STAIRS],
        [TileType.DOOR, TileType.WALL, TileType.FLOOR],
    ]
    enemy = _make_enemy(position=(2, 0))
    potion = _make_item()
    floor = Floor(
        floor_id=fid,
        tiles=tiles,
        enemies=[enemy],
        items={(2, 0): [potion]},
        stairs_down=(2, 0),
    )

    assert floor.floor_id == fid
    assert isinstance(floor.floor_id, UUID)
    assert floor.tiles is tiles
    assert floor.enemies == [enemy]
    assert floor.items == {(2, 0): [potion]}
    assert floor.stairs_down == (2, 0)


def test_floor_exposes_expected_fields() -> None:
    field_names = {f.name for f in fields(Floor)}

    assert field_names == {
        "floor_id",
        "tiles",
        "enemies",
        "items",
        "stairs_down",
    }


def test_floor_is_mutable() -> None:
    floor = _make_floor()
    enemy = _make_enemy()
    potion = _make_item()

    floor.enemies.append(enemy)
    floor.items[(3, 4)] = [potion]
    floor.stairs_down = (9, 9)

    assert floor.enemies == [enemy]
    assert floor.items == {(3, 4): [potion]}
    assert floor.stairs_down == (9, 9)


def test_floor_tiles_use_y_then_x_indexing() -> None:
    # Grid laid out as y rows × x columns: tiles[y][x].
    tiles = [
        [TileType.WALL, TileType.FLOOR, TileType.STAIRS],  # y = 0
        [TileType.DOOR, TileType.WALL, TileType.FLOOR],  # y = 1
    ]
    floor = _make_floor(tiles=tiles)

    # tiles[y=0][x=2] is the STAIRS in the top-right corner.
    assert floor.tiles[0][2] is TileType.STAIRS
    # tiles[y=1][x=0] is the DOOR on the left of the second row.
    assert floor.tiles[1][0] is TileType.DOOR
    # Outer dimension is height (y); inner is width (x).
    assert len(floor.tiles) == 2
    assert len(floor.tiles[0]) == 3


def test_floor_enemies_can_be_added_and_removed() -> None:
    floor = _make_floor()
    enemy = _make_enemy()

    floor.enemies.append(enemy)
    assert enemy in floor.enemies

    floor.enemies.remove(enemy)
    assert floor.enemies == []


def test_floor_items_keyed_by_position_supports_stacking() -> None:
    floor = _make_floor()
    potion_a = _make_item(ItemType.POTION)
    potion_b = _make_item(ItemType.POTION)
    sword = _make_item(ItemType.WEAPON)

    floor.items.setdefault((2, 3), []).append(potion_a)
    floor.items.setdefault((2, 3), []).append(potion_b)
    floor.items.setdefault((5, 7), []).append(sword)

    assert floor.items[(2, 3)] == [potion_a, potion_b]
    assert floor.items[(5, 7)] == [sword]
    assert (4, 4) not in floor.items


def test_grid_dimension_constants() -> None:
    assert GRID_WIDTH == 80
    assert GRID_HEIGHT == 50
