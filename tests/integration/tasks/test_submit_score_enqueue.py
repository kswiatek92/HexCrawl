"""Task 4.7 — ``SubmitScore`` enqueues the ``score_recalc`` task correctly.

This is the *wiring* test the :class:`IScoreRecalcQueue` port has pointed at since
task 3.3 (port docstring: "4.2 builds the task; 4.7 tests the enqueue"). It closes
a seam that no existing test covers, because the two halves are tested in isolation:

* ``tests/unit/application/test_submit_score.py`` (3.3) drives ``SubmitScore`` against
  a **hand-written fake** queue — the real Celery producer never runs.
* ``tests/unit/adapters/tasks/test_score_recalc.py`` (4.2) drives
  ``CeleryScoreRecalcQueue.enqueue`` directly with an arbitrary ``uuid4()`` — there is
  no ``SubmitScore`` in front, so it can't catch the id the *use case* computes from a
  run diverging from the id that reaches the task.

Here we wire the **real** ``SubmitScore`` use case to the **real**
``CeleryScoreRecalcQueue`` producer (and therefore the real, registered ``score_recalc``
task object), with only the data layer faked. The ``score_recalc.delay`` boundary is
spied — not forwarded — so no broker is contacted and the task *body* never runs (that
body's ``asyncio.run(_rebuild_leaderboard())`` is exercised separately in the 4.2 suite
via ``.apply()``, and would deadlock if run eagerly inside this test's event loop). What
this proves end-to-end: finishing a run dispatches exactly one ``score_recalc`` job,
addressed at the registered task, carrying the JSON-serialisable id the use case
persisted — and nothing at all for an abandoned run.
"""

from uuid import UUID, uuid4

import pytest

from src.adapters.tasks.score_recalc import CeleryScoreRecalcQueue, score_recalc
from src.application.submit_score import SubmitScore
from src.domain.models import Dungeon, Player, Score

# --- Fake data-layer ports (queue is REAL — that's the point of this test) -----
#
# Mirrors the fakes in tests/unit/application/test_submit_score.py: the use case
# needs an IGameRepository to load the finished run and an IScoreRepository to
# persist the score. Neither does real I/O. The IScoreRecalcQueue, by contrast, is
# the production CeleryScoreRecalcQueue — this test is about *that* seam.


class FakeGameRepository:
    """In-memory ``IGameRepository``: ``get`` reads back a seeded run."""

    def __init__(self) -> None:
        self.saved: dict[UUID, tuple[Dungeon, Player]] = {}

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self.saved[dungeon.dungeon_id] = (dungeon, player)
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        return self.saved.get(game_id)


class FakeScoreRepository:
    """In-memory ``IScoreRepository`` (idempotent on ``score_id``, like the real repo)."""

    def __init__(self) -> None:
        self.stored: dict[UUID, Score] = {}

    async def save(self, score: Score) -> Score:
        self.stored.setdefault(score.score_id, score)
        return self.stored[score.score_id]


# --- Helpers -------------------------------------------------------------------


def _make_run() -> tuple[Dungeon, Player]:
    """Build a finished-run ``(Dungeon, Player)`` pair (geometry irrelevant here)."""
    dungeon = Dungeon(dungeon_id=uuid4(), seed=42, floors=[], current_floor_index=4)
    player = Player(user_id=uuid4(), name="hero", position=(1, 1), damage_taken=7)
    return dungeon, player


def _build(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SubmitScore, FakeGameRepository, FakeScoreRepository, list[tuple[object, ...]]]:
    """Wire SubmitScore to the REAL Celery producer; spy on the registered task's ``.delay``.

    The producer (``CeleryScoreRecalcQueue.enqueue``) calls ``score_recalc.delay(...)``,
    resolving the attribute at call time — so patching ``score_recalc.delay`` records the
    exact arg the real producer hands the real, registered task, without touching a broker
    or running the task body.
    """
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(score_recalc, "delay", lambda *args: calls.append(args))

    games = FakeGameRepository()
    scores = FakeScoreRepository()
    submit = SubmitScore(games, scores, CeleryScoreRecalcQueue())
    return submit, games, scores, calls


def _seed(games: FakeGameRepository, dungeon: Dungeon, player: Player) -> None:
    games.saved[dungeon.dungeon_id] = (dungeon, player)


# --- Tests ---------------------------------------------------------------------


async def test_execute_enqueues_score_recalc_for_the_persisted_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The seam: a finished run dispatches exactly one score_recalc job whose id is the
    # one the use case computed and persisted. Break either side — SubmitScore enqueues
    # the wrong id, or stops enqueuing — and the equality / count fails. (Distinct from
    # the 4.2 producer test, which used a bare uuid4 with no SubmitScore in front.)
    submit, games, scores, calls = _build(monkeypatch)
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    result = await submit.execute(dungeon.dungeon_id, kills=6)

    assert result is not None
    assert result.score_id in scores.stored  # persisted before enqueue (real producer path)
    assert calls == [(str(result.score_id),)]


async def test_enqueued_arg_is_a_json_serialisable_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The Celery wire is JSON-only (task 4.1), so the id must cross as a str, not a raw
    # UUID. The real producer owns that conversion; assert it actually happens end-to-end.
    # Have the producer pass the UUID through unconverted and this fails.
    submit, games, scores, calls = _build(monkeypatch)
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    result = await submit.execute(dungeon.dungeon_id, kills=6)
    assert result is not None

    (enqueued_arg,) = calls[0]
    assert isinstance(enqueued_arg, str)
    assert enqueued_arg == str(result.score_id)


async def test_abandoned_run_enqueues_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Policy (QUESTIONS.md 3.3): an abandoned run posts no score and schedules no recalc.
    # The short-circuit lives in SubmitScore; remove it and a job would be dispatched here.
    submit, games, scores, calls = _build(monkeypatch)
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    result = await submit.execute(dungeon.dungeon_id, kills=6, abandoned=True)

    assert result is None
    assert scores.stored == {}
    assert calls == []


def test_producer_targets_the_registered_score_recalc_task() -> None:
    # The producer enqueues by dispatching the module-level `score_recalc` task object,
    # which must be the one registered under its wire name "score_recalc" — otherwise a
    # real worker (booted from celery_app) would never receive the job. This anchors the
    # spied `.delay` in the tests above to the *real* registered task, not a stray object.
    assert score_recalc.name == "score_recalc"
