"""Question and answer queries."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, joinedload

from app.models import Question


class QuestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, question_id: uuid.UUID) -> Question | None:
        return self.session.get(Question, question_id)

    def get_pending(self, match_id: uuid.UUID) -> Question | None:
        return self.session.scalar(select(Question).where(Question.pending_match_id == match_id))

    def list_by_match(self, match_id: uuid.UUID) -> list[Question]:
        return list(
            self.session.scalars(
                select(Question)
                .options(
                    joinedload(Question.author),
                    joinedload(Question.recipient_player),
                    joinedload(Question.recipient_team),
                    joinedload(Question.answer_author),
                )
                .where(Question.match_id == match_id)
                .order_by(Question.created_at, Question.id)
            )
        )

    def mark_answered(
        self,
        question_id: uuid.UUID,
        match_id: uuid.UUID,
        *,
        answer_content: str,
        answer_author_player_id: uuid.UUID,
        answered_at: datetime,
    ) -> bool:
        """Compare-and-swap an unanswered question to its answered state."""
        statement = (
            update(Question)
            .where(Question.id == question_id, Question.pending_match_id == match_id)
            .values(
                pending_match_id=None,
                answer_content=answer_content,
                answer_author_player_id=answer_author_player_id,
                answered_at=answered_at,
            )
            .execution_options(synchronize_session=False)
        )
        result = cast("CursorResult[Any]", self.session.execute(statement))
        return result.rowcount == 1
