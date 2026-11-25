"""Player model: a nickname-scoped participant with hashed session credentials."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import TOKEN_HASH_HEX_LENGTH
from app.database.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.room import Room
    from app.models.team import Team

NICKNAME_KEY_MAX_LENGTH = 48


class Player(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("room_id", "nickname_key", name="uq_players_room_id_nickname_key"),
        CheckConstraint("length(trim(nickname)) > 0", name="nickname_not_blank"),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nickname: Mapped[str] = mapped_column(String(40), nullable=False)
    nickname_key: Mapped[str] = mapped_column(String(NICKNAME_KEY_MAX_LENGTH), nullable=False)
    session_token_hash: Mapped[str] = mapped_column(
        String(TOKEN_HASH_HEX_LENGTH), nullable=False, unique=True, index=True
    )
    session_expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    reconnect_token_hash: Mapped[str | None] = mapped_column(
        String(TOKEN_HASH_HEX_LENGTH), nullable=True, unique=True, index=True
    )
    reconnect_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_connected: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    is_ready: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    room: Mapped["Room"] = relationship("Room", back_populates="players", foreign_keys=[room_id])
    team: Mapped["Team | None"] = relationship(
        "Team", back_populates="members", foreign_keys=[team_id]
    )
