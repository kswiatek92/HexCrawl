"""Tests for ``src.domain.services.score_service``.

Coverage targets the task 1.18 design intent (``QUESTIONS.md`` 1.4 / 1.7 /
1.18, ADR-0002) and the quiz questions in ``QUIZZES.md`` task 1.18:

* purity (no I/O, no hidden state, deterministic in inputs);
* additive per-type item multiplier with read-only weight map;
* caller-supplied ``score_id`` and ``computed_at`` (no clock / no
  ``uuid.uuid4`` inside the service);
* composition with the underlying ``compute_score_value`` formula
  (multiplicative-zero propagates correctly, damage penalty subtracts);
* the no-mutate contract on the inputs.
"""

import copy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.domain.models import (
    Dungeon,
    Floor,
    Item,
    ItemType,
    Player,
    Score,
    TileType,
)
from src.domain.services import (
    ITEM_TYPE_WEIGHTS,
    compute_item_multiplier,
    compute_score,
)

# --- Test fixture helpers --------------------------------------------------

_FIXED_WHEN = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _floor() -> Floor:
    """Minimal walkable floor — geometry is irrelevant for scoring tests."""
    return Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR]],
        enemies=[],
        items={},
        stairs_down=(0, 0),
    )


def _dungeon(*, current_floor_index: int = 0, dungeon_id: UUID | None = None) -> Dungeon:
    # Keep the invariant 0 <= current_floor_index < len(floors) — otherwise
    # any future scoring code that touches dungeon.floors[current_floor_index]
    # would crash only in tests, not in prod.
    return Dungeon(
        dungeon_id=dungeon_id or uuid4(),
        seed=42,
        floors=[_floor() for _ in range(current_floor_index + 1)],
        current_floor_index=current_floor_index,
    )


def _player(
    *,
    user_id: UUID | None = None,
    damage_taken: int = 0,
) -> Player:
    return Player(
        user_id=user_id or uuid4(),
        name="hero",
        position=(0, 0),
        damage_taken=damage_taken,
    )


def _item(item_type: ItemType, *, count: int = 1) -> Item:
    return Item(item_id=uuid4(), name=item_type.value.lower(), item_type=item_type, count=count)


# --- ITEM_TYPE_WEIGHTS -----------------------------------------------------


def test_item_type_weights_cover_all_item_types() -> None:
    # Lock-test: every ItemType variant must have a weight. Future additions
    # to ItemType (e.g. SCROLL in v2) without updating ITEM_TYPE_WEIGHTS
    # would silently KeyError at scoring time — fail at CI instead.
    assert set(ITEM_TYPE_WEIGHTS.keys()) == set(ItemType)


def test_item_type_weights_is_read_only() -> None:
    # MappingProxyType prevents accidental mutation from tests / hot-patching;
    # without it a stray `ITEM_TYPE_WEIGHTS[ItemType.WEAPON] = 99` in any
    # test would poison every later run in the same process.
    with pytest.raises(TypeError):
        ITEM_TYPE_WEIGHTS[ItemType.WEAPON] = 99.0  # type: ignore[index]


# --- compute_item_multiplier -----------------------------------------------


def test_compute_item_multiplier_empty_is_one() -> None:
    # Baseline: empty inventory ⇒ 1.0 (multiplicative identity). If this
    # returned 0.0, every pre-pickup run would score 0 via the
    # multiplicative chain in compute_score_value.
    assert compute_item_multiplier([]) == 1.0


def test_compute_item_multiplier_single_item_uses_weight() -> None:
    # One WEAPON (weight 0.5) ⇒ 1.0 + 0.5 = 1.5
    assert compute_item_multiplier([_item(ItemType.WEAPON)]) == pytest.approx(1.5)


def test_compute_item_multiplier_count_scales_linearly() -> None:
    # 5 POTION (weight 0.05) on one stack ⇒ 1.0 + 5 * 0.05 = 1.25.
    # Locks additive-per-count over multiplicative-per-item: multiplicative
    # would give 1.05**5 ≈ 1.2763, additive gives exactly 1.25.
    assert compute_item_multiplier([_item(ItemType.POTION, count=5)]) == pytest.approx(1.25)


def test_compute_item_multiplier_mixed_inventory_is_additive() -> None:
    # One of each ItemType ⇒ 1.0 + (0.5 + 0.3 + 0.2 + 0.05 + 0.1) = 2.15.
    items = [_item(t) for t in ItemType]
    assert compute_item_multiplier(items) == pytest.approx(2.15)


def test_compute_item_multiplier_consumes_generator_once() -> None:
    # Typed `Iterable[Item]`, not `Sequence[Item]` — callers can pass a
    # generator (e.g. chained inventory slots when those land on Player).
    # The function must iterate once, never subscript.
    gen = (_item(ItemType.WEAPON) for _ in range(2))
    assert compute_item_multiplier(gen) == pytest.approx(2.0)  # 1.0 + 2 * 0.5


# --- compute_score: arithmetic + wiring -----------------------------------


def test_compute_score_basic_run() -> None:
    # Floor 3 (index 2), 4 kills, 1 weapon (mult 1.5), 0 damage ⇒
    # 3**2 * 4 * 1.5 - 0 = 54.
    dungeon = _dungeon(current_floor_index=2)
    player = _player()

    score = compute_score(
        dungeon,
        player,
        kills=4,
        items=[_item(ItemType.WEAPON)],
        score_id=uuid4(),
        computed_at=_FIXED_WHEN,
    )

    assert score.value == 54
    assert score.floors_reached == 3
    assert score.kills == 4
    assert score.item_multiplier == pytest.approx(1.5)
    assert score.damage_taken == 0


def test_compute_score_floors_reached_is_current_index_plus_one() -> None:
    # 0-based engine index → 1-based human "Reached floor N". On spawn
    # (current_floor_index=0) the player has reached floor 1.
    dungeon = _dungeon(current_floor_index=0)
    player = _player()

    score = compute_score(dungeon, player, kills=1, score_id=uuid4(), computed_at=_FIXED_WHEN)

    assert score.floors_reached == 1


def test_compute_score_uses_player_damage_taken() -> None:
    # Same arithmetic in everything except player.damage_taken ⇒ different
    # value. Confirms damage_taken is actually wired into the formula, not
    # silently dropped on the floor.
    dungeon = _dungeon(current_floor_index=4)  # floor 5
    pristine = _player(damage_taken=0)
    bruised = _player(damage_taken=10)
    common_kwargs = {
        "dungeon": dungeon,
        "kills": 3,
        "items": (),
        "computed_at": _FIXED_WHEN,
    }

    s_pristine = compute_score(player=pristine, score_id=uuid4(), **common_kwargs)
    s_bruised = compute_score(player=bruised, score_id=uuid4(), **common_kwargs)

    # 5**2 * 3 * 1.0 = 75; pristine = 75, bruised = 75 - 10 = 65.
    assert s_pristine.value == 75
    assert s_bruised.value == 65
    assert s_bruised.damage_taken == 10


def test_compute_score_zero_kills_yields_zero() -> None:
    # Multiplicative-zero on the kills axis (composition with
    # compute_score_value, QUIZZES Task 1.7 Q1).
    dungeon = _dungeon(current_floor_index=9)  # floor 10
    score = compute_score(
        dungeon,
        _player(),
        kills=0,
        items=[_item(ItemType.WEAPON, count=10)],  # big multiplier, still 0
        score_id=uuid4(),
        computed_at=_FIXED_WHEN,
    )
    assert score.value == 0


def test_compute_score_empty_items_uses_baseline_multiplier() -> None:
    # Default `items=()` ⇒ baseline 1.0 ⇒ kills count directly.
    dungeon = _dungeon(current_floor_index=1)  # floor 2
    score = compute_score(dungeon, _player(), kills=7, score_id=uuid4(), computed_at=_FIXED_WHEN)
    # 2**2 * 7 * 1.0 = 28
    assert score.item_multiplier == 1.0
    assert score.value == 28


# --- compute_score: caller-supplied identifiers ---------------------------


def test_compute_score_score_id_is_passed_through() -> None:
    # No uuid4() generation inside the service — caller owns identity.
    sid = uuid4()
    score = compute_score(
        _dungeon(),
        _player(),
        kills=1,
        score_id=sid,
        computed_at=_FIXED_WHEN,
    )
    assert score.score_id == sid


def test_compute_score_user_and_dungeon_id_come_from_inputs() -> None:
    # Identity fields on Score are projections of the live state — not
    # synthesised. Future leaderboard joins rely on this contract.
    uid = uuid4()
    did = uuid4()
    score = compute_score(
        _dungeon(dungeon_id=did),
        _player(user_id=uid),
        kills=1,
        score_id=uuid4(),
        computed_at=_FIXED_WHEN,
    )
    assert score.user_id == uid
    assert score.dungeon_id == did


def test_compute_score_computed_at_is_passed_through() -> None:
    # QUIZZES Task 1.7 Q4 lock: timestamp from the caller, not
    # datetime.now() inside the service. Lets tests assert equality
    # without freezing the clock.
    fixed = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
    score = compute_score(_dungeon(), _player(), kills=1, score_id=uuid4(), computed_at=fixed)
    assert score.computed_at == fixed


# --- compute_score: purity contracts --------------------------------------


def test_compute_score_returns_frozen_score() -> None:
    # Sanity: Score is frozen (ADR-0002); the service must not return a
    # mutable proxy. Confirms the composition produces a real Score, not
    # some intermediate wrapper.
    score = compute_score(_dungeon(), _player(), kills=1, score_id=uuid4(), computed_at=_FIXED_WHEN)
    assert isinstance(score, Score)
    with pytest.raises(FrozenInstanceError):
        score.value = 0  # type: ignore[misc]


def test_compute_score_is_pure_repeatable() -> None:
    # Two calls with identical inputs ⇒ byte-identical Score (modulo
    # score_id, which is caller-supplied). Smoke test for purity — no
    # hidden RNG, no clock, no module-level mutable state leaking through.
    dungeon = _dungeon(current_floor_index=2)
    player = _player(damage_taken=2)
    items = [_item(ItemType.WEAPON), _item(ItemType.POTION, count=3)]
    sid = uuid4()

    a = compute_score(dungeon, player, kills=5, items=items, score_id=sid, computed_at=_FIXED_WHEN)
    b = compute_score(dungeon, player, kills=5, items=items, score_id=sid, computed_at=_FIXED_WHEN)

    assert a == b


def test_compute_score_does_not_mutate_inputs() -> None:
    # The service is pure modulo nothing — neither Dungeon nor Player nor
    # Item is touched. Snapshot via copy + equality compare. (The Floor
    # held on Dungeon.floors is itself mutable, so a deepcopy is the right
    # baseline; replace() / dataclass equality won't catch mutation inside
    # a nested list.)
    dungeon = _dungeon(current_floor_index=2)
    player = _player(damage_taken=4)
    items = [_item(ItemType.WEAPON, count=2), _item(ItemType.KEY)]
    snap_dungeon = copy.deepcopy(dungeon)
    snap_player = replace(player)
    snap_items = copy.deepcopy(items)

    compute_score(dungeon, player, kills=3, items=items, score_id=uuid4(), computed_at=_FIXED_WHEN)

    assert dungeon == snap_dungeon
    assert player == snap_player
    assert items == snap_items
