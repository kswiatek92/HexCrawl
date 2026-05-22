"""Shared pytest fixtures for the domain-services test package.

Promoted from the per-file ``_floor`` / ``_dungeon`` / ``_player`` / ``_item``
helpers in ``test_score_service.py``. Lives here so the matrix and property
suites (``test_score_service_matrix.py``, ``test_score_service_properties.py``)
can build the same domain objects without re-declaring the constructors.

Exposed as **fixture-factories** (each fixture returns a callable) rather
than plain fixtures because every helper takes kwargs — pytest fixtures
themselves cannot be parametrised at call site. The factories keep the
test bodies terse: ``dungeon = make_dungeon(current_floor_index=4)``.

``make_dungeon`` preserves the invariant ``0 <= current_floor_index <
len(floors)`` by generating ``current_floor_index + 1`` floors — same
discipline as the helper in ``test_score_service.py`` after the fix from
the Copilot review on PR #34.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.domain.models import (
    Dungeon,
    Floor,
    Item,
    ItemType,
    Player,
    TileType,
)


@pytest.fixture
def make_floor() -> Callable[[], Floor]:
    def _make() -> Floor:
        return Floor(
            floor_id=uuid4(),
            tiles=[[TileType.FLOOR]],
            enemies=[],
            items={},
            stairs_down=(0, 0),
        )

    return _make


@pytest.fixture
def make_dungeon(make_floor: Callable[[], Floor]) -> Callable[..., Dungeon]:
    def _make(*, current_floor_index: int = 0, dungeon_id: UUID | None = None) -> Dungeon:
        return Dungeon(
            dungeon_id=dungeon_id or uuid4(),
            seed=42,
            floors=[make_floor() for _ in range(current_floor_index + 1)],
            current_floor_index=current_floor_index,
        )

    return _make


@pytest.fixture
def make_player() -> Callable[..., Player]:
    def _make(*, user_id: UUID | None = None, damage_taken: int = 0) -> Player:
        return Player(
            user_id=user_id or uuid4(),
            name="hero",
            position=(0, 0),
            damage_taken=damage_taken,
        )

    return _make


@pytest.fixture
def make_item() -> Callable[..., Item]:
    def _make(item_type: ItemType, *, count: int = 1) -> Item:
        return Item(
            item_id=uuid4(),
            name=item_type.value.lower(),
            item_type=item_type,
            count=count,
        )

    return _make


@pytest.fixture
def fixed_when() -> datetime:
    return datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
