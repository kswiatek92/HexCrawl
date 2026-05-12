"""Port: score / leaderboard repository.

Structural contract that any persistence adapter must satisfy to store
:class:`~src.domain.models.Score` aggregates and serve the leaderboard
reads in :mod:`src.entrypoints.http` (Phase 3). Concrete implementations
live in ``src/adapters/db/`` (Phase 2.5) — this module never imports them,
and they conform via structural typing rather than inheritance.

Living in ``src/domain/ports/``, this module is bound by the hexagonal
golden rule (CLAUDE.md → "Architecture — Hexagonal / Ports & Adapters"):
zero framework imports. No SQLAlchemy, no asyncpg, no Pydantic. The port
describes *what* the domain needs from persistence, not *how* it is
implemented.

Design choices are pinned by ``QUIZZES.md`` task 1.11:

* **Protocol over ABC** — same rationale as :mod:`game_repository`:
  adapters conform structurally, the dependency arrow stays
  ``adapters → domain``, and test fakes need no inheritance.
* **`LeaderboardPeriod` enum, not `period: str`** (Q1) — strings have
  no static type-check coverage, allow typo-bound bugs
  (``"weekely"``) to ship, and break exhaustiveness on ``match``.
  The enum lives in ``src/domain/models/leaderboard_period.py``.
* **No read/write hint on the port** (Q2) — the leaderboard is
  read-heavy in production, but indexes, materialised views, read
  replicas, and the Redis leaderboard cache are *adapter* concerns.
  The port stays minimal so adapters can be swapped (in-memory for
  tests, Postgres-with-Redis-cache for prod) without renegotiating
  the contract.
* **Ordering and empty-result semantics are explicit** (Q3 / LSP) —
  every read method's docstring pins the sort order (``value`` DESC,
  then ``computed_at`` ASC) and the empty-result behaviour (``[]``
  or ``None``, never raising). A Postgres adapter that disagreed
  (raises on empty, sorts ascending, returns ``None`` for an empty
  list) would silently violate LSP — the wording here is what makes
  the contract enforceable in the Phase 2.5 integration tests.
* **No admin operations** (Q4) — no ``delete(score_id)``, no
  ``archive_week()``, no ``reset_weekly()``. The use cases that
  call this port (``SubmitScore``, the three ``/leaderboard/*``
  endpoints, the ``score_recalc`` Celery task) never need them.
  Per ISP, admin operations belong on a separate
  ``IScoreAdminRepository`` if and when an admin path actually
  surfaces — adding them here would force every fake to stub
  methods the domain does not exercise.
* **Domain types on every signature** (Q5) — ``Score`` and
  ``list[Score]``, never ``dict`` or ``list[dict]``. Leaking adapter
  row shape across the port would push validation into every caller
  and re-introduce the framework dependency the hexagonal layout
  exists to prevent.
* **Both methods async** — adapters use ``asyncpg`` / SQLAlchemy
  async per CLAUDE.md → "Code conventions — Async all the way
  down".
* **No `runtime_checkable`** — the project type-checks statically
  with mypy-strict; no ``isinstance(x, IScoreRepository)`` guards
  exist or are planned.
"""

from typing import Protocol
from uuid import UUID

from src.domain.models import LeaderboardPeriod, Score


class IScoreRepository(Protocol):
    """Persistence port for :class:`Score` aggregates and leaderboard reads.

    Adapters implementing this Protocol own the storage details
    (PostgreSQL row layout, the indexes that make ``top_n`` cheap, the
    week-boundary truncation rule, transaction boundaries, and whether
    a Redis layer fronts the reads). The domain only sees the contract
    below.
    """

    async def save(self, score: Score) -> Score:
        """Persist ``score`` and return the stored entity.

        Idempotent on ``score.score_id``: calling ``save`` twice with the
        same id is an upsert from the domain's point of view — adapters
        MUST NOT raise on a repeat save of the same aggregate. The
        returned object is the canonical post-write state and may carry
        adapter-refreshed fields not present on the input (e.g. a
        server-assigned ``created_at`` once the Phase 2.5 schema lands).

        Adapter-level errors (connection failure, serialisation bug,
        constraint violation that is not the idempotency case) propagate
        as exceptions; those are infrastructure faults, not domain
        outcomes.
        """
        ...

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        """Return the top ``n`` scores within ``period``.

        **Ordering** (LSP-locked, every adapter MUST honour it):

        * primary: ``Score.value`` descending — highest first.
        * tiebreaker: ``Score.computed_at`` ascending — the earlier run
          wins ties. Pinned so adapters cannot disagree on tied
          rankings, which would surface as nondeterministic leaderboard
          UIs across deploys.

        **Empty / boundary contract:**

        * Returns at most ``n`` results.
        * Returns ``[]`` — never ``None`` — when no qualifying scores
          exist for ``period``.
        * ``n <= 0`` returns ``[]`` without raising. Callers can pass a
          user-supplied page size straight through without a branch.

        ``period`` selects the time window the adapter applies; the
        domain does not know how "weekly" is bucketed (likely
        ``date_trunc('week', computed_at)`` in Postgres) — that
        contract lives with the adapter and its tests.
        """
        ...

    async def top_n_for_user(self, user_id: UUID, n: int) -> list[Score]:
        """Return ``user_id``'s top ``n`` personal-best scores.

        Same ordering rules as :meth:`top_n` (``value`` DESC, then
        ``computed_at`` ASC). Period-agnostic: this powers the
        ``GET /leaderboard/me`` personal-best history view (CLAUDE.md
        → API surface), which lists a user's strongest runs regardless
        of week.

        Returns ``[]`` — never ``None``, never raises — when the user
        has no scores. ``n <= 0`` returns ``[]``. Missing user is not
        an error: a freshly registered account legitimately has zero
        rows.
        """
        ...

    async def rank_of(
        self, user_id: UUID, period: LeaderboardPeriod
    ) -> int | None:
        """Return ``user_id``'s 1-indexed position within ``period``.

        Computed against the same ordering as :meth:`top_n` — so a
        user whose single best score sorts third in the global window
        returns ``3``. Only the user's *single best* score in
        ``period`` is ranked; secondary runs do not contribute to a
        worse-than-first rank.

        Returns ``None`` — never raises — when the user has no
        qualifying score in ``period``. Callers (the ``/leaderboard/me``
        endpoint, future profile views) map ``None`` to "unranked" at
        the entrypoint layer.

        Adapter-level errors (connection failure, etc.) propagate as
        exceptions; "no rank" is a domain outcome, "no database" is
        not.
        """
        ...
