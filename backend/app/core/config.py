"""Application configuration loaded from environment variables and ``.env`` files.

Settings are validated once at startup. In production the application refuses to
start with development defaults so that secrets are never silently reused.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEVELOPMENT_SECRET = "change-me-in-production"  # noqa: S105 (dev-only placeholder)
MINIMUM_PRODUCTION_SECRET_LENGTH = 32

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Typed application settings.

    Values are read from environment variables first, then from a ``.env`` file
    in the working directory or its parent (the repository root).
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Guess the Character"
    app_version: str = "0.1.0"
    environment: Environment = "development"
    debug: bool = False

    api_prefix: str = "/api"

    database_url: str = "sqlite:///./data/guess_the_character.db"
    secret_key: SecretStr = SecretStr(DEFAULT_DEVELOPMENT_SECRET)
    session_token_ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    reconnect_token_ttl_hours: int = Field(default=24 * 7, ge=1, le=24 * 30)

    media_root: Path = Path("./storage")
    media_url_prefix: str = "/media"
    frontend_dist_dir: Path | None = None
    image_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=5 * 1024 * 1024)
    image_download_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _validate_production_configuration(self) -> Settings:
        if not self.is_production:
            return self

        secret = self.secret_key.get_secret_value()
        if secret == DEFAULT_DEVELOPMENT_SECRET or len(secret) < MINIMUM_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                "SECRET_KEY must be set to a random value of at least "
                f"{MINIMUM_PRODUCTION_SECRET_LENGTH} characters in production."
            )
        if self.debug:
            raise ValueError("DEBUG must be false in production.")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not allowed in production.")
        return self

    @field_validator("media_url_prefix")
    @classmethod
    def _validate_media_url_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value == "/" or value.endswith("/"):
            raise ValueError("MEDIA_URL_PREFIX must start with '/' and must not end with '/'.")
        return value

    @model_validator(mode="after")
    def _validate_session_lifetimes(self) -> Settings:
        if self.reconnect_token_ttl_hours < self.session_token_ttl_hours:
            raise ValueError(
                "RECONNECT_TOKEN_TTL_HOURS must be greater than or equal to "
                "SESSION_TOKEN_TTL_HOURS."
            )
        return self

    @property
    def sqlite_file_path(self) -> Path | None:
        """Return the SQLite file path when the database URL points at a file."""
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        raw_path = self.database_url.removeprefix(prefix)
        if not raw_path or raw_path.startswith(":memory:") or raw_path.startswith("file:"):
            return None
        return Path(raw_path)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Cached so that configuration is parsed once. Tests and scripts that change
    the environment should call ``get_settings.cache_clear()``.
    """
    return Settings()
