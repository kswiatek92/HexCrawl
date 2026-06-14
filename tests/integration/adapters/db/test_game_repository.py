"""Integration tests for PostgresGameRepository against a real Postgres.

Covers what the in-memory mapper unit tests (``tests/unit/adapters/db/
test_game_repository.py``) cannot: the actual SQL round trip (JSONB tiles/items,
``selectin`` eager loading, the ``SAEnum(native_enum=False)`` behaviour column,
the ``BigInteger`` seed), the no-commit Unit-of-Work contract (DECISIONS.md
ADR-0006), and the ``merge`` + ``delete-orphan`` reconciliation on re-save.

Each builder uses asymmetric coordinates and distinct field values so a swapped
axis, a dropped field, or a misordered collection fails loudly.
"""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.game_repository import PostgresGameRepository
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


def _player(*, user_id: UUID | None = None) -> Player:
    return Player(
        user_id=user_id or uuid4(),
        name="Hero",
        position=(3, 7),  # asymmetric: catches an x/y swap through SQL
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
        # > 2**31 to exercise the BigInteger column: a plain INTEGER would overflow.
        seed=9_000_000_000,
        floors=[_rich_floor(), _bare_floor()] if floors is None else floors,
        current_floor_index=1,
        turn_count=3,
    )


async def _save_committed(
    sessionmaker: async_sessionmaker[AsyncSession],
    dungeon: Dungeon,
    player: Player,
) -> None:
    """Persist a run in its own transaction — the use case's commit (ADR-0006)."""
    async with sessionmaker() as session:
        await PostgresGameRepository(session).save(dungeon, player)
        await session.commit()


async def test_save_then_get_round_trips(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    dungeon, player = _dungeon(), _player()
    await _save_committed(sessionmaker, dungeon, player)

    # A *fresh* session: forces a real SELECT (selectin loads), not an
    # identity-map cache hit, so the JSONB/enum/bigint round trip is exercised.
    async with sessionmaker() as session:
        loaded = await PostgresGameRepository(session).get(dungeon.dungeon_id)

    assert loaded == (dungeon, player)


async def test_get_missing_returns_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        assert await PostgresGameRepository(session).get(uuid4()) is None


async def test_save_does_not_commit(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # The repo's UoW contract: save() merges + flushes but leaves the transaction
    # open for the caller to commit. Proven by a *second, independent* session
    # seeing nothing — flushed-but-uncommitted writes are invisible across
    # transactions. (Checking the same session would pass even if save committed,
    # so it would be a false positive.)
    dungeon, player = _dungeon(), _player()

    async with sessionmaker() as writer:
        await PostgresGameRepository(writer).save(dungeon, player)
        # deliberately no writer.commit()
        async with sessionmaker() as reader:
            assert await PostgresGameRepository(reader).get(dungeon.dungeon_id) is None


async def test_resave_reconciles_removed_floor_and_enemy(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # First save: 2 floors, the first carrying 2 enemies.
    dungeon, player = _dungeon(), _player()
    await _save_committed(sessionmaker, dungeon, player)

    # Mutate the run in place (domain models are mutable): drop the second floor
    # entirely and one enemy off the surviving floor, then re-save the same
    # dungeon_id. merge + cascade="all, delete-orphan" must delete the orphans.
    dungeon.floors.pop()  # remove the bare floor
    surviving_floor = dungeon.floors[0]
    surviving_enemy = surviving_floor.enemies[0]
    surviving_floor.enemies.pop()  # remove the Dragon, keep the Goblin
    await _save_committed(sessionmaker, dungeon, player)

    async with sessionmaker() as session:
        loaded = await PostgresGameRepository(session).get(dungeon.dungeon_id)

    assert loaded is not None
    loaded_dungeon, _ = loaded
    assert len(loaded_dungeon.floors) == 1
    assert [e.enemy_id for e in loaded_dungeon.floors[0].enemies] == [surviving_enemy.enemy_id]
