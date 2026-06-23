"""Integration tests for ``POST /v1/game/start`` (task 3.6).

The route is exercised through ``TestClient`` with the use case wired to
hand-written port fakes (no DB / Redis) and the auth dependency overridden —
the same override style as ``test_main.py``. The real ``StartGame`` use case
and the real domain generator run, so a started game produces a genuine 80×50
floor and a spawned player; only the persistence ports are faked.

Auth is overridden two ways depending on the test:

* most tests override ``get_current_user`` with a fixed principal — that
  short-circuits token verification entirely (the verifier subtree is never
  resolved);
* the "auth required" test leaves ``get_current_user`` real and instead
  overrides ``get_verifier`` with a stub, so dependency resolution doesn't try
  to build a Supabase JWKS client (which needs ``SUPABASE_URL``). With no
  ``Authorization`` header, the real dependency returns 401 before the stub is
  ever called.
"""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.start_game import StartGame
from src.config import Settings
from src.domain.models import Dungeon, Player
from src.entrypoints.http.auth import AuthenticatedUser, get_current_user, get_verifier
from src.entrypoints.http.dependencies import get_start_game
from src.entrypoints.http.main import create_app

# --- Hand-written port fakes ----------------------------------------------


class FakeGameRepository:
    """In-memory :class:`IGameRepository`: ``save`` stores, ``get`` reads back."""

    def __init__(self) -> None:
        self.saved: dict[UUID, tuple[Dungeon, Player]] = {}

    async def save(self, dungeon: Dungeon, player: Player) -> tuple[Dungeon, Player]:
        self.saved[dungeon.dungeon_id] = (dungeon, player)
        return dungeon, player

    async def get(self, game_id: UUID) -> tuple[Dungeon, Player] | None:
        return self.saved.get(game_id)


class FakeCachePort:
    """In-memory :class:`ICachePort` recording value + TTL per key."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        return entry[0] if entry is not None else None

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.store[key] = (value, ttl)


class _StubVerifier:
    """Stand-in for the JWKS verifier; only resolved, never invoked here."""

    def verify(self, token: str) -> AuthenticatedUser:  # pragma: no cover
        raise AssertionError("verifier should not be called in these tests")


# --- App / client builders -------------------------------------------------


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", cors_origins=["http://localhost:5173"])


def _make_app(
    repo: FakeGameRepository,
    cache: FakeCachePort,
    *,
    principal: AuthenticatedUser | None,
) -> FastAPI:
    """Build an app whose ``StartGame`` uses ``repo``/``cache``.

    If ``principal`` is given, ``get_current_user`` is overridden to return it
    (auth bypassed). If ``None``, the real auth dependency stays in place and
    only ``get_verifier`` is stubbed, so an unauthenticated request yields a
    real 401.
    """
    app = create_app(_settings())
    app.dependency_overrides[get_start_game] = lambda: StartGame(repo, cache)
    if principal is not None:
        app.dependency_overrides[get_current_user] = lambda: principal
    else:
        app.dependency_overrides[get_verifier] = _StubVerifier
    return app


@pytest.fixture
def repo() -> FakeGameRepository:
    return FakeGameRepository()


@pytest.fixture
def cache() -> FakeCachePort:
    return FakeCachePort()


# These tests override the use-case and auth dependencies, so the lifespan's
# DB/Redis resources are never touched — a plain ``TestClient`` (no context
# manager, no lifespan) is enough and avoids building unused engine/clients.


# --- Happy path ------------------------------------------------------------


def test_start_returns_201_with_location_and_full_state(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    user_id = uuid4()
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=user_id))
    client = TestClient(app)

    resp = client.post("/v1/game/start", json={"player_name": "hero", "seed": 42})

    assert resp.status_code == 201
    body = resp.json()

    # The created run is the one the repository now holds (not just "a 201").
    game_id = UUID(body["game_id"])
    assert game_id in repo.saved
    saved_dungeon, saved_player = repo.saved[game_id]

    # Location points at the run's canonical (GET 3.7) URL.
    assert resp.headers["Location"] == f"/v1/game/{game_id}"

    assert body["seed"] == 42
    assert body["current_floor_index"] == 0
    assert body["turn_count"] == 0

    # Full floor is returned, genuinely generated at 80×50.
    floor = body["floor"]
    assert floor["width"] == 80
    assert floor["height"] == 50
    assert len(floor["tiles"]) == 50
    assert all(len(row) == 80 for row in floor["tiles"])

    # Player is at the spawned position the use case persisted.
    assert tuple(body["player"]["position"]) == saved_player.position
    assert body["player"]["hp"] == 20
    # Identity / internal fields are not leaked into the player view.
    assert "user_id" not in body["player"]
    assert "damage_taken" not in body["player"]


def test_identity_comes_from_token_not_body(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    token_user = uuid4()
    body_user = uuid4()
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=token_user))
    client = TestClient(app)

    # A stray user_id in the body must be ignored — ownership follows the token.
    resp = client.post(
        "/v1/game/start",
        json={"player_name": "hero", "user_id": str(body_user)},
    )

    assert resp.status_code == 201
    game_id = UUID(resp.json()["game_id"])
    _, saved_player = repo.saved[game_id]
    assert saved_player.user_id == token_user
    assert saved_player.user_id != body_user


def test_explicit_seed_is_reproducible(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4()))
    client = TestClient(app)

    first = client.post("/v1/game/start", json={"player_name": "a", "seed": 123})
    second = client.post("/v1/game/start", json={"player_name": "b", "seed": 123})

    # Same seed → identical generated floor (determinism the leaderboard relies on).
    assert first.json()["floor"]["tiles"] == second.json()["floor"]["tiles"]


# --- Auth ------------------------------------------------------------------


def test_unauthenticated_request_is_401(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    app = _make_app(repo, cache, principal=None)
    client = TestClient(app)

    resp = client.post("/v1/game/start", json={"player_name": "hero"})

    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"
    # The use case never ran — nothing was persisted.
    assert repo.saved == {}


# --- Validation ------------------------------------------------------------


def test_out_of_range_seed_is_422(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4()))
    client = TestClient(app)

    resp = client.post(
        "/v1/game/start",
        json={"player_name": "hero", "seed": 2**63},  # one past signed-64-bit max
    )

    assert resp.status_code == 422
    assert repo.saved == {}


def test_empty_player_name_is_422(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4()))
    client = TestClient(app)

    resp = client.post("/v1/game/start", json={"player_name": ""})

    assert resp.status_code == 422
    assert repo.saved == {}
