import inspect
from datetime import UTC, datetime
from typing import get_type_hints
from uuid import UUID, uuid4

from src.domain.models import LeaderboardPeriod, Score
from src.domain.ports import IScoreRepository


def _make_score(
    *,
    value: int,
    user_id: UUID | None = None,
    computed_at: datetime | None = None,
    score_id: UUID | None = None,
    dungeon_id: UUID | None = None,
    floors_reached: int = 1,
    kills: int = 1,
    item_multiplier: float = 1.0,
    damage_taken: int = 0,
) -> Score:
    return Score(
        score_id=score_id or uuid4(),
        user_id=user_id or uuid4(),
        dungeon_id=dungeon_id or uuid4(),
        floors_reached=floors_reached,
        kills=kills,
        item_multiplier=item_multiplier,
        damage_taken=damage_taken,
        value=value,
        computed_at=computed_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


class _FakeScoreRepository:
    """Local in-memory fake used to lock the IScoreRepository contract.

    Stays private (``_`` prefix) and local to this test file until a
    second consumer (e.g. ``SubmitScore`` tests in Phase 3) appears —
    at which point this gets promoted to a shared fixture. YAGNI until
    then, matching the IGameRepository test pattern.

    Note the deliberate absence of ``IScoreRepository`` in the bases:
    structural conformance (Protocol) means inheritance is neither
    needed nor desirable. Conformance is asserted statically by
    ``test_fake_conforms_structurally`` below.

    The fake partitions scores by ``LeaderboardPeriod`` and sorts each
    bucket on ``(-value, computed_at)`` — the same ordering the port
    docstring pins. Phase 2.5 Postgres adapter tests will run against
    the same behavioural assertions; any drift fails LSP.
    """

    def __init__(self) -> None:
        self._by_id: dict[UUID, Score] = {}
        # Period → set of score_ids assigned to that period. The port
        # docstring leaves period bucketing to the adapter; the fake
        # accepts an explicit assignment via ``put`` because deriving
        # "weekly" from a wall-clock here would couple every test to
        # ``datetime.now()``.
        self._buckets: dict[LeaderboardPeriod, set[UUID]] = {
            LeaderboardPeriod.GLOBAL: set(),
            LeaderboardPeriod.WEEKLY: set(),
        }

    def put(self, score: Score, *, periods: tuple[LeaderboardPeriod, ...]) -> None:
        """Test helper: store ``score`` and assign it to the listed periods.

        Not part of the IScoreRepository contract — this exists only so
        ordering / filtering tests can construct a deterministic state
        without a clock. Production adapters derive period membership
        from columns on the row.
        """
        self._by_id[score.score_id] = score
        for period in periods:
            self._buckets[period].add(score.score_id)

    async def save(self, score: Score) -> Score:
        self._by_id[score.score_id] = score
        # Tests that exercise leaderboard membership use ``put`` to
        # pin which period a saved score belongs to. ``save`` itself
        # mirrors the production contract: persist the row, return
        # the canonical entity, do nothing else.
        return score

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        if n <= 0:
            return []
        bucket = self._buckets[period]
        candidates = [self._by_id[sid] for sid in bucket]
        candidates.sort(key=lambda s: (-s.value, s.computed_at))
        return candidates[:n]

    async def top_n_for_user(self, user_id: UUID, n: int) -> list[Score]:
        if n <= 0:
            return []
        owned = [s for s in self._by_id.values() if s.user_id == user_id]
        owned.sort(key=lambda s: (-s.value, s.computed_at))
        return owned[:n]

    async def rank_of(self, user_id: UUID, period: LeaderboardPeriod) -> int | None:
        bucket = self._buckets[period]
        candidates = [self._by_id[sid] for sid in bucket]
        candidates.sort(key=lambda s: (-s.value, s.computed_at))
        best_index: int | None = None
        for idx, s in enumerate(candidates):
            if s.user_id == user_id:
                if best_index is None or idx < best_index:
                    best_index = idx
        return None if best_index is None else best_index + 1


def test_protocol_is_a_protocol() -> None:
    # CPython sets ``_is_protocol = True`` on every class derived from
    # ``typing.Protocol``. Mirrors the regression guard on
    # IGameRepository: without ``(Protocol)`` as a base, structural
    # conformance breaks at every adapter and the type is silently
    # nominal.
    assert getattr(IScoreRepository, "_is_protocol", False) is True


def test_save_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IScoreRepository.save)
    sig = inspect.signature(IScoreRepository.save)
    assert list(sig.parameters) == ["self", "score"]
    hints = get_type_hints(IScoreRepository.save)
    assert hints["score"] is Score
    assert hints["return"] is Score


def test_top_n_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IScoreRepository.top_n)
    sig = inspect.signature(IScoreRepository.top_n)
    assert list(sig.parameters) == ["self", "n", "period"]
    hints = get_type_hints(IScoreRepository.top_n)
    assert hints["n"] is int
    assert hints["period"] is LeaderboardPeriod
    assert hints["return"] == list[Score]


def test_top_n_for_user_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IScoreRepository.top_n_for_user)
    sig = inspect.signature(IScoreRepository.top_n_for_user)
    assert list(sig.parameters) == ["self", "user_id", "n"]
    hints = get_type_hints(IScoreRepository.top_n_for_user)
    assert hints["user_id"] is UUID
    assert hints["n"] is int
    assert hints["return"] == list[Score]


def test_rank_of_signature_is_async_and_typed() -> None:
    assert inspect.iscoroutinefunction(IScoreRepository.rank_of)
    sig = inspect.signature(IScoreRepository.rank_of)
    assert list(sig.parameters) == ["self", "user_id", "period"]
    hints = get_type_hints(IScoreRepository.rank_of)
    assert hints["user_id"] is UUID
    assert hints["period"] is LeaderboardPeriod
    assert hints["return"] == int | None


def test_fake_conforms_structurally() -> None:
    repo: IScoreRepository = _FakeScoreRepository()
    assert repo is not None


async def test_save_returns_saved_score() -> None:
    repo = _FakeScoreRepository()
    score = _make_score(value=100)

    saved = await repo.save(score)

    # Field-equality, not ``is``: the port permits adapters to return a
    # fresh Score instance with refreshed server-owned fields.
    assert saved.score_id == score.score_id
    assert saved == score


async def test_save_is_idempotent_on_id() -> None:
    repo = _FakeScoreRepository()
    sid = uuid4()
    first = _make_score(value=100, score_id=sid)
    second = _make_score(value=200, score_id=sid, user_id=first.user_id)

    await repo.save(first)
    await repo.save(second)
    # No exception is the LSP-level assertion; behaviour-level
    # assertion is that the second save's discriminating field wins
    # on subsequent reads. We surface this via the user's
    # personal-best list since ``get(score_id)`` is deliberately not
    # part of the port surface.
    repo.put(second, periods=(LeaderboardPeriod.GLOBAL,))
    user_top = await repo.top_n_for_user(second.user_id, 5)
    assert len(user_top) == 1
    assert user_top[0].value == 200


async def test_top_n_orders_by_value_desc_then_computed_at_asc() -> None:
    repo = _FakeScoreRepository()
    early = _make_score(value=100, computed_at=datetime(2026, 1, 1, tzinfo=UTC))
    late = _make_score(value=100, computed_at=datetime(2026, 2, 1, tzinfo=UTC))
    highest = _make_score(value=500, computed_at=datetime(2026, 3, 1, tzinfo=UTC))

    for s in (early, late, highest):
        repo.put(s, periods=(LeaderboardPeriod.GLOBAL,))

    result = await repo.top_n(5, LeaderboardPeriod.GLOBAL)

    # Locks the LSP-critical contract: ``value`` DESC first; on a tie,
    # the earlier ``computed_at`` wins. If the docstring ever drifts to
    # "later wins" or "unspecified", this test fails. Removing the
    # ordering clauses entirely would also fail it.
    assert [s.score_id for s in result] == [highest.score_id, early.score_id, late.score_id]


async def test_top_n_respects_n_and_period() -> None:
    repo = _FakeScoreRepository()
    only_global = _make_score(value=300)
    only_weekly = _make_score(value=200)
    in_both = _make_score(value=400)

    repo.put(only_global, periods=(LeaderboardPeriod.GLOBAL,))
    repo.put(only_weekly, periods=(LeaderboardPeriod.WEEKLY,))
    repo.put(in_both, periods=(LeaderboardPeriod.GLOBAL, LeaderboardPeriod.WEEKLY))

    weekly_top = await repo.top_n(5, LeaderboardPeriod.WEEKLY)
    assert [s.score_id for s in weekly_top] == [in_both.score_id, only_weekly.score_id]
    # ``only_global`` is not present in the weekly bucket — proves the
    # period parameter actually filters and isn't just decorative.
    assert only_global.score_id not in {s.score_id for s in weekly_top}

    capped = await repo.top_n(1, LeaderboardPeriod.GLOBAL)
    assert len(capped) == 1
    assert capped[0].score_id == in_both.score_id


async def test_top_n_empty_returns_empty_list_not_none() -> None:
    repo = _FakeScoreRepository()
    result = await repo.top_n(10, LeaderboardPeriod.GLOBAL)
    # Empty repo + asking for ten back must yield [], not None. The
    # ``isinstance(result, list)`` check fences against an adapter that
    # tries to return ``None`` as a "nothing to see" sentinel — that
    # would force every caller into an extra branch and silently break
    # the JSON serializer downstream.
    assert isinstance(result, list)
    assert result == []


async def test_top_n_with_n_zero_returns_empty_list() -> None:
    repo = _FakeScoreRepository()
    repo.put(_make_score(value=999), periods=(LeaderboardPeriod.GLOBAL,))
    # Even with scores in the bucket, asking for zero must yield [],
    # not raise. Callers can pass user-supplied page sizes through
    # without a guard.
    assert await repo.top_n(0, LeaderboardPeriod.GLOBAL) == []
    assert await repo.top_n(-3, LeaderboardPeriod.GLOBAL) == []


async def test_top_n_for_user_filters_and_orders() -> None:
    repo = _FakeScoreRepository()
    alice = uuid4()
    bob = uuid4()
    alice_low = _make_score(value=50, user_id=alice, computed_at=datetime(2026, 1, 1, tzinfo=UTC))
    alice_high = _make_score(value=300, user_id=alice, computed_at=datetime(2026, 2, 1, tzinfo=UTC))
    bob_high = _make_score(value=900, user_id=bob)

    for s in (alice_low, alice_high, bob_high):
        await repo.save(s)

    result = await repo.top_n_for_user(alice, 5)
    assert [s.score_id for s in result] == [alice_high.score_id, alice_low.score_id]
    # Negative assertion: Bob's 900 must not leak into Alice's list,
    # even though it has the highest value globally.
    assert bob_high.score_id not in {s.score_id for s in result}


async def test_top_n_for_user_missing_user_returns_empty_list() -> None:
    repo = _FakeScoreRepository()
    await repo.save(_make_score(value=100))
    # A freshly registered account with zero rows must produce [], not
    # raise — "no scores yet" is a normal domain outcome, not an
    # error.
    assert await repo.top_n_for_user(uuid4(), 10) == []


async def test_rank_of_returns_one_indexed_position() -> None:
    repo = _FakeScoreRepository()
    target = uuid4()
    top = _make_score(value=900)
    mid = _make_score(value=500, user_id=target)
    bottom = _make_score(value=100)

    for s in (top, mid, bottom):
        repo.put(s, periods=(LeaderboardPeriod.GLOBAL,))

    # Target's best is 500, which sorts second behind 900. Ranks are
    # 1-indexed per the port docstring; returning 1 here would mean the
    # adapter sorted ascending or used zero-indexed positions.
    assert await repo.rank_of(target, LeaderboardPeriod.GLOBAL) == 2


async def test_rank_of_returns_none_when_user_has_no_score() -> None:
    repo = _FakeScoreRepository()
    repo.put(_make_score(value=100), periods=(LeaderboardPeriod.GLOBAL,))
    # Missing user must produce None, not raise and not 0 / -1. The
    # entrypoint maps None to "unranked" at the API boundary.
    assert await repo.rank_of(uuid4(), LeaderboardPeriod.GLOBAL) is None


async def test_rank_of_respects_period() -> None:
    repo = _FakeScoreRepository()
    target = uuid4()
    # Target has a score in GLOBAL only — querying WEEKLY must yield
    # None, not the global rank.
    repo.put(
        _make_score(value=500, user_id=target),
        periods=(LeaderboardPeriod.GLOBAL,),
    )
    assert await repo.rank_of(target, LeaderboardPeriod.GLOBAL) == 1
    assert await repo.rank_of(target, LeaderboardPeriod.WEEKLY) is None


async def test_rank_of_uses_user_single_best_score() -> None:
    repo = _FakeScoreRepository()
    target = uuid4()
    rival = uuid4()
    target_best = _make_score(
        value=600,
        user_id=target,
        computed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    target_worse = _make_score(
        value=200,
        user_id=target,
        computed_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    rival_score = _make_score(
        value=500,
        user_id=rival,
        computed_at=datetime(2026, 1, 15, tzinfo=UTC),
    )

    for s in (target_best, target_worse, rival_score):
        repo.put(s, periods=(LeaderboardPeriod.GLOBAL,))

    # Ordering of the bucket is target_best (600) → rival (500) →
    # target_worse (200). rank_of must pick target's single best,
    # which is position 1, not the position of their lower run
    # (which would be 3). This is the docstring clause that says
    # only the user's single best score is ranked.
    assert await repo.rank_of(target, LeaderboardPeriod.GLOBAL) == 1
