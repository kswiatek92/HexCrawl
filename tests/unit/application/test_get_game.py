"""Tests for ``src.application.get_game.GetGame`` (task 3.7).

Use cases are tested against hand-written fakes for the ports (not
``unittest.mock`` of a real DB/Redis client), per CLAUDE.md → "Testing
strategy". Coverage targets the read path's design intent: cache-first /
Postgres-fallback, the *read-only* guarantee (no cache write-back), the
not-found outcome, and ownership enforcement.
"""

from uuid import UUID, uuid4

import pytest

from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    game_state_cache_key,
    serialize_game_state,
)
from src.application.get_game import GameNotFoundError, GetGame, NotGameOwnerError
from src.domain.models import Dungeon, Floor, Player, TileType

# --- Hand-written port fakes ----------------------------------------------


class FakeGameRepository:
    """In-memory :class:`IGameRepository`: ``save`` stores, ``get`` reads back."""

    def __init__(self) -> None:
        self.saved: dict[UUID, tuple[Dungeon, Player]] = {}

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self.saved[dungeon.dungeon_id] = (dungeon, player)
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        return self.saved.get(game_id)


class FakeCachePort:
    """In-memory :class:`ICachePort` recording the value *and* TTL per key."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        return entry[0] if entry is not None else None

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.store[key] = (value, ttl)


# --- Domain fixtures -------------------------------------------------------


def _run(
    *, owner: UUID, seed: int = 7, name: str = "hero", game_id: UUID | None = None
) -> tuple[Dungeon, Player]:
    """A minimal but valid ``(Dungeon, Player)`` for a single 3x3 floor."""
    floor = Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR] * 3 for _ in range(3)],
        enemies=[],
        items={},
        stairs_down=(2, 2),
    )
    dungeon = Dungeon(
        dungeon_id=game_id or uuid4(),
        seed=seed,
        floors=[floor],
        current_floor_index=0,
    )
    player = Player(user_id=owner, name=name, position=(1, 1))
    return dungeon, player


# --- Load: cache-first / Postgres-fallback ---------------------------------


async def test_returns_run_from_cache() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    cache = FakeCachePort()
    cache.store[game_state_cache_key(dungeon.dungeon_id)] = (
        serialize_game_state(dungeon, player),
        GAME_STATE_TTL_SECONDS,
    )

    got_dungeon, got_player = await GetGame(FakeGameRepository(), cache).execute(
        dungeon.dungeon_id, owner
    )

    assert got_dungeon.dungeon_id == dungeon.dungeon_id
    assert got_player.user_id == owner
    assert got_player.position == player.position


async def test_falls_back_to_postgres_on_cache_miss() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)

    # Cache is empty: the run must come from the durable checkpoint.
    got_dungeon, got_player = await GetGame(games, FakeCachePort()).execute(
        dungeon.dungeon_id, owner
    )

    assert got_dungeon.dungeon_id == dungeon.dungeon_id
    assert got_player.user_id == owner


async def test_cache_takes_precedence_over_postgres() -> None:
    # Same id, different seed in each store. Cache-first means the cache copy
    # wins — remove the cache-first ordering and this returns the DB's seed.
    owner = uuid4()
    game_id = uuid4()
    cache_dungeon, cache_player = _run(owner=owner, seed=111, game_id=game_id)
    db_dungeon, db_player = _run(owner=owner, seed=999, game_id=game_id)

    games = FakeGameRepository()
    games.saved[cache_dungeon.dungeon_id] = (db_dungeon, db_player)
    cache = FakeCachePort()
    cache.store[game_state_cache_key(cache_dungeon.dungeon_id)] = (
        serialize_game_state(cache_dungeon, cache_player),
        GAME_STATE_TTL_SECONDS,
    )

    got_dungeon, _ = await GetGame(games, cache).execute(cache_dungeon.dungeon_id, owner)

    assert got_dungeon.seed == 111  # cache value, not the DB's 999


async def test_read_is_side_effect_free_on_cache_miss() -> None:
    # A GET must not mutate state: a cache miss reads Postgres but must NOT
    # write the run back into the cache (contrast ProcessTurn). Add a write-back
    # to GetGame._load and this fails.
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)
    cache = FakeCachePort()

    await GetGame(games, cache).execute(dungeon.dungeon_id, owner)

    assert cache.store == {}


# --- Not found -------------------------------------------------------------


async def test_unknown_id_raises_game_not_found() -> None:
    unknown = uuid4()
    with pytest.raises(GameNotFoundError, match=str(unknown)):
        await GetGame(FakeGameRepository(), FakeCachePort()).execute(unknown, uuid4())


# --- Ownership -------------------------------------------------------------


async def test_foreign_run_raises_not_game_owner() -> None:
    owner = uuid4()
    intruder = uuid4()
    dungeon, player = _run(owner=owner)
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)

    # The run exists, but the caller is not its owner → authZ failure, not 404.
    with pytest.raises(NotGameOwnerError, match=str(dungeon.dungeon_id)):
        await GetGame(games, FakeCachePort()).execute(dungeon.dungeon_id, intruder)


async def test_owner_match_returns_run() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)

    got_dungeon, got_player = await GetGame(games, FakeCachePort()).execute(
        dungeon.dungeon_id, owner
    )

    assert (got_dungeon, got_player) == (dungeon, player)


async def test_ownership_is_enforced_against_cached_state_too() -> None:
    # Ownership must hold regardless of which store the run loaded from.
    owner = uuid4()
    intruder = uuid4()
    dungeon, player = _run(owner=owner)
    cache = FakeCachePort()
    cache.store[game_state_cache_key(dungeon.dungeon_id)] = (
        serialize_game_state(dungeon, player),
        GAME_STATE_TTL_SECONDS,
    )

    with pytest.raises(NotGameOwnerError):
        await GetGame(FakeGameRepository(), cache).execute(dungeon.dungeon_id, intruder)
