"""Character queries used by the character service."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Character


class CharacterRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, character_id: uuid.UUID) -> Character | None:
        return self.session.get(Character, character_id)

    def list_by_room(self, room_id: uuid.UUID) -> list[Character]:
        """Return a room's collection in submission order for stable output."""
        return list(
            self.session.scalars(
                select(Character)
                .where(Character.room_id == room_id)
                .order_by(Character.created_at, Character.id)
            )
        )

    def name_keys_exist(
        self,
        room_id: uuid.UUID,
        name_key: str,
        franchise_key: str,
    ) -> bool:
        """Check the room-scoped normalized uniqueness key."""
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Character)
                .where(
                    Character.room_id == room_id,
                    Character.name_key == name_key,
                    Character.franchise_key == franchise_key,
                )
            )
            or 0
        ) > 0
