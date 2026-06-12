"""Port: game-state repository.

Structural contract that any persistence adapter must satisfy in order
to store and retrieve a saved run — the ``(Dungeon, Player)`` pair — for
the domain layer. Concrete implementations live in ``src/adapters/db/``
(Phase 2) — this module never imports them, and they conform via
structural typing rather than inheritance.

Living in ``src/domain/ports/``, this module is bound by the hexagonal
golden rule (CLAUDE.md → "Architecture — Hexagonal / Ports & Adapters"):
zero framework imports. No SQLAlchemy, no asyncpg, no Pydantic. The
port describes *what* the domain needs from persistence, not *how* it
is implemented.

Design choices are pinned by ``QUIZZES.md`` task 1.10:

* **Protocol over ABC** (Q1) — ports stay pure interfaces. Adapters in
  external packages (or test fakes) conform structurally with no
  inherit-from-domain coupling, which keeps the dependency arrow
  pointing the right way: ``adapters → ports``, never ``adapters →
  domain-base-class → ports``.
* **`save` takes and returns the `(Dungeon, Player)` pair** (Q2) — a
  saved run is both objects (ADR-0006). Returning them lets adapters
  refresh server-owned fields (e.g. an ``updated_at`` once it lands)
  without a call-site signature change, and keeps the use-case style
  fluent: the returned pair is the canonical post-write state.
* **`get` returns `tuple[Dungeon, Player] | None`** (Q4) — "not found"
  on a ``GET /game/{id}`` lookup is an expected outcome, not exceptional.
  Forcing callers into ``try/except`` for control flow is a code smell;
  ``None`` is checked at the type level by mypy-strict and surfaces
  cleanly through the application layer to a 404 at the entrypoint.
* **Both methods async** — adapters use ``asyncpg`` / SQLAlchemy async
  per CLAUDE.md → "Code conventions — Async all the way down". A sync
  port would force adapters to either block the event loop or wrap
  with ``asyncio.run`` at every call site, neither acceptable.
* **No `runtime_checkable`** (Q3) — the project type-checks statically
  with mypy-strict; no ``isinstance(x, IGameRepository)`` guards exist
  or are planned. Adding the decorator would imply a runtime guarantee
  it does not actually provide (it only checks attribute presence,
  not signatures or return types).
"""

from typing import Protocol
from uuid import UUID

from src.domain.models import Dungeon, Player


class IGameRepository(Protocol):
    """Persistence port for a saved run: the ``(Dungeon, Player)`` pair.

    A run's persisted state is the dungeon aggregate *and* the player who
    is playing it. The domain keeps ``Dungeon`` and ``Player`` as separate
    objects (services take both — ``process_turn(dungeon, player, action)``,
    see ``QUESTIONS.md`` line 41), but a *saved game* is the pair: restoring
    a run without its player would lose HP, position, and the owning user.
    So this port travels both together (see DECISIONS.md ADR-0006). The
    ``Player.user_id`` is also what an adapter records as the run's owner.

    Adapters implementing this Protocol own the storage details
    (PostgreSQL row layout, JSON encoding of ``floors``, transaction
    boundaries, retry semantics). The domain only sees the contract
    below.
    """

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        """Persist the ``(dungeon, player)`` pair and return it.

        Idempotent on ``dungeon.dungeon_id``: calling ``save`` twice with
        the same id is an upsert from the domain's point of view — adapters
        MUST NOT raise on a repeat save of the same run. The player is
        stored 1:1 with the dungeon, and the run's owner is taken from
        ``player.user_id``. The returned pair is the canonical post-write
        state and may carry adapter-refreshed fields not present on input.

        Adapter-level errors (connection failure, serialisation bug,
        constraint violation that is not the idempotency case)
        propagate as exceptions; those are infrastructure faults, not
        domain outcomes.
        """
        ...

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        """Fetch the ``(dungeon, player)`` for ``game_id``, or ``None``.

        ``game_id`` and ``Dungeon.dungeon_id`` are the same value. The
        parameter is named ``game_id`` deliberately — it matches the
        external vocabulary (``GET /game/{id}``, the ``StartGame`` use
        case, ``QUIZZES.md`` task 1.10 Q4) that callers think in. The
        dataclass field name ``dungeon_id`` is the internal-model
        vocabulary. Same identifier, two names depending on which
        side of the port you're on.

        A missing run is a normal outcome (the id was never persisted,
        or the run was hard-deleted by an admin path) and MUST NOT
        raise — it returns ``None``. A run that exists always has its
        player; a dungeon row with no player is a storage-integrity
        fault, which propagates as an exception. Other adapter-level
        errors propagate as exceptions too.
        """
        ...
