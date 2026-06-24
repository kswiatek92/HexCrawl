"""Integration tests for the RFC 7807 Problem Details error shape (task 3.13).

Asserts that every HTTP error leaves as ``application/problem+json`` with the
standard members (``type`` / ``title`` / ``status`` / ``instance``), exercised
through real endpoints rather than the handlers in isolation:

* a 404 / 403 from ``GET /game/{id}`` (mapped from use-case exceptions),
* a 401 from the auth dependency — checking the ``WWW-Authenticate`` header
  survives the handler,
* a 422 from query-param validation on ``/leaderboard/global`` — checking the
  per-field ``errors`` extension member rides along.

The harness reuses the fakes pattern from ``test_game_get.py`` /
``test_leaderboard_global.py``: real routing + handlers, faked persistence.
"""

from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.get_game import GetGame
from src.application.get_leaderboard import GetLeaderboard
from src.config import Settings
from src.domain.models import Dungeon, Floor, LeaderboardPeriod, Player, Score, TileType
from src.entrypoints.http.auth import AuthenticatedUser, get_current_user, get_verifier
from src.entrypoints.http.dependencies import get_get_game, get_leaderboard
from src.entrypoints.http.main import create_app
from src.entrypoints.http.problem_details import PROBLEM_JSON_MEDIA_TYPE

# --- Hand-written port fakes ----------------------------------------------


class FakeGameRepository:
    def __init__(self) -> None:
        self.saved: dict[UUID, tuple[Dungeon, Player]] = {}

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self.saved[dungeon.dungeon_id] = (dungeon, player)
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        return self.saved.get(game_id)


class FakeCachePort:
    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        return entry[0] if entry is not None else None

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.store[key] = (value, ttl)


class FakeScoreRepository:
    async def save(self, score: Score) -> Score:  # pragma: no cover - unused here
        return score

    async def top_n(self, n: int, period: LeaderboardPeriod) -> list[Score]:
        return []


class _StubVerifier:
    def verify(self, token: str) -> AuthenticatedUser:  # pragma: no cover
        raise AssertionError("verifier should not be called in these tests")


class _RaisingLeaderboard:
    """A use case that raises an unexpected fault — to exercise the 500 path."""

    async def execute(self, period: LeaderboardPeriod) -> list[Score]:
        raise RuntimeError("boom: internal detail that must not leak to the client")


# --- Builders --------------------------------------------------------------


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", cors_origins=["http://localhost:5173"])


def _seed_run(repo: FakeGameRepository, *, owner: UUID) -> UUID:
    game_id = uuid4()
    floor = Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR] * 80 for _ in range(50)],
        enemies=[],
        items={},
        stairs_down=(2, 2),
    )
    dungeon = Dungeon(dungeon_id=game_id, seed=7, floors=[floor], current_floor_index=0)
    player = Player(user_id=owner, name="hero", position=(1, 1))
    repo.saved[game_id] = (dungeon, player)
    return game_id


def _game_app(repo: FakeGameRepository, *, principal: AuthenticatedUser | None) -> FastAPI:
    app = create_app(_settings())
    app.dependency_overrides[get_get_game] = lambda: GetGame(repo, FakeCachePort())
    if principal is not None:
        app.dependency_overrides[get_current_user] = lambda: principal
    else:
        app.dependency_overrides[get_verifier] = _StubVerifier
    return app


def _leaderboard_app() -> FastAPI:
    app = create_app(_settings())
    app.dependency_overrides[get_leaderboard] = lambda: GetLeaderboard(
        FakeScoreRepository(), FakeCachePort()
    )
    return app


# --- Tests -----------------------------------------------------------------


def test_404_is_problem_json_with_standard_members() -> None:
    repo = FakeGameRepository()
    client = TestClient(_game_app(repo, principal=AuthenticatedUser(user_id=uuid4())))

    resp = client.get(f"/v1/game/{uuid4()}")

    assert resp.status_code == 404
    assert resp.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
    body = resp.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["type"] == "about:blank"
    assert body["detail"] == "game not found"
    # instance points at the failing request path.
    assert body["instance"].startswith("/v1/game/")


def test_403_is_problem_json() -> None:
    repo = FakeGameRepository()
    game_id = _seed_run(repo, owner=uuid4())
    # Authenticated as someone other than the owner.
    client = TestClient(_game_app(repo, principal=AuthenticatedUser(user_id=uuid4())))

    resp = client.get(f"/v1/game/{game_id}")

    assert resp.status_code == 403
    assert resp.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
    body = resp.json()
    assert body["status"] == 403
    assert body["title"] == "Forbidden"
    assert body["detail"] == "not your game"


def test_401_problem_json_preserves_www_authenticate_header() -> None:
    repo = FakeGameRepository()
    game_id = _seed_run(repo, owner=uuid4())
    client = TestClient(_game_app(repo, principal=None))

    resp = client.get(f"/v1/game/{game_id}")

    assert resp.status_code == 401
    assert resp.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
    # The 401's WWW-Authenticate header must survive the problem-detail handler.
    assert resp.headers.get("WWW-Authenticate") == "Bearer"
    assert resp.json()["status"] == 401


def test_422_validation_carries_errors_extension_member() -> None:
    client = TestClient(_leaderboard_app())

    resp = client.get("/v1/leaderboard/global?limit=101")

    assert resp.status_code == 422
    assert resp.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
    body = resp.json()
    assert body["status"] == 422
    assert body["title"] == "Unprocessable Entity"
    # The per-field validation breakdown rides along as an extension member.
    assert isinstance(body["errors"], list)
    assert body["errors"]  # non-empty: the limit-cap violation is reported


def test_unhandled_exception_is_problem_json_500_without_leaking_internals() -> None:
    app = create_app(_settings())
    # Wire the route to a use case that raises an unexpected RuntimeError.
    app.dependency_overrides[get_leaderboard] = lambda: _RaisingLeaderboard()
    # raise_server_exceptions=False so the TestClient returns the 500 response
    # instead of re-raising the propagated exception.
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/v1/leaderboard/global")

    assert resp.status_code == 500
    assert resp.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
    body = resp.json()
    assert body["status"] == 500
    assert body["title"] == "Internal Server Error"
    assert body["detail"] == "An unexpected error occurred."
    # The exception message must never reach the client.
    assert "boom" not in resp.text
