"""``GetLeaderboard`` — the cache-aside read behind ``GET /leaderboard/global``.

The leaderboard read-side query (task 3.10; the same use case serves the
``weekly`` board, task 3.11, by ``period``). It returns the ranked top-100
``Score`` slice for a period, reading it from Redis and rebuilding from Postgres
only on a miss.

**Cache-aside (CLAUDE.md → "leaderboard cache"; QUIZZES.md 3.10 Q1).** In
production the slice is kept fresh by the ``score_recalc`` Celery task (Phase 4),
so the hot path is a single cache read. On a miss — a cold key, an expired entry,
or any time before the first recalc — this use case falls back to
:meth:`IScoreRepository.top_n`, **populates** the cache with a TTL
(:data:`LEADERBOARD_CACHE_TTL_SECONDS`), and returns. The empty result is cached
too, so a cold board is read through to Postgres once, not on every request.

Like every use case it is *orchestration*, not domain rule: it wires the score
repository and the cache port together via the sibling ``leaderboard_cache``
codec, and holds no scoring logic. Bound by the hexagonal golden rule — it
imports domain models, the domain ports, and that codec only; never an adapter,
never a framework.
"""

import structlog

from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    deserialize_leaderboard,
    leaderboard_cache_key,
    serialize_leaderboard,
)
from src.domain.models import LeaderboardPeriod, Score
from src.domain.ports import ICachePort, IScoreRepository

logger = structlog.get_logger(__name__)


class GetLeaderboard:
    """Use case: fetch a period's ranked top-100 ``Score`` slice, cache-aside.

    Ports are constructor-injected (mirroring ``GetGame``), so the use case is
    unit-testable against simple hand-written fakes with no Redis or database.
    """

    def __init__(self, scores: IScoreRepository, cache: ICachePort) -> None:
        self._scores = scores
        self._cache = cache

    async def execute(self, period: LeaderboardPeriod = LeaderboardPeriod.GLOBAL) -> list[Score]:
        """Return the ranked top-100 scores for ``period``.

        Reads the cached slice first; on a miss — or a corrupt cache entry —
        rebuilds it from the score repository, re-populates the cache
        (TTL-bounded), and returns. Order is the repository's ranking order
        (``value`` DESC, ``computed_at`` ASC). The entrypoint paginates within
        the returned list.
        """
        key = leaderboard_cache_key(period)

        blob = await self._cache.get(key)
        if blob is not None:
            try:
                scores = deserialize_leaderboard(blob)
            except (ValueError, KeyError, TypeError):
                # A corrupt blob is recoverable: the leaderboard is derived data,
                # so treat a decode failure as a miss and rebuild — the rebuild
                # below overwrites the bad entry (ICachePort has no delete).
                logger.warning("leaderboard_cache_corrupt", period=period.value)
            else:
                logger.debug("leaderboard_cache_hit", period=period.value)
                return scores

        # Miss (or corrupt entry): rebuild from the durable store and re-populate
        # the cache. The empty result is cached too, so a cold board reads
        # through to Postgres once rather than on every request.
        logger.info("leaderboard_cache_miss", period=period.value)
        scores = await self._scores.top_n(LEADERBOARD_SIZE, period)
        await self._cache.set(key, serialize_leaderboard(scores), LEADERBOARD_CACHE_TTL_SECONDS)
        return scores
