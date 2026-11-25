"""Integration tests for health endpoints and error responses."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import get_db


def test_health_reports_service_metadata(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "name": "Guess the Character",
        "version": "0.1.0",
        "environment": "test",
    }


def test_health_uses_application_specific_settings(app: FastAPI) -> None:
    app.state.settings.app_version = "9.9.9"

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.json()["version"] == "9.9.9"


def test_readiness_checks_the_database(client: TestClient) -> None:
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_returns_503_when_database_is_unavailable(
    client: TestClient,
    app: FastAPI,
    tmp_path: Path,
) -> None:
    # Point a session at a database path whose parent directory does not exist.
    broken_engine = create_engine(
        f"sqlite:///{(tmp_path / 'missing-directory' / 'db.sqlite').as_posix()}"
    )
    broken_session = Session(bind=broken_engine)

    def broken_db() -> Iterator[Session]:
        yield broken_session

    app.dependency_overrides[get_db] = broken_db
    try:
        response = client.get("/api/health/ready")
    finally:
        app.dependency_overrides.clear()
        broken_session.close()
        broken_engine.dispose()

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Database is not available.",
        }
    }


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)


def test_method_not_allowed_uses_error_envelope(client: TestClient) -> None:
    response = client.post("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_errors_use_error_envelope(app: FastAPI) -> None:
    @app.get("/api/_test/echo")
    def echo(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/api/_test/echo", params={"value": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed."
    assert body["error"]["details"][0]["location"] == ["query", "value"]
    assert body["error"]["details"][0]["type"] == "int_parsing"


def test_unexpected_errors_do_not_leak_internals(app: FastAPI) -> None:
    @app.get("/api/_test/crash")
    def crash() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/_test/crash")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
        }
    }
    assert "hunter2" not in response.text


def test_cors_preflight_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/api/health" in schema["paths"]
    assert schema["info"]["title"] == "Guess the Character"
