"""Unit tests for the ``weekly_leaderboard_reset`` Celery task (task 4.4).

No broker, no DB, no Redis is contacted: the retry/registration contract is read
off the task object, and the sync→async bridge is exercised with the reset
use case monkeypatched out. The real worker round-trip (live Postgres + Redis) is
integration scope (the archive SQL is covered by
``tests/integration/adapters/db/test_score_admin_repository.py``).

Mirrors ``test_score_recalc.py``; the one structural difference is that this task
has no producer half (it is Beat-triggered, not enqueued), so there is nothing
like ``CeleryScoreRecalcQueue`` to test.
"""

import pytest

from src.adapters.tasks import weekly_leaderboard_reset as mod
from src.adapters.tasks.celery_app import app
from src.adapters.tasks.weekly_leaderboard_reset import weekly_leaderboard_reset


def test_task_is_registered_under_its_wire_name() -> None:
    # Beat references the task by this name when it schedules it (task 4.5).
    assert "weekly_leaderboard_reset" in app.tasks
    assert weekly_leaderboard_reset.name == "weekly_leaderboard_reset"


def test_task_module_is_in_worker_include() -> None:
    # A worker booted via `-A ...celery_app` only imports celery_app; without the
    # module in `include`, the @app.task decorator never runs at boot and the
    # worker rejects the job as unregistered. Drop the include and a real worker
    # breaks while this unit suite (which imports the module) stays green — so
    # assert the discovery wiring explicitly.
    assert "src.adapters.tasks.weekly_leaderboard_reset" in app.conf.include


def test_retry_contract_matches_recorded_policy() -> None:
    # QUESTIONS.md task 4.2: uniform exponential backoff, capped, 3 retries, with
    # jitter — the same policy across the Phase 4 tasks. The jitter is the
    # load-bearing assertion: without it, synchronised retries stampede a
    # recovering broker.
    assert weekly_leaderboard_reset.autoretry_for == (Exception,)
    assert weekly_leaderboard_reset.retry_backoff is True
    assert weekly_leaderboard_reset.retry_backoff_max == 600
    assert weekly_leaderboard_reset.retry_jitter is True
    assert weekly_leaderboard_reset.max_retries == 3


def test_body_runs_the_async_reset_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # The sync→async bridge: the task body must drive _reset_weekly via
    # asyncio.run. Patch the reset with an async spy and run the task eagerly
    # (.apply executes the body in-process, binding self — proving bind=True: the
    # body reads self.request.id, which a non-bound task could not supply).
    runs: list[bool] = []

    async def _spy() -> None:
        runs.append(True)

    monkeypatch.setattr(mod, "_reset_weekly", _spy)

    result = weekly_leaderboard_reset.apply(args=[])

    assert result.successful()
    assert runs == [True]


# --- _reset_weekly: resource lifecycle ------------------------------------
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
    monkeypatch.setattr(mod, "PostgresScoreAdminRepository", lambda *a, **k: object())
    monkeypatch.setattr(mod, "PostgresScoreRepository", lambda *a, **k: object())
    monkeypatch.setattr(mod, "RedisCache", lambda *a, **k: object())


async def test_reset_runs_use_case_and_disposes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, redis = _FakeEngine(), _FakeRedis()
    _patch_infra(monkeypatch, engine, redis)

    executed: list[bool] = []

    class _FakeReset:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self) -> None:
            executed.append(True)

    monkeypatch.setattr(mod, "ResetWeeklyLeaderboard", _FakeReset)

    await mod._reset_weekly()

    assert executed == [True]
    assert engine.disposed is True
    assert redis.closed is True


async def test_reset_disposes_resources_even_when_use_case_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The finally block is the point: a failed reset must not leak the engine /
    # Redis pool. Drop the finally and this leaks (disposed/closed stay False).
    engine, redis = _FakeEngine(), _FakeRedis()
    _patch_infra(monkeypatch, engine, redis)

    class _BoomReset:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self) -> None:
            raise RuntimeError("reset boom")

    monkeypatch.setattr(mod, "ResetWeeklyLeaderboard", _BoomReset)

    with pytest.raises(RuntimeError, match="reset boom"):
        await mod._reset_weekly()

    assert engine.disposed is True
    assert redis.closed is True


async def test_reset_closes_redis_even_when_engine_dispose_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The nested-finally guarantee: a failing engine.dispose() must NOT skip the
    # Redis teardown. Flatten the finally back to two sequential awaits and this
    # leaks (redis.closed stays False).
    engine, redis = _FakeEngine(), _FakeRedis()
    _patch_infra(monkeypatch, engine, redis)

    async def _boom_dispose() -> None:
        raise RuntimeError("dispose boom")

    monkeypatch.setattr(engine, "dispose", _boom_dispose)

    class _NoopReset:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self) -> None: ...

    monkeypatch.setattr(mod, "ResetWeeklyLeaderboard", _NoopReset)

    with pytest.raises(RuntimeError, match="dispose boom"):
        await mod._reset_weekly()

    # dispose raised and propagated, but Redis was still closed.
    assert redis.closed is True
