"""Append-only event-log queries."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GameEvent


class GameEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_page(
        self,
        match_id: uuid.UUID,
        *,
        limit: int,
        after_sequence: int | None = None,
    ) -> list[GameEvent]:
        """Return up to ``limit + 1`` events in ascending sequence order."""
        statement = select(GameEvent).where(GameEvent.match_id == match_id)
        if after_sequence is not None:
            statement = statement.where(GameEvent.sequence_number > after_sequence)
        return list(
            self.session.scalars(
                statement.order_by(GameEvent.sequence_number.asc()).limit(limit + 1)
            )
        )
