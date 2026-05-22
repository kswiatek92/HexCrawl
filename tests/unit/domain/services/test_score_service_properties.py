"""Property-based tests for ``src.domain.services.score_service``.

Companion to ``test_score_service.py`` (example suite, task 1.18) and
``test_score_service_matrix.py`` (parametrised matrix, task 1.19). This
module is the third leg: Hypothesis property tests that exercise
*structural* invariants of the scoring functions across the input space,
not just hand-picked examples.

Why properties belong here (QUIZZES.md task 1.19 Q1): the design intent
is that ``compute_score`` and ``compute_item_multiplier`` are **pure
functions** — no fakes, no mocks, no I/O. The cleanest demonstration of
that claim is a property test: "for all inputs in this range, this
invariant holds." If purity broke (a hidden clock, a mutable module
global, a stale cache), the property tests would flake or fail in
shrinking. Example tests can't catch that on their own.

Property selection follows the rule "test what the formula promises,
not what it computes." Each property is something the developer would
need true to call the formula correct — non-negativity, monotonicity
in each axis, permutation invariance of the multiplier sum, additivity
of the multiplier under list concatenation. The "depth dominates kills"
property the planner first sketched does **not** hold algebraically over
the full input range and is deliberately excluded.

Hypothesis settings: ``@settings(max_examples=50, deadline=None)`` on
every property, matching the sibling ``test_dungeon_generator_properties.py``
choice. Each call is O(1) arithmetic so 50 examples is more than enough
to surface structural violations; ``deadline=None`` prevents flakes on
slow CI runners without affecting correctness.
"""

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.models import Dungeon, Item, ItemType, Player
from src.domain.services import compute_item_multiplier, compute_score

# --- strategies ------------------------------------------------------------
# Items live as (ItemType, count) tuples in Hypothesis strategies so the
# test materialises real Item dataclasses via the conftest factory.
# Holding raw Item instances in strategies would burn a uuid4() on every
# example without adding coverage and would shrink poorly.

_item_type_st = st.sampled_from(list(ItemType))
_count_st = st.integers(min_value=1, max_value=100)
_item_spec_st = st.tuples(_item_type_st, _count_st)
_items_list_st = st.lists(_item_spec_st, min_size=0, max_size=20)

# floor_index bounded by TOTAL_FLOORS - 1 = 99; kills / damage bounded
# loosely to representative play ranges so float arithmetic stays
# precise and the suite stays under the 1-second domain budget.
_floor_index_st = st.integers(min_value=0, max_value=99)
_kills_st = st.integers(min_value=0, max_value=1_000)
_damage_st = st.integers(min_value=0, max_value=10_000)


def _materialise(specs: list[tuple[ItemType, int]], make_item: Callable[..., Item]) -> list[Item]:
    return [make_item(t, count=c) for t, c in specs]


# --- compute_item_multiplier properties ------------------------------------


@given(specs=_items_list_st)
@settings(max_examples=50, deadline=None)
def test_multiplier_always_at_least_one(
    specs: list[tuple[ItemType, int]],
    make_item: Callable[..., Item],
) -> None:
    # All current ITEM_TYPE_WEIGHTS are non-negative, so the additive
    # accumulator is bounded below by the 1.0 baseline. A future negative
    # weight (a "cursed" item) would break this property and force a
    # deliberate review — exactly the alarm we want.
    items = _materialise(specs, make_item)
    assert compute_item_multiplier(items) >= 1.0


@given(pair=_items_list_st.flatmap(lambda lst: st.tuples(st.just(lst), st.permutations(lst))))
@settings(max_examples=50, deadline=None)
def test_multiplier_permutation_invariant(
    pair: tuple[list[tuple[ItemType, int]], list[tuple[ItemType, int]]],
    make_item: Callable[..., Item],
) -> None:
    # Iteration order must not affect the result. Position-sensitive bugs
    # (e.g. an accumulator that drops the first or last element, or a
    # non-commutative combiner) would produce different sums for the
    # same multiset.
    original, shuffled = pair
    a = compute_item_multiplier(_materialise(original, make_item))
    b = compute_item_multiplier(_materialise(shuffled, make_item))
    assert a == pytest.approx(b)


@given(left=_items_list_st, right=_items_list_st)
@settings(max_examples=50, deadline=None)
def test_multiplier_concat_is_additive(
    left: list[tuple[ItemType, int]],
    right: list[tuple[ItemType, int]],
    make_item: Callable[..., Item],
) -> None:
    # mult(a + b) == mult(a) + mult(b) - 1.0 because each call adds the
    # 1.0 base once and the per-item contributions are linear in counts.
    # A multiplicative or otherwise non-linear accumulator would fail.
    combined = compute_item_multiplier(_materialise(left + right, make_item))
    pieces = (
        compute_item_multiplier(_materialise(left, make_item))
        + compute_item_multiplier(_materialise(right, make_item))
        - 1.0
    )
    assert combined == pytest.approx(pieces)


# --- compute_score properties ----------------------------------------------


@given(
    floor_idx=_floor_index_st,
    kills=_kills_st,
    specs=_items_list_st,
    damage=_damage_st,
)
@settings(max_examples=50, deadline=None)
def test_score_value_never_negative(
    floor_idx: int,
    kills: int,
    specs: list[tuple[ItemType, int]],
    damage: int,
    make_dungeon: Callable[..., Dungeon],
    make_player: Callable[..., Player],
    make_item: Callable[..., Item],
    fixed_when: datetime,
) -> None:
    # The max(0, ...) clamp in compute_score_value is the only thing
    # standing between huge damage and a negative leaderboard score.
    # Removing the clamp would surface here for any damage > base.
    score = compute_score(
        make_dungeon(current_floor_index=floor_idx),
        make_player(damage_taken=damage),
        kills=kills,
        items=_materialise(specs, make_item),
        score_id=uuid4(),
        computed_at=fixed_when,
    )
    assert score.value >= 0


@given(floor_idx=_floor_index_st)
@settings(max_examples=50, deadline=None)
def test_score_floors_reached_is_index_plus_one(
    floor_idx: int,
    make_dungeon: Callable[..., Dungeon],
    make_player: Callable[..., Player],
    fixed_when: datetime,
) -> None:
    # 0-based engine index → 1-based human "Reached floor N". An
    # off-by-one (returning current_floor_index directly, or +2) would
    # fail on every example.
    score = compute_score(
        make_dungeon(current_floor_index=floor_idx),
        make_player(),
        kills=1,
        score_id=uuid4(),
        computed_at=fixed_when,
    )
    assert score.floors_reached == floor_idx + 1


@given(
    floor_idx=_floor_index_st,
    kills=st.integers(min_value=0, max_value=999),
    damage=_damage_st,
)
@settings(max_examples=50, deadline=None)
def test_score_monotone_in_kills(
    floor_idx: int,
    kills: int,
    damage: int,
    make_dungeon: Callable[..., Dungeon],
    make_player: Callable[..., Player],
    fixed_when: datetime,
) -> None:
    # One extra kill cannot lower the score (other axes held fixed).
    # Catches a sign flip on the kills coefficient or a missing
    # multiplication. kills capped at 999 so +1 stays in the documented
    # range.
    def at(k: int) -> int:
        return compute_score(
            make_dungeon(current_floor_index=floor_idx),
            make_player(damage_taken=damage),
            kills=k,
            score_id=uuid4(),
            computed_at=fixed_when,
        ).value

    assert at(kills + 1) >= at(kills)


@given(
    floor_idx=st.integers(min_value=0, max_value=98),
    kills=st.integers(min_value=1, max_value=1_000),
    damage=_damage_st,
)
@settings(max_examples=50, deadline=None)
def test_score_monotone_in_floors(
    floor_idx: int,
    kills: int,
    damage: int,
    make_dungeon: Callable[..., Dungeon],
    make_player: Callable[..., Player],
    fixed_when: datetime,
) -> None:
    # Going one floor deeper cannot lower the score when kills > 0.
    # kills must be >= 1 because at kills=0 both sides collapse to 0
    # via the multiplicative-zero rule and the property degenerates.
    # floor_idx capped at 98 so +1 stays in the 0..99 range.
    def at(idx: int) -> int:
        return compute_score(
            make_dungeon(current_floor_index=idx),
            make_player(damage_taken=damage),
            kills=kills,
            score_id=uuid4(),
            computed_at=fixed_when,
        ).value

    assert at(floor_idx + 1) >= at(floor_idx)


@given(
    floor_idx=_floor_index_st,
    kills=_kills_st,
    damage=st.integers(min_value=0, max_value=9_999),
)
@settings(max_examples=50, deadline=None)
def test_more_damage_never_increases_score(
    floor_idx: int,
    kills: int,
    damage: int,
    make_dungeon: Callable[..., Dungeon],
    make_player: Callable[..., Player],
    fixed_when: datetime,
) -> None:
    # One extra point of damage cannot raise the score. Catches a sign
    # flip on the damage penalty (i.e. damage being added rather than
    # subtracted) and a dropped subtraction entirely.
    def at(d: int) -> int:
        return compute_score(
            make_dungeon(current_floor_index=floor_idx),
            make_player(damage_taken=d),
            kills=kills,
            score_id=uuid4(),
            computed_at=fixed_when,
        ).value

    assert at(damage + 1) <= at(damage)
