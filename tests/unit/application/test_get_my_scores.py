"""Tests for ``src.application.get_my_scores.GetMyScores``.

The per-user read use case behind ``GET /leaderboard/me``, tested against a
hand-written :class:`IScoreRepository` fake (no DB), per CLAUDE.md → "Testing
strategy". Coverage targets the design intent: it reads the user's top-100
personal bests plus their global and weekly board ranks, passes the right args
to each port method, and surfaces ``None`` ranks verbatim (unranked).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.application.get_my_scores import GetMyScores
from src.application.leaderboard_cache import LEADERBOARD_SIZE
from src.domain.models import LeaderboardPeriod, Score

# --- Hand-written port fake -----------------------------------------------


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository` recording per-user read calls.

    Returns a seeded personal-best list and a per-period rank map, and remembers
    the args it was asked for, so a test can assert what the use case requested.
    """

    def __init__(
        self,
        *,
        user_scores: list[Score] | None = None,
        ranks: dict[LeaderboardPeriod, int | None] | None = None,
    ) -> None:
        self.user_scores = user_scores if user_scores is not None else []
        self.ranks = ranks if ranks is not None else {}
        self.top_n_for_user_calls: list[tuple[UUID, int]] = []
        self.rank_of_calls: list[tuple[UUID, LeaderboardPeriod]] = []

    async def save(self, score: Score) -> Score:  # pragma: no cover - unused here
        return score

    async def top_n(  # pragma: no cover - unused here
        self, n: int, period: LeaderboardPeriod
    ) -> list[Score]:
        return []

    async def top_n_for_user(self, user_id: UUID, n: int) -> list[Score]:
        self.top_n_for_user_calls.append((user_id, n))
        return self.user_scores

    async def rank_of(self, user_id: UUID, period: LeaderboardPeriod) -> int | None:
        self.rank_of_calls.append((user_id, period))
        return self.ranks.get(period)


def _score(value: int, *, user_id: UUID) -> Score:
    return Score(
        score_id=uuid4(),
        user_id=user_id,
        dungeon_id=uuid4(),
        floors_reached=5,
        kills=3,
        item_multiplier=1.0,
        damage_taken=2,
        value=value,
        computed_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_returns_user_scores_and_both_ranks() -> None:
    user_id = uuid4()
    scores = [_score(900, user_id=user_id), _score(400, user_id=user_id)]
    repo = FakeScoreRepository(
        user_scores=scores,
        ranks={LeaderboardPeriod.GLOBAL: 3, LeaderboardPeriod.WEEKLY: 1},
    )

    result = await GetMyScores(repo).execute(user_id)

    assert result.scores == scores
    assert result.global_rank == 3
    assert result.weekly_rank == 1


@pytest.mark.asyncio
async def test_requests_top_100_for_the_caller() -> None:
    user_id = uuid4()
    repo = FakeScoreRepository()

    await GetMyScores(repo).execute(user_id)

    # The use case asks the durable store for the user's top-100, scoped to them.
    assert repo.top_n_for_user_calls == [(user_id, LEADERBOARD_SIZE)]


@pytest.mark.asyncio
async def test_queries_both_boards_for_rank() -> None:
    user_id = uuid4()
    repo = FakeScoreRepository()

    await GetMyScores(repo).execute(user_id)

    assert repo.rank_of_calls == [
        (user_id, LeaderboardPeriod.GLOBAL),
        (user_id, LeaderboardPeriod.WEEKLY),
    ]


@pytest.mark.asyncio
async def test_unranked_user_surfaces_none_ranks_and_empty_history() -> None:
    user_id = uuid4()
    # A fresh account: no runs, unranked on both boards. rank_of returns None.
    repo = FakeScoreRepository(user_scores=[], ranks={})

    result = await GetMyScores(repo).execute(user_id)

    assert result.scores == []
    assert result.global_rank is None
    assert result.weekly_rank is None
