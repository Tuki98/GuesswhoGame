"""Append-only match event log for persistence and ordering."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import GameEventType, enum_column_type

if TYPE_CHECKING:
    from app.models.match import Match


class GameEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "game_events"
    __table_args__ = (
        CheckConstraint("sequence_number > 0", name="sequence_number_positive"),
        UniqueConstraint(
            "match_id", "sequence_number", name="uq_game_events_match_id_sequence_number"
        ),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[GameEventType] = mapped_column(
        enum_column_type(GameEventType, "game_event_type"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    match: Mapped["Match"] = relationship("Match", back_populates="events")
