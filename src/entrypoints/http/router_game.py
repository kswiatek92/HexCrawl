"""Game router — REST endpoints for a dungeon run.

Routes are thin adapters: they validate the request body (Pydantic), resolve
the caller's identity from the bearer token (``get_current_user``), invoke an
application use case, and map the domain result to a response schema. No game
rule lives here — that is the domain's job, reached only through the use case.

Endpoints land across tasks 3.6 (`POST /start`), 3.7 (`GET /{id}`), 3.8
(`POST /{id}/abandon`).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.application.get_game import GameNotFoundError, GetGame, NotGameOwnerError
from src.application.start_game import StartGame
from src.entrypoints.http.auth import AuthenticatedUser, get_current_user
from src.entrypoints.http.dependencies import get_get_game, get_start_game
from src.entrypoints.http.schemas import GameStateResponse, StartGameRequest

router = APIRouter(prefix="/game", tags=["game"])


@router.post("/start", status_code=status.HTTP_201_CREATED)
async def start_game(
    body: StartGameRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[StartGame, Depends(get_start_game)],
    response: Response,
) -> GameStateResponse:
    """Create a new dungeon run for the authenticated caller.

    Returns ``201 Created`` with the full game state and a ``Location`` header
    pointing at the run's canonical URL (``GET /v1/game/{id}``, task 3.7).
    Identity is taken from the verified token, never the body — a client cannot
    start a run as another user. An out-of-range ``seed`` is rejected by the
    request schema as ``422`` before the use case runs.
    """
    dungeon, player = await use_case.execute(
        user_id=current_user.user_id,
        player_name=body.player_name,
        seed=body.seed,
    )
    response.headers["Location"] = f"/v1/game/{dungeon.dungeon_id}"
    return GameStateResponse.from_domain(dungeon, player)


@router.get("/{game_id}")
async def get_game(
    game_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[GetGame, Depends(get_get_game)],
) -> GameStateResponse:
    """Fetch the current state of an existing run owned by the caller.

    Returns ``200`` with the same ``GameStateResponse`` shape ``POST /start``
    emits (the run's current floor + player). A non-UUID ``{game_id}`` is
    rejected as ``422`` by the path parameter before the use case runs.

    Two failure outcomes are mapped from the use case, deliberately distinct:
    ``404`` when no run exists for the id, and ``403`` when the run exists but
    belongs to another user — ownership is decided in the use case beside the
    data (``auth.py`` Q5), never at this edge. The token's identity is the only
    source of the caller's id; the path carries the resource, not the principal.
    """
    try:
        dungeon, player = await use_case.execute(game_id, current_user.user_id)
    except GameNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found") from exc
    except NotGameOwnerError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your game") from exc
    return GameStateResponse.from_domain(dungeon, player)
