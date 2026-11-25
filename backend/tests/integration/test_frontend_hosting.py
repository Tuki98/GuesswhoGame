"""Same-origin hosting of the built React application by FastAPI."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TEST_SECRET = "test-secret-key-for-tests-only-0123456789"


def _settings(tmp_path: Path, *, dist_dir: Path | None) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite://",
        secret_key=TEST_SECRET,
        media_root=tmp_path / "media",
        frontend_dist_dir=dist_dir,
    )


def _build_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><div id="root"></div>', encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets / "app-123.js").write_text("console.log('app');", encoding="utf-8")
    return dist


def test_frontend_hosting_is_disabled_without_a_dist_directory(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, dist_dir=None))

    with TestClient(app) as client:
        response = client.get("/room/ABC123")

    assert response.status_code == 404


def test_frontend_hosting_is_disabled_when_index_is_missing(tmp_path: Path) -> None:
    empty = tmp_path / "empty-dist"
    empty.mkdir()
    app = create_app(_settings(tmp_path, dist_dir=empty))

    with TestClient(app) as client:
        response = client.get("/room/ABC123")

    assert response.status_code == 404


def test_root_assets_and_client_routes_are_served_from_one_origin(tmp_path: Path) -> None:
    dist = _build_dist(tmp_path)
    app = create_app(_settings(tmp_path, dist_dir=dist))

    with TestClient(app) as client:
        root = client.get("/")
        deep_link = client.get("/room/ABC123/play")
        asset = client.get("/assets/app-123.js")
        favicon = client.get("/favicon.svg")
        health = client.get("/api/health")

    for response in (root, deep_link):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Cache-Control" in response.headers
        assert '<div id="root">' in response.text

    assert asset.status_code == 200
    assert asset.text == "console.log('app');"
    assert "javascript" in asset.headers["content-type"]
    assert favicon.status_code == 200
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


@pytest.mark.parametrize(
    "path",
    [
        "/api/not-a-real-endpoint",
        "/media/not-a-real-file.png",
        "/ws/rooms/ABC123",
        "/openapi.json/not-a-route",
    ],
)
def test_spa_fallback_does_not_shadow_reserved_prefixes(tmp_path: Path, path: str) -> None:
    dist = _build_dist(tmp_path)
    app = create_app(_settings(tmp_path, dist_dir=dist))

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")
    assert '<div id="root">' not in response.text


def test_documentation_routes_still_work_with_the_spa_enabled(tmp_path: Path) -> None:
    dist = _build_dist(tmp_path)
    app = create_app(_settings(tmp_path, dist_dir=dist))

    with TestClient(app) as client:
        docs = client.get("/docs")
        schema = client.get("/openapi.json")

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text.lower()
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "Guess the Character"


def test_spa_fallback_cannot_escape_the_dist_directory(tmp_path: Path) -> None:
    dist = _build_dist(tmp_path)
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("must-not-be-served", encoding="utf-8")
    app = create_app(_settings(tmp_path, dist_dir=dist))

    with TestClient(app) as client:
        encoded = client.get("/assets/..%2F..%2Foutside-secret.txt")
        plain = client.get("/../outside-secret.txt")

    for response in (encoded, plain):
        assert "must-not-be-served" not in response.text
    assert encoded.status_code == 404
    assert plain.status_code in {200, 404}
