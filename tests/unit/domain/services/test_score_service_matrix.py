"""Parametrised matrix tests for ``src.domain.services.score_service``.

Companion to ``test_score_service.py`` (the example-based suite shipped
with task 1.18) and ``test_score_service_properties.py`` (the hypothesis
suite for task 1.19). This module is the parametrised middle layer:
hand-crafted ``(input → expected)`` rows that pin specific arithmetic
outcomes the example suite covered narratively and the property suite
covers structurally.

Why parametrize for ``ScoreService`` (QUIZZES.md task 1.19 Q3):

* the formula has four independent input axes (``floors_reached``,
  ``kills``, ``item_multiplier``, ``damage_taken``) — a matrix is the
  natural way to assert a representative cross-section without writing
  twenty near-identical ``def test_…`` blocks;
* ``pytest`` reports each row as its own test id, so a regression
  blames the exact failing combination rather than a generic
  ``test_compute_score_examples``;
* a row whose expected value is wrong is obvious on inspection of the
  parametrize block — the calibration is one screenful, not scattered.

**Anti-tautology rule:** every expected value below is computed **by
hand** — never by calling ``compute_score_value`` or
``compute_item_multiplier`` to derive what we then assert. Calling the
service to compute its own expected output is the classic false-positive
trap (any bug in the formula would be matched on both sides). The
expected numbers are committed as literals; if the formula changes, the
matrix is the audit trail that says "this is what it used to produce."
"""

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

import pytest

from src.domain.models import Dungeon, Item, ItemType, Player
from src.domain.services import compute_item_multiplier, compute_score

# --- compute_item_multiplier matrix ----------------------------------------
# Each row: (items_spec, expected) where items_spec is a list of
# (ItemType, count) tuples. Expected = 1.0 + Σ weight × count.
# Weights are: WEAPON 0.5, ARMOR 0.3, SHIELD 0.2, POTION 0.05, KEY 0.1.

_MULTIPLIER_MATRIX = [
    pytest.param([], 1.0, id="empty"),
    pytest.param([(ItemType.WEAPON, 1)], 1.5, id="single_weapon"),
    pytest.param([(ItemType.ARMOR, 1)], 1.3, id="single_armor"),
    pytest.param([(ItemType.SHIELD, 1)], 1.2, id="single_shield"),
    pytest.param([(ItemType.POTION, 1)], 1.05, id="single_potion"),
    pytest.param([(ItemType.KEY, 1)], 1.1, id="single_key"),
    # 1.0 + 3 × 0.5 = 2.5
    pytest.param([(ItemType.WEAPON, 3)], 2.5, id="weapon_count_3"),
    # 1.0 + 20 × 0.05 = 2.0
    pytest.param([(ItemType.POTION, 20)], 2.0, id="potion_count_20"),
    # 1.0 + 0.5 + 0.1 = 1.6 — cross-type sum (catches "only last item counted")
    pytest.param([(ItemType.WEAPON, 1), (ItemType.KEY, 1)], 1.6, id="weapon_plus_key"),
    # 1.0 + 0.5 + 0.3 + 0.2 + 0.05 + 0.1 = 2.15 — every type contributes once
    pytest.param(
        [
            (ItemType.WEAPON, 1),
            (ItemType.ARMOR, 1),
            (ItemType.SHIELD, 1),
            (ItemType.POTION, 1),
            (ItemType.KEY, 1),
        ],
        2.15,
        id="all_types_count_1",
    ),
    # 1.0 + 2 × 0.5 + 2 × 0.3 = 2.6 — per-item count on multi-item lists
    pytest.param([(ItemType.WEAPON, 2), (ItemType.ARMOR, 2)], 2.6, id="two_weapons_two_armors"),
]


@pytest.mark.parametrize("items_spec, expected", _MULTIPLIER_MATRIX)
def test_compute_item_multiplier_matrix(
    make_item: Callable[..., Item],
    items_spec: list[tuple[ItemType, int]],
    expected: float,
) -> None:
    items = [make_item(t, count=c) for t, c in items_spec]
    assert compute_item_multiplier(items) == pytest.approx(expected)


# --- compute_score matrix --------------------------------------------------
# Each row: (floor_idx, kills, items_spec, damage, expected_value,
# expected_floors_reached). Expected value computed by hand via
#     max(0, int(floors_reached ** 2 * kills * mult - damage))
# where mult = 1.0 + Σ weight × count over items_spec.

_SCORE_MATRIX = [
    # floor 1, 1 kill, no items, 0 dmg → 1²×1×1.0 − 0 = 1.
    pytest.param(0, 1, [], 0, 1, 1, id="minimal"),
    # floor 3, 4 kills, 1 weapon (mult 1.5), 0 dmg → 9×4×1.5 = 54.
    # If multiplier is silently dropped: 9×4×1.0 = 36.
    pytest.param(2, 4, [(ItemType.WEAPON, 1)], 0, 54, 3, id="floor3_kill4_weapon"),
    # floor 1, 1 kill, 0 items, 999 dmg → max(0, 1 − 999) = 0.
    # Catches removal of the max(0, …) clamp.
    pytest.param(0, 1, [], 999, 0, 1, id="damage_erases_score"),
    # floor 10, 0 kills, big multiplier, 0 dmg → 100×0×… = 0.
    # Catches kills-axis multiplicative-zero regression.
    pytest.param(9, 0, [(ItemType.WEAPON, 2)], 0, 0, 10, id="zero_kills_always_zero"),
    # floor 5, 3 kills, no items, 0 dmg → 25×3×1.0 = 75.
    # If floors_reached used the 0-based index: 16×3 = 48 (≠ 75).
    pytest.param(4, 3, [], 0, 75, 5, id="floor5_kill3_no_items"),
    # Same as above with damage 10 → 75 − 10 = 65. Damage sign / wiring.
    pytest.param(4, 3, [], 10, 65, 5, id="floor5_kill3_damage10"),
    # floor 7, 1 kill — cross-check the +1 translation at a non-trivial floor.
    # 49 × 1 × 1.0 = 49. Off-by-one would give 36 (idx²) or 64 ((idx+2)²).
    pytest.param(6, 1, [], 0, 49, 7, id="floors_reached_index_6"),
    # floor 10, 50 kills, one of each item (mult 2.15), 500 dmg.
    # 100 × 50 × 2.15 − 500 = 10750 − 500 = 10250. Combined-axis sanity.
    pytest.param(
        9,
        50,
        [
            (ItemType.WEAPON, 1),
            (ItemType.ARMOR, 1),
            (ItemType.SHIELD, 1),
            (ItemType.POTION, 1),
            (ItemType.KEY, 1),
        ],
        500,
        10250,
        10,
        id="large_run",
    ),
    # floor 2, 5 kills, 3 potions on one stack (mult 1.15), 0 dmg.
    # 4 × 5 × 1.15 = 23. If item.count is ignored: 4 × 5 × 1.05 = 21.
    pytest.param(1, 5, [(ItemType.POTION, 3)], 0, 23, 2, id="multiplier_count_scaling"),
]


@pytest.mark.parametrize(
    "floor_idx, kills, items_spec, damage, expected_value, expected_floors",
    _SCORE_MATRIX,
)
def test_compute_score_matrix(
    make_dungeon: Callable[..., Dungeon],
    make_player: Callable[..., Player],
    make_item: Callable[..., Item],
    fixed_when: datetime,
    floor_idx: int,
    kills: int,
    items_spec: list[tuple[ItemType, int]],
    damage: int,
    expected_value: int,
    expected_floors: int,
) -> None:
    dungeon = make_dungeon(current_floor_index=floor_idx)
    player = make_player(damage_taken=damage)
    items = [make_item(t, count=c) for t, c in items_spec]

    score = compute_score(
        dungeon,
        player,
        kills=kills,
        items=items,
        score_id=uuid4(),
        computed_at=fixed_when,
    )

    assert score.value == expected_value
    assert score.floors_reached == expected_floors
