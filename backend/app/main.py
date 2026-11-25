"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import websockets as websockets_api
from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.database.session import Database
from app.websockets.manager import ConnectionManager

DESCRIPTION = """
Backend for a real-time multiplayer character-guessing game.

The service currently provides the application foundation, private room
creation, invitation-code joining, player session authentication, host
administration, secure reconnection, per-room character management with
validated image uploads or downloads, team formation, and the REST game
engine: match lifecycle, secure character assignment, turns, questions and
answers, guessing, winner determination, event history, and player-specific
state serialization.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Release the database engine when the application shuts down."""
    yield
    database: Database = app.state.database
    database.dispose()


_FRAMEWORK_PATHS = ("/ws", "/docs", "/redoc", "/openapi.json")


def _is_reserved_path(path: str, settings: Settings) -> bool:
    """Return whether ``path`` belongs to the API, media, or framework routes."""
    normalized = f"/{path.lstrip('/')}"
    reserved = {
        settings.api_prefix.rstrip("/"),
        settings.media_url_prefix.rstrip("/"),
        *_FRAMEWORK_PATHS,
    }
    return any(normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in reserved)


def _register_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built SPA from FastAPI when ``FRONTEND_DIST_DIR`` points at it.

    API, media, and WebSocket routes are registered before the fallback, and the
    fallback refuses to answer reserved prefixes so unknown API calls still
    return JSON 404s instead of the HTML shell.
    """
    dist_dir = settings.frontend_dist_dir
    if dist_dir is None:
        return
    index_file = dist_dir / "index.html"
    if not index_file.is_file():
        return

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="frontend-assets",
        )

    root = dist_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        if _is_reserved_path(full_path, settings):
            raise HTTPException(status_code=404, detail="Not found.")
        if full_path:
            candidate = (dist_dir / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application instance with explicit, injectable settings."""
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description=DESCRIPTION,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = Database(resolved_settings.database_url)
    app.state.connection_manager = ConnectionManager()

    resolved_settings.media_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        resolved_settings.media_url_prefix,
        StaticFiles(directory=resolved_settings.media_root, check_dir=False),
        name="media",
    )

    if resolved_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=resolved_settings.api_prefix)
    app.include_router(websockets_api.router)
    _register_frontend(app, resolved_settings)
    return app


app = create_app()
