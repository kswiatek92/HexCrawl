"""``weekly_leaderboard_reset`` — the Celery worker task for the weekly reset (4.4).

The worker-side adapter behind CLAUDE.md's ``weekly_leaderboard`` task ("Archive
+ reset weekly scores"). It runs once a week — Celery Beat fires it at Monday
00:00 UTC (the schedule itself is task 4.5) — and is a thin *adapter* over the
:class:`ResetWeeklyLeaderboard` application use case: it stands up the concrete
repos/cache and bridges Celery's synchronous worker to the async data layer.

Unlike ``score_recalc`` / ``map_generation`` this task has **no producer half**:
nothing in the application layer enqueues it, so there is no queue port. It is
*scheduled*, not *triggered by a use case* — Beat is its only caller.

As an *adapter* it imports frameworks (``celery``, ``sqlalchemy``, ``redis`` via
``RedisCache``) and must never be imported by ``domain/`` or ``application/`` —
the dependency arrow stays ``adapters → application/domain``.

Design notes (shared with ``score_recalc`` — see that module for the long form):

* **Sync→async bridge via ``asyncio.run``** — a fresh event loop per invocation,
  with the engine + Redis client built *inside* the coroutine and torn down
  before it returns (a pool is bound to its creating loop). The reset reads and
  writes Postgres (the archive) **and** Redis (the weekly cache slice), so unlike
  ``map_generation`` it needs both.

* **Retry policy (QUESTIONS.md task 4.2)** — uniform across the Phase 4 tasks:
  retry on any exception, exponential backoff capped at 600s, ``max_retries=3``,
  with jitter (the load-bearing bit — it breaks the synchronised-retry thundering
  herd against a recovering broker). The use case is idempotent (archive replaces
  its week; cache ``set`` overwrites), so a retried run is safe.

* **``bind=True``** — gives the task ``self`` so it can log its ``request.id`` /
  ``request.retries`` across the automatic retries.

* **Failure handling** — a terminal failure (retries exhausted) is caught by the
  ``task_failure`` log-and-drop handler in :mod:`celery_app` (QUESTIONS.md 4.1).
  The archive is the durable copy; a dropped *cache* refresh only means the
  weekly slice is briefly stale until the next ``score_recalc`` rebuilds it, and
  a missed reset entirely is caught by the following Monday's run.
"""

import asyncio

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.cache.redis_cache import RedisCache, create_redis_client
from src.adapters.db.score_admin_repository import PostgresScoreAdminRepository
from src.adapters.db.score_repository import PostgresScoreRepository
from src.adapters.tasks.celery_app import app
from src.application.reset_weekly_leaderboard import ResetWeeklyLeaderboard
from src.config import Settings

logger = structlog.get_logger(__name__)


async def _reset_weekly() -> None:
    """Build the concrete adapters and run :class:`ResetWeeklyLeaderboard`.

    Reads :class:`Settings` at call time and stands up a throwaway async engine +
    Redis client for this single run, disposing both in a nested ``finally`` (so a
    failing ``engine.dispose()`` cannot skip the Redis teardown — otherwise the
    pool leaks once per retried attempt). The use case runs inside
    ``session.begin()``: the archive's delete+insert is one Unit of Work, and the
    weekly cache refresh follows in the same task.
    """
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    redis = create_redis_client(settings.redis_url)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session, session.begin():
            use_case = ResetWeeklyLeaderboard(
                PostgresScoreAdminRepository(session),
                PostgresScoreRepository(session),
                RedisCache(redis),
            )
            await use_case.execute()
    finally:
        try:
            await engine.dispose()
        finally:
            await redis.aclose()


@app.task(  # type: ignore[untyped-decorator]  # celery ships no stubs (mypy-strict)
    bind=True,
    name="weekly_leaderboard_reset",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def weekly_leaderboard_reset(self: Task) -> None:
    """Archive the completed week and reset the weekly leaderboard slice.

    Takes no arguments — Beat schedules it with none, and there is nothing to
    parameterise (the completed week is derived from the DB clock).
    """
    logger.info(
        "weekly_leaderboard_reset_start",
        task_id=self.request.id,
        retries=self.request.retries,
    )
    asyncio.run(_reset_weekly())
    logger.info("weekly_leaderboard_reset_done", task_id=self.request.id)
