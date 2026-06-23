"""Tests for ``src.application.abandon_game.AbandonGame`` (task 3.8).

Use cases are tested against hand-written fakes for the ports (not
``unittest.mock`` of a real DB/Redis client), per CLAUDE.md → "Testing
strategy". Coverage targets the abandon path's design intent: cache-first /
Postgres-fallback load, the domain ``Abandon`` action actually running, the
game-over checkpoint, the cache refresh, ownership enforcement (before any
mutation), and the not-found outcome.
"""

from uuid import UUID, uuid4

import pytest

from src.application.abandon_game import AbandonGame, GameNotFoundError, NotGameOwnerError
from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    deserialize_game_state,
    game_state_cache_key,
    serialize_game_state,
)
from src.domain.models import Dungeon, Floor, Player, TileType

# --- Hand-written port fakes ----------------------------------------------


class FakeGameRepository:
    """In-memory :class:`IGameRepository` that also counts ``save`` calls."""

    def __init__(self) -> None:
        self.saved: dict[UUID, tuple[Dungeon, Player]] = {}
        self.save_calls = 0

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self.save_calls += 1
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


# --- Happy path: domain action + checkpoint + cache refresh ----------------


async def test_abandon_returns_run_and_runs_domain_action() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    before = dungeon.turn_count
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)

    got_dungeon, got_player = await AbandonGame(games, FakeCachePort()).execute(
        dungeon.dungeon_id, owner
    )

    assert got_dungeon.dungeon_id == dungeon.dungeon_id
    assert got_player.user_id == owner
    # The Abandon action ran (process_turn always increments turn_count). Remove
    # the process_turn call and this assertion fails.
    assert got_dungeon.turn_count == before + 1


async def test_abandon_checkpoints_to_postgres() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)

    await AbandonGame(games, FakeCachePort()).execute(dungeon.dungeon_id, owner)

    # The terminal state is persisted (game-over checkpoint). Drop the save and
    # this counter stays at 0.
    assert games.save_calls == 1


async def test_abandon_refreshes_cache_with_terminal_state() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    before = dungeon.turn_count
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)
    cache = FakeCachePort()

    await AbandonGame(games, cache).execute(dungeon.dungeon_id, owner)

    key = game_state_cache_key(dungeon.dungeon_id)
    assert key in cache.store
    blob, ttl = cache.store[key]
    assert ttl == GAME_STATE_TTL_SECONDS
    # The cached copy is post-abandon, not the pre-abandon state. Remove the
    # cache refresh and the key is never written.
    cached_dungeon, _ = deserialize_game_state(blob)
    assert cached_dungeon.turn_count == before + 1


# --- Load: cache-first / Postgres-fallback ---------------------------------


async def test_abandon_loads_from_cache_first() -> None:
    # Same id, different seed in each store: cache-first means the cache copy is
    # the one abandoned and re-saved. Remove cache-first and the DB seed wins.
    owner = uuid4()
    game_id = uuid4()
    cache_dungeon, cache_player = _run(owner=owner, seed=111, game_id=game_id)
    db_dungeon, db_player = _run(owner=owner, seed=999, game_id=game_id)

    games = FakeGameRepository()
    games.saved[game_id] = (db_dungeon, db_player)
    cache = FakeCachePort()
    cache.store[game_state_cache_key(game_id)] = (
        serialize_game_state(cache_dungeon, cache_player),
        GAME_STATE_TTL_SECONDS,
    )

    got_dungeon, _ = await AbandonGame(games, cache).execute(game_id, owner)

    assert got_dungeon.seed == 111  # cache value, not the DB's 999


async def test_abandon_falls_back_to_postgres_on_cache_miss() -> None:
    owner = uuid4()
    dungeon, player = _run(owner=owner)
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)

    # Cache empty: the run must come from the durable checkpoint and still abandon.
    got_dungeon, _ = await AbandonGame(games, FakeCachePort()).execute(dungeon.dungeon_id, owner)

    assert got_dungeon.dungeon_id == dungeon.dungeon_id


# --- Not found -------------------------------------------------------------


async def test_abandon_unknown_id_raises_game_not_found() -> None:
    unknown = uuid4()
    with pytest.raises(GameNotFoundError, match=str(unknown)):
        await AbandonGame(FakeGameRepository(), FakeCachePort()).execute(unknown, uuid4())


# --- Ownership -------------------------------------------------------------


async def test_abandon_foreign_run_raises_and_does_not_mutate() -> None:
    owner = uuid4()
    intruder = uuid4()
    dungeon, player = _run(owner=owner)
    before = dungeon.turn_count
    games = FakeGameRepository()
    games.saved[dungeon.dungeon_id] = (dungeon, player)
    cache = FakeCachePort()

    with pytest.raises(NotGameOwnerError, match=str(dungeon.dungeon_id)):
        await AbandonGame(games, cache).execute(dungeon.dungeon_id, intruder)

    # The ownership check runs before any mutation: no turn taken, no save, no
    # cache write. A non-owner cannot end someone else's run.
    assert dungeon.turn_count == before
    assert games.save_calls == 0
    assert cache.store == {}
