"""Service-level tests for authentication and reconnect race handling."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import InvalidSessionError
from app.core.room_config import RoomConfig
from app.services.rooms import RoomService
from app.services.sessions import SessionService


def test_authenticate_rejects_empty_token(
    db_session: Session,
    settings: Settings,
) -> None:
    with pytest.raises(InvalidSessionError):
        SessionService(db_session, settings).authenticate("")


def test_reconnect_rejects_empty_token(
    db_session: Session,
    settings: Settings,
) -> None:
    with pytest.raises(InvalidSessionError):
        SessionService(db_session, settings).reconnect("")


def test_reconnect_aborts_when_rotation_loses_the_race(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = RoomService(db_session, settings).create_room("Alice", RoomConfig())

    class ZeroRows:
        rowcount = 0

    monkeypatch.setattr(Session, "execute", lambda _self, _statement: ZeroRows())

    with pytest.raises(InvalidSessionError):
        SessionService(db_session, settings).reconnect(host.issued.reconnect_token)
