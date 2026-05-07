"""Port: game-state repository.

Structural contract that any persistence adapter must satisfy in order
to store and retrieve a :class:`~src.domain.models.Dungeon` for the
domain layer. Concrete implementations live in ``src/adapters/db/``
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
* **`save` returns the saved `Dungeon`** (Q2) — adapters may refresh
  server-owned fields on the returned entity (e.g. an ``updated_at``
  timestamp once Phase 2 schema lands) without requiring a signature
  change at call sites. Also keeps the use-case style fluent: the
  returned object is the canonical post-write state.
* **`get` returns `Dungeon | None`** (Q4) — "not found" on a
  ``GET /game/{id}`` lookup is an expected outcome, not exceptional.
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

from src.domain.models import Dungeon


class IGameRepository(Protocol):
    """Persistence port for :class:`Dungeon` aggregates.

    Adapters implementing this Protocol own the storage details
    (PostgreSQL row layout, JSON encoding of ``floors``, transaction
    boundaries, retry semantics). The domain only sees the contract
    below.
    """

    async def save(self, dungeon: Dungeon) -> Dungeon:
        """Persist ``dungeon`` and return the stored entity.

        Idempotent on ``dungeon.dungeon_id``: calling ``save`` twice
        with the same id is an upsert from the domain's point of
        view — adapters MUST NOT raise on a repeat save of the same
        aggregate. The returned object is the canonical post-write
        state and may carry adapter-refreshed fields not present on
        the input.

        Adapter-level errors (connection failure, serialisation bug,
        constraint violation that is not the idempotency case)
        propagate as exceptions; those are infrastructure faults, not
        domain outcomes.
        """
        ...

    async def get(self, game_id: UUID) -> Dungeon | None:
        """Fetch the dungeon with ``game_id``, or ``None`` if missing.

        A missing row is a normal outcome (the id was never persisted,
        or the run was hard-deleted by an admin path) and MUST NOT
        raise. Adapter-level errors propagate as exceptions.
        """
        ...
