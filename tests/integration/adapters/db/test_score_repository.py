"""Integration tests for PostgresScoreRepository against a real Postgres.

Covers the live-SQL behaviour the in-memory mapper unit tests
(``tests/unit/adapters/db/test_score_repository.py``) defer to task 2.6: the
full round trip through ``timestamptz`` / ``float`` columns, the
``ON CONFLICT (score_id) DO NOTHING`` idempotency (no overwrite — Score is
immutable), the port-locked ordering (value DESC, computed_at ASC, score_id
ASC), the ``date_trunc('week')`` weekly window, ``top_n_for_user`` scoping, and
``rank_of``.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.adapters.db.score_repository import PostgresScoreRepository
from src.domain.models import LeaderboardPeriod, Score

# Fixed timestamps for window-independent ordering tests (GLOBAL ignores the
# week window). All carry UTC tzinfo to match the timestamptz column.
_EARLY = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
_LATE = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)


def _score(
    *,
    value: int,
    computed_at: datetime = _EARLY,
    user_id: UUID | None = None,
    score_id: UUID | None = None,
) -> Score:
    return Score(
        score_id=score_id or uuid4(),
        user_id=user_id or uuid4(),
        dungeon_id=uuid4(),
        floors_reached=7,
        kills=13,
        item_multiplier=2.5,
        damage_taken=4,
        value=value,
        computed_at=computed_at,
    )


async def _save_committed(
    sessionmaker: async_sessionmaker[AsyncSession],
    *scores: Score,
) -> None:
    """Persist scores in one committed transaction (the use case's UoW)."""
    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        for score in scores:
            await repo.save(score)
        await session.commit()


async def test_save_round_trips_full_score(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # One score read back via top_n must equal the input field-for-field —
    # exercises the float item_multiplier and the timestamptz computed_at.
    score = _score(value=812)
    await _save_committed(sessionmaker, score)

    async with sessionmaker() as session:
        result = await PostgresScoreRepository(session).top_n(1, LeaderboardPeriod.GLOBAL)

    assert result == [score]


async def test_save_does_not_commit(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # UoW contract: save() executes the insert but leaves commit to the caller.
    # An independent session sees nothing until then.
    score = _score(value=500)
    async with sessionmaker() as writer:
        await PostgresScoreRepository(writer).save(score)
        # no writer.commit()
        async with sessionmaker() as reader:
            assert await PostgresScoreRepository(reader).top_n(10, LeaderboardPeriod.GLOBAL) == []


async def test_save_is_idempotent_and_does_not_overwrite(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Re-saving the same score_id is a no-op (ON CONFLICT DO NOTHING), not a PK
    # violation — and the original row is preserved, not overwritten (Score is
    # immutable, so DO NOTHING rather than DO UPDATE).
    sid = uuid4()
    await _save_committed(sessionmaker, _score(value=100, score_id=sid))
    await _save_committed(sessionmaker, _score(value=999, score_id=sid))

    async with sessionmaker() as session:
        result = await PostgresScoreRepository(session).top_n(10, LeaderboardPeriod.GLOBAL)

    assert len(result) == 1
    assert result[0].value == 100  # the first write survives, not 999


async def test_top_n_orders_by_value_desc_and_limits(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _save_committed(
        sessionmaker,
        _score(value=100),
        _score(value=300),
        _score(value=200),
    )
    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        top_all = await repo.top_n(10, LeaderboardPeriod.GLOBAL)
        top_two = await repo.top_n(2, LeaderboardPeriod.GLOBAL)

    assert [s.value for s in top_all] == [300, 200, 100]
    assert [s.value for s in top_two] == [300, 200]  # limit honoured


async def test_top_n_tiebreakers(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # All equal value -> earlier computed_at wins; equal value AND time ->
    # smaller score_id wins (the final deterministic tiebreaker).
    a = _score(value=500, computed_at=_EARLY, score_id=uuid4())
    later_big = _score(value=500, computed_at=_LATE, score_id=UUID(int=2))
    later_small = _score(value=500, computed_at=_LATE, score_id=UUID(int=1))
    await _save_committed(sessionmaker, later_big, a, later_small)

    async with sessionmaker() as session:
        result = await PostgresScoreRepository(session).top_n(10, LeaderboardPeriod.GLOBAL)

    # a (earliest), then the two LATE rows by ascending score_id (int=1 before int=2).
    assert [s.score_id for s in result] == [a.score_id, later_small.score_id, later_big.score_id]


async def test_top_n_weekly_window_excludes_old_scores(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    # `now` is always within the current week; two weeks back is always before
    # this week's Monday 00:00 UTC — robust regardless of the weekday the test runs.
    recent = _score(value=10, computed_at=now)
    old = _score(value=1000, computed_at=now - timedelta(days=14))
    await _save_committed(sessionmaker, recent, old)

    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        weekly = await repo.top_n(10, LeaderboardPeriod.WEEKLY)
        global_ = await repo.top_n(10, LeaderboardPeriod.GLOBAL)

    assert [s.score_id for s in weekly] == [recent.score_id]  # old one filtered out
    # GLOBAL ignores the window and includes both, ordered by value desc.
    assert [s.score_id for s in global_] == [old.score_id, recent.score_id]


async def test_top_n_for_user_scopes_to_user(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user = uuid4()
    other = uuid4()
    mine_low = _score(value=100, user_id=user)
    mine_high = _score(value=300, user_id=user)
    theirs = _score(value=500, user_id=other)
    await _save_committed(sessionmaker, mine_low, mine_high, theirs)

    async with sessionmaker() as session:
        result = await PostgresScoreRepository(session).top_n_for_user(user, 10)

    # Only this user's scores, ordered value DESC; the other user's higher score absent.
    assert [s.score_id for s in result] == [mine_high.score_id, mine_low.score_id]


async def test_rank_of(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    first = uuid4()
    second = uuid4()
    third = uuid4()
    await _save_committed(
        sessionmaker,
        _score(value=300, user_id=first),
        _score(value=200, user_id=second),
        _score(value=100, user_id=third),
    )
    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        assert await repo.rank_of(first, LeaderboardPeriod.GLOBAL) == 1
        assert await repo.rank_of(second, LeaderboardPeriod.GLOBAL) == 2
        assert await repo.rank_of(third, LeaderboardPeriod.GLOBAL) == 3
        # A user with no qualifying score is unranked, not an error.
        assert await repo.rank_of(uuid4(), LeaderboardPeriod.GLOBAL) is None


async def test_rank_of_uses_weekly_window(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # rank_of(WEEKLY) must rank only within the current week. An old, higher
    # score from another user must neither inflate the rank nor count itself.
    now = datetime.now(UTC)
    me = uuid4()
    rival = uuid4()
    stale = uuid4()
    await _save_committed(
        sessionmaker,
        _score(value=100, user_id=me, computed_at=now),
        _score(value=200, user_id=rival, computed_at=now),
        _score(value=999, user_id=stale, computed_at=now - timedelta(days=14)),
    )
    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        # Only `rival` (200) is ahead this week; the stale 999 is out of window.
        assert await repo.rank_of(me, LeaderboardPeriod.WEEKLY) == 2
        # `stale` has no in-window score → unranked weekly.
        assert await repo.rank_of(stale, LeaderboardPeriod.WEEKLY) is None


async def test_nonpositive_n_returns_empty_list(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Port contract: n <= 0 short-circuits to [] (callers pass page sizes through
    # without a branch). Even with rows present, no query runs.
    await _save_committed(sessionmaker, _score(value=500))
    async with sessionmaker() as session:
        repo = PostgresScoreRepository(session)
        assert await repo.top_n(0, LeaderboardPeriod.GLOBAL) == []
        assert await repo.top_n_for_user(uuid4(), -1) == []


async def test_top_n_empty_returns_empty_list(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        assert await PostgresScoreRepository(session).top_n(10, LeaderboardPeriod.GLOBAL) == []
