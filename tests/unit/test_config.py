import pytest

from src.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.database_url.startswith("postgresql")
    assert settings.redis_url.startswith("redis://")
    assert settings.celery_broker_url.startswith("redis://")
    assert settings.celery_result_backend.startswith("redis://")


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "override")

    settings = Settings()

    assert settings.jwt_secret == "override"
