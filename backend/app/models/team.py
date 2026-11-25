"""Team model for team-based matches."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.player import Player
    from app.models.room import Room


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("room_id", "name", name="uq_teams_room_id_name"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)

    room: Mapped["Room"] = relationship("Room", back_populates="teams")
    members: Mapped[list["Player"]] = relationship(
        "Player", back_populates="team", foreign_keys="Player.team_id"
    )
