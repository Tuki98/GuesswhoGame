"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.base import Base
from app.main import create_app

TEST_SECRET = "test-secret-key-for-tests-only-0123456789"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings using an in-memory database and media directory."""
    return Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite://",
        secret_key=TEST_SECRET,
        media_root=tmp_path / "media",
    )


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    """Application instance with the schema created from model metadata."""
    application = create_app(settings)
    Base.metadata.create_all(application.state.database.engine)
    yield application
    application.state.database.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """HTTP client with startup/shutdown lifespan handling."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session(app: FastAPI) -> Iterator[Session]:
    """Database session sharing the test app's in-memory database."""
    with app.state.database.session() as session:
        yield session
        session.rollback()
