"""``ResetWeeklyLeaderboard`` — the application half of the weekly reset (task 4.4).

The use case behind the ``weekly_leaderboard_reset`` Celery job (CLAUDE.md →
Celery task table: "Archive + reset weekly scores"). It runs once a week, on the
Beat tick at Monday 00:00 UTC, and does two things in order:

1. **Archive first.** Snapshot the *just-completed* week's ranked top-100 into
   the durable archive store via :class:`IScoreAdminRepository`. This is the
   only step that preserves "who won week N" — once the live weekly window
   advances past the boundary, those standings are otherwise unrecoverable.
   Archiving *before* the visible reset is deliberate: no destructive-feeling
   step without a durable copy already taken (QUIZZES.md 4.4 Q1).
2. **Reset the view.** Overwrite the ``leaderboard:WEEKLY`` cache slice with the
   *new* week's standings (empty at the boundary), so a reader sees the fresh
   week immediately instead of the stale finishing-week slice that would linger
   until its TTL (or the next ``score_recalc``) expires it. This is the whole of
   "reset": no rows are deleted — the weekly board is a ``computed_at`` window
   over the shared ``scores`` table (``IScoreRepository.top_n(.., WEEKLY)``), so
   advancing the week *is* the reset; the cache refresh just makes it visible
   now. Mirrors a single period of :class:`RebuildLeaderboard`.

Like every use case it is *orchestration*, not domain rule: it wires the admin
repo, the score repo, and the cache port together through the sibling
``leaderboard_cache`` codec, and holds no leaderboard logic. Bound by the
hexagonal golden rule — it imports domain models, domain ports, and that codec
only; never an adapter (the Celery task that *runs* it constructs the concrete
repos/cache), never a framework.

**Concurrency note (QUESTIONS.md task 4.4; QUIZZES.md 4.4 Q2/Q4).** A
``score_recalc`` running concurrently writes the same ``leaderboard:WEEKLY``
key: a recalc that read the board *before* the boundary could land its write
*after* this one, momentarily restoring the finished week's slice. For v1 that
is accepted, not guarded — the cache is derived and eventually-consistent (the
task-4.1 log-and-drop posture): the very next ``score_recalc`` (fired on the
next game-over) rebuilds the correct new-week slice, and a few minutes of a
stale *cached* weekly board is harmless. The mitigation, if it ever matters, is
a Redis ``SET NX`` lock around the cache write (with the usual Redlock caveats),
added then — not premature infra now.
"""

import structlog

from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    leaderboard_cache_key,
    serialize_leaderboard,
)
from src.domain.models import LeaderboardPeriod
from src.domain.ports import ICachePort, IScoreAdminRepository, IScoreRepository

logger = structlog.get_logger(__name__)


class ResetWeeklyLeaderboard:
    """Use case: archive the finished week, then refresh the weekly cache slice.

    Ports are constructor-injected (mirroring :class:`RebuildLeaderboard`), so
    the use case is unit-testable against simple hand-written fakes with no Redis
    or database.
    """

    def __init__(
        self,
        admin: IScoreAdminRepository,
        scores: IScoreRepository,
        cache: ICachePort,
    ) -> None:
        self._admin = admin
        self._scores = scores
        self._cache = cache

    async def execute(self) -> None:
        """Archive the completed week, then reset the ``leaderboard:WEEKLY`` slice.

        Order is load-bearing: the durable archive is taken first, then the cache
        is refreshed to the new week. Both steps are idempotent (the archive
        replaces its week's snapshot; the cache ``set`` overwrites), so a retried
        task is safe.
        """
        result = await self._admin.archive_completed_week(LEADERBOARD_SIZE)

        new_week = await self._scores.top_n(LEADERBOARD_SIZE, LeaderboardPeriod.WEEKLY)
        await self._cache.set(
            leaderboard_cache_key(LeaderboardPeriod.WEEKLY),
            serialize_leaderboard(new_week),
            LEADERBOARD_CACHE_TTL_SECONDS,
        )

        logger.info(
            "weekly_leaderboard_reset",
            week_start=result.week_start.isoformat(),
            archived=result.archived_count,
            new_week_size=len(new_week),
        )
