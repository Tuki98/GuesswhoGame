"""Service-level tests for atomic room creation and capacity enforcement."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.core.room_config import RoomConfig
from app.database.base import Base
from app.database.session import Database
from app.models import Player, Room, RoomStatus
from app.repositories.players import PlayerRepository
from app.services import rooms as rooms_module
from app.services.rooms import RoomService
from app.services.sessions import IssuedSession
from tests.factories import make_room


def test_create_room_rolls_back_completely_on_failure(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_issuance(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("credential service unavailable")

    monkeypatch.setattr("app.services.rooms.issue_session", fail_issuance)

    with pytest.raises(RuntimeError, match="credential service unavailable"):
        RoomService(db_session, settings).create_room("Alice", RoomConfig())

    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(Room)) == 0
    assert db_session.scalar(select(func.count()).select_from(Player)) == 0


def test_create_room_retries_after_code_collision(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_room(db_session, code="GTC-TAKEN")
    db_session.commit()

    codes = iter(["GTC-TAKEN", "GTC-FREE"])
    monkeypatch.setattr("app.services.rooms.generate_room_code", lambda: next(codes))

    membership = RoomService(db_session, settings).create_room("Alice", RoomConfig())

    assert membership.room.code == "GTC-FREE"
    assert membership.player.nickname == "Alice"
    assert membership.room.host_player_id == membership.player.id


def test_create_room_fails_after_collision_retries_are_exhausted(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_room(db_session, code="GTC-TAKEN")
    db_session.commit()

    monkeypatch.setattr("app.services.rooms.generate_room_code", lambda: "GTC-TAKEN")

    with pytest.raises(ConflictError, match="Could not create a room"):
        RoomService(db_session, settings).create_room("Alice", RoomConfig())

    assert db_session.scalar(select(func.count()).select_from(Room)) == 1


def test_create_room_retries_after_credential_collision(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RoomService(db_session, settings)
    existing = service.create_room("Existing", RoomConfig())
    original_issue_session = rooms_module.issue_session
    calls = 0

    def colliding_issuance(
        current_settings: Settings,
        *,
        now: object | None = None,
    ) -> IssuedSession:
        nonlocal calls
        calls += 1
        if calls == 1:
            return IssuedSession(
                session_token="colliding-token",
                session_token_hash=existing.player.session_token_hash,
                session_expires_at=existing.issued.session_expires_at,
                reconnect_token="colliding-reconnect",
                reconnect_token_hash="c" * 64,
                reconnect_expires_at=existing.issued.reconnect_expires_at,
            )
        return original_issue_session(current_settings)

    monkeypatch.setattr(rooms_module, "issue_session", colliding_issuance)

    membership = service.create_room("Alice", RoomConfig())

    assert calls == 2
    assert membership.player.nickname == "Alice"
    assert db_session.scalar(select(func.count()).select_from(Player)) == 2
    assert db_session.scalar(select(func.count()).select_from(Room)) == 2


def test_join_aborts_if_room_stops_waiting_mid_transaction(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RoomService(db_session, settings)
    host = service.create_room("Alice", RoomConfig())
    original_flush = Session.flush
    triggered = False

    def flush_and_close_room(
        session: Session,
        objects: object | None = None,
    ) -> None:
        nonlocal triggered
        original_flush(session, objects)
        if not triggered:
            triggered = True
            session.execute(
                update(Room).where(Room.id == host.room.id).values(status=RoomStatus.CLOSED)
            )

    monkeypatch.setattr(Session, "flush", flush_and_close_room)

    with pytest.raises(ConflictError, match="not accepting"):
        service.join_room(host.room.code, "Bob")

    assert db_session.scalar(select(func.count()).select_from(Player)) == 1


def test_join_maps_unique_violation_to_conflict(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RoomService(db_session, settings)
    host = service.create_room("Alice", RoomConfig())
    monkeypatch.setattr(
        PlayerRepository,
        "nickname_key_exists",
        lambda _self, _room_id, _key: False,
    )

    with pytest.raises(ConflictError, match="already in use"):
        service.join_room(host.room.code, "alice")

    assert db_session.scalar(select(func.count()).select_from(Player)) == 1


def test_join_rolls_back_on_unexpected_failure(
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RoomService(db_session, settings)
    host = service.create_room("Alice", RoomConfig())

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        service.join_room(host.room.code, "Bob")

    assert db_session.scalar(select(func.count()).select_from(Player)) == 1


def test_service_rejects_invalid_nickname_and_settings(
    db_session: Session,
    settings: Settings,
) -> None:
    service = RoomService(db_session, settings)

    with pytest.raises(DomainValidationError):
        service.create_room("a", RoomConfig())

    host = service.create_room("Alice", RoomConfig())
    with pytest.raises(DomainValidationError):
        service.update_settings(host.room.id, host.player, {"max_players": 99})


def test_service_reports_missing_room(
    db_session: Session,
    settings: Settings,
) -> None:
    service = RoomService(db_session, settings)
    host = service.create_room("Alice", RoomConfig())

    with pytest.raises(NotFoundError):
        service.get_room(uuid.uuid4(), host.player)


def test_join_room_is_rejected_once_capacity_is_reached(
    db_session: Session,
    settings: Settings,
) -> None:
    service = RoomService(db_session, settings)
    host = service.create_room("Alice", RoomConfig(max_players=2))
    service.join_room(host.room.code, "Bob")

    with pytest.raises(ConflictError, match="full"):
        service.join_room(host.room.code, "Carol")

    assert db_session.scalar(select(func.count()).select_from(Player)) == 2


def test_concurrent_joins_never_exceed_capacity(tmp_path: Path, settings: Settings) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'concurrent.db').as_posix()}")
    Base.metadata.create_all(database.engine)
    file_settings = settings.model_copy(
        update={"database_url": f"sqlite:///{(tmp_path / 'concurrent.db').as_posix()}"}
    )

    try:
        with database.session() as session:
            host = RoomService(session, file_settings).create_room(
                "Alice", RoomConfig(max_players=2)
            )
            code = host.room.code

        barrier = threading.Barrier(2)
        results: list[str] = []
        lock = threading.Lock()

        def attempt_join(nickname: str) -> None:
            with database.session() as session:
                barrier.wait()
                try:
                    RoomService(session, file_settings).join_room(code, nickname)
                    outcome = "joined"
                except (ConflictError, OperationalError):
                    outcome = "rejected"
                with lock:
                    results.append(outcome)

        threads = [
            threading.Thread(target=attempt_join, args=("Bob",)),
            threading.Thread(target=attempt_join, args=("Carol",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        with database.session() as session:
            player_count = session.scalar(select(func.count()).select_from(Player))

        assert results.count("joined") <= 1
        assert player_count is not None
        assert player_count <= 2
        assert player_count == 1 + results.count("joined")
    finally:
        database.dispose()
