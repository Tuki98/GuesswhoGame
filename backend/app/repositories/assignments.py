"""Secret assignment queries."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Assignment


class AssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_match(self, match_id: uuid.UUID) -> list[Assignment]:
        return list(
            self.session.scalars(
                select(Assignment)
                .options(joinedload(Assignment.character))
                .where(Assignment.match_id == match_id)
                .order_by(Assignment.created_at, Assignment.id)
            )
        )

    def get_for_player(self, match_id: uuid.UUID, player_id: uuid.UUID) -> Assignment | None:
        return self.session.scalar(
            select(Assignment)
            .options(joinedload(Assignment.character))
            .where(Assignment.match_id == match_id, Assignment.player_id == player_id)
        )

    def get_for_team(self, match_id: uuid.UUID, team_id: uuid.UUID) -> Assignment | None:
        return self.session.scalar(
            select(Assignment)
            .options(joinedload(Assignment.character))
            .where(Assignment.match_id == match_id, Assignment.team_id == team_id)
        )
