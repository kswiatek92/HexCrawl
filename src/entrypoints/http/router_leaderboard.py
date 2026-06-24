"""Leaderboard router — public read endpoints for the score boards.

Like the game router, routes here are thin adapters: they parse query params
(Pydantic via ``Query``), invoke a read use case, and map the domain result to a
response schema. No scoring or ranking rule lives here — ordering is the
repository's contract (``IScoreRepository.top_n``), caching is the use case's
(``GetLeaderboard``).

``GET /global`` (task 3.10) is **unauthenticated**: the all-time board is public
per CLAUDE.md's API surface. Only ``GET /me`` (task 3.12) will
``Depends(get_current_user)``. The weekly board (3.11) reuses the same use case
with a different ``LeaderboardPeriod``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.get_leaderboard import GetLeaderboard
from src.application.leaderboard_cache import LEADERBOARD_SIZE
from src.domain.models import LeaderboardPeriod
from src.entrypoints.http.dependencies import get_leaderboard
from src.entrypoints.http.schemas import LeaderboardResponse

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/global")
async def leaderboard_global(
    use_case: Annotated[GetLeaderboard, Depends(get_leaderboard)],
    limit: Annotated[int, Query(ge=1, le=LEADERBOARD_SIZE)] = LEADERBOARD_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeaderboardResponse:
    """Return the all-time global top scores, served from the Redis cache.

    Public (no auth). The use case reads the ranked top-100 slice cache-aside —
    a cache hit is a single Redis read; a miss rebuilds from Postgres and
    re-populates the cache. ``limit``/``offset`` paginate within that slice
    (fixed page size cap of 100, QUESTIONS.md Phase 3 decision); an out-of-range
    ``limit``/``offset`` is rejected as ``422`` by the query schema before the
    use case runs. Ranks in the response are absolute (``offset``-aware), not
    page-relative.
    """
    scores = await use_case.execute(LeaderboardPeriod.GLOBAL)
    return LeaderboardResponse.from_scores(
        LeaderboardPeriod.GLOBAL, scores, offset=offset, limit=limit
    )


@router.get("/weekly")
async def leaderboard_weekly(
    use_case: Annotated[GetLeaderboard, Depends(get_leaderboard)],
    limit: Annotated[int, Query(ge=1, le=LEADERBOARD_SIZE)] = LEADERBOARD_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeaderboardResponse:
    """Return this week's top scores, served from the Redis cache.

    Identical to ``/global`` (same use case, same cache-aside read, same public
    no-auth access, same ``limit``/``offset`` pagination over the top-100) — the
    *only* difference is the period: ``WEEKLY`` scopes the board to the current
    week. The window itself (Monday 00:00 UTC, per CLAUDE.md's Celery weekly
    reset) is the repository's contract, applied in ``IScoreRepository.top_n``;
    the period also namespaces a distinct cache key (``leaderboard:WEEKLY``), so
    the weekly and global slices never collide.
    """
    scores = await use_case.execute(LeaderboardPeriod.WEEKLY)
    return LeaderboardResponse.from_scores(
        LeaderboardPeriod.WEEKLY, scores, offset=offset, limit=limit
    )
