"""Smoke tests for the FastAPI application skeleton (task 3.4).

These tests verify the app wiring — routing, CORS headers, status codes — without
starting real infra (no DB, no Redis). The lifespan is not triggered because
``TestClient`` is used directly (not as a context manager), and none of the tested
endpoints depend on session or Redis resources.

``create_app`` is called with a minimal ``Settings`` instance that has a known
``cors_origins`` value, avoiding a real ``.env`` file requirement in CI.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.entrypoints.http.main import create_app

_ALLOWED_ORIGIN = "http://localhost:5173"
_BLOCKED_ORIGIN = "http://evil.example.com"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    settings = Settings(
        jwt_secret="test-secret",
        cors_origins=[_ALLOWED_ORIGIN],
    )
    with TestClient(create_app(settings), raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404


def test_v1_prefix_is_mounted(client: TestClient) -> None:
    # Stub routers are mounted; no endpoints yet → 404, but not from a missing
    # router — the 404 detail differs from a totally unknown path because FastAPI
    # returns its standard {"detail": "Not Found"} for both, so we just confirm
    # the prefix is reachable (i.e., doesn't 307 to somewhere else or 500).
    response = client.get("/v1/game/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Auth (task 3.5 / DECISIONS.md ADR-0007)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/v1/auth/login", "/v1/auth/register"])
def test_backend_exposes_no_auth_routes(client: TestClient, path: str) -> None:
    # ADR-0007: the backend is a verify-only resource server — sign-up / login /
    # refresh are owned by the frontend Supabase SDK, so these routes must NOT
    # exist. A 404 (no such route) locks the decision in: if someone later adds a
    # backend login endpoint, this fails and forces a revisit of ADR-0007.
    response = client.post(path, json={"email": "a@b.com", "password": "pw"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_preflight_allowed_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


def test_cors_simple_request_allowed_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": _ALLOWED_ORIGIN})
    assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


def test_cors_blocked_origin_has_no_allow_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": _BLOCKED_ORIGIN})
    assert "access-control-allow-origin" not in response.headers
