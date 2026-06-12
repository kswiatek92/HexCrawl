"""Pure mapper guards for PostgresGameRepository (no DB).

These lock the domain↔ORM translation — the part a Postgres round trip can't
isolate. The mappers (`_to_orm`/`_to_domain`) touch no session, so a full
`_to_domain(_to_orm(...)) == (...)` round trip runs in-memory. The real
save/get-through-SQL behaviour is covered by the task 2.6 integration tests.

Coordinates are deliberately asymmetric and enum values distinct so a swapped
axis or a constant-returning mapper can't pass.
"""

from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.db.game_repository import (
    PostgresGameRepository,
    _to_domain,
    _to_orm,
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
from src.domain.ports import IGameRepository


def _player(*, user_id: UUID | None = None) -> Player:
    return Player(
        user_id=user_id or uuid4(),
        name="Hero",
        position=(3, 7),  # asymmetric: catches an x/y swap
        hp=15,
        max_hp=20,
        attack=4,
        defense=2,
        damage_taken=5,
    )


def _rich_floor() -> Floor:
    return Floor(
        floor_id=uuid4(),
        tiles=[
            [TileType.WALL, TileType.FLOOR, TileType.DOOR],
            [TileType.FLOOR, TileType.STAIRS, TileType.WALL],
        ],
        enemies=[
            Enemy(
                enemy_id=uuid4(),
                name="Goblin",
                position=(8, 2),
                behaviour=BehaviourType.MELEE,
                hp=6,
                max_hp=6,
                attack=2,
                defense=0,
                awake=True,
            ),
            Enemy(
                enemy_id=uuid4(),
                name="Dragon",
                position=(1, 9),
                behaviour=BehaviourType.BOSS,
                hp=40,
                max_hp=40,
                attack=9,
                defense=5,
            ),
        ],
        items={
            (2, 4): [
                Item(item_id=uuid4(), name="Sword", item_type=ItemType.WEAPON, effect=3),
                Item(item_id=uuid4(), name="Potion", item_type=ItemType.POTION, effect=10, count=2),
            ],
            (0, 0): [Item(item_id=uuid4(), name="Key", item_type=ItemType.KEY)],
        },
        stairs_down=(5, 9),
    )


def _bare_floor() -> Floor:
    return Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR]],
        enemies=[],
        items={},
        stairs_down=(0, 1),
    )


def _dungeon(*, floors: list[Floor] | None = None) -> Dungeon:
    return Dungeon(
        dungeon_id=uuid4(),
        seed=1234,
        floors=[_rich_floor(), _bare_floor()] if floors is None else floors,
        current_floor_index=1,
        turn_count=3,
    )


def test_round_trip_preserves_dungeon_and_player() -> None:
    dungeon, player = _dungeon(), _player()
    assert _to_domain(_to_orm(dungeon, player)) == (dungeon, player)


def test_round_trip_empty_dungeon() -> None:
    dungeon, player = _dungeon(floors=[]), _player()
    restored_dungeon, restored_player = _to_domain(_to_orm(dungeon, player))
    assert restored_dungeon == dungeon
    assert restored_dungeon.floors == []
    assert restored_player == player


def test_round_trip_floor_without_enemies_or_items() -> None:
    dungeon, player = _dungeon(floors=[_bare_floor()]), _player()
    assert _to_domain(_to_orm(dungeon, player)) == (dungeon, player)


def test_owner_is_taken_from_player() -> None:
    dungeon, player = _dungeon(), _player()
    row = _to_orm(dungeon, player)
    # dungeons.user_id (NOT NULL) is denormalised from the player...
    assert row.user_id == player.user_id
    # ...and the 1:1 player row links back by dungeon_id.
    assert row.player.user_id == player.user_id
    assert row.player.dungeon_id == dungeon.dungeon_id


def test_positions_map_to_columns_without_swapping() -> None:
    dungeon, player = _dungeon(), _player()
    row = _to_orm(dungeon, player)
    assert (row.player.position_x, row.player.position_y) == player.position  # (3, 7)
    floor, enemy = dungeon.floors[0], dungeon.floors[0].enemies[0]
    enemy_row = row.floors[0].enemies[0]
    assert (enemy_row.position_x, enemy_row.position_y) == enemy.position  # (8, 2)
    assert (row.floors[0].stairs_x, row.floors[0].stairs_y) == floor.stairs_down  # (5, 9)


def test_floor_index_follows_list_order() -> None:
    floors = [_bare_floor(), _rich_floor(), _bare_floor()]
    row = _to_orm(_dungeon(floors=floors), _player())
    assert [floor_row.floor_index for floor_row in row.floors] == [0, 1, 2]


def test_tiles_serialise_to_strings() -> None:
    dungeon, player = _dungeon(), _player()
    tiles = _to_orm(dungeon, player).floors[0].tiles
    assert tiles == [[tile.value for tile in row] for row in dungeon.floors[0].tiles]
    assert all(isinstance(value, str) for row in tiles for value in row)


def test_items_keyed_by_position_string() -> None:
    row = _to_orm(_dungeon(), _player())
    # Ground items become a JSON object keyed by "x,y".
    assert set(row.floors[0].items) == {"2,4", "0,0"}
    assert len(row.floors[0].items["2,4"]) == 2  # stacked items on one tile


def test_repository_conforms_to_protocol() -> None:
    # Structural (Protocol) conformance is verified by mypy via the annotation;
    # no session call is made, so a cast-None session is harmless here.
    repo: IGameRepository = PostgresGameRepository(cast(AsyncSession, None))
    assert isinstance(repo, PostgresGameRepository)
