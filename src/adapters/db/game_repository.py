"""PostgreSQL adapter implementing :class:`IGameRepository`.

Persists a saved run — the ``(Dungeon, Player)`` pair (DECISIONS.md ADR-0006) —
to the relational schema from task 2.3, and rebuilds it on read. This is an
*adapter*: it imports SQLAlchemy + the ORM models + domain models
(``adapters → domain`` is allowed) and must never be imported by ``domain/`` or
``application/``. It conforms to ``IGameRepository`` **structurally** (no
inheritance) — mypy checks the match, there is no ``implements`` keyword.

Two halves:

* **Pure mappers** ``_to_orm`` / ``_to_domain`` translate between the domain
  dataclasses and the ``*Row`` ORM objects. They touch no session and do no
  I/O, so they round-trip-test without a database (the DB round-trip itself is
  covered by the task 2.6 integration tests).
* **The repository** owns only the session calls. It does **not** commit:
  ``save`` merges + flushes, leaving the transaction boundary (the Unit of
  Work) to the calling use case / ambient ``session.begin()`` (Phase 3). The
  SQLAlchemy ``Session`` is itself the per-request UoW.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.db.models import DungeonRow, EnemyRow, FloorRow, PlayerRow
from src.domain.models import (
    Dungeon,
    Enemy,
    Floor,
    Item,
    ItemType,
    Player,
    TileType,
)


def _tiles_to_json(tiles: list[list[TileType]]) -> list[list[str]]:
    # TileType is a StrEnum, so each member is already its wire string.
    return [[tile.value for tile in row] for row in tiles]


def _tiles_from_json(data: list[list[str]]) -> list[list[TileType]]:
    return [[TileType(value) for value in row] for row in data]


def _item_to_json(item: Item) -> dict[str, Any]:
    return {
        "item_id": str(item.item_id),
        "name": item.name,
        "item_type": item.item_type.value,
        "effect": item.effect,
        "count": item.count,
    }


def _item_from_json(data: dict[str, Any]) -> Item:
    return Item(
        item_id=UUID(data["item_id"]),
        name=data["name"],
        item_type=ItemType(data["item_type"]),
        effect=data["effect"],
        count=data["count"],
    )


def _items_to_json(
    items: dict[tuple[int, int], list[Item]],
) -> dict[str, list[dict[str, Any]]]:
    # Ground items are keyed by an (x, y) tuple; JSON object keys must be
    # strings, so the position becomes "x,y".
    return {f"{x},{y}": [_item_to_json(item) for item in stack] for (x, y), stack in items.items()}


def _items_from_json(
    data: dict[str, list[dict[str, Any]]],
) -> dict[tuple[int, int], list[Item]]:
    result: dict[tuple[int, int], list[Item]] = {}
    for key, stack in data.items():
        x_str, y_str = key.split(",")
        result[(int(x_str), int(y_str))] = [_item_from_json(item) for item in stack]
    return result


def _to_orm(dungeon: Dungeon, player: Player) -> DungeonRow:
    """Build the full ORM graph for one saved run (pure, no session)."""
    floor_rows = [
        FloorRow(
            floor_id=floor.floor_id,
            dungeon_id=dungeon.dungeon_id,
            # The floor's depth is its index in the ordered floors list — the
            # domain Floor has no index field; position in the list is canonical.
            floor_index=index,
            tiles=_tiles_to_json(floor.tiles),
            items=_items_to_json(floor.items),
            stairs_x=floor.stairs_down[0],
            stairs_y=floor.stairs_down[1],
            enemies=[
                EnemyRow(
                    enemy_id=enemy.enemy_id,
                    floor_id=floor.floor_id,
                    name=enemy.name,
                    position_x=enemy.position[0],
                    position_y=enemy.position[1],
                    behaviour=enemy.behaviour,
                    hp=enemy.hp,
                    max_hp=enemy.max_hp,
                    attack=enemy.attack,
                    defense=enemy.defense,
                    awake=enemy.awake,
                )
                for enemy in floor.enemies
            ],
        )
        for index, floor in enumerate(dungeon.floors)
    ]
    player_row = PlayerRow(
        dungeon_id=dungeon.dungeon_id,
        user_id=player.user_id,
        name=player.name,
        position_x=player.position[0],
        position_y=player.position[1],
        hp=player.hp,
        max_hp=player.max_hp,
        attack=player.attack,
        defense=player.defense,
        damage_taken=player.damage_taken,
    )
    return DungeonRow(
        dungeon_id=dungeon.dungeon_id,
        # The run's owner is the player's user — denormalised onto dungeons so
        # "my games" can be queried without joining players.
        user_id=player.user_id,
        seed=dungeon.seed,
        current_floor_index=dungeon.current_floor_index,
        turn_count=dungeon.turn_count,
        player=player_row,
        floors=floor_rows,
    )


def _to_domain(row: DungeonRow) -> tuple[Dungeon, Player]:
    """Rebuild the ``(Dungeon, Player)`` pair from an ORM graph (pure)."""
    if row.player is None:
        # A persisted run always has its player (save writes both). A dungeon
        # row without one is a storage-integrity fault, not a domain outcome.
        raise RuntimeError(f"dungeon {row.dungeon_id} has no persisted player")

    floors = [
        Floor(
            floor_id=floor_row.floor_id,
            tiles=_tiles_from_json(floor_row.tiles),
            enemies=[
                Enemy(
                    enemy_id=enemy_row.enemy_id,
                    name=enemy_row.name,
                    position=(enemy_row.position_x, enemy_row.position_y),
                    behaviour=enemy_row.behaviour,
                    hp=enemy_row.hp,
                    max_hp=enemy_row.max_hp,
                    attack=enemy_row.attack,
                    defense=enemy_row.defense,
                    awake=enemy_row.awake,
                )
                for enemy_row in floor_row.enemies
            ],
            items=_items_from_json(floor_row.items),
            stairs_down=(floor_row.stairs_x, floor_row.stairs_y),
        )
        # floors come back ordered by floor_index (relationship order_by, 2.3).
        for floor_row in row.floors
    ]
    dungeon = Dungeon(
        dungeon_id=row.dungeon_id,
        seed=row.seed,
        floors=floors,
        current_floor_index=row.current_floor_index,
        turn_count=row.turn_count,
    )
    player = Player(
        user_id=row.player.user_id,
        name=row.player.name,
        position=(row.player.position_x, row.player.position_y),
        hp=row.player.hp,
        max_hp=row.player.max_hp,
        attack=row.player.attack,
        defense=row.player.defense,
        damage_taken=row.player.damage_taken,
    )
    return dungeon, player


class PostgresGameRepository:
    """Async SQLAlchemy implementation of :class:`IGameRepository`.

    The session is injected (not created here) so the caller owns the engine,
    the connection pool, and — crucially — the transaction boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        # merge = upsert by primary key for a detached graph; with the
        # delete-orphan cascade from 2.3 it reconciles removed floors/enemies.
        # flush surfaces constraint errors now; commit is the caller's job.
        await self._session.merge(_to_orm(dungeon, player))
        await self._session.flush()
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        # selectin relationships (2.3) eager-load player + floors + enemies as
        # part of the get, so _to_domain reads in-memory data with no lazy I/O.
        row = await self._session.get(DungeonRow, game_id)
        if row is None:
            return None
        return _to_domain(row)
