from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def supabase_issuer(self) -> str:
        """The `iss` claim Supabase mints into its access tokens.

        Derived from ``supabase_url`` (single source of truth) rather than a
        separate env var, so the two can never drift. Tolerant of a trailing
        slash on the URL.
        """
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        """Endpoint serving the project's public JWT signing keys (JWKS).

        Supabase signs access tokens asymmetrically (RS256/ES256); a resource
        server fetches these public keys to verify signatures — no shared
        secret. Consumed by the `get_current_user` dependency in task 2.10.
        """
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
