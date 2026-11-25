"""Tests for configuration parsing and production safeguards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_DEVELOPMENT_SECRET,
    Settings,
    get_settings,
)

STRONG_SECRET = "a-strong-production-secret-with-32-plus-characters"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"_env_file": None}
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_development_defaults_are_typed_and_sane() -> None:
    settings = make_settings(environment="development")

    assert settings.app_name == "Guess the Character"
    assert settings.api_prefix == "/api"
    assert settings.database_url.endswith("guess_the_character.db")
    assert settings.debug is False
    assert settings.session_token_ttl_hours == 24
    assert "http://localhost:5173" in settings.cors_origins


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make_settings(environment="production")


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        make_settings(environment="production", secret_key="short-secret")


def test_production_accepts_strong_secret() -> None:
    settings = make_settings(environment="production", secret_key=STRONG_SECRET)

    assert settings.is_production is True
    assert settings.secret_key.get_secret_value() == STRONG_SECRET


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        make_settings(environment="production", secret_key=STRONG_SECRET, debug=True)


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS"):
        make_settings(
            environment="production",
            secret_key=STRONG_SECRET,
            cors_origins=["*"],
        )


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(environment="staging")


@pytest.mark.parametrize("ttl", [0, -1, 24 * 30 + 1])
def test_session_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(session_token_ttl_hours=ttl)


def test_reconnect_ttl_defaults_to_one_week() -> None:
    settings = make_settings()

    assert settings.reconnect_token_ttl_hours == 24 * 7


@pytest.mark.parametrize("ttl", [0, -1, 24 * 30 + 1])
def test_reconnect_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(reconnect_token_ttl_hours=ttl)


def test_reconnect_ttl_must_not_be_shorter_than_session_ttl() -> None:
    with pytest.raises(ValidationError, match="RECONNECT_TOKEN_TTL_HOURS"):
        make_settings(session_token_ttl_hours=24, reconnect_token_ttl_hours=12)

    settings = make_settings(session_token_ttl_hours=24, reconnect_token_ttl_hours=24)
    assert settings.reconnect_token_ttl_hours == 24


def test_secret_is_masked_in_representation() -> None:
    settings = make_settings(secret_key="super-secret-value")

    assert "super-secret-value" not in repr(settings)
    assert DEFAULT_DEVELOPMENT_SECRET not in repr(make_settings())


def test_sqlite_file_path_is_derived_from_url() -> None:
    settings = make_settings(database_url="sqlite:///./data/test.db")

    assert settings.sqlite_file_path is not None
    assert settings.sqlite_file_path.name == "test.db"


@pytest.mark.parametrize(
    "database_url",
    ["sqlite://", "sqlite:///:memory:", "postgresql://user:pass@localhost/db"],
)
def test_non_file_database_urls_have_no_sqlite_path(database_url: str) -> None:
    assert make_settings(database_url=database_url).sqlite_file_path is None


def test_environment_variables_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Configured Game")
    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.app_name == "Configured Game"
    assert settings.debug is True
