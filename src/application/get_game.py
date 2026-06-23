"""``GetGame`` — the use case for reading a saved run's current state.

The read-side query behind ``GET /game/{id}`` (task 3.7), the counterpart to
``StartGame`` (which *creates* a run) and ``ProcessTurn`` (which *advances* one).
It loads a run's active ``(Dungeon, Player)`` state for a caller, checks the
caller owns it, and hands the pair back for the entrypoint (task 3.7) to
serialise into a ``GameStateResponse``.

Like every use case it is *orchestration*, not game rule: it wires the
persistence ports together and makes the authorisation decision, but holds no
domain logic. Bound by the hexagonal golden rule — it imports domain models,
the domain ports, and the sibling ``game_state`` codec only; never an adapter,
never a framework.

**Load — cache-first, Postgres-fallback (read-only).** The hot, turn-by-turn
state lives in Redis, not Postgres (CLAUDE.md: "Active game state lives in Redis
(TTL 2h)"), so the read tries the cache first — exactly as ``ProcessTurn`` does.
A miss is not fatal: a run whose 2h TTL lapsed is rebuilt from its last Postgres
checkpoint. Only when *neither* holds the run is it genuinely gone —
:class:`GameNotFoundError`. **Unlike ``ProcessTurn``, this is a pure read:** a
``GET`` is a safe/idempotent HTTP method, so on a cache miss we read Postgres and
return it *without* writing back to Redis. The query never mutates state.

**Authorisation lives here, beside the data** (``auth.py`` Q5: "authN at the
edge, authZ next to the resource"). The HTTP edge proves *who* the caller is
(``get_current_user``); this use case decides whether the run is *theirs* by
comparing ``player.user_id`` to the requester. A foreign run raises
:class:`NotGameOwnerError` — which the entrypoint maps to ``403``, distinct from
the ``404`` of a run that does not exist.
"""

from uuid import UUID

from src.application.game_state import deserialize_game_state, game_state_cache_key

# Reuse the "no such run" outcome already defined by ProcessTurn rather than
# minting a second, identical exception — the same precedent SubmitScore follows.
from src.application.process_turn import GameNotFoundError
from src.domain.models import Dungeon, Player
from src.domain.ports import ICachePort, IGameRepository

__all__ = ["GameNotFoundError", "GetGame", "NotGameOwnerError"]


class NotGameOwnerError(Exception):
    """The run exists, but the caller is not its owner.

    An *authorisation* outcome, not a "not found" one: the requester's
    ``user_id`` does not match the run's ``player.user_id``. The entrypoint
    (task 3.7) maps this to ``403 Forbidden`` — deliberately distinct from the
    ``404`` of :class:`GameNotFoundError`. The trade-off is that a non-owner can
    tell a given run id *exists* (403 vs 404); accepted per the project's
    auth convention (``auth.py`` Q5), which reserves 403 for "this isn't yours".
    """


class GetGame:
    """Use case: fetch a run's current ``(Dungeon, Player)`` for its owner.

    Ports are constructor-injected (mirroring ``StartGame`` / ``ProcessTurn``),
    so the use case is unit-testable against simple hand-written fakes with no
    Redis or database.
    """

    def __init__(self, games: IGameRepository, cache: ICachePort) -> None:
        self._games = games
        self._cache = cache

    async def execute(self, game_id: UUID, requester_id: UUID) -> tuple[Dungeon, Player]:
        """Return the ``(dungeon, player)`` for ``game_id``, if ``requester_id`` owns it.

        Loads the active state (cache-first, Postgres-fallback, no write-back),
        then authorises. Raises :class:`GameNotFoundError` if no run exists for
        ``game_id``, or :class:`NotGameOwnerError` if it exists but belongs to a
        different user. Load happens before the ownership check, so an unknown
        id is "not found" and a known-but-foreign id is "forbidden".
        """
        dungeon, player = await self._load(game_id)
        if player.user_id != requester_id:
            raise NotGameOwnerError(str(game_id))
        return dungeon, player

    async def _load(self, game_id: UUID) -> tuple[Dungeon, Player]:
        """Load active state: Redis first, Postgres checkpoint on a cache miss.

        Read-only: a cache miss reads from Postgres but does **not** re-seed the
        cache (contrast ``ProcessTurn``, whose turn write re-seeds it). Raises
        :class:`GameNotFoundError` if neither store holds the run.
        """
        blob = await self._cache.get(game_state_cache_key(game_id))
        if blob is not None:
            return deserialize_game_state(blob)

        loaded = await self._games.get(game_id)
        if loaded is None:
            raise GameNotFoundError(str(game_id))
        return loaded
