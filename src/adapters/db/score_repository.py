"""PostgreSQL adapter implementing :class:`IScoreRepository`.

Persists :class:`~src.domain.models.Score` aggregates to the ``scores`` table
(task 2.3) and serves the three leaderboard reads that back the ``/leaderboard/*``
endpoints (Phase 3) and the ``score_recalc`` Celery task (Phase 4). This is an
*adapter*: it imports SQLAlchemy + the ORM models + domain models
(``adapters → domain`` is allowed) and must never be imported by ``domain/`` or
``application/``. It conforms to ``IScoreRepository`` **structurally** (no
inheritance) — mypy checks the match, there is no ``implements`` keyword.

Two halves, mirroring :mod:`game_repository`:

* **Pure mappers** ``_to_values`` / ``_to_domain`` translate between the
  ``Score`` dataclass and the ``ScoreRow`` ORM shape. They touch no session and
  do no I/O. ``Score`` ↔ ``ScoreRow`` is a flat 1:1 field copy, so a single
  round-trip unit test locks the translation; the real SQL behaviour
  (ordering, the weekly window, ``rank_of``, upsert idempotency) needs a live
  Postgres and is covered by the task 2.6 integration tests.
* **The repository** owns only the session calls. It does **not** commit:
  ``save`` issues an upsert and leaves the transaction boundary (the Unit of
  Work) to the calling use case / ambient ``session.begin()`` (Phases 3–4).

Ordering is **LSP-locked** by the port (``QUIZZES.md`` task 1.11 Q3): every read
sorts by ``value`` DESC then ``computed_at`` ASC, matching the
``ix_scores_value_computed_at`` composite index defined alongside ``ScoreRow``.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.db.models import ScoreRow
from src.domain.models import LeaderboardPeriod, Score

# Ordering shared by every read (port-locked): highest value first, the earlier
# run winning ties. Identical to the columns of ix_scores_value_computed_at.
_ORDER_BY = (ScoreRow.value.desc(), ScoreRow.computed_at.asc())


def _current_week_start() -> ColumnElement[Any]:
    """SQL expression: Monday 00:00 UTC of the current week, as ``timestamptz``.

    Computed by the database clock (``now()``), not Python, so the weekly window
    is single-sourced and the adapter stays clock-injection-free. Robust to the
    session ``TimeZone`` setting: ``now() AT TIME ZONE 'UTC'`` yields the UTC
    wall-clock as a naive timestamp, ``date_trunc('week', …)`` floors it to
    Monday 00:00 (Postgres weeks are Monday-based), and the outer
    ``AT TIME ZONE 'UTC'`` reattaches UTC so the result compares directly
    against the ``timestamptz`` ``computed_at`` column. Monday-00:00-UTC matches
    the weekly-reset cadence in CLAUDE.md (Celery Beat, Mon 00:00 UTC).
    """
    return func.timezone(
        "UTC",
        func.date_trunc("week", func.timezone("UTC", func.now())),
    )


def _to_values(score: Score) -> dict[str, Any]:
    """Flatten a ``Score`` into a column->value dict for the Core upsert (pure)."""
    return {
        "score_id": score.score_id,
        "user_id": score.user_id,
        "dungeon_id": score.dungeon_id,
        "floors_reached": score.floors_reached,
        "kills": score.kills,
        "item_multiplier": score.item_multiplier,
        "damage_taken": score.damage_taken,
        "value": score.value,
        "computed_at": score.computed_at,
    }


def _to_domain(row: ScoreRow) -> Score:
    """Rebuild the immutable ``Score`` dataclass from a ``ScoreRow`` (pure)."""
    return Score(
        score_id=row.score_id,
        user_id=row.user_id,
        dungeon_id=row.dungeon_id,
        floors_reached=row.floors_reached,
        kills=row.kills,
        item_multiplier=row.item_multiplier,
        damage_taken=row.damage_taken,
        value=row.value,
        computed_at=row.computed_at,
    )


class PostgresScoreRepository:
    """Async SQLAlchemy implementation of :class:`IScoreRepository`.

    The session is injected (not created here) so the caller owns the engine,
    the connection pool, and — crucially — the transaction boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, score: Score) -> Score:
        # INSERT ... ON CONFLICT (score_id) DO UPDATE — an atomic upsert. A
        # Score is published under at-least-once delivery (the score_recalc
        # Celery task can be retried), so a repeat save of the same score_id
        # must be a no-op-equivalent, not a primary-key violation. ON CONFLICT
        # is stronger than ORM merge() (which is select-then-write and races
        # under concurrency). commit is the caller's job; execute participates
        # in the ambient transaction and surfaces constraint errors now.
        values = _to_values(score)
        stmt = pg_insert(ScoreRow).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ScoreRow.score_id],
            set_={key: value for key, value in values.items() if key != "score_id"},
        )
        await self._session.execute(stmt)
        return score

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        if n <= 0:
            # Callers can pass a user-supplied page size straight through.
            return []
        stmt = select(ScoreRow).order_by(*_ORDER_BY).limit(n)
        if period is LeaderboardPeriod.WEEKLY:
            stmt = stmt.where(ScoreRow.computed_at >= _current_week_start())
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars()]

    async def top_n_for_user(self, user_id: UUID, n: int) -> list[Score]:
        if n <= 0:
            return []
        stmt = select(ScoreRow).where(ScoreRow.user_id == user_id).order_by(*_ORDER_BY).limit(n)
        result = await self._session.execute(stmt)
        return [_to_domain(row) for row in result.scalars()]

    async def rank_of(self, user_id: UUID, period: LeaderboardPeriod) -> int | None:
        weekly = period is LeaderboardPeriod.WEEKLY

        # The user's single best score in the period (port: only the best ranks).
        best_stmt = select(ScoreRow.value, ScoreRow.computed_at).where(ScoreRow.user_id == user_id)
        if weekly:
            best_stmt = best_stmt.where(ScoreRow.computed_at >= _current_week_start())
        best_stmt = best_stmt.order_by(*_ORDER_BY).limit(1)
        best = (await self._session.execute(best_stmt)).first()
        if best is None:
            return None
        best_value, best_at = best

        # 1-indexed rank = (# scores strictly ahead under the port ordering) + 1.
        # "Strictly ahead" = higher value, or equal value with an earlier run.
        # The user's own best is never strictly ahead of itself, so no DISTINCT
        # on user is needed.
        ahead_stmt = (
            select(func.count())
            .select_from(ScoreRow)
            .where(
                or_(
                    ScoreRow.value > best_value,
                    and_(ScoreRow.value == best_value, ScoreRow.computed_at < best_at),
                )
            )
        )
        if weekly:
            ahead_stmt = ahead_stmt.where(ScoreRow.computed_at >= _current_week_start())
        ahead = (await self._session.execute(ahead_stmt)).scalar_one()
        return int(ahead) + 1
