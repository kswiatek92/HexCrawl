"""Port: outbound queue for the asynchronous leaderboard recalculation.

Structural contract for whatever offloads the leaderboard rebuild off the
request path. ``SubmitScore`` (task 3.3) persists a :class:`~src.domain.models.Score`
synchronously, then *enqueues* a ``score_recalc`` job through this port; a
worker rebuilds the leaderboard cache out-of-band (CLAUDE.md → Celery task
table: ``score_recalc`` — "Async leaderboard rebuild (non-blocking)"). The
concrete adapter is a Celery task producer in ``src/adapters/tasks/`` and
lands in Phase 4 (task 4.2 builds the task; 4.7 tests the enqueue). This
module never imports it — adapters conform structurally.

Living in ``src/domain/ports/``, this module is bound by the hexagonal golden
rule (CLAUDE.md → "Architecture — Hexagonal / Ports & Adapters"): zero
framework imports. No ``celery``, no ``redis``, no ``pydantic``. The port
describes *what* the application needs — "schedule a recalc for this score" —
not *how* a broker delivers it.

Design choices:

* **Protocol over ABC** — same rationale as the repository / cache ports:
  adapters conform structurally, the dependency arrow stays
  ``adapters → ports``, and the test fake needs no inheritance.
* **Pass the ``score_id``, never a domain object** — a task argument crosses
  a process boundary and must be a minimal, serialisable identifier, not a
  pickled ``Dungeon`` / ``Score`` (QUIZZES.md task 3.3 Q2; mirrors the
  JSON-not-pickle cache-serialisation choice). The worker re-reads whatever
  it needs from Postgres by id, so the leaderboard rebuild always runs
  against the durable copy rather than a snapshot that may already be stale.
  The port speaks the **domain ``UUID`` type**, not ``str``: a raw ``UUID`` is
  not JSON-serialisable by default, so the Celery adapter stringifies it for
  the wire (``str(score_id)``) — serialisation is the *adapter's* job. Keeping
  the port domain-typed mirrors ``IScoreRepository`` speaking ``Score`` (not
  ``dict``): ports speak domain types, adapters own the wire format.
* **One method, no admin surface** (ISP) — the only producer is
  ``SubmitScore``. No ``cancel``, no ``enqueue_weekly_reset`` (that task is
  Celery-Beat-scheduled, not use-case-triggered): they would force the test
  fake to stub calls the application never makes.
* **Async** — adapters do broker I/O; an async contract keeps it consistent
  with the other ports (CLAUDE.md → "Async all the way down") and lets a
  future async producer ``await`` natively.
* **No ``runtime_checkable``** — the project type-checks statically with
  mypy-strict; no ``isinstance`` guards exist or are planned.
"""

from typing import Protocol
from uuid import UUID


class IScoreRecalcQueue(Protocol):
    """Outbound port: schedule the async leaderboard recalculation.

    Adapters implementing this Protocol own the delivery details (the Celery
    app, the broker connection, routing, retry policy). The application only
    sees the contract below.
    """

    async def enqueue(self, score_id: UUID) -> None:
        """Schedule a ``score_recalc`` job for the score identified by ``score_id``.

        Fire-and-forget from the caller's point of view: returns once the job
        is handed to the broker, not when the rebuild completes (the
        leaderboard is eventually consistent — QUIZZES.md task 3.3 Q5). The
        worker re-reads the score and rebuilds the leaderboard cache itself,
        so only the id crosses the boundary.

        Idempotency is the *task's* concern, not this port's: ``score_recalc``
        rebuilds from the durable store and is safe to run more than once, so
        a duplicate enqueue (e.g. a retried submission) is harmless.

        Adapter-level failures (broker unreachable, serialisation error)
        propagate as exceptions — scheduling the rebuild is part of the
        submit command's contract, not a best-effort side effect.
        """
        ...
