"""Team queries used by team-management and match services."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Team


class TeamRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, team_id: uuid.UUID) -> Team | None:
        return self.session.get(Team, team_id)

    def list_by_room(self, room_id: uuid.UUID) -> list[Team]:
        return list(
            self.session.scalars(
                select(Team).where(Team.room_id == room_id).order_by(Team.created_at, Team.id)
            )
        )

    def name_exists(self, room_id: uuid.UUID, name: str) -> bool:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Team)
                .where(Team.room_id == room_id, Team.name == name)
            )
            or 0
        ) > 0
