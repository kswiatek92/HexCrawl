"""Tests for ``src.application.leaderboard_cache`` — the leaderboard codec.

Pure, I/O-free unit tests for the key/TTL constants and the
``list[Score]`` <-> JSON round-trip. The codec is the application-layer home for
the leaderboard cache's wire shape (mirroring ``game_state``); these assert it is
an exact inverse so a corrupted-on-the-wire score can never silently differ from
the persisted one.
"""

from datetime import UTC, datetime
from uuid import uuid4

from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    LEADERBOARD_SIZE,
    deserialize_leaderboard,
    leaderboard_cache_key,
    serialize_leaderboard,
)
from src.domain.models import LeaderboardPeriod, Score


def _score(value: int, *, floors: int = 3, kills: int = 4) -> Score:
    """Build a non-trivial ``Score`` with distinct field values.

    Distinct numbers per field mean a codec that crossed two fields (or dropped
    one) would fail the round-trip assertion, not pass by coincidence.
    """
    return Score(
        score_id=uuid4(),
        user_id=uuid4(),
        dungeon_id=uuid4(),
        floors_reached=floors,
        kills=kills,
        item_multiplier=1.5,
        damage_taken=7,
        value=value,
        computed_at=datetime(2026, 6, 24, 10, 30, 15, tzinfo=UTC),
    )


def test_round_trip_preserves_scores_and_order() -> None:
    scores = [_score(900, floors=10, kills=5), _score(450, floors=4, kills=2)]

    restored = deserialize_leaderboard(serialize_leaderboard(scores))

    # Frozen dataclass equality compares every field, incl. computed_at and the
    # UUIDs — so this fails if any field is dropped, mistyped, or reordered.
    assert restored == scores


def test_round_trip_empty_list() -> None:
    assert deserialize_leaderboard(serialize_leaderboard([])) == []


def test_computed_at_survives_as_aware_datetime() -> None:
    [restored] = deserialize_leaderboard(serialize_leaderboard([_score(100)]))

    assert restored.computed_at == datetime(2026, 6, 24, 10, 30, 15, tzinfo=UTC)
    assert restored.computed_at.tzinfo is not None


def test_cache_key_is_namespaced_per_period() -> None:
    assert leaderboard_cache_key(LeaderboardPeriod.GLOBAL) == "leaderboard:GLOBAL"
    assert leaderboard_cache_key(LeaderboardPeriod.WEEKLY) == "leaderboard:WEEKLY"


def test_constants() -> None:
    assert LEADERBOARD_SIZE == 100
    assert LEADERBOARD_CACHE_TTL_SECONDS == 300
