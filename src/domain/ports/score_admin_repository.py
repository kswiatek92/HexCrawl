"""Port: score-leaderboard *admin* repository.

The administrative counterpart to :class:`~src.domain.ports.score_repository.IScoreRepository`.
That read/write port deliberately carries **no** admin operations — its
docstring (QUIZZES.md task 1.11 Q4) is explicit: "no ``archive_week()``, no
``reset_weekly()`` … admin operations belong on a separate
``IScoreAdminRepository`` if and when an admin path actually surfaces." Task 4.4
(the ``weekly_leaderboard_reset`` Celery job) is that path, so this is that
separate port — split out per the Interface Segregation Principle, so the many
callers of ``IScoreRepository`` (``SubmitScore``, the ``/leaderboard/*``
endpoints, ``score_recalc``) and their fakes never have to stub an archive
method they do not exercise.

Living in ``src/domain/ports/``, this module obeys the hexagonal golden rule
(CLAUDE.md → "Architecture"): zero framework imports — no SQLAlchemy, no
asyncpg, no Pydantic. It describes *what* the weekly reset needs from
persistence, not *how*. The concrete implementation
(``PostgresScoreAdminRepository``) lives in ``src/adapters/db/`` and conforms
structurally (no inheritance), exactly like the other repositories.

Why this is *archive*-only and never deletes: the weekly leaderboard is
**window-derived**, not a separate row set — ``IScoreRepository.top_n(n,
WEEKLY)`` filters the one shared ``scores`` table by ``computed_at`` against the
current week, and the all-time board reads the same table unwindowed. The weekly
view therefore resets itself when the week boundary advances; deleting "weekly"
rows would destroy the global all-time history that shares them (see
``adapters/db/models.py`` ``ScoreRow``: "scores outlive their runs"). The only
thing lost across the boundary is the *record of who won the finished week*, so
the admin op's job is to preserve that — archive, never wipe.
"""

from typing import Protocol

from src.domain.models import WeeklyArchiveResult


class IScoreAdminRepository(Protocol):
    """Persistence port for leaderboard administration (the weekly reset).

    A single operation for v1. Adapters own the storage details — how a "week"
    is bucketed (the Monday-00:00-UTC boundary), the archive table layout, and
    the transaction boundary (adapters do not commit; the calling use case /
    ambient ``session.begin()`` owns the Unit of Work).
    """

    async def archive_completed_week(self, top_n: int) -> WeeklyArchiveResult:
        """Snapshot the most-recently-*completed* week's ranked top ``top_n``.

        "Completed week" is the window ``[previous Monday 00:00 UTC, this Monday
        00:00 UTC)`` — the week that has just ended. This matters because the
        reset runs *at* the boundary (Celery Beat, Mon 00:00 UTC): by then the
        live weekly window already points at the new, empty week, so the archive
        must reach back one week rather than read the current window.

        Entries are ranked by the leaderboard ordering (``value`` DESC, then
        ``computed_at`` ASC) and written to the durable archive store.

        **Idempotent per week** (QUIZZES.md 4.4 Q3): re-running for the same
        completed week replaces that week's snapshot rather than duplicating it,
        so at-least-once task delivery / a retried job is safe.

        **Non-destructive**: this MUST NOT delete from the ``scores`` table —
        the global all-time board shares those rows.

        Returns a :class:`WeeklyArchiveResult` carrying the archived week's start
        and the entry count. An empty completed week yields ``archived_count ==
        0`` (a normal outcome, not an error). Adapter-level errors (connection
        failure, etc.) propagate as exceptions.
        """
        ...
