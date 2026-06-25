"""``RebuildLeaderboard`` — the write-side refresh behind the ``score_recalc`` task.

The application half of Phase 4's ``score_recalc`` job (CLAUDE.md → Celery task
table: "Async leaderboard rebuild (non-blocking)"). Where :class:`GetLeaderboard`
(task 3.10) reads a period's slice *cache-aside* — Redis first, Postgres on a miss
— this use case is its mirror image: it unconditionally recomputes every period's
ranked top-100 from Postgres and **overwrites** the cached slice. It is the
steady-state refresher the read path's TTL docstring points at
(``leaderboard_cache.py``: "the steady-state refresh is the Phase 4
``score_recalc`` task, not this TTL").

Triggered out-of-band after each ``SubmitScore`` (a fresh score can change both
the all-time and the weekly board), so it rebuilds **all** periods, not just one.
Iterating :class:`LeaderboardPeriod` keeps that forward-compatible: a future
``DAILY`` / ``SEASON`` variant is refreshed automatically with no edit here.

Like every use case it is *orchestration*, not domain rule: it wires the score
repository and the cache port together through the sibling ``leaderboard_cache``
codec, and holds no scoring logic. Bound by the hexagonal golden rule — it imports
domain models, the domain ports, and that codec only; never an adapter (the
Celery task that *runs* it lives in ``adapters/tasks/`` and constructs the
concrete repo/cache), never a framework.

**Idempotent by construction** (QUIZZES.md 4.2 Q1/Q4). Each run is a full
overwrite from the durable store, so running it twice — as at-least-once delivery
guarantees can happen — leaves the cache in the same state as running it once. No
read-modify-write, nothing to double-count.
"""

import structlog

from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    leaderboard_cache_key,
    serialize_leaderboard,
)
from src.domain.models import LeaderboardPeriod
from src.domain.ports import ICachePort, IScoreRepository

logger = structlog.get_logger(__name__)


class RebuildLeaderboard:
    """Use case: recompute and overwrite every period's cached leaderboard slice.

    Ports are constructor-injected (mirroring :class:`GetLeaderboard`), so the
    use case is unit-testable against simple hand-written fakes with no Redis or
    database.
    """

    def __init__(self, scores: IScoreRepository, cache: ICachePort) -> None:
        self._scores = scores
        self._cache = cache

    async def execute(self) -> None:
        """Rebuild the cached top-100 slice for every :class:`LeaderboardPeriod`.

        For each period: read the ranked slice from the durable store
        (``value`` DESC, ``computed_at`` ASC — :meth:`IScoreRepository.top_n`),
        serialise it via the shared codec, and overwrite the cache entry with a
        bounded TTL. An empty period is written as an empty slice too, so a cold
        board is represented explicitly rather than left to a stale entry.
        """
        for period in LeaderboardPeriod:
            scores = await self._scores.top_n(LEADERBOARD_SIZE, period)
            await self._cache.set(
                leaderboard_cache_key(period),
                serialize_leaderboard(scores),
                LEADERBOARD_CACHE_TTL_SECONDS,
            )
            logger.debug("leaderboard_slice_rebuilt", period=period.value, count=len(scores))
