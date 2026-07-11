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


def test_supabase_storage_buckets_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.delenv("SUPABASE_STORAGE_SAVES_BUCKET", raising=False)
    monkeypatch.delenv("SUPABASE_STORAGE_AVATARS_BUCKET", raising=False)

    settings = Settings(_env_file=None)

    assert settings.supabase_storage_saves_bucket == "saves"
    assert settings.supabase_storage_avatars_bucket == "avatars"


def test_supabase_storage_saves_bucket_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_STORAGE_SAVES_BUCKET", "runs")

    assert Settings(_env_file=None).supabase_storage_saves_bucket == "runs"


def test_supabase_storage_avatars_bucket_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_STORAGE_AVATARS_BUCKET", "portraits")

    assert Settings(_env_file=None).supabase_storage_avatars_bucket == "portraits"


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


@pytest.mark.parametrize("blank_url", ["", "   ", "/", " / "])
def test_supabase_derived_urls_raise_when_url_blank(
    monkeypatch: pytest.MonkeyPatch, blank_url: str
) -> None:
    # A blank/whitespace-only SUPABASE_URL must fail loud rather than yield a
    # malformed relative URL like "/auth/v1". Remove the guard and these would
    # return garbage instead of raising.
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_URL", blank_url)

    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="SUPABASE_URL is not configured"):
        _ = settings.supabase_issuer
    with pytest.raises(ValueError, match="SUPABASE_URL is not configured"):
        _ = settings.supabase_jwks_url


def test_supabase_url_whitespace_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Surrounding whitespace on SUPABASE_URL must not leak into the derived URLs.
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SUPABASE_URL", "  https://abc.supabase.co  ")

    settings = Settings(_env_file=None)

    assert settings.supabase_issuer == "https://abc.supabase.co/auth/v1"


def test_cors_origins_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # The documented form (QUESTIONS.md task 3.4). Regression for the 6.3 bug:
    # without NoDecode on the field, pydantic-settings JSON-decodes the env
    # value *before* the validator runs, so any non-JSON string (even a single
    # origin) raised SettingsError and this test would fail at construction.
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")

    assert Settings(_env_file=None).cors_origins == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_origins_single_origin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # The exact value the prod compose passes (no comma at all).
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")

    assert Settings(_env_file=None).cors_origins == ["http://localhost:5173"]


def test_cors_origins_json_list_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # The JSON form stays supported: NoDecode turns off the built-in decoding,
    # so the validator must (and does) handle it itself.
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.example", "https://b.example"]')

    assert Settings(_env_file=None).cors_origins == [
        "https://a.example",
        "https://b.example",
    ]
