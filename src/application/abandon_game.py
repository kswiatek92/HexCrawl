"""``AbandonGame`` — the use case for ending a run without scoring.

The write-side command behind ``POST /game/{id}/abandon`` (task 3.8). Where
``StartGame`` (3.1) *creates* a run and ``ProcessTurn`` (3.2) *advances* one,
this *terminates* one at the player's request: it loads the run, checks the
caller owns it, runs the domain ``Abandon`` action, checkpoints the terminal
state, and hands the pair back for the entrypoint to serialise.

Like every use case it is *orchestration*, not game rule: the meaning of
abandoning lives in the domain (``process_turn`` with an ``Abandon`` action
emits ``RunAbandoned`` and sets ``game_over``); this module only wires that to
the persistence ports. Bound by the hexagonal golden rule — it imports domain
models, the domain ports, the domain service, and the sibling ``game_state``
codec only; never an adapter, never a framework.

**No score, by design (QUESTIONS.md task 3.3: "abandoned → no score").** An
abandoned run earns no leaderboard entry, so this use case never touches
``IScoreRepository`` / ``IScoreRecalcQueue`` — it is *not* a thin wrapper over
``SubmitScore``. (It could not be one yet anyway: ``SubmitScore`` needs the
``IScoreRecalcQueue`` adapter, which is Phase 4.) Abandon's whole job is to end
the run, not to record a result.

**Load — cache-first, Postgres-fallback** (mirrors ``GetGame`` / ``ProcessTurn``):
the hot state lives in Redis (CLAUDE.md: "Active game state lives in Redis"); a
lapsed-TTL run is rebuilt from its last Postgres checkpoint. Only when neither
store holds the run is it genuinely gone — :class:`GameNotFoundError`.

**Persist — Postgres checkpoint, then cache refresh.** Abandon is a game-over
turn, so the terminal state is checkpointed to Postgres exactly as
``ProcessTurn`` checkpoints game over. The durable save goes **first**; the
Redis working copy is then refreshed so a subsequent cache-first ``GET`` does
not return the pre-abandon state (there is no ``ICachePort.delete`` to evict it
— eviction is by the 2h TTL).

**Authorisation lives here, beside the data** (``auth.py`` Q5): the HTTP edge
proves *who* the caller is (``get_current_user``); this use case decides whether
the run is *theirs* by comparing ``player.user_id`` to the requester. A foreign
run raises :class:`NotGameOwnerError` (→ 403), distinct from the
:class:`GameNotFoundError` (→ 404) of a run that does not exist. The ownership
check runs *before* any mutation, so a non-owner can never abandon a run.
"""

from uuid import UUID

# Reuse the outcomes the sibling use cases already define rather than minting
# duplicates: "no such run" from ProcessTurn, "not the owner" from GetGame.
from src.application.game_state import (
    GAME_STATE_TTL_SECONDS,
    deserialize_game_state,
    game_state_cache_key,
    serialize_game_state,
)
from src.application.get_game import NotGameOwnerError
from src.application.process_turn import GameNotFoundError
from src.domain.models import Abandon, Dungeon, Player
from src.domain.ports import ICachePort, IGameRepository
from src.domain.services import process_turn

__all__ = ["AbandonGame", "GameNotFoundError", "NotGameOwnerError"]


class AbandonGame:
    """Use case: end a run without scoring, for its owner.

    Ports are constructor-injected (mirroring ``StartGame`` / ``ProcessTurn`` /
    ``GetGame``), so the use case is unit-testable against simple hand-written
    fakes with no Redis or database.
    """

    def __init__(self, games: IGameRepository, cache: ICachePort) -> None:
        self._games = games
        self._cache = cache

    async def execute(self, game_id: UUID, requester_id: UUID) -> tuple[Dungeon, Player]:
        """Abandon ``game_id`` for ``requester_id`` and return its final state.

        Loads the run (cache-first, Postgres-fallback), authorises ownership,
        runs the domain ``Abandon`` action, checkpoints the terminal state to
        Postgres, refreshes the cache, and returns the post-save
        ``(dungeon, player)``. Raises :class:`GameNotFoundError` if no run
        exists for ``game_id``, or :class:`NotGameOwnerError` if it exists but
        belongs to a different user. The ownership check happens before any
        mutation, so a foreign request never ends someone else's run.
        """
        key = game_state_cache_key(game_id)
        dungeon, player = await self._load(game_id, key)

        if player.user_id != requester_id:
            raise NotGameOwnerError(str(game_id))

        # Domain-blessed termination: emits RunAbandoned, sets game_over, and
        # increments turn_count. The TurnResult is intentionally unused — an
        # abandoned run posts no score, so there is no event to dispatch on.
        process_turn(dungeon, player, Abandon())

        # Checkpoint the terminal state durably first (game-over persistence,
        # mirroring ProcessTurn), then refresh the hot copy so a later
        # cache-first GET reflects the abandon rather than pre-abandon state.
        dungeon, player = await self._games.save(dungeon, player)
        await self._cache.set(key, serialize_game_state(dungeon, player), GAME_STATE_TTL_SECONDS)

        return dungeon, player

    async def _load(self, game_id: UUID, key: str) -> tuple[Dungeon, Player]:
        """Load active state: Redis first, Postgres checkpoint on a cache miss.

        Raises :class:`GameNotFoundError` if neither store holds the run.
        """
        blob = await self._cache.get(key)
        if blob is not None:
            return deserialize_game_state(blob)

        loaded = await self._games.get(game_id)
        if loaded is None:
            raise GameNotFoundError(str(game_id))
        return loaded
