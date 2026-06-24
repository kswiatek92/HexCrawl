"""Integration tests for ``GET /v1/leaderboard/me`` (task 3.12).

The route is exercised through ``TestClient`` with the ``GetMyScores`` use case
wired to a hand-written ``IScoreRepository`` fake (no DB / Redis). The real use
case, schema mapping, and query-param validation run; only persistence is faked.

Unlike ``/global`` and ``/weekly`` this board is **authenticated**, so the
harness mirrors ``test_game_get.py``: most tests override ``get_current_user``
with a fixed principal; the "auth required" test instead stubs ``get_verifier``
and sends no token so the real dependency returns 401.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.get_my_scores import GetMyScores
from src.config import Settings
from src.domain.models import LeaderboardPeriod, Score
from src.entrypoints.http.auth import AuthenticatedUser, get_current_user, get_verifier
from src.entrypoints.http.dependencies import get_my_scores
from src.entrypoints.http.main import create_app

# --- Hand-written port fake -----------------------------------------------


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository` serving a fixed per-user board."""

    def __init__(
        self,
        *,
        user_scores: list[Score] | None = None,
        ranks: dict[LeaderboardPeriod, int | None] | None = None,
    ) -> None:
        self.user_scores = user_scores if user_scores is not None else []
        self.ranks = ranks if ranks is not None else {}

    async def save(self, score: Score) -> Score:  # pragma: no cover - unused here
        return score

    async def top_n(  # pragma: no cover - unused here
        self, n: int, period: LeaderboardPeriod
    ) -> list[Score]:
        return []

    async def top_n_for_user(self, user_id: UUID, n: int) -> list[Score]:
        return self.user_scores

    async def rank_of(self, user_id: UUID, period: LeaderboardPeriod) -> int | None:
        return self.ranks.get(period)


class _StubVerifier:
    """Stand-in for the JWKS verifier; only resolved, never invoked here."""

    def verify(self, token: str) -> AuthenticatedUser:  # pragma: no cover
        raise AssertionError("verifier should not be called in these tests")


# --- App / client builders -------------------------------------------------


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", cors_origins=["http://localhost:5173"])


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


def _make_app(
    repo: FakeScoreRepository,
    *,
    principal: AuthenticatedUser | None,
) -> FastAPI:
    """Build an app whose ``GetMyScores`` uses ``repo``.

    If ``principal`` is given, ``get_current_user`` is overridden to return it.
    If ``None``, the real auth dependency stays and only ``get_verifier`` is
    stubbed, so an unauthenticated request yields a real 401.
    """
    app = create_app(_settings())
    app.dependency_overrides[get_my_scores] = lambda: GetMyScores(repo)
    if principal is not None:
        app.dependency_overrides[get_current_user] = lambda: principal
    else:
        app.dependency_overrides[get_verifier] = _StubVerifier
    return app


# --- Happy path ------------------------------------------------------------


def test_returns_personal_bests_with_board_ranks() -> None:
    me = uuid4()
    repo = FakeScoreRepository(
        user_scores=[_score(900, user_id=me), _score(400, user_id=me)],
        ranks={LeaderboardPeriod.GLOBAL: 3, LeaderboardPeriod.WEEKLY: 1},
    )
    client = TestClient(_make_app(repo, principal=AuthenticatedUser(user_id=me)))

    resp = client.get("/v1/leaderboard/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["global_rank"] == 3
    assert body["weekly_rank"] == 1
    # Entries are the user's own runs, ranked by their position in that history.
    assert [e["rank"] for e in body["entries"]] == [1, 2]
    assert [e["value"] for e in body["entries"]] == [900, 400]
    assert body["entries"][0]["user_id"] == str(me)


def test_unranked_user_has_null_ranks_and_empty_entries() -> None:
    me = uuid4()
    repo = FakeScoreRepository(user_scores=[], ranks={})  # fresh account
    client = TestClient(_make_app(repo, principal=AuthenticatedUser(user_id=me)))

    resp = client.get("/v1/leaderboard/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["global_rank"] is None
    assert body["weekly_rank"] is None
    assert body["entries"] == []


def test_pagination_slices_and_keeps_absolute_ranks() -> None:
    me = uuid4()
    repo = FakeScoreRepository(
        user_scores=[_score(v, user_id=me) for v in (900, 800, 700, 600)],
        ranks={LeaderboardPeriod.GLOBAL: 1},
    )
    client = TestClient(_make_app(repo, principal=AuthenticatedUser(user_id=me)))

    resp = client.get("/v1/leaderboard/me?limit=2&offset=1")

    assert resp.status_code == 200
    body = resp.json()
    entries = body["entries"]
    assert [e["value"] for e in entries] == [800, 700]
    assert [e["rank"] for e in entries] == [2, 3]
    # Board rank is pagination-independent — still the user's true global rank.
    assert body["global_rank"] == 1


# --- Auth ------------------------------------------------------------------


def test_unauthenticated_is_401() -> None:
    repo = FakeScoreRepository()
    client = TestClient(_make_app(repo, principal=None))

    resp = client.get("/v1/leaderboard/me")

    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


# --- Validation ------------------------------------------------------------


def test_limit_over_cap_is_rejected() -> None:
    client = TestClient(
        _make_app(FakeScoreRepository(), principal=AuthenticatedUser(user_id=uuid4()))
    )

    assert client.get("/v1/leaderboard/me?limit=101").status_code == 422
    assert client.get("/v1/leaderboard/me?limit=0").status_code == 422


def test_negative_offset_is_rejected() -> None:
    client = TestClient(
        _make_app(FakeScoreRepository(), principal=AuthenticatedUser(user_id=uuid4()))
    )

    assert client.get("/v1/leaderboard/me?offset=-1").status_code == 422
