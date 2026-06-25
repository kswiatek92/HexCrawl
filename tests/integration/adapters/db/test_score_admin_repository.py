"""Integration tests for PostgresScoreAdminRepository against a real Postgres.

Covers the live-SQL behaviour the use-case unit tests cannot: the completed-week
window (``[prev Monday 00:00 UTC, this Monday 00:00 UTC)``) computed off the DB
clock, the ranked archive write, the non-destructive guarantee (``scores`` is
never touched), and the idempotent delete-then-insert per week.

The week boundary is anchored to a Python-computed Monday-00:00-UTC that mirrors
Postgres ``date_trunc('week')`` (Monday-based), so seeded ``computed_at`` values
land deterministically inside / outside the completed week regardless of the
weekday the suite runs.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.models import ScoreRow, WeeklyLeaderboardArchiveRow
from src.adapters.db.score_admin_repository import PostgresScoreAdminRepository
from src.adapters.db.score_repository import PostgresScoreRepository
from src.domain.models import Score, WeeklyArchiveResult


def _this_monday() -> datetime:
    """Monday 00:00 UTC of the current week — the Python mirror of Postgres
    ``date_trunc('week', now())``."""
    now = datetime.now(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=now.weekday())


def _score(
    *,
    value: int,
    computed_at: datetime,
    user_id: UUID | None = None,
    score_id: UUID | None = None,
) -> Score:
    return Score(
        score_id=score_id or uuid4(),
        user_id=user_id or uuid4(),
        dungeon_id=uuid4(),
        floors_reached=7,
        kills=13,
        item_multiplier=2.5,
        damage_taken=4,
        value=value,
        computed_at=computed_at,
    )


async def _save_committed(
    sessionmaker: async_sessionmaker[AsyncSession],
    *scores: Score,
) -> None:
    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        for score in scores:
            await repo.save(score)
        await session.commit()


async def _archive_committed(
    sessionmaker: async_sessionmaker[AsyncSession],
    top_n: int,
) -> WeeklyArchiveResult:
    """Run the archive in its own committed transaction (mirroring the task's UoW)."""
    async with sessionmaker() as session:
        result = await PostgresScoreAdminRepository(session).archive_completed_week(top_n)
        await session.commit()
        return result


async def _read_archive(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> list[WeeklyLeaderboardArchiveRow]:
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(WeeklyLeaderboardArchiveRow).order_by(WeeklyLeaderboardArchiveRow.rank)
            )
        ).scalars()
        return list(rows)


async def _count_scores(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return int((await session.execute(select(func.count()).select_from(ScoreRow))).scalar_one())


async def test_archives_only_the_completed_week_ranked(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    this_monday = _this_monday()
    prev_monday = this_monday - timedelta(days=7)

    # Two scores inside the just-ended week (distinct values → ranking), one in the
    # current week, one older than the completed week. Only the first two archive.
    prev_high = _score(value=300, computed_at=prev_monday + timedelta(hours=1))
    prev_low = _score(value=100, computed_at=prev_monday + timedelta(days=2))
    current = _score(value=999, computed_at=this_monday + timedelta(hours=1))
    older = _score(value=999, computed_at=prev_monday - timedelta(days=1))
    await _save_committed(sessionmaker, prev_high, prev_low, current, older)

    result = await _archive_committed(sessionmaker, 100)

    archived = await _read_archive(sessionmaker)
    # Exactly the two completed-week scores, ranked value DESC → rank 1, 2.
    assert [(r.rank, r.score_id, r.value) for r in archived] == [
        (1, prev_high.score_id, 300),
        (2, prev_low.score_id, 100),
    ]
    assert all(r.week_start == prev_monday for r in archived)
    # Result summary reports the completed week and its entry count.
    assert result.week_start == prev_monday
    assert result.archived_count == 2


async def test_archive_does_not_delete_scores(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # The load-bearing non-destructive guarantee: the shared scores table — which
    # the global all-time board reads — is untouched by the archive.
    this_monday = _this_monday()
    prev_monday = this_monday - timedelta(days=7)
    await _save_committed(
        sessionmaker,
        _score(value=300, computed_at=prev_monday + timedelta(hours=1)),
        _score(value=50, computed_at=this_monday + timedelta(hours=1)),
    )

    before = await _count_scores(sessionmaker)
    await _archive_committed(sessionmaker, 100)
    after = await _count_scores(sessionmaker)

    assert before == after == 2


async def test_archive_is_idempotent_per_week(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Re-running for the same completed week replaces, not duplicates: the
    # delete-then-insert (and the uq(week_start, score_id) constraint) keep exactly
    # one snapshot. Drop the delete and the second run would raise / double the rows.
    this_monday = _this_monday()
    prev_monday = this_monday - timedelta(days=7)
    await _save_committed(
        sessionmaker,
        _score(value=300, computed_at=prev_monday + timedelta(hours=1)),
        _score(value=100, computed_at=prev_monday + timedelta(days=2)),
    )

    await _archive_committed(sessionmaker, 100)
    await _archive_committed(sessionmaker, 100)

    archived = await _read_archive(sessionmaker)
    assert [(r.rank, r.value) for r in archived] == [(1, 300), (2, 100)]


async def test_empty_completed_week_archives_nothing(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # No scores in the completed week (only a current-week one): archive is empty,
    # count is 0, and the result still reports the real completed-week boundary.
    this_monday = _this_monday()
    prev_monday = this_monday - timedelta(days=7)
    await _save_committed(
        sessionmaker,
        _score(value=500, computed_at=this_monday + timedelta(hours=1)),
    )

    result = await _archive_committed(sessionmaker, 100)

    assert await _read_archive(sessionmaker) == []
    assert result.archived_count == 0
    assert result.week_start == prev_monday
