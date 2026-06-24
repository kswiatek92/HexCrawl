"""WebSocket turn-loop endpoint — ``WS /ws/game/{session_id}``.

The real-time half of the game API (CLAUDE.md → "WebSocket turn loop"). A client
opens a long-lived socket, authenticates with its Supabase access token, then
sends one :class:`~src.domain.models.Action` per message and receives the
resulting game state plus the turn's event narrative back. The handler is a thin
adapter: it owns the *socket lifecycle* and the *wire framing*, and reaches the
game rules only through the application use cases, via :class:`GameSessionRunner`.

**Lifecycle** (QUIZZES task 3.9 Q1):

1. ``accept()`` the upgrade.
2. **First-message auth** (Q2): browsers can't set WS headers, so instead of a
   bearer header we await an ``{"type": "auth", "token": "<jwt>"}`` frame within
   a short deadline and verify it with the *same* :class:`SupabaseJWTVerifier`
   the HTTP edge uses, offloaded to a thread (the verify + JWKS fetch is sync).
   Missing / malformed / invalid / late → ``close(1008)``. The token never
   appears in a URL or access log.
3. **Authorise once, at connect** (``GetGame`` via the runner): confirm the run
   exists and the caller owns it, then push the initial ``connected`` frame.
   A foreign / unknown run → ``close(1008)``. The loop then trusts the session.
4. **Receive / process / send loop**, one turn per inbound frame.
5. ``close()`` on game over (1000), client disconnect, or fatal error (1011).

**Resilience** (Q3/Q4/Q5):

* A frame that isn't valid JSON, or doesn't parse to a known action, gets an
  ``error`` frame and the loop **continues** — one bad message must not kill the
  session.
* A client closing the tab surfaces as :class:`WebSocketDisconnect`; we stop.
  The Redis working copy is left to its 2 h TTL (``ICachePort`` has no ``delete``
  by design), so there's nothing to leak.
* **Backpressure**: the loop ``await``s each turn before reading the next frame,
  so exactly one turn is ever in flight per connection — a flooding client just
  queues at the transport.
"""

import asyncio
import json
from collections.abc import Mapping
from typing import Annotated, Final
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from jwt import InvalidTokenError

from src.application.get_game import GameNotFoundError, NotGameOwnerError
from src.entrypoints.http.auth import SupabaseJWTVerifier, get_verifier
from src.entrypoints.http.dependencies import GameSessionRunner, get_game_session_runner
from src.entrypoints.http.schemas import GameStateResponse
from src.entrypoints.ws.protocol import ActionParseError, parse_action, serialize_event

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["game"])

# How long after ``accept()`` the client has to send its auth frame before we
# close the socket. Bounds a connection that opens but never authenticates.
_AUTH_DEADLINE_SECONDS: Final[float] = 10.0


@router.websocket("/ws/game/{session_id}")
async def game_ws(
    websocket: WebSocket,
    session_id: UUID,
    verifier: Annotated[SupabaseJWTVerifier, Depends(get_verifier)],
    runner: Annotated[GameSessionRunner, Depends(get_game_session_runner)],
) -> None:
    """Drive one client's turn loop for run ``session_id``.

    ``session_id`` *is* the game id (the ``/game/{id}`` and ``/ws/game/{id}``
    vocabulary share ``Dungeon.dungeon_id`` — see ``application/game_state.py``).
    A non-UUID path segment is rejected by FastAPI before this runs.
    """
    await websocket.accept()

    user_id = await _authenticate(websocket, verifier)
    if user_id is None:
        return  # _authenticate has already closed the socket (or it dropped).

    try:
        dungeon, player = await runner.load_authorized(session_id, user_id)
    except GameNotFoundError:
        await _close(websocket, status.WS_1008_POLICY_VIOLATION, "game not found")
        return
    except NotGameOwnerError:
        await _close(websocket, status.WS_1008_POLICY_VIOLATION, "not your game")
        return

    await websocket.send_json(
        {
            "type": "connected",
            "game_id": str(session_id),
            "state": GameStateResponse.from_domain(dungeon, player).model_dump(mode="json"),
        }
    )

    await _turn_loop(websocket, session_id, runner)


async def _authenticate(websocket: WebSocket, verifier: SupabaseJWTVerifier) -> UUID | None:
    """Run the first-message auth handshake; return the user id or ``None``.

    On any failure — no frame within the deadline, a non-auth / malformed frame,
    or a token that fails verification — closes the socket with ``1008`` and
    returns ``None``. A client that drops mid-handshake also yields ``None``
    (nothing to close).
    """
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=_AUTH_DEADLINE_SECONDS)
    except WebSocketDisconnect:
        return None  # Client vanished during the handshake; nothing to close.
    except (TimeoutError, json.JSONDecodeError):
        await _close(websocket, status.WS_1008_POLICY_VIOLATION, "auth required")
        return None

    if not isinstance(frame, Mapping) or frame.get("type") != "auth":
        await _close(websocket, status.WS_1008_POLICY_VIOLATION, "auth required")
        return None
    token = frame.get("token")
    if not isinstance(token, str):
        await _close(websocket, status.WS_1008_POLICY_VIOLATION, "auth required")
        return None

    try:
        # Verify off the event loop — the same discipline get_current_user uses,
        # since verification (and a JWKS cache miss) is blocking.
        user = await asyncio.to_thread(verifier.verify, token)
    except InvalidTokenError:
        # Never log the token; only that auth failed.
        logger.debug("ws_auth_failed")
        await _close(websocket, status.WS_1008_POLICY_VIOLATION, "invalid token")
        return None
    return user.user_id


async def _turn_loop(websocket: WebSocket, game_id: UUID, runner: GameSessionRunner) -> None:
    """Receive → process → send, one turn per frame, until close.

    Bad frames are answered with an ``error`` frame and the loop continues; a
    client disconnect ends it cleanly; ``game_over`` ends it with ``1000``; an
    unexpected turn failure ends it with ``1011``.
    """
    while True:
        try:
            frame = await websocket.receive_json()
        except WebSocketDisconnect:
            logger.info("ws_client_disconnected", game_id=str(game_id))
            return
        except json.JSONDecodeError:
            await websocket.send_json(_error("message was not valid JSON"))
            continue

        try:
            action = parse_action(frame)
        except ActionParseError as exc:
            await websocket.send_json(_error(str(exc)))
            continue

        try:
            result, dungeon, player = await runner.process(game_id, action)
        except GameNotFoundError:
            # The run was removed out from under an authorised session.
            await websocket.send_json(_error("game not found"))
            await _close(websocket, status.WS_1008_POLICY_VIOLATION, "game not found")
            return
        except Exception:  # noqa: BLE001
            # One turn's unexpected fault must close this session gracefully,
            # not crash the worker serving other connections.
            logger.exception("ws_turn_failed", game_id=str(game_id))
            await _close(websocket, status.WS_1011_INTERNAL_ERROR, "internal error")
            return

        await websocket.send_json(
            {
                "type": "turn",
                "events": [serialize_event(event) for event in result.events],
                "state": GameStateResponse.from_domain(dungeon, player).model_dump(mode="json"),
                "game_over": result.game_over,
            }
        )

        if result.game_over:
            await _close(websocket, status.WS_1000_NORMAL_CLOSURE, "game over")
            return


def _error(detail: str) -> dict[str, str]:
    """Build a recoverable ``error`` frame (the loop continues after sending it)."""
    return {"type": "error", "detail": detail}


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    """Close the socket, tolerating an already-closed/dropped connection."""
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        # Peer already gone or close already sent — nothing left to do.
        pass
