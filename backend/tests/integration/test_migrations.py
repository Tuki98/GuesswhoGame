"""Verify that Alembic migrations produce the model metadata exactly."""

from __future__ import annotations

import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401  (registers all model metadata)
from app.database.base import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


def test_initial_migration_matches_metadata(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            table_names = set(inspector.get_table_names())
            assert table_names == set(Base.metadata.tables) | {"alembic_version"}

            context = MigrationContext.configure(connection)
            differences = compare_metadata(context, Base.metadata)

        assert differences == []
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            remaining = set(inspect(connection).get_table_names())
        assert remaining <= {"alembic_version"}
    finally:
        engine.dispose()


def test_phase_two_migration_converts_existing_phase_one_data(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'phase2.db').as_posix()}"
    config = _alembic_config(database_url)
    command.upgrade(config, "0001")

    waiting_room = uuid.uuid4()
    in_progress_room = uuid.uuid4()
    finished_room = uuid.uuid4()
    first_player = uuid.uuid4()
    second_player = uuid.uuid4()
    joined_at = "2026-01-01 00:00:00.000000"

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO rooms"
                    " (id, code, host_player_id, status, configuration, created_at, updated_at)"
                    " VALUES (:id, :code, NULL, :status, '{}', :timestamp, :timestamp)"
                ),
                [
                    {
                        "id": room.hex,
                        "code": code,
                        "status": status,
                        "timestamp": joined_at,
                    }
                    for room, code, status in (
                        (waiting_room, "GTC-WAIT", "lobby"),
                        (in_progress_room, "GTC-PLAY", "in_game"),
                        (finished_room, "GTC-DONE", "finished"),
                    )
                ],
            )
            connection.execute(
                sa.text(
                    "INSERT INTO players"
                    " (id, room_id, nickname, session_token_hash, team_id,"
                    " is_connected, is_ready, joined_at, last_seen_at)"
                    " VALUES (:id, :room_id, :nickname, :token_hash, NULL, 0, 0,"
                    " :timestamp, :timestamp)"
                ),
                [
                    {
                        "id": player.hex,
                        "room_id": waiting_room.hex,
                        "nickname": nickname,
                        "token_hash": token_hash,
                        "timestamp": joined_at,
                    }
                    for player, nickname, token_hash in (
                        (first_player, "Alice", "a" * 64),
                        (second_player, "alice", "b" * 64),
                    )
                ],
            )
            connection.execute(
                sa.text("UPDATE rooms SET host_player_id = :host WHERE id = :room"),
                {"host": first_player.hex, "room": waiting_room.hex},
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            statuses = dict(connection.execute(sa.text("SELECT code, status FROM rooms")).all())
            players = connection.execute(
                sa.text(
                    "SELECT nickname, nickname_key, session_expires_at,"
                    " reconnect_token_hash, reconnect_expires_at"
                    " FROM players ORDER BY nickname"
                )
            ).all()
        assert statuses == {
            "GTC-WAIT": "waiting",
            "GTC-PLAY": "in_progress",
            "GTC-DONE": "closed",
        }
        assert [(row.nickname, row.nickname_key) for row in players] == [
            ("Alice", "alice"),
            ("alice", "alice-2"),
        ]
        assert all(row.session_expires_at.startswith("2026-01-02") for row in players)
        assert all(row.reconnect_token_hash is None for row in players)
        assert all(row.reconnect_expires_at is None for row in players)
    finally:
        engine.dispose()

    command.downgrade(config, "0001")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            statuses = dict(connection.execute(sa.text("SELECT code, status FROM rooms")).all())
            player_columns = {
                column["name"] for column in inspect(connection).get_columns("players")
            }
        # Upgraded ``finished`` and ``closed`` both map to ``closed``, so a
        # downgrade cannot distinguish them; both remain closed.
        assert statuses == {
            "GTC-WAIT": "lobby",
            "GTC-PLAY": "in_game",
            "GTC-DONE": "closed",
        }
        assert "nickname_key" not in player_columns
        assert "session_expires_at" not in player_columns
        assert "reconnect_token_hash" not in player_columns
    finally:
        engine.dispose()


def test_phase_four_migration_adds_question_and_event_sequence(tmp_path: Path) -> None:
    """The Phase 4 upgrade preserves prior match events and adds questions."""
    database_url = f"sqlite:///{(tmp_path / 'phase4.db').as_posix()}"
    config = _alembic_config(database_url)
    command.upgrade(config, "0003")

    room_id = uuid.uuid4()
    match_id = uuid.uuid4()
    created_at = "2026-01-01 00:00:00.000000"

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO rooms"
                    " (id, code, host_player_id, status, configuration, created_at, updated_at)"
                    " VALUES (:id, 'GTC-4E', NULL, 'waiting', '{}', :timestamp, :timestamp)"
                ),
                {"id": room_id.hex, "timestamp": created_at},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO matches"
                    " (id, room_id, mode, status, turn_index, configuration, started_at,"
                    " finished_at, winner_id, winner_team_id, created_at, updated_at)"
                    " VALUES (:id, :room_id, 'individual', 'active', 0, '{}', :started_at,"
                    " NULL, NULL, NULL, :created_at, :created_at)"
                ),
                {
                    "id": match_id.hex,
                    "room_id": room_id.hex,
                    "started_at": created_at,
                    "created_at": created_at,
                },
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO game_events"
                    " (match_id, actor_player_id, event_type, payload, sequence_number,"
                    "  created_at, id)"
                    " VALUES (:match_id, NULL, 'match_started', '{}', 2, :created_at, :id)"
                ),
                {"match_id": match_id.hex, "created_at": created_at, "id": uuid.uuid4().hex},
            )
    finally:
        engine.dispose()

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("matches")}
            event_types = (
                connection.execute(sa.text("SELECT event_type FROM game_events")).scalars().all()
            )
            table_names = set(inspect(connection).get_table_names())
    finally:
        engine.dispose()

    assert "event_sequence" in columns
    assert "questions" in table_names
    assert list(event_types) == ["match_started"]

    command.downgrade(config, "0003")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            columns_after_downgrade = {
                column["name"] for column in inspect(connection).get_columns("matches")
            }
            tables_after_downgrade = set(inspect(connection).get_table_names())
    finally:
        engine.dispose()

    assert "event_sequence" not in columns_after_downgrade
    assert "questions" not in tables_after_downgrade
