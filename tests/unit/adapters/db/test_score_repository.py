"""Pure mapper guards for PostgresScoreRepository (no DB).

These lock the Score<->ORM translation — the part a Postgres round trip can't
isolate. The mappers (`_to_values`/`_to_domain`) touch no session, so a full
`_to_domain(ScoreRow(**_to_values(...)))` round trip runs in-memory. The real
query behaviour (ordering, weekly window, rank_of, ON CONFLICT idempotency)
needs a live Postgres and is covered by the task 2.6 integration tests.

Field values are deliberately all-distinct so a swapped field or a
constant-returning mapper can't pass.
"""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.db.models import ScoreRow
from src.adapters.db.score_repository import (
    PostgresScoreRepository,
    _to_domain,
    _to_values,
)
from src.domain.models import Score
from src.domain.ports import IScoreRepository


def _score(*, user_id: UUID | None = None) -> Score:
    # Every numeric field distinct: catches a transposed mapper line.
    return Score(
        score_id=uuid4(),
        user_id=user_id or uuid4(),
        dungeon_id=uuid4(),
        floors_reached=7,
        kills=13,
        item_multiplier=2.5,
        damage_taken=4,
        value=812,
        computed_at=datetime(2026, 6, 14, 12, 30, tzinfo=UTC),
    )


def test_round_trip_preserves_score() -> None:
    score = _score()
    assert _to_domain(ScoreRow(**_to_values(score))) == score


def test_to_values_carries_all_fields_including_conflict_key() -> None:
    score = _score()
    values = _to_values(score)
    # score_id must be present: it is the ON CONFLICT target in save().
    assert values["score_id"] == score.score_id
    assert set(values) == {
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


def test_to_domain_reads_each_field() -> None:
    score = _score()
    restored = _to_domain(ScoreRow(**_to_values(score)))
    assert restored.floors_reached == 7
    assert restored.kills == 13
    assert restored.item_multiplier == 2.5
    assert restored.damage_taken == 4
    assert restored.value == 812
    assert restored.computed_at == datetime(2026, 6, 14, 12, 30, tzinfo=UTC)


def test_repository_conforms_to_protocol() -> None:
    # Structural (Protocol) conformance is verified by mypy via the annotation;
    # no session call is made, so a cast-None session is harmless here.
    repo: IScoreRepository = PostgresScoreRepository(cast(AsyncSession, None))
    assert isinstance(repo, PostgresScoreRepository)
