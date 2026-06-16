"""Tests for the Supabase JWT verification dependency (task 2.10).

Tokens here are signed with a **real** RSA keypair generated in-process, so the
verifier's signature check runs for real — a no-op or signature-skipping
implementation (the QUIZZES task 2.10 Q2 bug) would fail these tests, not pass
them. The JWKS network fetch is replaced by ``_FakeJWKClient``, which hands the
verifier the matching public key; no Supabase, no network.

No FastAPI app exists until task 3.4, so the dependency function is exercised by
calling it directly with an injected verifier rather than through ``TestClient``.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from src.config import Settings
from src.entrypoints.http.auth import (
    AuthenticatedUser,
    SupabaseJWTVerifier,
    build_verifier,
    get_current_user,
)

ISSUER = "https://project-ref.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-signing-key"


class _FakeJWKClient:
    """Stands in for ``PyJWKClient`` — returns a fixed public key, no network."""

    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return SimpleNamespace(key=self._public_key)


class _NoMatchingKeyJWKClient:
    """A JWK client that finds no key for the token — unknown/absent ``kid``.

    Mirrors what the real ``PyJWKClient`` raises when the token's ``kid`` is not
    in the JWKS (forged/rotated key) or the JWKS fetch fails.
    """

    def get_signing_key_from_jwt(self, token: str) -> Any:
        raise jwt.PyJWKClientError("Unable to find a signing key that matches")


@pytest.fixture
def rsa_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(rsa_key: RSAPrivateKey) -> SupabaseJWTVerifier:
    return SupabaseJWTVerifier(
        _FakeJWKClient(rsa_key.public_key()),
        issuer=ISSUER,
        audience=AUDIENCE,
    )


def _encode(
    private_key: Any,
    *,
    payload: dict[str, Any],
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(payload, private_key, algorithm=algorithm, headers={"kid": KID})


def _claims(
    *,
    sub: Any = None,
    aud: str = AUDIENCE,
    iss: str = ISSUER,
    exp_delta: timedelta = timedelta(hours=1),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": str(uuid4()) if sub is None else sub,
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + exp_delta,
    }


# --- SupabaseJWTVerifier.verify -------------------------------------------------


def test_valid_token_returns_principal(
    verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey
) -> None:
    user_id = uuid4()
    token = _encode(rsa_key, payload=_claims(sub=str(user_id)))

    principal = verifier.verify(token)

    assert principal == AuthenticatedUser(user_id=user_id)


def test_forged_signature_is_rejected(verifier: SupabaseJWTVerifier) -> None:
    # Signed with a *different* key than the verifier trusts: the claims are
    # well-formed, so only the signature check can catch this.
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _encode(attacker_key, payload=_claims())

    with pytest.raises(jwt.InvalidSignatureError):
        verifier.verify(token)


def test_unsigned_alg_none_token_is_rejected(verifier: SupabaseJWTVerifier) -> None:
    # The classic bypass: an attacker sets alg=none to skip the signature.
    # Pinning algorithms to RS256/ES256 must reject it.
    token = jwt.encode(_claims(), key=None, algorithm="none", headers={"kid": KID})

    with pytest.raises(jwt.InvalidAlgorithmError):
        verifier.verify(token)


def test_expired_token_is_rejected(verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey) -> None:
    token = _encode(rsa_key, payload=_claims(exp_delta=timedelta(hours=-1)))

    with pytest.raises(jwt.ExpiredSignatureError):
        verifier.verify(token)


def test_wrong_audience_is_rejected(verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey) -> None:
    token = _encode(rsa_key, payload=_claims(aud="some-other-service"))

    with pytest.raises(jwt.InvalidAudienceError):
        verifier.verify(token)


def test_wrong_issuer_is_rejected(verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey) -> None:
    token = _encode(rsa_key, payload=_claims(iss="https://evil.example.com/auth/v1"))

    with pytest.raises(jwt.InvalidIssuerError):
        verifier.verify(token)


def test_missing_sub_claim_is_rejected(
    verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey
) -> None:
    claims = _claims()
    del claims["sub"]
    token = _encode(rsa_key, payload=claims)

    with pytest.raises(jwt.MissingRequiredClaimError):
        verifier.verify(token)


def test_non_uuid_sub_is_rejected(verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey) -> None:
    # A correctly signed token whose sub is not a UUID is still unusable; it must
    # be normalised to the InvalidTokenError family so the edge maps it to 401.
    token = _encode(rsa_key, payload=_claims(sub="not-a-uuid"))

    with pytest.raises(jwt.InvalidTokenError):
        verifier.verify(token)


def test_unknown_kid_is_rejected_as_invalid_token(rsa_key: RSAPrivateKey) -> None:
    # PyJWKClientError (no matching kid) is NOT a subclass of InvalidTokenError;
    # verify must normalise it so the edge's `except InvalidTokenError` catches
    # it and returns 401 instead of letting it bubble up as a 500.
    verifier = SupabaseJWTVerifier(_NoMatchingKeyJWKClient(), issuer=ISSUER, audience=AUDIENCE)
    token = _encode(rsa_key, payload=_claims())

    with pytest.raises(jwt.InvalidTokenError):
        verifier.verify(token)


def test_clock_skew_within_leeway_is_accepted(
    verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey
) -> None:
    # A token that expired a few seconds ago is still accepted within the
    # configured clock-skew leeway (30s).
    token = _encode(rsa_key, payload=_claims(exp_delta=timedelta(seconds=-5)))

    assert verifier.verify(token).user_id is not None


# --- build_verifier wiring ------------------------------------------------------


def test_build_verifier_wires_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # The verifier must take its issuer/audience from Settings (derived from
    # SUPABASE_URL) — a swapped field would silently accept foreign tokens.
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    settings = Settings(_env_file=None)

    verifier = build_verifier(settings)

    assert verifier._issuer == settings.supabase_issuer
    assert verifier._audience == settings.supabase_jwt_audience


# --- get_current_user dependency ------------------------------------------------


async def test_get_current_user_returns_principal(
    verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey
) -> None:
    user_id = uuid4()
    token = _encode(rsa_key, payload=_claims(sub=str(user_id)))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    principal = await get_current_user(credentials, verifier)

    assert principal == AuthenticatedUser(user_id=user_id)


async def test_get_current_user_missing_token_is_401(
    verifier: SupabaseJWTVerifier,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(None, verifier)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


async def test_get_current_user_invalid_token_is_401(
    verifier: SupabaseJWTVerifier, rsa_key: RSAPrivateKey
) -> None:
    # Forged signature reaches the dependency as an InvalidTokenError and must
    # surface as 401 with the challenge header, never bubble up as a 500.
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _encode(attacker_key, payload=_claims())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials, verifier)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
