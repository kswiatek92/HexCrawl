from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.domain.models import (
    DAMAGE_PENALTY_WEIGHT,
    Score,
    compute_score_value,
)


def _make_score(
    *,
    score_id: UUID | None = None,
    user_id: UUID | None = None,
    dungeon_id: UUID | None = None,
    floors_reached: int = 5,
    kills: int = 10,
    item_multiplier: float = 1.5,
    damage_taken: int = 4,
    value: int = 371,
    computed_at: datetime | None = None,
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
        computed_at=computed_at or datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
    )


def test_score_is_dataclass() -> None:
    assert is_dataclass(Score)


def test_score_is_frozen() -> None:
    score = _make_score()

    with pytest.raises(FrozenInstanceError):
        score.value = 0  # type: ignore[misc]


def test_score_exposes_expected_fields() -> None:
    field_names = {f.name for f in fields(Score)}

    assert field_names == {
        "score_id",
        "user_id",
        "dungeon_id",
        "floors_reached",
        "kills",
        "item_multiplier",
        "damage_taken",
        "value",
        "computed_at",
    }


def test_score_accepts_all_fields() -> None:
    sid = uuid4()
    uid = uuid4()
    did = uuid4()
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    score = Score(
        score_id=sid,
        user_id=uid,
        dungeon_id=did,
        floors_reached=12,
        kills=37,
        item_multiplier=2.25,
        damage_taken=18,
        value=998,
        computed_at=when,
    )

    assert score.score_id == sid
    assert isinstance(score.score_id, UUID)
    assert score.user_id == uid
    assert score.dungeon_id == did
    assert score.floors_reached == 12
    assert score.kills == 37
    assert score.item_multiplier == 2.25
    assert score.damage_taken == 18
    assert score.value == 998
    assert score.computed_at == when


def test_score_computed_at_is_passed_in() -> None:
    # Locks QUIZZES Task 1.7 Q4: the timestamp is supplied by the caller,
    # not pulled from datetime.now() inside the model — so tests can assert
    # equality without freezing the system clock.
    fixed = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
    score = _make_score(computed_at=fixed)

    assert score.computed_at is fixed


def test_compute_basic() -> None:
    # 2² × 3 × 1.0 - 0 = 12
    assert compute_score_value(floors_reached=2, kills=3, item_multiplier=1.0, damage_taken=0) == 12


def test_compute_floors_squared_not_linear() -> None:
    # Locks the squared exponent: 3² × 1 × 1.0 = 9, not 3.
    assert compute_score_value(floors_reached=3, kills=1, item_multiplier=1.0, damage_taken=0) == 9


def test_compute_zero_floors_yields_zero() -> None:
    # Multiplicative-zero risk (QUIZZES Q1), axis 1.
    assert compute_score_value(floors_reached=0, kills=50, item_multiplier=2.0, damage_taken=0) == 0


def test_compute_zero_kills_yields_zero() -> None:
    # Multiplicative-zero risk (QUIZZES Q1), axis 2.
    assert compute_score_value(floors_reached=10, kills=0, item_multiplier=2.0, damage_taken=0) == 0


def test_compute_damage_penalty_subtracts() -> None:
    # 2² × 2 × 1.0 = 8, minus damage 3 × weight 1 → 5.
    assert compute_score_value(floors_reached=2, kills=2, item_multiplier=1.0, damage_taken=3) == 5


def test_compute_damage_penalty_clamped_to_zero() -> None:
    # 1² × 1 × 1.0 = 1, minus damage 99 → -98 → clamped to 0.
    assert compute_score_value(floors_reached=1, kills=1, item_multiplier=1.0, damage_taken=99) == 0


def test_compute_truncates_float_multiplier_to_int() -> None:
    # 2² × 2 × 1.5 = 12.0, exact int. Locks the float→int return shape.
    assert compute_score_value(floors_reached=2, kills=2, item_multiplier=1.5, damage_taken=0) == 12


def test_compute_is_pure_repeatable_call() -> None:
    # Calling twice with identical inputs yields identical output —
    # smoke test for purity (no hidden global state, no time-dependence).
    args = {"floors_reached": 7, "kills": 5, "item_multiplier": 1.25, "damage_taken": 2}
    assert compute_score_value(**args) == compute_score_value(**args)


def test_damage_penalty_weight_is_one_for_v1() -> None:
    # If this constant changes, every v1 score recomputes — make the bump
    # a conscious decision by failing this test.
    assert DAMAGE_PENALTY_WEIGHT == 1
