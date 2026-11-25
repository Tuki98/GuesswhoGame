"""Match model: one play session of a room."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Uuid,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.models.enums import GameMode, MatchStatus, enum_column_type

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.game_event import GameEvent
    from app.models.question import Question
    from app.models.room import Room


class Match(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("turn_index >= 0", name="turn_index_non_negative"),
        CheckConstraint("event_sequence >= 0", name="event_sequence_non_negative"),
        CheckConstraint(
            "winner_id IS NULL OR winner_team_id IS NULL",
            name="single_winner",
        ),
        Index("ix_matches_room_id_status", "room_id", "status"),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[GameMode] = mapped_column(enum_column_type(GameMode, "game_mode"), nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        enum_column_type(MatchStatus, "match_status"),
        nullable=False,
        default=MatchStatus.PENDING,
        server_default=MatchStatus.PENDING.value,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Monotonic event-log counter. Allocating from the match row makes event
    # sequencing and the accompanying state change a single write transaction.
    event_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    winner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )

    room: Mapped["Room"] = relationship("Room", back_populates="matches")
    assignments: Mapped[list["Assignment"]] = relationship(
        "Assignment",
        back_populates="match",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["GameEvent"]] = relationship(
        "GameEvent",
        back_populates="match",
        cascade="all, delete-orphan",
        order_by="GameEvent.sequence_number",
    )
    questions: Mapped[list["Question"]] = relationship(
        "Question",
        back_populates="match",
        cascade="all, delete-orphan",
        foreign_keys="Question.match_id",
        order_by="Question.created_at",
    )
