from enum import StrEnum


class LeaderboardPeriod(StrEnum):
    """Time-window the leaderboard is queried against.

    ``StrEnum`` (Python 3.11+) mirrors ``TileType`` / ``BehaviourType`` /
    ``ItemType``: str inheritance means variants serialise cleanly as JSON
    over the HTTP/WebSocket boundary and compare equal to their wire-format
    literals, while still being singletons
    (``LeaderboardPeriod.GLOBAL is LeaderboardPeriod.GLOBAL``) for fast,
    typo-proof comparisons in service code.

    Lives in ``domain/models/`` rather than ``domain/ports/`` because the
    period is a property of the leaderboard concept (CLAUDE.md → "Leaderboard
    — global all-time + weekly"), not a port-specific type. Use cases,
    Pydantic schemas in Phase 3, and the ``IScoreRepository`` Protocol all
    import from the same module.

    Why an enum at all (vs. ``period: str``): the original `top_n(n, period:
    str)` shape was the deliberate antipattern in QUIZZES.md Task 1.11 Q1 —
    strings have no static type-check coverage, allow typos
    (``"weekley"``) to ship to production, and make exhaustiveness checks in
    ``match`` statements impossible.

    v1 surface is ``GLOBAL | WEEKLY`` to match the two leaderboard
    endpoints in CLAUDE.md (``GET /leaderboard/global`` and ``GET
    /leaderboard/weekly``). Future variants (``DAILY``, ``MONTHLY``,
    ``SEASON``) are additive — adapters that don't yet recognise them will
    fail the LSP ordering tests rather than silently mis-bucketing scores.
    """

    GLOBAL = "GLOBAL"
    WEEKLY = "WEEKLY"
