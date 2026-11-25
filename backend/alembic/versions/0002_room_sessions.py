"""Phase 2 room lifecycle and player session credentials.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import sqlalchemy as sa
from alembic import op

from app.core.nicknames import nickname_key
from app.database.base import UTCDateTime, utc_now

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NICKNAME_KEY_LENGTH = 48
DEFAULT_SESSION_TTL = timedelta(hours=24)

players_table = sa.table(
    "players",
    sa.column("id", sa.Uuid()),
    sa.column("room_id", sa.Uuid()),
    sa.column("nickname", sa.String()),
    sa.column("joined_at", UTCDateTime()),
    sa.column("nickname_key", sa.String()),
    sa.column("session_expires_at", UTCDateTime()),
)


def _room_status_type(*values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name="room_status",
        native_enum=False,
        create_constraint=True,
        length=32,
    )


def _rebuild_rooms(*, statuses: tuple[str, str, str], default: str, mapping: str) -> None:
    """Recreate ``rooms`` with a new status CHECK constraint and mapped values.

    SQLite cannot alter a CHECK constraint in place, and the old constraint
    rejects the new status values. The table is rebuilt through a temporary
    name so the surrounding foreign keys keep pointing at ``rooms``.
    """
    op.create_table(
        "rooms_phase2",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("host_player_id", sa.Uuid(), nullable=True),
        sa.Column("status", _room_status_type(*statuses), server_default=default, nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["host_player_id"],
            ["players.id"],
            name=op.f("fk_rooms_host_player_id_players"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rooms")),
    )
    op.execute(
        f"""
        INSERT INTO rooms_phase2
            (id, code, host_player_id, status, configuration, created_at, updated_at)
        SELECT id, code, host_player_id, {mapping}, configuration, created_at, updated_at
        FROM rooms
        """
    )
    op.drop_table("rooms")
    op.rename_table("rooms_phase2", "rooms")
    op.create_index(op.f("ix_rooms_code"), "rooms", ["code"], unique=True)
    op.create_index(op.f("ix_rooms_host_player_id"), "rooms", ["host_player_id"], unique=False)


def _backfill_credentials() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            players_table.c.id,
            players_table.c.room_id,
            players_table.c.nickname,
            players_table.c.joined_at,
        )
    ).all()

    seen: dict[str, set[str]] = {}
    fallback_now = utc_now()
    for row in rows:
        key = nickname_key(row.nickname)[:NICKNAME_KEY_LENGTH] or "player"

        # Phase 1 allowed case-sensitive nickname duplicates. Make the new
        # case-insensitive key unique without deleting existing players.
        room_seen = seen.setdefault(str(row.room_id), set())
        if key in room_seen:
            suffix = 2
            while f"{key}-{suffix}" in room_seen:
                suffix += 1
            key = f"{key[: NICKNAME_KEY_LENGTH - len(str(suffix)) - 1]}-{suffix}"
        room_seen.add(key)

        joined_at = row.joined_at or fallback_now
        connection.execute(
            sa.update(players_table)
            .where(players_table.c.id == row.id)
            .values(
                nickname_key=key,
                session_expires_at=joined_at + DEFAULT_SESSION_TTL,
            )
        )


def upgrade() -> None:
    """Add session expiry, reconnect credentials, and case-insensitive names."""
    _rebuild_rooms(
        statuses=("waiting", "in_progress", "closed"),
        default="waiting",
        mapping=(
            "CASE status "
            "WHEN 'lobby' THEN 'waiting' "
            "WHEN 'in_game' THEN 'in_progress' "
            "WHEN 'finished' THEN 'closed' "
            "ELSE status END"
        ),
    )

    op.add_column("players", sa.Column("nickname_key", sa.String(length=48), nullable=True))
    op.add_column("players", sa.Column("session_expires_at", UTCDateTime(), nullable=True))
    op.add_column(
        "players", sa.Column("reconnect_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "players", sa.Column("reconnect_expires_at", UTCDateTime(), nullable=True)
    )

    _backfill_credentials()

    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.drop_constraint("uq_players_room_id_nickname", type_="unique")
        batch_op.alter_column(
            "nickname_key",
            existing_type=sa.String(length=48),
            nullable=False,
        )
        batch_op.alter_column(
            "session_expires_at",
            existing_type=UTCDateTime(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_players_room_id_nickname_key", ["room_id", "nickname_key"]
        )
        batch_op.create_index(
            batch_op.f("ix_players_reconnect_token_hash"),
            ["reconnect_token_hash"],
            unique=True,
        )


def downgrade() -> None:
    """Restore the Phase 1 room statuses and player credential columns."""
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_players_reconnect_token_hash"))
        batch_op.drop_constraint("uq_players_room_id_nickname_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_players_room_id_nickname", ["room_id", "nickname"]
        )
        batch_op.drop_column("reconnect_expires_at")
        batch_op.drop_column("reconnect_token_hash")
        batch_op.drop_column("session_expires_at")
        batch_op.drop_column("nickname_key")

    _rebuild_rooms(
        statuses=("lobby", "in_game", "finished", "closed"),
        default="lobby",
        mapping=(
            "CASE status "
            "WHEN 'waiting' THEN 'lobby' "
            "WHEN 'in_progress' THEN 'in_game' "
            "WHEN 'closed' THEN 'closed' "
            "ELSE status END"
        ),
    )
