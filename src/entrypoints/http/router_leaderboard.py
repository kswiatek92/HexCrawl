"""Leaderboard router — public read endpoints for the score boards.

Like the game router, routes here are thin adapters: they parse query params
(Pydantic via ``Query``), invoke a read use case, and map the domain result to a
response schema. No scoring or ranking rule lives here — ordering is the
repository's contract (``IScoreRepository.top_n``), caching is the use case's
(``GetLeaderboard``).

``GET /global`` (task 3.10) and ``GET /weekly`` (3.11) are **unauthenticated**:
the all-time and weekly boards are public per CLAUDE.md's API surface, and both
reuse one ``GetLeaderboard`` use case with a different ``LeaderboardPeriod``.
``GET /me`` (task 3.12) is the lone authenticated route — it
``Depends(get_current_user)`` and serves a per-user board through the separate,
uncached ``GetMyScores`` use case.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.get_leaderboard import GetLeaderboard
from src.application.get_my_scores import GetMyScores
from src.application.leaderboard_cache import LEADERBOARD_SIZE
from src.domain.models import LeaderboardPeriod
from src.entrypoints.http.auth import AuthenticatedUser, get_current_user
from src.entrypoints.http.dependencies import get_leaderboard, get_my_scores
from src.entrypoints.http.schemas import LeaderboardResponse, MyScoresResponse

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


@router.get("/me")
async def leaderboard_me(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[GetMyScores, Depends(get_my_scores)],
    limit: Annotated[int, Query(ge=1, le=LEADERBOARD_SIZE)] = LEADERBOARD_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MyScoresResponse:
    """Return the authenticated caller's best runs and their board standings.

    The only **authenticated** leaderboard route (``Depends(get_current_user)``):
    ``global`` / ``weekly`` are public, but "me" is scoped to the caller, whose
    identity comes from the verified bearer token, never a query param — a client
    cannot read another user's board. A missing/invalid token is rejected as
    ``401`` by ``get_current_user`` before the use case runs.

    Unlike the public boards this is not cache-served: the slice is per-user, so
    the use case reads straight through to Postgres. ``limit``/``offset``
    paginate the user's run history (same fixed cap of 100, QUESTIONS.md Phase 3
    decision); an out-of-range value is a ``422`` from the query schema. The two
    ``*_rank`` fields are pagination-independent — they report where the user's
    single best run sits on each public board, or ``null`` when unranked.
    """
    my_scores = await use_case.execute(current_user.user_id)
    return MyScoresResponse.from_my_scores(
        my_scores.scores,
        global_rank=my_scores.global_rank,
        weekly_rank=my_scores.weekly_rank,
        offset=offset,
        limit=limit,
    )
