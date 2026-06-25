"""Unit tests for the ``map_generation`` Celery task + producer (task 4.3).

No broker, no Redis is contacted: the retry/registration contract is read off the
task object, the sync→async bridge is exercised with ``_generate_floor`` either
monkeypatched out (body test) or run against fake infra (lifecycle test), and the
producer is checked by stubbing ``apply_async``. The real worker round-trip (live
Redis) is integration scope. Mirrors ``test_score_recalc.py``.
"""

import inspect
from uuid import uuid4

import pytest

from src.adapters.tasks import map_generation as mod
from src.adapters.tasks.celery_app import app
from src.adapters.tasks.map_generation import CeleryMapGenerationQueue, map_generation


def test_task_is_registered_under_its_wire_name() -> None:
    # The producer enqueues by this name; the descent path references it too.
    assert "map_generation" in app.tasks
    assert map_generation.name == "map_generation"


def test_task_module_is_in_worker_include() -> None:
    # A worker booted via `-A ...celery_app` only imports celery_app; without the
    # module in `include`, the @app.task decorator never runs at boot and the
    # worker rejects the job as unregistered. Assert the discovery wiring.
    assert "src.adapters.tasks.map_generation" in app.conf.include


def test_retry_contract_matches_recorded_policy() -> None:
    # QUESTIONS.md task 4.2: uniform exponential backoff, capped, 3 retries, jitter
    # — applied identically across the Phase 4 tasks.
    assert map_generation.autoretry_for == (Exception,)
    assert map_generation.retry_backoff is True
    assert map_generation.retry_backoff_max == 600
    assert map_generation.retry_jitter is True
    assert map_generation.max_retries == 3


def test_body_parses_ids_and_runs_the_async_bridge_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # The sync→async bridge: the body must drive _generate_floor via asyncio.run,
    # parsing the string ids back to UUIDs. Patch the coroutine with an async spy
    # and run the task eagerly (.apply binds self — proving bind=True, since the
    # body reads self.request.id).
    calls: list[tuple[object, ...]] = []

    async def _spy(*args: object) -> None:
        calls.append(args)

    monkeypatch.setattr(mod, "_generate_floor", _spy)

    game_id, floor_id = uuid4(), uuid4()
    result = map_generation.apply(args=[str(game_id), 555, 10, str(floor_id)])

    assert result.successful()
    # UUIDs reconstructed from the wire strings; seed/index passed through.
    assert calls == [(game_id, 555, 10, floor_id)]


async def test_generate_floor_runs_use_case_and_closes_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    _patch_infra(monkeypatch, redis)

    executed: list[tuple[object, ...]] = []

    class _FakeGenerateFloor:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self, *args: object) -> None:
            executed.append(args)

    monkeypatch.setattr(mod, "GenerateFloor", _FakeGenerateFloor)

    game_id, floor_id = uuid4(), uuid4()
    await mod._generate_floor(game_id, 7, 10, floor_id)

    assert executed == [(game_id, 7, 10, floor_id)]
    assert redis.closed is True


async def test_generate_floor_closes_redis_even_when_use_case_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The finally block is the point: a failed generation must not leak the Redis
    # client. Drop the finally and this leaks (closed stays False).
    redis = _FakeRedis()
    _patch_infra(monkeypatch, redis)

    class _BoomGenerateFloor:
        def __init__(self, *a: object, **k: object) -> None: ...

        async def execute(self, *args: object) -> None:
            raise RuntimeError("gen boom")

    monkeypatch.setattr(mod, "GenerateFloor", _BoomGenerateFloor)

    with pytest.raises(RuntimeError, match="gen boom"):
        await mod._generate_floor(uuid4(), 7, 10, uuid4())

    assert redis.closed is True


async def test_producer_enqueues_with_stringified_ids_and_dedup_task_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The producer's job beyond delegating: stringify UUIDs for the JSON-only wire
    # (task 4.1) and pass a deterministic task_id so duplicate triggers for the
    # same floor collapse to one logical job (quiz 4.3 Q2). Stub apply_async so no
    # broker is touched.
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(map_generation, "apply_async", lambda **kwargs: calls.append(kwargs))

    game_id, floor_id = uuid4(), uuid4()
    await CeleryMapGenerationQueue().enqueue(game_id, 321, 10, floor_id)

    assert calls == [
        {
            "args": [str(game_id), 321, 10, str(floor_id)],
            "task_id": f"map_generation:{game_id}:10",
        }
    ]


def test_producer_enqueue_is_async() -> None:
    # IMapGenerationQueue.enqueue is async; the adapter must honour that so a future
    # async producer can await natively (port docstring).
    assert inspect.iscoroutinefunction(CeleryMapGenerationQueue.enqueue)


# --- fakes for the _generate_floor resource lifecycle ----------------------


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _patch_infra(monkeypatch: pytest.MonkeyPatch, redis: _FakeRedis) -> None:
    monkeypatch.setattr(mod, "create_redis_client", lambda *a, **k: redis)
    monkeypatch.setattr(mod, "RedisCache", lambda *a, **k: object())
