"""Unit tests for the ``score_recalc`` Celery task + producer (task 4.2).

No broker, no DB, no Redis is contacted: the retry/registration contract is read
off the task object, the sync→async bridge is exercised with the rebuild
monkeypatched out, and the producer is checked by stubbing ``.delay``. The real
worker round-trip (live Postgres + Redis) is integration scope.
"""

import inspect
from uuid import uuid4

import pytest

from src.adapters.tasks import score_recalc as mod
from src.adapters.tasks.celery_app import app
from src.adapters.tasks.score_recalc import CeleryScoreRecalcQueue, score_recalc


def test_task_is_registered_under_its_wire_name() -> None:
    # The producer enqueues by this name; Beat/other callers reference it too.
    assert "score_recalc" in app.tasks
    assert score_recalc.name == "score_recalc"


def test_task_module_is_in_worker_include() -> None:
    # A worker booted via `-A ...celery_app` only imports celery_app; without the
    # module in `include`, the @app.task decorator never runs at boot and the
    # worker rejects the job as an unregistered task. Drop the include and a real
    # worker breaks while this unit suite (which imports the module) stays green —
    # so assert the discovery wiring explicitly.
    assert "src.adapters.tasks.score_recalc" in app.conf.include


def test_retry_contract_matches_recorded_policy() -> None:
    # QUESTIONS.md task 4.2: uniform exponential backoff, capped, 3 retries, with
    # jitter. The jitter is the load-bearing assertion (QUIZZES.md 4.2 Q5):
    # without it, synchronised retries stampede a recovering broker.
    assert score_recalc.autoretry_for == (Exception,)
    assert score_recalc.retry_backoff is True
    assert score_recalc.retry_backoff_max == 600
    assert score_recalc.retry_jitter is True
    assert score_recalc.max_retries == 3


def test_body_runs_the_async_rebuild_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # The sync→async bridge: the task body must drive _rebuild_leaderboard via
    # asyncio.run. Patch the rebuild with an async spy and run the task eagerly
    # (.apply executes the body in-process, binding self — proving bind=True:
    # the body reads self.request.id, which a non-bound task could not supply).
    runs: list[bool] = []

    async def _spy() -> None:
        runs.append(True)

    monkeypatch.setattr(mod, "_rebuild_leaderboard", _spy)

    result = score_recalc.apply(args=[str(uuid4())])

    assert result.successful()
    assert runs == [True]


async def test_producer_enqueues_stringified_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    # The producer's one job beyond delegating to Celery: stringify the UUID for
    # the JSON-only wire (task 4.1). Stub .delay so no broker is touched.
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(score_recalc, "delay", lambda *args: calls.append(args))

    score_id = uuid4()
    await CeleryScoreRecalcQueue().enqueue(score_id)

    assert calls == [(str(score_id),)]


def test_producer_enqueue_is_async() -> None:
    # IScoreRecalcQueue.enqueue is async; the adapter must honour that so a future
    # async producer can await natively (port docstring).
    assert inspect.iscoroutinefunction(CeleryScoreRecalcQueue.enqueue)


# --- _rebuild_leaderboard: resource lifecycle -----------------------------
#
# The bridge builds a throwaway engine + Redis client per run; the contract that
# matters (and the real failure mode) is that BOTH are torn down afterwards —
# otherwise every task invocation leaks a connection pool. These tests fake the
# infrastructure so the wiring and the finally-block cleanup are exercised with
# no real Postgres / Redis.


class _FakeAsyncCM:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def begin(self) -> _FakeAsyncCM:
        return _FakeAsyncCM()


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _patch_infra(monkeypatch: pytest.MonkeyPatch, engine: _FakeEngine, redis: _FakeRedis) -> None:
    monkeypatch.setattr(mod, "create_async_engine", lambda *a, **k: engine)
    monkeypatch.setattr(mod, "create_redis_client", lambda *a, **k: redis)
    monkeypatch.setattr(mod, "async_sessionmaker", lambda *a, **k: (lambda: _FakeSession()))
    monkeypatch.setattr(mod, "PostgresScoreRepository", lambda *a, **k: object())
    monkeypatch.setattr(mod, "RedisCache", lambda *a, **k: object())


async def test_rebuild_runs_use_case_and_disposes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, redis = _FakeEngine(), _FakeRedis()
    _patch_infra(monkeypatch, engine, redis)

    executed: list[bool] = []

    class _FakeRebuild:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self) -> None:
            executed.append(True)

    monkeypatch.setattr(mod, "RebuildLeaderboard", _FakeRebuild)

    await mod._rebuild_leaderboard()

    assert executed == [True]
    assert engine.disposed is True
    assert redis.closed is True


async def test_rebuild_disposes_resources_even_when_use_case_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The finally block is the point: a failed rebuild must not leak the engine /
    # Redis pool. Drop the finally and this leaks (disposed/closed stay False).
    engine, redis = _FakeEngine(), _FakeRedis()
    _patch_infra(monkeypatch, engine, redis)

    class _BoomRebuild:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self) -> None:
            raise RuntimeError("rebuild boom")

    monkeypatch.setattr(mod, "RebuildLeaderboard", _BoomRebuild)

    with pytest.raises(RuntimeError, match="rebuild boom"):
        await mod._rebuild_leaderboard()

    assert engine.disposed is True
    assert redis.closed is True
