"""Tests for ``src.application.get_leaderboard.GetLeaderboard``.

The cache-aside read use case behind ``GET /leaderboard/global``, tested against
hand-written port fakes (no Redis / DB), per CLAUDE.md → "Testing strategy".
Coverage targets the design intent (QUIZZES.md 3.10 Q1): cache hit short-circuits
the repository; a miss rebuilds from the repo, populates the cache with a TTL,
and returns; the empty board is cached too; ``period`` is passed through.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.application.get_leaderboard import GetLeaderboard
from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    leaderboard_cache_key,
    serialize_leaderboard,
)
from src.domain.models import LeaderboardPeriod, Score

# --- Hand-written port fakes ----------------------------------------------


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository` recording every ``top_n`` call.

    Returns a seeded list and remembers the ``(n, period)`` it was asked for, so
    a test can assert the repo was (or was not) consulted and with what args.
    """

    def __init__(self, scores: list[Score] | None = None) -> None:
        self.scores = scores if scores is not None else []
        self.top_n_calls: list[tuple[int, LeaderboardPeriod]] = []

    async def save(self, score: Score) -> Score:  # pragma: no cover - unused here
        return score

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        self.top_n_calls.append((n, period))
        return self.scores


class FakeCachePort:
    """In-memory :class:`ICachePort` recording value + TTL per key."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        return entry[0] if entry is not None else None

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.store[key] = (value, ttl)


def _score(value: int) -> Score:
    return Score(
        score_id=uuid4(),
        user_id=uuid4(),
        dungeon_id=uuid4(),
        floors_reached=5,
        kills=3,
        item_multiplier=1.0,
        damage_taken=2,
        value=value,
        computed_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_and_skips_repository() -> None:
    cached = [_score(900), _score(400)]
    cache = FakeCachePort()
    cache.store[leaderboard_cache_key(LeaderboardPeriod.GLOBAL)] = (
        serialize_leaderboard(cached),
        LEADERBOARD_CACHE_TTL_SECONDS,
    )
    repo = FakeScoreRepository(scores=[_score(1)])  # different data; must be ignored

    result = await GetLeaderboard(repo, cache).execute(LeaderboardPeriod.GLOBAL)

    assert result == cached
    assert repo.top_n_calls == []  # hit path never touches the durable store


@pytest.mark.asyncio
async def test_cache_miss_rebuilds_from_repo_and_populates_cache() -> None:
    scores = [_score(900), _score(400)]
    cache = FakeCachePort()
    repo = FakeScoreRepository(scores=scores)

    result = await GetLeaderboard(repo, cache).execute(LeaderboardPeriod.GLOBAL)

    assert result == scores
    assert repo.top_n_calls == [(LEADERBOARD_SIZE, LeaderboardPeriod.GLOBAL)]
    # Cache populated with the serialised slice and the TTL.
    stored = cache.store[leaderboard_cache_key(LeaderboardPeriod.GLOBAL)]
    assert stored == (serialize_leaderboard(scores), LEADERBOARD_CACHE_TTL_SECONDS)


@pytest.mark.asyncio
async def test_corrupt_cache_entry_falls_back_to_repo_and_overwrites() -> None:
    scores = [_score(900)]
    cache = FakeCachePort()
    key = leaderboard_cache_key(LeaderboardPeriod.GLOBAL)
    cache.store[key] = ("not valid json{", LEADERBOARD_CACHE_TTL_SECONDS)  # corrupt
    repo = FakeScoreRepository(scores=scores)

    result = await GetLeaderboard(repo, cache).execute(LeaderboardPeriod.GLOBAL)

    # A decode failure is treated as a miss: repo consulted, bad entry overwritten.
    assert result == scores
    assert repo.top_n_calls == [(LEADERBOARD_SIZE, LeaderboardPeriod.GLOBAL)]
    assert cache.store[key] == (serialize_leaderboard(scores), LEADERBOARD_CACHE_TTL_SECONDS)


@pytest.mark.asyncio
async def test_cache_miss_with_empty_board_still_populates_cache() -> None:
    cache = FakeCachePort()
    repo = FakeScoreRepository(scores=[])

    result = await GetLeaderboard(repo, cache).execute(LeaderboardPeriod.GLOBAL)

    assert result == []
    # The empty result is cached so a cold board reads through to Postgres once.
    assert leaderboard_cache_key(LeaderboardPeriod.GLOBAL) in cache.store


@pytest.mark.asyncio
async def test_period_is_passed_through_to_repo_and_key() -> None:
    cache = FakeCachePort()
    repo = FakeScoreRepository(scores=[_score(10)])

    await GetLeaderboard(repo, cache).execute(LeaderboardPeriod.WEEKLY)

    assert repo.top_n_calls == [(LEADERBOARD_SIZE, LeaderboardPeriod.WEEKLY)]
    assert leaderboard_cache_key(LeaderboardPeriod.WEEKLY) in cache.store


@pytest.mark.asyncio
async def test_defaults_to_global_period() -> None:
    cache = FakeCachePort()
    repo = FakeScoreRepository(scores=[])

    await GetLeaderboard(repo, cache).execute()

    assert repo.top_n_calls == [(LEADERBOARD_SIZE, LeaderboardPeriod.GLOBAL)]
