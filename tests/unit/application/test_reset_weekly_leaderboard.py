"""Tests for ``src.application.reset_weekly_leaderboard.ResetWeeklyLeaderboard`` (task 4.4).

The use case behind the ``weekly_leaderboard_reset`` Celery task. Tested against
hand-written port fakes (no Redis / DB / archive table), per CLAUDE.md → "Testing
strategy". Coverage targets the 4.4 design intent: archive the completed week
*before* the visible reset (QUIZZES.md 4.4 Q1), then overwrite the
``leaderboard:WEEKLY`` slice with the *new* week's standings — and never touch
the GLOBAL slice or delete anything.
"""

from datetime import UTC, datetime
from uuid import uuid4

from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    deserialize_leaderboard,
    leaderboard_cache_key,
)
from src.application.reset_weekly_leaderboard import ResetWeeklyLeaderboard
from src.domain.models import LeaderboardPeriod, Score, WeeklyArchiveResult

# --- Hand-written port fakes ----------------------------------------------


class FakeScoreAdminRepository:
    """In-memory :class:`IScoreAdminRepository`. Records each archive call and
    appends ``"archive"`` to a shared trace so call order can be asserted."""

    def __init__(self, result: WeeklyArchiveResult, trace: list[str]) -> None:
        self._result = result
        self._trace = trace
        self.archive_calls: list[int] = []

    async def archive_completed_week(self, top_n: int) -> WeeklyArchiveResult:
        self.archive_calls.append(top_n)
        self._trace.append("archive")
        return self._result


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository`: ``top_n`` returns a seeded weekly slice."""

    def __init__(self, weekly: list[Score]) -> None:
        self._weekly = weekly
        self.top_n_calls: list[tuple[int, LeaderboardPeriod]] = []

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        self.top_n_calls.append((n, period))
        return self._weekly if period is LeaderboardPeriod.WEEKLY else []


class FakeCache:
    """In-memory :class:`ICachePort` recording every ``set`` as ``key -> (value, ttl)``;
    appends ``"cache"`` to the shared trace so the archive-before-cache order shows."""

    def __init__(self, trace: list[str]) -> None:
        self._trace = trace
        self.sets: dict[str, tuple[str, int]] = {}

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._trace.append("cache")
        self.sets[key] = (value, ttl)

    async def get(self, key: str) -> str | None:
        entry = self.sets.get(key)
        return entry[0] if entry is not None else None


# --- Helpers ---------------------------------------------------------------


def _score(value: int) -> Score:
    return Score(
        score_id=uuid4(),
        user_id=uuid4(),
        dungeon_id=uuid4(),
        floors_reached=3,
        kills=4,
        item_multiplier=1.0,
        damage_taken=2,
        value=value,
        computed_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )


def _result() -> WeeklyArchiveResult:
    return WeeklyArchiveResult(
        week_start=datetime(2026, 5, 25, 0, 0, tzinfo=UTC),
        archived_count=2,
    )


# --- Tests -----------------------------------------------------------------


async def test_archives_before_refreshing_cache() -> None:
    # The durable-copy-first invariant (QUIZZES.md 4.4 Q1): the archive must be
    # taken before the cache is reset. Reorder the two steps in execute() and
    # this trace flips to ["cache", "archive"] and the test fails.
    trace: list[str] = []
    admin = FakeScoreAdminRepository(_result(), trace)
    repo = FakeScoreRepository([_score(200), _score(100)])
    cache = FakeCache(trace)

    await ResetWeeklyLeaderboard(admin, repo, cache).execute()

    assert trace == ["archive", "cache"]
    assert admin.archive_calls == [LEADERBOARD_SIZE]


async def test_refreshes_weekly_slice_to_new_week() -> None:
    # The reset overwrites leaderboard:WEEKLY with the *new* week's standings,
    # under the shared TTL, and deserialises back to exactly what top_n returned.
    new_week = [_score(50), _score(20)]
    trace: list[str] = []
    admin = FakeScoreAdminRepository(_result(), trace)
    repo = FakeScoreRepository(new_week)
    cache = FakeCache(trace)

    await ResetWeeklyLeaderboard(admin, repo, cache).execute()

    value, ttl = cache.sets[leaderboard_cache_key(LeaderboardPeriod.WEEKLY)]
    assert ttl == LEADERBOARD_CACHE_TTL_SECONDS
    assert deserialize_leaderboard(value) == new_week
    # The new week is read from the WEEKLY window at the full leaderboard size.
    assert repo.top_n_calls == [(LEADERBOARD_SIZE, LeaderboardPeriod.WEEKLY)]


async def test_only_weekly_slice_is_touched() -> None:
    # Reset is weekly-scoped: GLOBAL is never overwritten (no rows deleted, so the
    # all-time board is untouched). Only the WEEKLY key is written.
    trace: list[str] = []
    admin = FakeScoreAdminRepository(_result(), trace)
    repo = FakeScoreRepository([_score(10)])
    cache = FakeCache(trace)

    await ResetWeeklyLeaderboard(admin, repo, cache).execute()

    assert list(cache.sets.keys()) == [leaderboard_cache_key(LeaderboardPeriod.WEEKLY)]
    assert leaderboard_cache_key(LeaderboardPeriod.GLOBAL) not in cache.sets


async def test_empty_new_week_writes_empty_slice() -> None:
    # At the boundary the new week is empty: the cache is still overwritten with an
    # explicit [] so the weekly board reads cold rather than serving the stale week.
    trace: list[str] = []
    admin = FakeScoreAdminRepository(_result(), trace)
    repo = FakeScoreRepository([])
    cache = FakeCache(trace)

    await ResetWeeklyLeaderboard(admin, repo, cache).execute()

    value, _ = cache.sets[leaderboard_cache_key(LeaderboardPeriod.WEEKLY)]
    assert deserialize_leaderboard(value) == []


async def test_idempotent_across_two_runs() -> None:
    # A retried task runs execute() twice; both steps overwrite, so the cache ends
    # at the same value and nothing errors. archive is called once per run.
    new_week = [_score(50)]
    trace: list[str] = []
    admin = FakeScoreAdminRepository(_result(), trace)
    repo = FakeScoreRepository(new_week)
    cache = FakeCache(trace)
    use_case = ResetWeeklyLeaderboard(admin, repo, cache)

    await use_case.execute()
    first = cache.sets[leaderboard_cache_key(LeaderboardPeriod.WEEKLY)]
    await use_case.execute()
    second = cache.sets[leaderboard_cache_key(LeaderboardPeriod.WEEKLY)]

    assert first == second
    assert admin.archive_calls == [LEADERBOARD_SIZE, LEADERBOARD_SIZE]
