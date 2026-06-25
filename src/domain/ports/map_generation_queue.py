"""Port: outbound queue for asynchronous deep-floor pre-generation.

Structural contract for whatever offloads BSP floor generation off the turn
loop. Deep floors are CPU-bound to generate, and the WebSocket turn loop is
single-threaded async — running a generation inline would block the event loop
(asyncio cannot parallelise pure-Python CPU work under the GIL; only a separate
*process* can). The domain ``process_turn`` therefore refuses to generate the
next floor in-line (``game_service.py`` ``_player_descend``: "Pre-generation of
the next floor is StartGame/Celery's job (task 4.3)"). This port is how the
application asks a worker to pre-generate a floor and stash it in the cache for
the descent path to pick up later (CLAUDE.md → Celery task table:
``map_generation`` — "Offload heavy BSP gen for floors 10+").

The concrete adapter is a Celery task producer in ``src/adapters/tasks/`` (task
4.3). This module never imports it — adapters conform structurally.

Living in ``src/domain/ports/``, this module is bound by the hexagonal golden
rule (CLAUDE.md → "Architecture — Hexagonal / Ports & Adapters"): zero framework
imports. No ``celery``, no ``redis``, no ``pydantic``. The port describes *what*
the application needs — "pre-generate this floor" — not *how* a broker delivers it.

Design choices (mirroring :mod:`score_recalc_queue`):

* **Protocol over ABC** — adapters conform structurally, the dependency arrow
  stays ``adapters → ports``, and the test fake needs no inheritance.
* **Pass primitives, never a domain object** — task arguments cross a process
  boundary and must be JSON-serialisable (the Celery app is JSON-only, never
  pickle — task 4.1), so the worker is handed the *recipe* for the floor
  (``seed`` + ``floor_index``), not a pickled ``Floor``. The worker regenerates
  the geometry itself — ``dungeon_generator.generate`` is a pure deterministic
  function of ``(seed, floor_index)``, so the recipe fully determines the result.
  ``game_id`` namespaces the cache entry to the run; ``floor_id`` is the row
  identifier the generator stamps onto the produced ``Floor`` (the generator
  leaves geometry independent of it — see ``dungeon_generator.generate``), passed
  explicitly so a retried/duplicated job lands a *stable* id rather than minting
  a fresh ``uuid4`` each time. ``UUID``s are the domain type here; the adapter
  stringifies them for the wire, exactly as :class:`IScoreRecalcQueue` does.
* **One method, no admin surface** (ISP) — the only producer is the descent
  path. No ``cancel`` (an orphaned pre-gen entry expires by TTL — quiz 4.3 Q4),
  which would force the test fake to stub a call the application never makes.
* **Async** — adapters do broker I/O; an async contract keeps it consistent with
  the other ports (CLAUDE.md → "Async all the way down").
* **No ``runtime_checkable``** — the project type-checks statically with
  mypy-strict; no ``isinstance`` guards exist or are planned.
"""

from typing import Protocol
from uuid import UUID


class IMapGenerationQueue(Protocol):
    """Outbound port: schedule asynchronous pre-generation of a deep floor.

    Adapters implementing this Protocol own the delivery details (the Celery
    app, the broker connection, routing, retry policy, deduplication). The
    application only sees the contract below.
    """

    async def enqueue(self, game_id: UUID, seed: int, floor_index: int, floor_id: UUID) -> None:
        """Schedule pre-generation of floor ``floor_index`` for run ``game_id``.

        Fire-and-forget from the caller's point of view: returns once the job is
        handed to the broker, not when the floor is generated (the descent path
        polls the cache for readiness). The worker regenerates the geometry from
        ``(seed, floor_index)`` — both fully determine the layout — stamps the
        ``floor_id`` onto it, and writes the serialised ``Floor`` to the cache
        under a key derived from ``(game_id, floor_index)``.

        Idempotency is the *task's* concern, not this port's: the worker
        overwrites the whole cached floor, so a duplicate enqueue (e.g. a
        re-triggered descent) is harmless. The adapter additionally deduplicates
        via a deterministic task id, but exactly-once is unachievable in a
        distributed queue, so idempotency is the real guarantee.

        Adapter-level failures (broker unreachable, serialisation error)
        propagate as exceptions — same convention as :class:`IScoreRecalcQueue`.
        """
        ...
