import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://hexcrawl:hexcrawl@localhost/hexcrawl"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_storage_saves_bucket: str = "saves"
    supabase_storage_avatars_bucket: str = "avatars"
    # NoDecode is load-bearing: pydantic-settings JSON-decodes complex fields
    # *at the env source*, before any validator runs — so without it,
    # CORS_ORIGINS=https://a,https://b dies with a SettingsError and the
    # validator below never gets a say (found by the prod compose, task 6.3,
    # the first environment to actually set the variable; see BUGS.md).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        """Accept either a JSON list or a comma-separated string.

        pydantic-settings v2 requires JSON for list[str] by default, which
        means CORS_ORIGINS=https://a,https://b would raise a ValidationError.
        NoDecode on the field hands the raw env string here instead; this
        validator then supports both forms, matching the documented decision
        in QUESTIONS.md (task 3.4). NoDecode also disables the built-in JSON
        parsing, so the JSON-list form is decoded here too.
        """
        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):
                return json.loads(text)
            return [o.strip() for o in text.split(",") if o.strip()]
        return v

    def _supabase_base_url(self) -> str:
        """Normalised Supabase base URL, or fail loud if unconfigured.

        Strips surrounding whitespace and any trailing slash so the derived
        issuer/JWKS URLs are well-formed. Raises rather than returning a
        malformed relative URL (``/auth/v1``) when ``supabase_url`` is blank:
        a silent garbage value would only surface as a confusing fetch/verify
        error later (task 2.10), so the misconfiguration is reported at the
        earliest point instead.
        """
        base = self.supabase_url.strip().rstrip("/")
        if not base:
            raise ValueError(
                "SUPABASE_URL is not configured; cannot derive the Supabase auth "
                "issuer/JWKS URL. Set SUPABASE_URL (see docs/auth-setup.md)."
            )
        return base

    @property
    def supabase_issuer(self) -> str:
        """The `iss` claim Supabase mints into its access tokens.

        Derived from ``supabase_url`` (single source of truth) rather than a
        separate env var, so the two can never drift.
        """
        return f"{self._supabase_base_url()}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        """Endpoint serving the project's public JWT signing keys (JWKS).

        Supabase signs access tokens asymmetrically (RS256/ES256); a resource
        server fetches these public keys to verify signatures — no shared
        secret. Consumed by the `get_current_user` dependency in task 2.10.
        """
        return f"{self._supabase_base_url()}/auth/v1/.well-known/jwks.json"
