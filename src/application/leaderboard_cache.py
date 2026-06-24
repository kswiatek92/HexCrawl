"""Leaderboard cache contract: key, TTL, and serialisation.

The leaderboard is read-heavy and bounded (top-100 per period), so its
computed slice is kept in Redis rather than recomputed from Postgres on every
request (CLAUDE.md → "Cache — Redis (active game state, leaderboard cache)").
In production the slice is refreshed by the ``score_recalc`` Celery task
(Phase 4); the read endpoints (tasks 3.10–3.12) read it cache-aside and, on a
miss, rebuild it from :class:`IScoreRepository` and re-populate the cache.

This module is the single home for *how* that cache entry is shaped — the
**key**, the **TTL**, and the **serialisation** of ``list[Score]`` to the
``str`` the cache port speaks. It mirrors :mod:`src.application.game_state`:
per :mod:`src.domain.ports.cache_port` (docstring "Use cases own serialisation,
not the cache adapter"), the conversion lives here in the application layer,
never in the Redis adapter — the adapter stays a generic ``str`` store that
imports no domain type. Bound by the hexagonal rule: domain models only, never
an adapter or a framework.

The wire shape is a JSON array of score objects, ordered exactly as the
repository returned them (``value`` DESC, then ``computed_at`` ASC — see
``IScoreRepository.top_n``). UUIDs serialise as their ``str`` form and
``computed_at`` as ISO-8601 (``datetime.isoformat`` ↔ ``datetime.fromisoformat``).
``serialize_leaderboard`` and ``deserialize_leaderboard`` are exact inverses
over that format.
"""

import json
from datetime import datetime
from typing import Final, cast
from uuid import UUID

from src.domain.models import LeaderboardPeriod, Score

# 5-minute staleness window for a cache-aside re-populate. This is a *chosen*
# number, not derived from a measurement: it bounds how stale a freshly landed
# high score can be when the endpoint itself rebuilt the slice (the steady-state
# refresh is the Phase 4 ``score_recalc`` task, not this TTL). Tune against real
# traffic / the recalc cadence once both exist (QUESTIONS.md Phase 3).
LEADERBOARD_CACHE_TTL_SECONDS: Final[int] = 300

# The leaderboard is the "top 100" per CLAUDE.md's API surface; the cached slice
# holds exactly that many, and the endpoints paginate within it.
LEADERBOARD_SIZE: Final[int] = 100


def leaderboard_cache_key(period: LeaderboardPeriod) -> str:
    """Return the cache key for ``period``'s leaderboard slice.

    The ``leaderboard:`` prefix namespaces these slices away from the
    ``game:`` active-run entries that share the same Redis instance (see
    :func:`src.application.game_state.game_state_cache_key`). ``period.value``
    is the ``StrEnum`` wire string (``"GLOBAL"`` / ``"WEEKLY"``).
    """
    return f"leaderboard:{period.value}"


def serialize_leaderboard(scores: list[Score]) -> str:
    """Serialise an ordered ``list[Score]`` to a JSON string for the cache.

    Order is preserved as given (the repository's ranking order). The inverse,
    :func:`deserialize_leaderboard`, reads this exact shape back.
    """
    return json.dumps([_score_to_dict(score) for score in scores])


def deserialize_leaderboard(blob: str) -> list[Score]:
    """Rebuild the ordered ``list[Score]`` from a cached JSON string.

    The exact inverse of :func:`serialize_leaderboard`. ``json.loads`` is
    untyped (its result is ``Any``); rather than annotate ``Any`` — forbidden in
    the application layer — the parsed values are narrowed with localized
    :func:`cast`, exactly as :mod:`src.application.game_state` does. A malformed
    blob raises (``KeyError`` / ``ValueError`` / ``TypeError``); the caller
    treats that as a corrupt cache entry, not a normal outcome.
    """
    payload = json.loads(blob)
    rows = cast("list[dict[str, object]]", payload)
    return [_score_from_dict(row) for row in rows]


def _score_to_dict(score: Score) -> dict[str, object]:
    return {
        "score_id": str(score.score_id),
        "user_id": str(score.user_id),
        "dungeon_id": str(score.dungeon_id),
        "floors_reached": score.floors_reached,
        "kills": score.kills,
        "item_multiplier": score.item_multiplier,
        "damage_taken": score.damage_taken,
        "value": score.value,
        "computed_at": score.computed_at.isoformat(),
    }


def _score_from_dict(data: dict[str, object]) -> Score:
    return Score(
        score_id=UUID(cast("str", data["score_id"])),
        user_id=UUID(cast("str", data["user_id"])),
        dungeon_id=UUID(cast("str", data["dungeon_id"])),
        floors_reached=cast("int", data["floors_reached"]),
        kills=cast("int", data["kills"]),
        item_multiplier=cast("float", data["item_multiplier"]),
        damage_taken=cast("int", data["damage_taken"]),
        value=cast("int", data["value"]),
        computed_at=datetime.fromisoformat(cast("str", data["computed_at"])),
    )
