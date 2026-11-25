"""Room aggregate root."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RoomStatus, enum_column_type

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.match import Match
    from app.models.player import Player
    from app.models.team import Team


class Room(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rooms"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    host_player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[RoomStatus] = mapped_column(
        enum_column_type(RoomStatus, "room_status"),
        nullable=False,
        default=RoomStatus.WAITING,
        server_default=RoomStatus.WAITING.value,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    host: Mapped["Player | None"] = relationship(
        "Player",
        foreign_keys=[host_player_id],
        post_update=True,
    )
    players: Mapped[list["Player"]] = relationship(
        "Player",
        back_populates="room",
        foreign_keys="Player.room_id",
        cascade="all, delete-orphan",
    )
    teams: Mapped[list["Team"]] = relationship(
        "Team",
        back_populates="room",
        cascade="all, delete-orphan",
    )
    characters: Mapped[list["Character"]] = relationship(
        "Character",
        back_populates="room",
        cascade="all, delete-orphan",
    )
    matches: Mapped[list["Match"]] = relationship(
        "Match",
        back_populates="room",
        cascade="all, delete-orphan",
    )
