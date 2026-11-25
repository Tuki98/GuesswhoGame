"""Room queries used by room services."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models import Player, Room, RoomStatus


class RoomRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, room_id: uuid.UUID) -> Room | None:
        return self.session.get(Room, room_id)

    def get_by_code(self, code: str) -> Room | None:
        return self.session.scalar(select(Room).where(Room.code == code))

    def code_exists(self, code: str) -> bool:
        return (
            self.session.scalar(select(func.count()).select_from(Room).where(Room.code == code))
            or 0
        ) > 0

    def count_players(self, room_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                select(func.count()).select_from(Player).where(Player.room_id == room_id)
            )
            or 0
        )

    def transition_status(
        self,
        room_id: uuid.UUID,
        *,
        expected: RoomStatus,
        new: RoomStatus,
    ) -> bool:
        """Compare-and-swap the room status; SQLite writers are serialized."""
        statement = (
            update(Room)
            .where(Room.id == room_id, Room.status == expected)
            .values(status=new)
            .execution_options(synchronize_session=False)
        )
        result = cast("CursorResult[Any]", self.session.execute(statement))
        return result.rowcount == 1
