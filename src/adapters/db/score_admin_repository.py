"""PostgreSQL adapter implementing :class:`IScoreAdminRepository`.

The admin-side counterpart to :mod:`score_repository`: it owns the one
write-heavy administrative operation the read/write repository deliberately
excludes — archiving a completed week's leaderboard for the
``weekly_leaderboard_reset`` task (4.4). An *adapter*: it imports SQLAlchemy +
the ORM models + domain models (``adapters → domain`` is allowed) and must never
be imported by ``domain/`` or ``application/``. It conforms to
:class:`IScoreAdminRepository` **structurally** — mypy checks the match, there is
no inheritance.

It reuses two helpers from :mod:`score_repository` rather than duplicate them:
``_current_week_start`` single-sources the subtle Monday-00:00-UTC week boundary
(computed by the DB clock, robust to the session timezone), and ``_ORDER_BY`` is
the LSP-locked leaderboard ordering (``value`` DESC, ``computed_at`` ASC,
``score_id`` ASC). Re-deriving either here would risk the archive disagreeing
with the live board on week boundaries or tie-breaks.

Like the other repositories it does **not** commit: the archive runs inside the
caller's ambient ``session.begin()`` (the ``weekly_leaderboard_reset`` task owns
the Unit of Work). It also never touches the ``scores`` table — archiving is
non-destructive; the global all-time board shares those rows.
"""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.db.models import ScoreRow, WeeklyLeaderboardArchiveRow
from src.adapters.db.score_repository import _ORDER_BY, _current_week_start
from src.domain.models import WeeklyArchiveResult

# A "week" is 7 days; the completed week is the one ending at the current week's
# Monday-00:00-UTC start. Computed in Python from the DB-sourced boundary — exact
# in UTC (no DST), so no SQL interval arithmetic is needed.
_ONE_WEEK = timedelta(days=7)


class PostgresScoreAdminRepository:
    """Async SQLAlchemy implementation of :class:`IScoreAdminRepository`.

    The session is injected (not created here) so the caller owns the engine, the
    connection pool, and the transaction boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def archive_completed_week(self, top_n: int) -> WeeklyArchiveResult:
        # The completed week is [prev_start, this_start): the week that just ended.
        # this_start is the DB-clock Monday-00:00-UTC of the *current* week, so at
        # the Beat boundary (Mon 00:00) the archive correctly reaches one week back
        # rather than reading the new, empty window.
        this_start: datetime = (
            await self._session.execute(select(_current_week_start()))
        ).scalar_one()
        prev_start = this_start - _ONE_WEEK

        if top_n <= 0:
            # Symmetry with the read repo's n<=0 guard: nothing to archive, and the
            # week is still reported so the caller logs a real boundary.
            return WeeklyArchiveResult(week_start=prev_start, archived_count=0)

        # The just-ended week's ranked top-N, under the shared leaderboard ordering.
        rows_stmt = (
            select(ScoreRow)
            .where(ScoreRow.computed_at >= prev_start, ScoreRow.computed_at < this_start)
            .order_by(*_ORDER_BY)
            .limit(top_n)
        )
        scores = list((await self._session.execute(rows_stmt)).scalars())

        # Idempotent per week: clear any prior snapshot of this week, then insert the
        # fresh ranking. A retried task replaces rather than duplicates (the
        # uq_weekly_leaderboard_archive_week_start constraint also guards this).
        await self._session.execute(
            delete(WeeklyLeaderboardArchiveRow).where(
                WeeklyLeaderboardArchiveRow.week_start == prev_start
            )
        )
        self._session.add_all(
            [
                WeeklyLeaderboardArchiveRow(
                    archive_id=uuid4(),
                    week_start=prev_start,
                    rank=index + 1,
                    score_id=score.score_id,
                    user_id=score.user_id,
                    value=score.value,
                    computed_at=score.computed_at,
                )
                for index, score in enumerate(scores)
            ]
        )
        # Flush so the delete+insert hit the DB within this transaction (and any
        # constraint violation surfaces now), while commit stays the caller's job.
        await self._session.flush()

        return WeeklyArchiveResult(week_start=prev_start, archived_count=len(scores))
