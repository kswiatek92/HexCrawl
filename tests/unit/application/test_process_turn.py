"""Tests for ``src.application.process_turn.ProcessTurn``.

Use cases are tested against hand-written fakes for the ports (not
``unittest.mock`` of a real DB/Redis client), per CLAUDE.md → "Testing
strategy". Coverage targets the task 3.2 design intent (QUIZZES.md Q1–Q5 +
the two forks confirmed this session): cache-first load with Postgres
fallback, Redis-every-turn / Postgres-on-checkpoint persistence, and the
propagate-not-swallow cache-write contract.

Floors here are deliberately *enemy-free*, so a ``Wait`` produces an empty,
deterministic event list — these tests exercise orchestration, not combat
(combat RNG is the domain service's own test surface).
"""

import json
from uuid import UUID, uuid4

import pytest

from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    game_state_cache_key,
    serialize_game_state,
)
from src.application.process_turn import GameNotFoundError, ProcessTurn
from src.domain.models import (
    Abandon,
    Descend,
    Direction,
    Dungeon,
    Floor,
    Move,
    Player,
    TileType,
    Wait,
)

# --- Hand-written port fakes ----------------------------------------------


class FakeGameRepository:
    """In-memory :class:`IGameRepository` that counts ``save`` calls."""

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


class FailingSetCachePort:
    """:class:`ICachePort` whose ``set`` always raises (Redis-down stand-in).

    ``get`` returns a pre-seeded blob so a turn reaches the write step.
    """

    def __init__(self, seeded: dict[str, str]) -> None:
        self._seeded = seeded

    async def get(self, key: str) -> str | None:
        return self._seeded.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        raise RuntimeError("redis unavailable")


# --- State builders --------------------------------------------------------

# A 3x3 grid, all FLOOR except a STAIRS tile, ringed conceptually by the test's
# choice of player position. Enemy-free so Wait/Move stay deterministic.
_OPEN_3X3 = [
    [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
    [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
    [TileType.FLOOR, TileType.FLOOR, TileType.STAIRS],
]


def _floor(stairs: tuple[int, int] = (2, 2)) -> Floor:
    return Floor(
        floor_id=uuid4(),
        tiles=[row[:] for row in _OPEN_3X3],
        enemies=[],
        items={},
        stairs_down=stairs,
    )


def _run(
    *,
    floors: list[Floor] | None = None,
    current_floor_index: int = 0,
    position: tuple[int, int] = (1, 1),
    turn_count: int = 0,
) -> tuple[Dungeon, Player]:
    dungeon = Dungeon(
        dungeon_id=uuid4(),
        seed=42,
        floors=floors if floors is not None else [_floor()],
        current_floor_index=current_floor_index,
        turn_count=turn_count,
    )
    player = Player(user_id=uuid4(), name="hero", position=position)
    return dungeon, player


def _seed_cache(cache: FakeCachePort, dungeon: Dungeon, player: Player) -> str:
    key = game_state_cache_key(dungeon.dungeon_id)
    cache.store[key] = (serialize_game_state(dungeon, player), GAME_STATE_TTL_SECONDS)
    return key


# --- Tests -----------------------------------------------------------------


async def test_cache_hit_processes_and_rewrites_without_postgres() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    dungeon, player = _run(turn_count=3)
    key = _seed_cache(cache, dungeon, player)

    result = await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Wait())

    # Domain ran: turn_count advanced and the cache reflects the new state.
    assert result.game_over is False
    new_blob, ttl = cache.store[key]
    assert json.loads(new_blob)["dungeon"]["turn_count"] == 4
    assert ttl == GAME_STATE_TTL_SECONDS
    # A normal turn is not a checkpoint — Postgres is untouched.
    assert games.save_calls == 0


async def test_cache_miss_falls_back_to_postgres_checkpoint() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()  # empty: simulates a lapsed TTL
    dungeon, player = _run()
    games.saved[dungeon.dungeon_id] = (dungeon, player)  # last durable checkpoint

    result = await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Wait())

    # The run was rehydrated from Postgres and the turn processed...
    assert result.game_over is False
    # ...and the cache is re-seeded so the next turn is a hit.
    assert game_state_cache_key(dungeon.dungeon_id) in cache.store


async def test_missing_everywhere_raises_game_not_found() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    unknown = uuid4()

    with pytest.raises(GameNotFoundError, match=str(unknown)):
        await ProcessTurn(games, cache).execute(unknown, Wait())

    assert games.save_calls == 0
    assert cache.store == {}


async def test_game_over_checkpoints_to_postgres() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    dungeon, player = _run()
    key = _seed_cache(cache, dungeon, player)

    result = await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Abandon())

    assert result.game_over is True
    # Game over is a checkpoint: durable write happened, cache still refreshed.
    # (The use case loads a fresh copy from the cache, so we assert on the
    # persisted state, not the local instances.) The saved dungeon reflects the
    # processed turn — turn_count advanced from 0 to 1.
    assert games.save_calls == 1
    assert games.saved[dungeon.dungeon_id][0].turn_count == 1
    assert key in cache.store


async def test_floor_descent_checkpoints_to_postgres() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    # Two floors; player stands on floor 0's STAIRS so Descend succeeds.
    dungeon, player = _run(floors=[_floor(), _floor()], position=(2, 2))
    _seed_cache(cache, dungeon, player)

    result = await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Descend())

    assert result.game_over is False
    # Floor descent is a checkpoint even though the run continues. Assert on the
    # persisted copy (the use case mutated the cache-loaded instance, not the
    # local one): the descent landed on floor index 1.
    assert games.save_calls == 1
    assert games.saved[dungeon.dungeon_id][0].current_floor_index == 1


async def test_normal_move_does_not_checkpoint() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    dungeon, player = _run(position=(1, 1))
    _seed_cache(cache, dungeon, player)

    await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Move(Direction.NORTH))

    # A plain move is neither game-over nor descent: no durable write.
    assert games.save_calls == 0


async def test_move_mutation_is_carried_into_the_rewritten_cache() -> None:
    games = FakeGameRepository()
    cache = FakeCachePort()
    dungeon, player = _run(position=(1, 1))
    key = _seed_cache(cache, dungeon, player)

    await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Move(Direction.NORTH))

    # NORTH is (0, -1): the deserialize -> process_turn -> serialize pipeline
    # must thread the position change all the way back into the cache blob.
    new_position = json.loads(cache.store[key][0])["player"]["position"]
    assert new_position == [1, 0]


async def test_cache_write_failure_propagates() -> None:
    # The cache is the authoritative copy of mid-game state, so a failed write
    # must surface — not be swallowed. Wrap the set() in a try/except in
    # execute() and this stops raising.
    games = FakeGameRepository()
    dungeon, player = _run()
    key = game_state_cache_key(dungeon.dungeon_id)
    cache = FailingSetCachePort({key: serialize_game_state(dungeon, player)})

    with pytest.raises(RuntimeError, match="redis unavailable"):
        await ProcessTurn(games, cache).execute(dungeon.dungeon_id, Wait())
