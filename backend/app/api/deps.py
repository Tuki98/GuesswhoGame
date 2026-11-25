"""Reusable API dependencies and their annotated aliases."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import InvalidSessionError
from app.core.image_download import ImageDownloader
from app.core.media import MediaStorage
from app.database.session import Database, get_db
from app.models import Player
from app.services.sessions import SessionService
from app.websockets.manager import ConnectionManager

_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="SessionToken",
    description="Session token issued when creating or joining a room.",
)


def get_app_settings(request: Request) -> Settings:
    """Return the settings bound to the running application instance."""
    return cast(Settings, request.app.state.settings)


AppSettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbSessionDep = Annotated[Session, Depends(get_db)]


def get_media_storage(settings: AppSettingsDep) -> MediaStorage:
    """Return storage bound to the running application's media settings."""
    return MediaStorage(settings.media_root, settings.media_url_prefix)


def get_image_downloader(settings: AppSettingsDep) -> ImageDownloader:
    """Return a downloader using the application's limits and timeouts."""
    return ImageDownloader(
        timeout=settings.image_download_timeout_seconds,
        max_bytes=settings.image_max_bytes,
    )


def get_connection_manager(request: Request) -> ConnectionManager:
    """Return the in-process connection manager bound to the app instance."""
    return cast(ConnectionManager, request.app.state.connection_manager)


MediaStorageDep = Annotated[MediaStorage, Depends(get_media_storage)]
ImageDownloaderDep = Annotated[ImageDownloader, Depends(get_image_downloader)]
ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]


# WebSocket routes cannot use ``Request``-typed dependencies, so the following
# variants resolve the same application singletons from ``WebSocket.app``.
def get_ws_settings(websocket: WebSocket) -> Settings:
    """Return the settings bound to the running application instance."""
    return cast(Settings, websocket.app.state.settings)


def get_ws_database(websocket: WebSocket) -> Database:
    """Return the database bound to the running application instance."""
    return cast(Database, websocket.app.state.database)


def get_ws_connection_manager(websocket: WebSocket) -> ConnectionManager:
    """Return the connection manager bound to the running app instance."""
    return cast(ConnectionManager, websocket.app.state.connection_manager)


WsAppSettingsDep = Annotated[Settings, Depends(get_ws_settings)]
WsDatabaseDep = Annotated[Database, Depends(get_ws_database)]
WsConnectionManagerDep = Annotated[ConnectionManager, Depends(get_ws_connection_manager)]


def get_current_player(
    session: DbSessionDep,
    settings: AppSettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> Player:
    """Authenticate a bearer session token and return its player."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidSessionError()
    return SessionService(session, settings).authenticate(credentials.credentials)


CurrentPlayerDep = Annotated[Player, Depends(get_current_player)]
