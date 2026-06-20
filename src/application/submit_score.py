"""``SubmitScore`` — the use case for finalising a finished run's score.

The third write-side command, after ``StartGame`` (3.1) and ``ProcessTurn``
(3.2). When a run ends — the player dies, wins, or abandons — this use case
computes the final :class:`~src.domain.models.Score`, writes it to the
leaderboard store, and schedules the asynchronous leaderboard rebuild. It is
the seam the WebSocket handler (task 3.9) and the abandon endpoint (task 3.8)
call at game over.

Like every use case it is *orchestration*, not game rule: the scoring formula
lives in the domain (the ``compute_score`` service function → ``compute_score_value``,
ADR-0002); this module only wires that service to the persistence ports in the
right order. Bound by the hexagonal golden rule — it imports domain models, the
domain ports, and the domain service only; never an adapter, never a framework.

**Sync-persist, then enqueue (QUESTIONS.md task 3.3).** The ``Score`` is the
user's run result and must not be lost to a dropped broker message, so it is
written durably through :class:`IScoreRepository` *first*; only then is the
``score_recalc`` job enqueued through :class:`IScoreRecalcQueue`. The
leaderboard rebuild is derived cache work and is eventually consistent
(QUIZZES.md 3.3 Q5) — fine to run out-of-band. The use case does **not**
commit: ``save`` flushes and the ambient request transaction is the Unit of
Work (ADR-0006, mirrors ``StartGame``).

**Idempotency by deterministic id (QUIZZES.md 3.3 Q3).** ``score_id`` is
derived from the run id via ``uuid5`` rather than freshly generated, so a
retried submission produces the *same* id. The repository's
``INSERT ... ON CONFLICT (score_id) DO NOTHING`` then makes the repeat a no-op
— one score per run, enforced at the database. Re-enqueuing the recalc on a
retry is harmless: the task rebuilds from the durable store.

**Abandoned runs score nothing (AskUserQuestion this turn; QUIZZES.md 1.18 Q3).**
"An abandoned run = no leaderboard score" is an orchestration policy, so it
lives here, not in the pure ``compute_score`` service. ``execute`` short-circuits before
computing, persisting, or enqueuing anything. The caller passes ``abandoned``,
derived from a ``RunAbandoned`` event in the run's final ``TurnResult``.

**No Redis cleanup.** The active game-state entry is left to its 2h TTL —
``ICachePort`` has no ``delete`` by deliberate design (see ``cache_port.py``),
so eviction at game over is handled by TTL, not an explicit call. This use case
therefore takes no cache dependency at all.
"""

from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid5

import structlog

from src.application.process_turn import GameNotFoundError
from src.domain.models import Dungeon, Player, Score
from src.domain.ports import IGameRepository, IScoreRecalcQueue, IScoreRepository
from src.domain.services import compute_score

logger = structlog.get_logger(__name__)

# Fixed namespace for deriving a deterministic ``score_id`` from a run id.
# Any constant UUID works — its only job is to scope the uuid5 hash so a run
# id never collides with an unrelated uuid5 name elsewhere in the system. It
# is arbitrary and must never change: changing it would re-key every run and
# break the idempotency guarantee for in-flight submissions.
_SCORE_NAMESPACE: Final[UUID] = UUID("9d3e7b1c-2a4f-4c6e-8b0d-5f1a2c3d4e5f")


class SubmitScore:
    """Use case: finalise and persist a finished run's score.

    Ports are constructor-injected (mirroring ``StartGame`` / ``ProcessTurn``),
    so the use case is unit-testable against simple hand-written fakes with no
    database or broker.
    """

    def __init__(
        self,
        games: IGameRepository,
        scores: IScoreRepository,
        recalc: IScoreRecalcQueue,
    ) -> None:
        self._games = games
        self._scores = scores
        self._recalc = recalc

    async def execute(
        self,
        game_id: UUID,
        *,
        kills: int,
        abandoned: bool = False,
    ) -> Score | None:
        """Finalise the score for ``game_id`` and return it (``None`` if abandoned).

        Loads the finished run's durable state, computes the ``Score``,
        persists it, and enqueues the async leaderboard recalc — in that order.
        Returns the persisted ``Score``, or ``None`` for an abandoned run
        (which earns no leaderboard entry).

        ``kills`` is caller-supplied: no domain model carries a kill counter,
        so the caller aggregates ``EnemyKilled`` events over the run and passes
        the total (``compute_score`` was designed for this). Items
        are not yet pickable in v1 (``PickUp`` is ``not_implemented_v1``), so
        the item multiplier rides ``compute_score``'s empty default.

        Raises :class:`GameNotFoundError` if no run exists for ``game_id``.
        """
        if abandoned:
            # Policy, not formula: an abandoned run posts no score. Short-circuit
            # before any load / compute / persist / enqueue.
            logger.info("submit_score_abandoned_no_score", game_id=str(game_id))
            return None

        dungeon, player = await self._load(game_id)

        # Deterministic id → the DB's ON CONFLICT (score_id) makes a retried
        # submit idempotent (one score per run). computed_at is stamped here,
        # at the impure boundary, never inside the pure compute_score service.
        score = compute_score(
            dungeon,
            player,
            kills=kills,
            score_id=uuid5(_SCORE_NAMESPACE, str(dungeon.dungeon_id)),
            computed_at=datetime.now(UTC),
        )

        # Durable write first: the score must survive even if the broker is
        # down. The repo flushes but does not commit (the request scope owns
        # the transaction). ``save`` returns the canonical post-write entity.
        saved = await self._scores.save(score)

        # Then schedule the eventually-consistent leaderboard rebuild. A
        # failure here propagates — scheduling the recalc is part of submit's
        # contract, and the durable score is already safe.
        await self._recalc.enqueue(saved.score_id)

        logger.info(
            "submit_score_recorded",
            game_id=str(game_id),
            score_id=str(saved.score_id),
            value=saved.value,
        )
        return saved

    async def _load(self, game_id: UUID) -> tuple[Dungeon, Player]:
        """Load the finished run's durable state from Postgres.

        Scoring reads the authoritative copy (``ProcessTurn`` already
        checkpointed it on game over) and runs once, off the hot turn path —
        so there is no cache read here, unlike ``ProcessTurn``. A missing run
        is a normal application outcome, mapped to a 404 / close frame by the
        entrypoint.
        """
        loaded = await self._games.get(game_id)
        if loaded is None:
            raise GameNotFoundError(str(game_id))
        return loaded
