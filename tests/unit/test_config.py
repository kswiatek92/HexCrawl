import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql")
    assert settings.redis_url.startswith("redis://")
    assert settings.celery_broker_url.startswith("redis://")
    assert settings.celery_result_backend.startswith("redis://")


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "override")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret == "override"


def test_settings_missing_jwt_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_supabase_jwt_audience_defaults_to_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.delenv("SUPABASE_JWT_AUDIENCE", raising=False)

    assert Settings(_env_file=None).supabase_jwt_audience == "authenticated"


def test_supabase_jwt_audience_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "service")

    assert Settings(_env_file=None).supabase_jwt_audience == "service"


def test_supabase_issuer_derived_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")

    assert Settings(_env_file=None).supabase_issuer == "https://abc.supabase.co/auth/v1"


def test_supabase_jwks_url_derived_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")

    assert (
        Settings(_env_file=None).supabase_jwks_url
        == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
    )


def test_supabase_url_trailing_slash_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    # A trailing slash on SUPABASE_URL must not produce a double slash in the
    # derived issuer/JWKS URL. Fails if `.rstrip('/')` is dropped from the
    # derivation (the issuer would become ".../co//auth/v1").
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/")

    settings = Settings(_env_file=None)

    assert settings.supabase_issuer == "https://abc.supabase.co/auth/v1"
    assert settings.supabase_jwks_url == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
