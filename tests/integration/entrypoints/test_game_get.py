"""Integration tests for ``GET /v1/game/{id}`` (task 3.7).

The route is exercised through ``TestClient`` with the ``GetGame`` use case wired
to hand-written port fakes (no DB / Redis) and the auth dependency overridden —
the same harness style as ``test_game_start.py``. The real use case and the real
schema mapping run; only the persistence ports are faked.

Auth is overridden two ways depending on the test (see ``test_game_start.py`` for
the full rationale): most tests override ``get_current_user`` with a fixed
principal; the "auth required" test instead stubs ``get_verifier`` and sends no
token so the real dependency returns 401.
"""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.get_game import GetGame
from src.config import Settings
from src.domain.models import Dungeon, Floor, Player, TileType
from src.entrypoints.http.auth import AuthenticatedUser, get_current_user, get_verifier
from src.entrypoints.http.dependencies import get_get_game
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
    """Build an app whose ``GetGame`` uses ``repo``/``cache``.

    If ``principal`` is given, ``get_current_user`` is overridden to return it
    (auth bypassed). If ``None``, the real auth dependency stays in place and
    only ``get_verifier`` is stubbed, so an unauthenticated request yields a
    real 401.
    """
    app = create_app(_settings())
    app.dependency_overrides[get_get_game] = lambda: GetGame(repo, cache)
    if principal is not None:
        app.dependency_overrides[get_current_user] = lambda: principal
    else:
        app.dependency_overrides[get_verifier] = _StubVerifier
    return app


def _seed_run(repo: FakeGameRepository, *, owner: UUID, seed: int = 7) -> UUID:
    """Persist a minimal valid run owned by ``owner`` into ``repo``; return its id."""
    game_id = uuid4()
    floor = Floor(
        floor_id=uuid4(),
        tiles=[[TileType.FLOOR] * 80 for _ in range(50)],
        enemies=[],
        items={},
        stairs_down=(2, 2),
    )
    dungeon = Dungeon(dungeon_id=game_id, seed=seed, floors=[floor], current_floor_index=0)
    player = Player(user_id=owner, name="hero", position=(1, 1))
    repo.saved[game_id] = (dungeon, player)
    return game_id


@pytest.fixture
def repo() -> FakeGameRepository:
    return FakeGameRepository()


@pytest.fixture
def cache() -> FakeCachePort:
    return FakeCachePort()


# --- Happy path ------------------------------------------------------------


def test_get_returns_200_with_full_state_for_owner(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    owner = uuid4()
    game_id = _seed_run(repo, owner=owner, seed=42)
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=owner))
    client = TestClient(app)

    resp = client.get(f"/v1/game/{game_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert UUID(body["game_id"]) == game_id
    assert body["seed"] == 42
    assert body["current_floor_index"] == 0

    floor = body["floor"]
    assert floor["width"] == 80
    assert floor["height"] == 50

    assert tuple(body["player"]["position"]) == (1, 1)
    # Identity / internal fields are not leaked into the player view.
    assert "user_id" not in body["player"]
    assert "damage_taken" not in body["player"]


# --- Not found -------------------------------------------------------------


def test_get_unknown_id_is_404(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4()))
    client = TestClient(app)

    resp = client.get(f"/v1/game/{uuid4()}")

    assert resp.status_code == 404


# --- Ownership -------------------------------------------------------------


def test_get_foreign_run_is_403(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    owner = uuid4()
    intruder = uuid4()
    game_id = _seed_run(repo, owner=owner)
    # The caller is authenticated as someone other than the run's owner.
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=intruder))
    client = TestClient(app)

    resp = client.get(f"/v1/game/{game_id}")

    assert resp.status_code == 403


# --- Auth ------------------------------------------------------------------


def test_get_unauthenticated_is_401(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    game_id = _seed_run(repo, owner=uuid4())
    app = _make_app(repo, cache, principal=None)
    client = TestClient(app)

    resp = client.get(f"/v1/game/{game_id}")

    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


# --- Validation ------------------------------------------------------------


def test_get_non_uuid_id_is_422(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    app = _make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4()))
    client = TestClient(app)

    resp = client.get("/v1/game/not-a-uuid")

    assert resp.status_code == 422
