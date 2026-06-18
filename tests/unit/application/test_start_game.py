"""Tests for ``src.application.start_game.StartGame``.

Use cases are tested against hand-written fakes for the ports (not
``unittest.mock`` of a real DB/Redis client), per CLAUDE.md → "Testing
strategy". Coverage targets the task 3.1 design intent (QUIZZES.md Q1–Q5):
the orchestration order, primitive inputs, seed handling, the cached blob,
and the cache-failure tolerance.
"""

import json
from uuid import UUID, uuid4

import pytest

from src.application.game_state import GAME_STATE_TTL_SECONDS, game_state_cache_key
from src.application.start_game import StartGame
from src.domain.models import Dungeon, Player, TileType

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


class FailingCachePort:
    """:class:`ICachePort` whose ``set`` always raises (Redis-down stand-in)."""

    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        raise RuntimeError("redis unavailable")


# --- Tests -----------------------------------------------------------------


async def test_returns_persisted_dungeon_and_player() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    user_id = uuid4()

    dungeon, player = await StartGame(games, cache).execute(user_id, "hero", seed=42)

    # The returned pair is exactly what the repository now holds.
    assert games.saved[dungeon.dungeon_id] == (dungeon, player)
    assert await games.get(dungeon.dungeon_id) == (dungeon, player)


async def test_new_run_starts_on_floor_zero() -> None:
    dungeon, _ = await StartGame(FakeGameRepository(), FakeCachePort()).execute(
        uuid4(), "hero", seed=42
    )
    assert dungeon.current_floor_index == 0
    assert dungeon.turn_count == 0
    assert len(dungeon.floors) == 1


async def test_player_uses_default_stats_and_spawns_on_walkable_tile() -> None:
    user_id = uuid4()
    dungeon, player = await StartGame(FakeGameRepository(), FakeCachePort()).execute(
        user_id, "hero", seed=42
    )
    assert player.user_id == user_id
    assert player.name == "hero"
    assert (player.hp, player.max_hp, player.attack, player.defense) == (20, 20, 3, 1)
    assert player.damage_taken == 0
    x, y = player.position
    assert dungeon.floors[0].tiles[y][x] in (TileType.FLOOR, TileType.STAIRS)


async def test_explicit_seed_is_used_and_deterministic() -> None:
    a_dungeon, a_player = await StartGame(FakeGameRepository(), FakeCachePort()).execute(
        uuid4(), "a", seed=2026
    )
    b_dungeon, b_player = await StartGame(FakeGameRepository(), FakeCachePort()).execute(
        uuid4(), "b", seed=2026
    )
    assert a_dungeon.seed == 2026
    # Same seed → identical floor geometry and spawn position.
    assert a_dungeon.floors[0].tiles == b_dungeon.floors[0].tiles
    assert a_dungeon.floors[0].stairs_down == b_dungeon.floors[0].stairs_down
    assert a_player.position == b_player.position


async def test_omitted_seed_is_server_generated() -> None:
    dungeon, _ = await StartGame(FakeGameRepository(), FakeCachePort()).execute(uuid4(), "hero")
    assert isinstance(dungeon.seed, int)
    assert dungeon.floors[0].tiles  # a real floor was generated from it


async def test_caches_serialized_state_at_ttl() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()

    dungeon, _ = await StartGame(games, cache).execute(uuid4(), "hero", seed=42)

    key = game_state_cache_key(dungeon.dungeon_id)
    assert key in cache.store
    value, ttl = cache.store[key]
    assert ttl == GAME_STATE_TTL_SECONDS
    # The cached blob is the serialized run, not some placeholder.
    parsed = json.loads(value)
    assert parsed["dungeon"]["dungeon_id"] == str(dungeon.dungeon_id)
    assert parsed["dungeon"]["seed"] == 42


async def test_cache_failure_does_not_fail_the_command() -> None:
    # Q4: the durable DB write already succeeded; a cache-write failure must
    # not fail "new game". Remove the try/except in execute() and this fails.
    games = FakeGameRepository()
    dungeon, player = await StartGame(games, FailingCachePort()).execute(uuid4(), "hero", seed=42)
    assert games.saved[dungeon.dungeon_id] == (dungeon, player)


async def test_distinct_runs_get_distinct_ids() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    start = StartGame(games, cache)
    first, _ = await start.execute(uuid4(), "hero", seed=42)
    second, _ = await start.execute(uuid4(), "hero", seed=42)
    # Same seed, but each run is its own resource with its own id.
    assert first.dungeon_id != second.dungeon_id
    assert len(games.saved) == 2


@pytest.mark.parametrize("bad_seed", [2**63, -(2**63) - 1, 10**40])
async def test_explicit_seed_out_of_bigint_range_is_rejected(bad_seed: int) -> None:
    # A client seed that won't fit the BIGINT column fails early and clearly
    # here, not later as an opaque DB DataError. Nothing is persisted.
    games = FakeGameRepository()
    with pytest.raises(ValueError, match="signed 64-bit range"):
        await StartGame(games, FakeCachePort()).execute(uuid4(), "hero", seed=bad_seed)
    assert games.saved == {}


@pytest.mark.parametrize("edge_seed", [2**63 - 1, -(2**63), 0])
async def test_explicit_seed_at_range_boundaries_is_accepted(edge_seed: int) -> None:
    dungeon, _ = await StartGame(FakeGameRepository(), FakeCachePort()).execute(
        uuid4(), "hero", seed=edge_seed
    )
    assert dungeon.seed == edge_seed
