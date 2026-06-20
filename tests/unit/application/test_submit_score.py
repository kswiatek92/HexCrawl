"""Tests for ``src.application.submit_score.SubmitScore``.

Use cases are tested against hand-written fakes for the ports (not
``unittest.mock`` of a real DB/broker client), per CLAUDE.md → "Testing
strategy". Coverage targets the task 3.3 design intent (QUIZZES.md 3.3 Q1–Q5 +
the decisions locked this turn): sync-persist-then-enqueue ordering,
deterministic-id idempotency, the abandoned short-circuit, and the
load-from-durable-store + not-found path.
"""

from uuid import UUID, uuid4, uuid5

import pytest

from src.application.process_turn import GameNotFoundError
from src.application.submit_score import SubmitScore
from src.domain.models import Dungeon, Player, Score
from src.domain.models.score import compute_score_value

# --- Hand-written port fakes ----------------------------------------------


class FakeGameRepository:
    """In-memory :class:`IGameRepository`: ``get`` reads back a seeded run."""

    def __init__(self) -> None:
        self.saved: dict[UUID, tuple[Dungeon, Player]] = {}

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self.saved[dungeon.dungeon_id] = (dungeon, player)
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        return self.saved.get(game_id)


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository`.

    ``save`` is idempotent on ``score_id`` — modelling the adapter's
    ``ON CONFLICT (score_id) DO NOTHING``: a repeat save of the same id keeps
    the first row and never duplicates.
    """

    def __init__(self) -> None:
        self.stored: dict[UUID, Score] = {}

    async def save(self, score: Score) -> Score:
        # DO NOTHING on conflict: the first write wins, repeats are no-ops.
        self.stored.setdefault(score.score_id, score)
        return self.stored[score.score_id]


class FakeScoreRecalcQueue:
    """In-memory :class:`IScoreRecalcQueue` recording every enqueued id.

    Holds a reference to the score repo so it can assert, at enqueue time, that
    the score is *already* persisted — proving the sync-persist-then-enqueue
    ordering rather than just the end state.
    """

    def __init__(self, scores: FakeScoreRepository) -> None:
        self._scores = scores
        self.enqueued: list[UUID] = []
        self.persisted_when_enqueued: list[bool] = []

    async def enqueue(self, score_id: UUID) -> None:
        self.enqueued.append(score_id)
        self.persisted_when_enqueued.append(score_id in self._scores.stored)


# --- Helpers ---------------------------------------------------------------


def _make_run(
    *,
    user_id: UUID | None = None,
    current_floor_index: int = 4,
    damage_taken: int = 7,
) -> tuple[Dungeon, Player]:
    """Build a finished-run ``(Dungeon, Player)`` pair (geometry irrelevant here)."""
    uid = user_id if user_id is not None else uuid4()
    dungeon = Dungeon(
        dungeon_id=uuid4(),
        seed=42,
        floors=[],
        current_floor_index=current_floor_index,
    )
    player = Player(
        user_id=uid,
        name="hero",
        position=(1, 1),
        damage_taken=damage_taken,
    )
    return dungeon, player


def _seed(games: FakeGameRepository, dungeon: Dungeon, player: Player) -> None:
    games.saved[dungeon.dungeon_id] = (dungeon, player)


def _build() -> tuple[SubmitScore, FakeGameRepository, FakeScoreRepository, FakeScoreRecalcQueue]:
    games = FakeGameRepository()
    scores = FakeScoreRepository()
    recalc = FakeScoreRecalcQueue(scores)
    return SubmitScore(games, scores, recalc), games, scores, recalc


# --- Tests -----------------------------------------------------------------


async def test_persists_one_score_and_enqueues_recalc() -> None:
    submit, games, scores, recalc = _build()
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    result = await submit.execute(dungeon.dungeon_id, kills=6)

    assert result is not None
    # Exactly one score persisted, and it is what the use case returned.
    assert list(scores.stored.values()) == [result]
    # Recalc enqueued exactly once, with that score's id.
    assert recalc.enqueued == [result.score_id]


async def test_score_value_matches_domain_formula() -> None:
    submit, games, scores, _ = _build()
    dungeon, player = _make_run(current_floor_index=4, damage_taken=7)
    _seed(games, dungeon, player)

    result = await submit.execute(dungeon.dungeon_id, kills=6)
    assert result is not None

    # floors_reached is the 1-based depth; kills/damage flow straight through.
    expected_floors = dungeon.current_floor_index + 1
    assert result.floors_reached == expected_floors
    assert result.kills == 6
    assert result.damage_taken == player.damage_taken
    assert result.user_id == player.user_id
    assert result.dungeon_id == dungeon.dungeon_id
    assert result.value == compute_score_value(
        floors_reached=expected_floors,
        kills=6,
        item_multiplier=result.item_multiplier,
        damage_taken=player.damage_taken,
    )
    # computed_at is stamped at the boundary and is timezone-aware.
    assert result.computed_at.tzinfo is not None


async def test_score_id_is_deterministic_per_run() -> None:
    # The id is derived from the run id, so two independent SubmitScore
    # instances scoring the same run agree. (Remove the uuid5 derivation in
    # favour of uuid4() and this fails.)
    dungeon, player = _make_run()

    submit_a, games_a, _, _ = _build()
    _seed(games_a, dungeon, player)
    a = await submit_a.execute(dungeon.dungeon_id, kills=3)

    submit_b, games_b, _, _ = _build()
    _seed(games_b, dungeon, player)
    b = await submit_b.execute(dungeon.dungeon_id, kills=3)

    assert a is not None and b is not None
    assert (
        a.score_id
        == b.score_id
        == uuid5(UUID("9d3e7b1c-2a4f-4c6e-8b0d-5f1a2c3d4e5f"), str(dungeon.dungeon_id))
    )


async def test_retried_submission_does_not_double_count() -> None:
    submit, games, scores, recalc = _build()
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    first = await submit.execute(dungeon.dungeon_id, kills=6)
    second = await submit.execute(dungeon.dungeon_id, kills=6)

    # Same id, one stored row — the repeat is a DB-level no-op.
    assert first is not None and second is not None
    assert first.score_id == second.score_id
    assert len(scores.stored) == 1


async def test_score_is_persisted_before_recalc_is_enqueued() -> None:
    # Ordering, not just end state: at the moment enqueue fires the score is
    # already in the repo. (Swap the two awaits in execute() and this fails.)
    submit, games, scores, recalc = _build()
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    await submit.execute(dungeon.dungeon_id, kills=6)

    assert recalc.persisted_when_enqueued == [True]


async def test_abandoned_run_scores_nothing() -> None:
    # Remove the abandoned guard in execute() and a row would be persisted —
    # so this asserts on the *absence* of any persist / enqueue.
    submit, games, scores, recalc = _build()
    dungeon, player = _make_run()
    _seed(games, dungeon, player)

    result = await submit.execute(dungeon.dungeon_id, kills=6, abandoned=True)

    assert result is None
    assert scores.stored == {}
    assert recalc.enqueued == []


async def test_missing_run_raises_and_persists_nothing() -> None:
    submit, _games, scores, recalc = _build()

    with pytest.raises(GameNotFoundError):
        await submit.execute(uuid4(), kills=6)

    assert scores.stored == {}
    assert recalc.enqueued == []
