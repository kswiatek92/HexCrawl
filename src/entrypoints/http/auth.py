"""HTTP authentication edge: verify Supabase access-token JWTs.

The backend is a **stateless resource server** (``docs/auth-setup.md``, task 2.9):
the frontend owns the Supabase login / refresh-token flow, and this layer only
*verifies* the access-token JWT presented on each request, reading the user id
(``sub``) from its claims. There is **no shared secret** on the backend —
Supabase signs tokens asymmetrically (RS256/ES256) and publishes the matching
public keys at a JWKS endpoint, which we fetch and verify against.

Living in ``src/entrypoints/http/``, this module *is* allowed to import a
framework (``fastapi``, ``jwt``) — it is the outer edge. The hexagonal golden
rule runs the other way: nothing here may be imported by ``domain/`` or
``application/``. The verified principal (:class:`AuthenticatedUser`) is an
edge concept and stays here; use cases (Phase 3) receive a plain ``user_id:
UUID``, so the domain never learns that auth — let alone Supabase — exists.

Design pinned to ``QUIZZES.md`` task 2.10 and the contract in
``docs/auth-setup.md``:

* **Asymmetric (JWKS) verification, algorithms pinned** (Q2, Q3) — we decode
  with ``algorithms=["RS256", "ES256"]`` only. Pinning is the fix for the
  classic JWT bypass: a verifier that trusts the token's own ``alg`` header
  accepts ``alg: none`` (unsigned) or an HS256 token signed with the *public*
  key as if it were a secret. Skipping signature verification entirely
  (``verify_signature=False``) means any forged ``sub`` is accepted — the
  critical bug in the Q2 snippet.
* **Verify signature + ``exp`` + ``aud`` + ``iss``** (Q3) — the signature
  proves the token is genuine, ``exp`` that it is current, and ``aud``/``iss``
  that it was minted *for this API by this project* (so a token from another
  Supabase project or service cannot be replayed). All four claims are
  ``require``-d, so a token missing any of them is rejected.
* **No token and bad token both → 401, with ``WWW-Authenticate: Bearer``**
  (Q4) — authe*ntication* failure. We use ``HTTPBearer(auto_error=False)``
  precisely so a *missing* header yields 401 (FastAPI's built-in auto-error
  raises 403, which conflates "who are you?" with "you may not"). 403 is for
  authe*risation* — "this isn't your game" — which is **not** decided here.
* **AuthZ lives next to the resource** (Q5) — ownership checks ("is this *your*
  dungeon?") belong in the use case beside the data, not at the edge. This
  dependency answers only "who is the caller?". authN at the edge, authZ next
  to the resource.

The blocking JWKS network fetch (on cache miss / key rotation) is offloaded
with :func:`asyncio.to_thread` so it never stalls the event loop — the same
event-loop discipline ``RedisCache`` follows (QUIZZES task 2.7 Q3).
"""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Protocol
from uuid import UUID

import jwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWK, PyJWKClient

from src.config import Settings

logger = structlog.get_logger(__name__)

# Supabase signs access tokens asymmetrically. Pinning the accepted algorithms
# to this set is what rejects ``alg: none`` and algorithm-confusion attacks —
# never derive the algorithm from the token's own header.
_SUPABASE_JWT_ALGORITHMS = ("RS256", "ES256")

# Claims that must be present *and* valid for a token to be accepted. PyJWT
# verifies aud/iss/exp when given the values; ``require`` additionally rejects a
# token that simply omits any of them.
_REQUIRED_CLAIMS = ("exp", "sub", "aud", "iss")


@dataclass(frozen=True)
class AuthenticatedUser:
    """The verified caller behind a request — the principal, nothing more.

    Carries only the Supabase user id (the JWT ``sub`` claim, a UUID). This is
    deliberately minimal: it is an identity, not a profile. Use cases compare
    ``user_id`` against a resource's owner to make authorisation decisions.
    """

    user_id: UUID


class _SigningKeyResolver(Protocol):
    """The slice of :class:`jwt.PyJWKClient` the verifier depends on.

    Declaring it as a Protocol makes the JWKS source an injection seam: the
    real client fetches from Supabase, while tests pass a fake that returns a
    locally generated key — so signature verification is exercised for real
    without a network round-trip.
    """

    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


class SupabaseJWTVerifier:
    """Verifies a Supabase access-token JWT and extracts the principal.

    Synchronous and side-effect-free apart from the JWKS lookup delegated to the
    injected ``jwk_client`` (which caches keys). Kept sync so it is trivially
    unit-testable with a real RSA keypair; the async edge offloads it to a
    thread. Every rejection surfaces as an :class:`jwt.InvalidTokenError`
    subclass, so the dependency above needs a single ``except`` clause.
    """

    def __init__(
        self,
        jwk_client: _SigningKeyResolver,
        *,
        issuer: str,
        audience: str,
        algorithms: tuple[str, ...] = _SUPABASE_JWT_ALGORITHMS,
    ) -> None:
        self._jwk_client = jwk_client
        self._issuer = issuer
        self._audience = audience
        self._algorithms = list(algorithms)

    def verify(self, token: str) -> AuthenticatedUser:
        """Verify ``token`` and return the principal, or raise.

        Raises an :class:`jwt.InvalidTokenError` subclass on any failure:
        unknown ``kid``, bad signature, wrong/none algorithm, expired token,
        wrong ``aud``/``iss``, a missing required claim, or a ``sub`` that is
        not a UUID.
        """
        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=self._algorithms,
            audience=self._audience,
            issuer=self._issuer,
            options={"require": list(_REQUIRED_CLAIMS)},
        )
        try:
            user_id = UUID(payload["sub"])
        except (ValueError, TypeError, AttributeError) as exc:
            # A structurally valid, correctly signed token whose ``sub`` is not
            # a UUID is still unusable as a principal. Normalise to the same
            # error family as every other rejection so the edge treats it as 401.
            raise InvalidTokenError("sub claim is not a valid UUID") from exc
        return AuthenticatedUser(user_id=user_id)


@lru_cache
def get_settings() -> Settings:
    """Process-wide :class:`Settings`, cached so env is read once."""
    return Settings()


def build_verifier(settings: Settings) -> SupabaseJWTVerifier:
    """Construct a verifier wired to the project's Supabase JWKS endpoint.

    ``PyJWKClient`` caches the fetched JWK set (default lifespan 300s) and
    matches the token's ``kid`` to the right public key, refetching on rotation.
    """
    return SupabaseJWTVerifier(
        PyJWKClient(settings.supabase_jwks_url),
        issuer=settings.supabase_issuer,
        audience=settings.supabase_jwt_audience,
    )


@lru_cache
def get_verifier() -> SupabaseJWTVerifier:
    """Process-singleton verifier — shares one JWKS cache across requests.

    A FastAPI dependency; override via ``app.dependency_overrides`` in tests.
    """
    return build_verifier(get_settings())


# Module-level so FastAPI registers a single "bearer" security scheme in the
# OpenAPI doc. ``auto_error=False`` hands us ``None`` for a missing/blank
# Authorization header instead of raising 403, so we can return 401 ourselves.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[SupabaseJWTVerifier, Depends(get_verifier)],
) -> AuthenticatedUser:
    """FastAPI dependency: resolve and verify the caller's identity.

    Returns the :class:`AuthenticatedUser` on success; raises ``401`` (with a
    ``WWW-Authenticate: Bearer`` header) for a missing or invalid token. Because
    FastAPI caches a dependency's result per request, several route dependencies
    can all ask for the current user and the token is verified only once.
    """
    if credentials is None:
        raise _unauthorized("missing bearer token")
    try:
        return await asyncio.to_thread(verifier.verify, credentials.credentials)
    except InvalidTokenError as exc:
        # Never log the token itself — only why it was rejected.
        logger.info("jwt_verification_failed", error=type(exc).__name__)
        raise _unauthorized("invalid or expired token") from exc


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
