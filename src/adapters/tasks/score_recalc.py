"""``score_recalc`` — the Celery worker task + producer for the leaderboard rebuild.

This is the concrete Phase 4 adapter the :class:`IScoreRecalcQueue` port has been
pointing at since task 3.3 (port docstring: "task 4.2 builds the task; 4.7 tests
the enqueue"). Two cohesive halves live here:

* **The worker side** — the ``score_recalc`` Celery task. It runs out-of-band
  after a run is scored and rebuilds the cached leaderboard slices from Postgres.
  The actual rebuild is the application use case :class:`RebuildLeaderboard`; this
  task is the thin *adapter* that stands up the concrete repo/cache and bridges
  Celery's synchronous worker to the async data layer.
* **The producer side** — :class:`CeleryScoreRecalcQueue`, which implements
  :class:`IScoreRecalcQueue` by publishing a ``score_recalc`` message to the
  broker. ``SubmitScore`` enqueues through this (wired in when ``SubmitScore``
  itself is connected to the WS game-over / abandon flow).

As an *adapter* it imports frameworks (``celery``, ``sqlalchemy``, ``redis`` via
``RedisCache``) and therefore must never be imported by ``domain/`` or
``application/`` — the dependency arrow stays ``adapters → application/domain``.

Design notes:

* **Sync→async bridge via ``asyncio.run``** — a Celery worker executes tasks
  synchronously, but the repositories and cache are async (asyncpg, redis.asyncio,
  per CLAUDE.md "Async all the way down"). The task body therefore drives the
  async rebuild with ``asyncio.run``, which spins up a *fresh* event loop per
  invocation. That is also why the engine and Redis client are built *inside* the
  coroutine and torn down before it returns: a connection pool is bound to the
  loop that created it, so a cached one from a previous task's (now-closed) loop
  would be unusable. Per-task construction is the correct simple choice here, not
  a leak. (A persistent worker-level pool is a Phase-6 optimisation, not v1.)

* **Retry policy (QUESTIONS.md task 4.2; QUIZZES.md 4.2 Q5)** — uniform across
  the Phase 4 tasks: retry on any exception with exponential backoff capped at
  600s, ``max_retries=3``, **and jitter**. The jitter is the load-bearing bit:
  without it a broker/Redis outage makes every worker that failed at the same
  instant retry in lockstep, hammering the recovering service in synchronised
  waves (a thundering herd). ``retry_jitter=True`` spreads the retries out.

* **``bind=True``** (QUIZZES.md 4.2 Q3) — gives the task ``self``, so it can log
  its own ``request.id`` and ``request.retries`` for traceability across the
  automatic retries above.

* **Idempotency (Q1/Q4)** — ``score_recalc`` is safe to run more than once, which
  at-least-once delivery requires: :class:`RebuildLeaderboard` fully overwrites
  each slice from the durable store, so a duplicate delivery is harmless. The
  ``score_id`` argument is a logged correlation id; the rebuild re-reads the whole
  ranked slice (which already includes that score) rather than acting on the id
  alone.

* **Failure handling** — a terminal failure (retries exhausted) is caught by the
  ``task_failure`` log-and-drop handler in :mod:`celery_app` (QUESTIONS.md task
  4.1): the durable ``Score`` row is written *before* the recalc is ever enqueued
  (task 3.3), so a dropped rebuild only means a momentarily stale cache that the
  next game-over rebuilds.
"""

import asyncio
from uuid import UUID

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters.cache.redis_cache import RedisCache, create_redis_client
from src.adapters.db.score_repository import PostgresScoreRepository
from src.adapters.tasks.celery_app import app
from src.application.rebuild_leaderboard import RebuildLeaderboard
from src.config import Settings

logger = structlog.get_logger(__name__)


async def _rebuild_leaderboard() -> None:
    """Build the concrete adapters and run the :class:`RebuildLeaderboard` use case.

    Reads :class:`Settings` at call time (not import time) and stands up a
    throwaway async engine + Redis client for this single run, disposing both in
    a ``finally`` so no connection leaks across task invocations. The rebuild
    runs inside ``session.begin()`` — the same per-unit-of-work transaction
    boundary the HTTP/WS paths use — even though it only reads, for a consistent
    session lifecycle (mirrors ``GameSessionRunner``).
    """
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    redis = create_redis_client(settings.redis_url)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session, session.begin():
            use_case = RebuildLeaderboard(PostgresScoreRepository(session), RedisCache(redis))
            await use_case.execute()
    finally:
        await engine.dispose()
        await redis.aclose()


@app.task(  # type: ignore[untyped-decorator]  # celery ships no stubs (mypy-strict)
    bind=True,
    name="score_recalc",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def score_recalc(self: Task, score_id: str) -> None:
    """Rebuild the cached leaderboard slices after a run is scored.

    ``score_id`` is the run's score id (stringified for the JSON wire by the
    producer); it is logged as a correlation id — the rebuild itself recomputes
    the whole ranked slice from Postgres, which already reflects that score.
    """
    logger.info(
        "score_recalc_start",
        score_id=score_id,
        task_id=self.request.id,
        retries=self.request.retries,
    )
    asyncio.run(_rebuild_leaderboard())
    logger.info("score_recalc_done", score_id=score_id)


class CeleryScoreRecalcQueue:
    """Celery producer implementing :class:`IScoreRecalcQueue`.

    Conforms to the port **structurally** (no inheritance) — mypy checks the
    match, exactly like ``RedisCache`` vs ``ICachePort``. Owns the one detail the
    port leaves to the adapter: turning the domain ``UUID`` into the
    JSON-serialisable ``str`` the broker carries (the app is configured
    JSON-only, never pickle — task 4.1).
    """

    async def enqueue(self, score_id: UUID) -> None:
        """Publish a ``score_recalc`` job for ``score_id`` to the broker.

        Fire-and-forget: ``.delay`` hands the message to the broker and returns
        immediately (the rebuild is eventually consistent). The ``UUID`` is
        stringified here because task arguments must be JSON-serialisable.
        """
        score_recalc.delay(str(score_id))
