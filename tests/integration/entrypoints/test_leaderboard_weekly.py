"""Integration tests for ``GET /v1/leaderboard/weekly`` (task 3.11).

The route is exercised through ``TestClient`` with the ``GetLeaderboard`` use
case wired to hand-written port fakes (no DB / Redis) — the same harness style as
``test_leaderboard_global.py``. The real use case, schema mapping, and
query-param validation run; only the persistence ports are faked.

``/weekly`` is the same handler as ``/global`` with a different
``LeaderboardPeriod``, so these tests mirror the global suite but pin the
weekly-specific contract: the response echoes ``"WEEKLY"``, the use case is
called with ``LeaderboardPeriod.WEEKLY``, and the slice is cached under the
``leaderboard:WEEKLY`` key. The actual week-boundary truncation
(``date_trunc('week', now())``) lives in the Postgres adapter and is covered by
the task 2.6 DB integration tests, not here — the fake repository returns a
fixed ranked list regardless of window.

Like ``/global`` the weekly board is **public**, so no auth dependency is
overridden and requests carry no token.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.get_leaderboard import GetLeaderboard
from src.application.leaderboard_cache import (
    LEADERBOARD_CACHE_TTL_SECONDS,
    leaderboard_cache_key,
    serialize_leaderboard,
)
from src.config import Settings
from src.domain.models import LeaderboardPeriod, Score
from src.entrypoints.http.dependencies import get_leaderboard
from src.entrypoints.http.main import create_app

# --- Hand-written port fakes ----------------------------------------------


class FakeScoreRepository:
    """In-memory :class:`IScoreRepository` serving a fixed ranked list."""

    def __init__(self, scores: list[Score]) -> None:
        self.scores = scores
        self.top_n_calls: list[tuple[int, LeaderboardPeriod]] = []

    async def save(self, score: Score) -> Score:  # pragma: no cover - unused here
        return score

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        self.top_n_calls.append((n, period))
        return self.scores


class FakeCachePort:
    """In-memory :class:`ICachePort` recording value + TTL per key."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        return entry[0] if entry is not None else None

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.store[key] = (value, ttl)


# --- Builders --------------------------------------------------------------


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", cors_origins=["http://localhost:5173"])


def _score(value: int, *, user_id: UUID | None = None, floors: int = 5, kills: int = 3) -> Score:
    return Score(
        score_id=uuid4(),
        user_id=user_id or uuid4(),
        dungeon_id=uuid4(),
        floors_reached=floors,
        kills=kills,
        item_multiplier=1.0,
        damage_taken=2,
        value=value,
        computed_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


def _make_app(repo: FakeScoreRepository, cache: FakeCachePort) -> FastAPI:
    """Build an app whose ``GetLeaderboard`` uses ``repo``/``cache``.

    No auth override: the weekly board is public, so the real (absent) auth path
    is irrelevant and requests carry no token.
    """
    app = create_app(_settings())
    app.dependency_overrides[get_leaderboard] = lambda: GetLeaderboard(repo, cache)
    return app


# --- Tests -----------------------------------------------------------------


def test_returns_ranked_entries_on_cache_miss() -> None:
    top_user = uuid4()
    repo = FakeScoreRepository([_score(900, user_id=top_user), _score(400)])
    cache = FakeCachePort()
    client = TestClient(_make_app(repo, cache))

    resp = client.get("/v1/leaderboard/weekly")

    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "WEEKLY"
    assert [e["rank"] for e in body["entries"]] == [1, 2]
    assert body["entries"][0]["user_id"] == str(top_user)
    assert body["entries"][0]["value"] == 900
    # Miss path consulted the repo for the WEEKLY window and back-filled the cache.
    assert repo.top_n_calls == [(100, LeaderboardPeriod.WEEKLY)]
    stored = cache.store[leaderboard_cache_key(LeaderboardPeriod.WEEKLY)]
    assert stored[1] == LEADERBOARD_CACHE_TTL_SECONDS


def test_served_from_cache_without_touching_repo() -> None:
    cached = [_score(700), _score(300)]
    cache = FakeCachePort()
    cache.store[leaderboard_cache_key(LeaderboardPeriod.WEEKLY)] = (
        serialize_leaderboard(cached),
        LEADERBOARD_CACHE_TTL_SECONDS,
    )
    repo = FakeScoreRepository([_score(1)])  # different; must be ignored on a hit
    client = TestClient(_make_app(repo, cache))

    resp = client.get("/v1/leaderboard/weekly")

    assert resp.status_code == 200
    assert [e["value"] for e in resp.json()["entries"]] == [700, 300]
    assert repo.top_n_calls == []  # cache hit never hits the durable store


def test_pagination_slices_and_keeps_absolute_ranks() -> None:
    scores = [_score(v) for v in (900, 800, 700, 600)]
    client = TestClient(_make_app(FakeScoreRepository(scores), FakeCachePort()))

    resp = client.get("/v1/leaderboard/weekly?limit=2&offset=1")

    assert resp.status_code == 200
    entries = resp.json()["entries"]
    # offset=1 -> the 2nd and 3rd scores, ranked by absolute position (2, 3).
    assert [e["value"] for e in entries] == [800, 700]
    assert [e["rank"] for e in entries] == [2, 3]


def test_offset_past_end_returns_empty_page() -> None:
    client = TestClient(_make_app(FakeScoreRepository([_score(900)]), FakeCachePort()))

    resp = client.get("/v1/leaderboard/weekly?offset=50")

    assert resp.status_code == 200
    assert resp.json()["entries"] == []


def test_no_auth_required() -> None:
    client = TestClient(_make_app(FakeScoreRepository([_score(900)]), FakeCachePort()))

    # No Authorization header at all — a public endpoint must still answer 200,
    # unlike /game/* (401) or the future /leaderboard/me.
    resp = client.get("/v1/leaderboard/weekly")

    assert resp.status_code == 200


def test_limit_over_cap_is_rejected() -> None:
    client = TestClient(_make_app(FakeScoreRepository([]), FakeCachePort()))

    assert client.get("/v1/leaderboard/weekly?limit=101").status_code == 422
    assert client.get("/v1/leaderboard/weekly?limit=0").status_code == 422


def test_negative_offset_is_rejected() -> None:
    client = TestClient(_make_app(FakeScoreRepository([]), FakeCachePort()))

    assert client.get("/v1/leaderboard/weekly?offset=-1").status_code == 422


def test_global_cache_entry_is_not_served_by_weekly() -> None:
    # Period isolation: a pre-populated GLOBAL slice must not satisfy a /weekly
    # request. Guards against a copy-paste that forgets to swap the period — the
    # handler must read (and rebuild) the WEEKLY key, not GLOBAL.
    cache = FakeCachePort()
    cache.store[leaderboard_cache_key(LeaderboardPeriod.GLOBAL)] = (
        serialize_leaderboard([_score(999)]),
        LEADERBOARD_CACHE_TTL_SECONDS,
    )
    repo = FakeScoreRepository([_score(500)])
    client = TestClient(_make_app(repo, cache))

    resp = client.get("/v1/leaderboard/weekly")

    assert resp.status_code == 200
    # Did not serve the GLOBAL-cached 999; missed and rebuilt the WEEKLY slice.
    assert [e["value"] for e in resp.json()["entries"]] == [500]
    assert repo.top_n_calls == [(100, LeaderboardPeriod.WEEKLY)]
    assert leaderboard_cache_key(LeaderboardPeriod.WEEKLY) in cache.store
