"""Integration tests for ``WS /ws/game/{session_id}`` (task 3.9).

The endpoint is exercised through ``TestClient``'s in-process WebSocket transport
(no real ``websockets`` server needed). The ``GameSessionRunner`` is overridden
with a fake backed by hand-written port fakes that drives the **real** ``GetGame``
/ ``ProcessTurn`` use cases and the real ``game_state`` codec — so the only thing
faked is persistence, mirroring ``test_game_abandon.py``. The JWKS verifier is
overridden with a stub that accepts a known token and rejects the rest.

Auth is first-message (no header): every test opens the socket, then sends an
``{"type":"auth","token":...}`` frame as its first message.
"""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from jwt import InvalidTokenError

from src.application.game_state import deserialize_game_state, game_state_cache_key
from src.application.get_game import GetGame
from src.application.process_turn import ProcessTurn
from src.config import Settings
from src.domain.models import Action, Dungeon, Floor, Player, TileType
from src.domain.services import TurnResult
from src.entrypoints.http.auth import AuthenticatedUser, get_verifier
from src.entrypoints.http.dependencies import get_game_session_runner
from src.entrypoints.http.main import create_app

_VALID_TOKEN = "good-token"

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


class FakeRunner:
    """Stand-in for ``GameSessionRunner`` that drives the real use cases on fakes.

    Faithfully mirrors the production runner's two operations — ``load_authorized``
    via ``GetGame`` and ``process`` via ``ProcessTurn`` followed by the cache
    re-read — without opening a DB session.
    """

    def __init__(self, repo: FakeGameRepository, cache: FakeCachePort) -> None:
        self._repo = repo
        self._cache = cache

    async def load_authorized(self, game_id: UUID, requester_id: UUID) -> tuple[Dungeon, Player]:
        return await GetGame(self._repo, self._cache).execute(game_id, requester_id)

    async def process(self, game_id: UUID, action: Action) -> tuple[TurnResult, Dungeon, Player]:
        result = await ProcessTurn(self._repo, self._cache).execute(game_id, action)
        blob = await self._cache.get(game_state_cache_key(game_id))
        assert blob is not None  # ProcessTurn always refreshes the cache
        dungeon, player = deserialize_game_state(blob)
        return result, dungeon, player


class StubVerifier:
    """Verifier that accepts ``_VALID_TOKEN`` and rejects everything else."""

    def __init__(self, principal: AuthenticatedUser) -> None:
        self._principal = principal

    def verify(self, token: str) -> AuthenticatedUser:
        if token == _VALID_TOKEN:
            return self._principal
        raise InvalidTokenError("bad token")


# --- App / client builders -------------------------------------------------


def _settings() -> Settings:
    return Settings(jwt_secret="test-secret", cors_origins=["http://localhost:5173"])


def _make_app(
    repo: FakeGameRepository,
    cache: FakeCachePort,
    *,
    principal: AuthenticatedUser,
) -> FastAPI:
    """Build an app whose WS runner uses ``repo``/``cache`` and whose verifier
    accepts ``_VALID_TOKEN`` as ``principal``."""
    app = create_app(_settings())
    runner = FakeRunner(repo, cache)
    app.dependency_overrides[get_game_session_runner] = lambda: runner
    app.dependency_overrides[get_verifier] = lambda: StubVerifier(principal)
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


def test_auth_then_wait_returns_connected_and_turn_frames(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    owner = uuid4()
    game_id = _seed_run(repo, owner=owner, seed=42)
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=owner)))

    with client.websocket_connect(f"/ws/game/{game_id}") as ws:
        ws.send_json({"type": "auth", "token": _VALID_TOKEN})

        connected = ws.receive_json()
        assert connected["type"] == "connected"
        assert UUID(connected["game_id"]) == game_id
        assert connected["state"]["seed"] == 42
        assert connected["state"]["turn_count"] == 0

        ws.send_json({"action": "wait"})
        turn = ws.receive_json()
        assert turn["type"] == "turn"
        assert turn["game_over"] is False
        # turn_count advances 0 -> 1 only because the turn actually ran.
        assert turn["state"]["turn_count"] == 1
        assert isinstance(turn["events"], list)


# --- Auth handshake --------------------------------------------------------


def test_invalid_token_closes_1008(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    game_id = _seed_run(repo, owner=uuid4())
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4())))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/game/{game_id}") as ws:
            ws.send_json({"type": "auth", "token": "wrong"})
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_missing_token_closes_1008(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    game_id = _seed_run(repo, owner=uuid4())
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4())))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/game/{game_id}") as ws:
            ws.send_json({"type": "auth"})  # no token field
            ws.receive_json()
    assert exc_info.value.code == 1008


# --- Authorisation at connect ---------------------------------------------


def test_unknown_game_closes_1008(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    # No run seeded for this id -> GetGame raises GameNotFoundError.
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=uuid4())))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/game/{uuid4()}") as ws:
            ws.send_json({"type": "auth", "token": _VALID_TOKEN})
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_foreign_run_closes_1008(repo: FakeGameRepository, cache: FakeCachePort) -> None:
    owner = uuid4()
    intruder = uuid4()
    game_id = _seed_run(repo, owner=owner)
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=intruder)))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/game/{game_id}") as ws:
            ws.send_json({"type": "auth", "token": _VALID_TOKEN})
            ws.receive_json()
    assert exc_info.value.code == 1008
    # A rejected connection must not have advanced or persisted anything.
    assert cache.store == {}


# --- Resilience: one bad message must not kill the loop --------------------


def test_unknown_action_returns_error_frame_then_loop_survives(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    owner = uuid4()
    game_id = _seed_run(repo, owner=owner)
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=owner)))

    with client.websocket_connect(f"/ws/game/{game_id}") as ws:
        ws.send_json({"type": "auth", "token": _VALID_TOKEN})
        assert ws.receive_json()["type"] == "connected"

        ws.send_json({"action": "teleport"})  # unknown action
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "unknown action" in error["detail"]

        # The session is still alive: a valid action still processes.
        ws.send_json({"action": "wait"})
        assert ws.receive_json()["type"] == "turn"


def test_non_json_text_returns_error_frame_then_loop_survives(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    owner = uuid4()
    game_id = _seed_run(repo, owner=owner)
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=owner)))

    with client.websocket_connect(f"/ws/game/{game_id}") as ws:
        ws.send_json({"type": "auth", "token": _VALID_TOKEN})
        assert ws.receive_json()["type"] == "connected"

        ws.send_text("this is not json")
        error = ws.receive_json()
        assert error["type"] == "error"

        ws.send_json({"action": "wait"})
        assert ws.receive_json()["type"] == "turn"


# --- Game over -------------------------------------------------------------


def test_abandon_sends_game_over_then_closes_1000(
    repo: FakeGameRepository, cache: FakeCachePort
) -> None:
    owner = uuid4()
    game_id = _seed_run(repo, owner=owner)
    client = TestClient(_make_app(repo, cache, principal=AuthenticatedUser(user_id=owner)))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/game/{game_id}") as ws:
            ws.send_json({"type": "auth", "token": _VALID_TOKEN})
            assert ws.receive_json()["type"] == "connected"

            ws.send_json({"action": "abandon"})
            turn = ws.receive_json()
            assert turn["type"] == "turn"
            assert turn["game_over"] is True
            assert any(e["type"] == "run_abandoned" for e in turn["events"])

            # Server closes normally after game over.
            ws.receive_json()
    assert exc_info.value.code == 1000
