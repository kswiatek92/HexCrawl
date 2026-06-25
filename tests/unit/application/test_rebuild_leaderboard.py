"""Tests for ``src.application.rebuild_leaderboard.RebuildLeaderboard`` (task 4.2).

The write-side use case behind the ``score_recalc`` Celery task. Tested against
hand-written port fakes (no Redis / DB), per CLAUDE.md → "Testing strategy".
Coverage targets the task 4.2 design intent (QUIZZES.md 4.2 Q1/Q4): every period
is recomputed from the durable store and the cache slice is *overwritten* with
the serialised top-N under the shared TTL — including the empty (cold-board) case.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    deserialize_leaderboard,
    leaderboard_cache_key,
)
from src.application.rebuild_leaderboard import RebuildLeaderboard
from src.domain.models import LeaderboardPeriod, Score

# --- Hand-written port fakes ----------------------------------------------


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository`: ``top_n`` returns a seeded slice per period."""

    def __init__(self, by_period: dict[LeaderboardPeriod, list[Score]]) -> None:
        self._by_period = by_period
        self.top_n_calls: list[tuple[int, LeaderboardPeriod]] = []

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        self.top_n_calls.append((n, period))
        return self._by_period.get(period, [])


class FakeCache:
    """In-memory :class:`ICachePort` recording every ``set`` as ``key -> (value, ttl)``."""

    def __init__(self) -> None:
        self.sets: dict[str, tuple[str, int]] = {}

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.sets[key] = (value, ttl)

    async def get(self, key: str) -> str | None:
        entry = self.sets.get(key)
        return entry[0] if entry is not None else None


# --- Helpers ---------------------------------------------------------------


def _score(value: int, *, user_id: UUID | None = None) -> Score:
    """Build a ``Score`` with a given ``value`` (other fields are irrelevant here)."""
    return Score(
        score_id=uuid4(),
        user_id=user_id if user_id is not None else uuid4(),
        dungeon_id=uuid4(),
        floors_reached=3,
        kills=4,
        item_multiplier=1.0,
        damage_taken=2,
        value=value,
        computed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )


# --- Tests -----------------------------------------------------------------


async def test_rebuilds_every_period_slice() -> None:
    global_slice = [_score(300), _score(200), _score(100)]
    weekly_slice = [_score(200), _score(100)]
    repo = FakeScoreRepository(
        {LeaderboardPeriod.GLOBAL: global_slice, LeaderboardPeriod.WEEKLY: weekly_slice}
    )
    cache = FakeCache()

    await RebuildLeaderboard(repo, cache).execute()

    # Both period slices were written, each at the shared key with the shared TTL,
    # and each deserialises back to exactly the slice the repo returned (order
    # preserved). Skip a period or mis-serialise and this fails.
    for period, expected in (
        (LeaderboardPeriod.GLOBAL, global_slice),
        (LeaderboardPeriod.WEEKLY, weekly_slice),
    ):
        value, ttl = cache.sets[leaderboard_cache_key(period)]
        assert ttl == LEADERBOARD_CACHE_TTL_SECONDS
        assert deserialize_leaderboard(value) == expected


async def test_reads_full_leaderboard_size_per_period() -> None:
    repo = FakeScoreRepository({})
    cache = FakeCache()

    await RebuildLeaderboard(repo, cache).execute()

    # Exactly one top_n read per period, each asking for the full top-100 slice.
    # Asserted against LeaderboardPeriod dynamically (not a hard-coded member
    # list) so the test tracks the use case's "iterate every period" contract and
    # survives a future period being added.
    assert repo.top_n_calls == [(LEADERBOARD_SIZE, period) for period in LeaderboardPeriod]


async def test_cold_board_writes_empty_slice_per_period() -> None:
    # No scores anywhere: every period is still overwritten with an explicit
    # empty slice, so a cold board reads as [] rather than leaving a stale entry.
    repo = FakeScoreRepository({})
    cache = FakeCache()

    await RebuildLeaderboard(repo, cache).execute()

    for period in LeaderboardPeriod:
        value, ttl = cache.sets[leaderboard_cache_key(period)]
        assert ttl == LEADERBOARD_CACHE_TTL_SECONDS
        assert deserialize_leaderboard(value) == []
