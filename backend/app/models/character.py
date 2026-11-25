"""Character model for a room's shared character collection."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import CharacterCategory, enum_column_type

if TYPE_CHECKING:
    from app.models.room import Room

CHARACTER_KEY_MAX_LENGTH = 240


class Character(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "name_key",
            "franchise_key",
            name="uq_characters_room_id_name_key_franchise_key",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(image_path) > 0", name="image_path_not_blank"),
    )

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_key: Mapped[str] = mapped_column(String(CHARACTER_KEY_MAX_LENGTH), nullable=False)
    franchise: Mapped[str | None] = mapped_column(String(80), nullable=True)
    franchise_key: Mapped[str] = mapped_column(
        String(CHARACTER_KEY_MAX_LENGTH), nullable=False, default=""
    )
    category: Mapped[CharacterCategory] = mapped_column(
        enum_column_type(CharacterCategory, "character_category"),
        nullable=False,
    )
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    contributed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    room: Mapped["Room"] = relationship("Room", back_populates="characters")
