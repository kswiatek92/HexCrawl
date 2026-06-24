"""RFC 7807 Problem Details error responses (task 3.13).

The single, self-describing error shape for the whole HTTP surface. Per the
QUESTIONS.md Phase 3 decision, HexCrawl emits errors as
``application/problem+json`` (RFC 7807) rather than FastAPI's default
``{"detail": ...}``: the standard carries ``type`` / ``title`` / ``status`` /
``detail`` / ``instance``, is documented and machine-readable for the React
client, and is swapped in via two app-wide exception handlers instead of being
hand-rolled per route — so the ``HTTPException``\\ s already raised in
``router_game`` / ``router_leaderboard`` keep working unchanged and just render
through here.

Living in ``src/entrypoints/http/``, this is the outer edge and may import
``fastapi`` / ``starlette`` / ``pydantic`` freely. Two handlers are installed by
:func:`install_problem_handlers` (called from ``main.create_app``):

* every ``HTTPException`` (Starlette's base, which FastAPI's subclasses) — the
  raised ``status_code`` and ``detail`` map straight onto the problem; any
  headers the exception carried (notably ``WWW-Authenticate: Bearer`` on a 401)
  are preserved.
* ``RequestValidationError`` (FastAPI's 422 for a bad path/query/body) — the
  per-field errors ride along in an ``errors`` extension member so the client
  still gets the granular validation detail FastAPI would have returned.
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

# RFC 7807 media type. Clients can branch on this to parse the standard error
# envelope, distinct from a normal ``application/json`` success body.
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

# The literal, not ``status.HTTP_422_UNPROCESSABLE_ENTITY``: that constant is
# deprecated (renamed UNPROCESSABLE_CONTENT) in current Starlette, and accessing
# it emits a DeprecationWarning. The code is the stable contract; FastAPI raises
# RequestValidationError as 422 regardless of the constant's spelling.
_HTTP_422_UNPROCESSABLE = 422


class ProblemDetail(BaseModel):
    """An RFC 7807 problem object — the wire shape of every HTTP error.

    ``type`` defaults to ``"about:blank"`` (the RFC's sentinel for "no further
    type information, the status code says it all"), which lets us ship without a
    docs site of error-type URIs yet. ``title`` is the HTTP reason phrase,
    ``status`` the code, ``detail`` the human-readable specifics, and
    ``instance`` the request path that produced it. ``errors`` is a non-standard
    *extension member* (RFC 7807 §3.2 permits these) carrying FastAPI's
    per-field validation breakdown on a 422.
    """

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


def _title_for(status_code: int) -> str:
    """The HTTP reason phrase for ``status_code`` (e.g. 404 -> "Not Found").

    Falls back to a generic title for a non-standard code so a custom status can
    never blow up the error handler itself.
    """
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:  # pragma: no cover - defensive; all routes use standard codes
        return "Error"


def _render(problem: ProblemDetail, *, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """Serialise ``problem`` as an ``application/problem+json`` response.

    ``exclude_none`` drops absent optional members (``detail`` / ``instance`` /
    ``errors``) so the envelope stays minimal. ``headers`` carries through
    anything the originating exception set — e.g. ``WWW-Authenticate`` on a 401.
    """
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=headers,
    )


async def _http_exception_handler(request: Request, exc: Exception) -> Response:
    """Render any raised ``HTTPException`` as an RFC 7807 problem.

    Registered for ``StarletteHTTPException`` (FastAPI's ``HTTPException``
    subclasses it), so ``exc`` is always that type — the cast satisfies the
    handler's ``Exception`` signature without a runtime check.
    """
    http_exc = cast(StarletteHTTPException, exc)
    problem = ProblemDetail(
        title=_title_for(http_exc.status_code),
        status=http_exc.status_code,
        # FastAPI's default detail is a plain string; a structured detail (dict)
        # is left to the extension members rather than coerced into a string.
        detail=http_exc.detail if isinstance(http_exc.detail, str) else None,
        instance=request.url.path,
    )
    return _render(problem, headers=http_exc.headers)


async def _validation_exception_handler(request: Request, exc: Exception) -> Response:
    """Render a request-validation failure (422) as an RFC 7807 problem.

    Keeps FastAPI's per-field breakdown in the ``errors`` extension member —
    ``jsonable_encoder`` flattens any non-JSON values (e.g. a ``ValueError`` in a
    validator's ``ctx``) so the body always serialises.
    """
    validation_exc = cast(RequestValidationError, exc)
    problem = ProblemDetail(
        title=_title_for(_HTTP_422_UNPROCESSABLE),
        status=_HTTP_422_UNPROCESSABLE,
        detail="Request parameters failed validation.",
        instance=request.url.path,
        errors=jsonable_encoder(validation_exc.errors()),
    )
    return _render(problem)


def install_problem_handlers(app: FastAPI) -> None:
    """Register the RFC 7807 exception handlers on ``app``.

    Called once from ``create_app``. Overrides FastAPI's default ``HTTPException``
    and ``RequestValidationError`` handlers so every error — from a route's
    explicit ``raise HTTPException`` to an automatic 422 — leaves as
    ``application/problem+json``.
    """
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
