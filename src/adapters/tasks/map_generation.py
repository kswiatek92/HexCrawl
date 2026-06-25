"""``map_generation`` — the Celery worker task + producer for deep-floor pre-gen.

The concrete Phase 4 adapter behind the :class:`IMapGenerationQueue` port. Deep
floors are CPU-bound to generate; the WebSocket turn loop is single-threaded
async, so generating one inline would block the event loop (asyncio cannot
parallelise pure-Python CPU work under the GIL — only a separate *process* can,
which is exactly what a Celery worker is). This module offloads that work. Two
cohesive halves, mirroring ``score_recalc.py``:

* **The worker side** — the ``map_generation`` task. It runs out-of-band, builds
  the floor geometry, and writes it to Redis for the descent path to pick up. The
  actual generate-and-cache is the application use case :class:`GenerateFloor`;
  this task is the thin *adapter* that stands up the concrete cache and bridges
  Celery's synchronous worker to the async data layer.
* **The producer side** — :class:`CeleryMapGenerationQueue`, which implements
  :class:`IMapGenerationQueue` by publishing a ``map_generation`` message. The
  descent path enqueues through this when the player approaches a deep floor
  (wired in when the WS loop is connected to deep-floor descent).

As an *adapter* it imports frameworks (``celery``, ``redis`` via ``RedisCache``)
and therefore must never be imported by ``domain/`` or ``application/`` — the
dependency arrow stays ``adapters → application/domain``.

Design notes (the deltas from ``score_recalc``; see that module for the shared
rationale on the sync→async bridge, ``bind=True``, and the retry policy):

* **Cache only, no Postgres.** Pre-generation reads nothing from the relational
  store and writes only to Redis, so ``_generate_floor`` builds a throwaway Redis
  client and disposes it in ``finally`` — but no async engine. (``score_recalc``
  needs both because it reads scores from Postgres.)

* **Deduplication via a deterministic task id** (QUIZZES.md 4.3 Q2) — the producer
  submits with ``task_id=f"map_generation:{game_id}:{floor_index}"`` so two
  triggers for the same floor collapse to one logical job id. Exactly-once is
  unachievable in a distributed queue, so this is best-effort: the real guarantee
  is that :class:`GenerateFloor` overwrites the whole cached floor, making a
  duplicate delivery harmless ("effectively once via idempotency").

* **TTL cleanup, no explicit delete** (QUIZZES.md 4.3 Q4) — a pre-generated floor
  the player never reaches (they die before descending) is cleaned up by the cache
  entry's TTL, set by :class:`GenerateFloor`. There is nothing to delete and no
  cleanup task to run.

* **Failure handling** — terminal failures hit the ``task_failure`` log-and-drop
  handler in :mod:`celery_app` (task 4.1). A dropped pre-gen only means the floor
  is not warm in the cache; the descent path falls back to generating it inline on
  a cache miss, so nothing is lost (the geometry is a pure function of the seed).
"""

import asyncio
from uuid import UUID

import structlog
from celery import Task

from src.adapters.cache.redis_cache import RedisCache, create_redis_client
from src.adapters.tasks.celery_app import app
from src.application.generate_floor import GenerateFloor
from src.config import Settings

logger = structlog.get_logger(__name__)


async def _generate_floor(game_id: UUID, seed: int, floor_index: int, floor_id: UUID) -> None:
    """Build the concrete cache and run :class:`GenerateFloor`.

    Reads :class:`Settings` at call time (not import time) and stands up a
    throwaway Redis client for this single run, closing it in a ``finally`` so no
    connection leaks across task invocations. No Postgres engine — pre-generation
    only writes the cache.
    """
    settings = Settings()
    redis = create_redis_client(settings.redis_url)
    try:
        await GenerateFloor(RedisCache(redis)).execute(game_id, seed, floor_index, floor_id)
    finally:
        await redis.aclose()


@app.task(  # type: ignore[untyped-decorator]  # celery ships no stubs (mypy-strict)
    bind=True,
    name="map_generation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def map_generation(self: Task, game_id: str, seed: int, floor_index: int, floor_id: str) -> None:
    """Pre-generate floor ``floor_index`` for run ``game_id`` and cache it.

    The id arguments arrive as strings (the JSON-only wire — task 4.1); they are
    parsed back to ``UUID`` here and handed to the async bridge.
    """
    logger.info(
        "map_generation_start",
        game_id=game_id,
        floor_index=floor_index,
        task_id=self.request.id,
        retries=self.request.retries,
    )
    asyncio.run(_generate_floor(UUID(game_id), seed, floor_index, UUID(floor_id)))
    logger.info("map_generation_done", game_id=game_id, floor_index=floor_index)


class CeleryMapGenerationQueue:
    """Celery producer implementing :class:`IMapGenerationQueue`.

    Conforms to the port **structurally** (no inheritance), exactly like
    ``CeleryScoreRecalcQueue``. Owns the two adapter-side details the port leaves
    open: stringifying the ``UUID``s for the JSON-only wire, and the deterministic
    ``task_id`` that deduplicates repeat triggers for the same floor.
    """

    async def enqueue(self, game_id: UUID, seed: int, floor_index: int, floor_id: UUID) -> None:
        """Publish a ``map_generation`` job for ``(game_id, floor_index)``.

        Fire-and-forget: ``apply_async`` hands the message to the broker and
        returns immediately. The deterministic ``task_id`` collapses duplicate
        triggers to one logical job; the ``UUID``s are stringified because task
        arguments must be JSON-serialisable.
        """
        map_generation.apply_async(
            args=[str(game_id), seed, floor_index, str(floor_id)],
            task_id=f"map_generation:{game_id}:{floor_index}",
        )
