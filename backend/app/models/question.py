"""A question asked during a match and its optional free-text answer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.player import Player
    from app.models.team import Team

QUESTION_MAX_LENGTH = 500
ANSWER_MAX_LENGTH = 1000


class Question(UUIDPrimaryKeyMixin, Base):
    """A single question in a match.

    ``pending_match_id`` is equal to the match id while the question is
    unanswered and NULL afterwards. Its unique constraint makes the database
    itself reject a second concurrently-created pending question for the same
    match. Multiple NULL values are allowed by SQLite and the SQL standard.
    """

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("length(trim(content)) > 0", name="content_not_blank"),
        CheckConstraint(
            f"length(content) <= {QUESTION_MAX_LENGTH}",
            name="content_max_length",
        ),
        CheckConstraint(
            "answer_content IS NULL OR length(trim(answer_content)) > 0",
            name="answer_not_blank",
        ),
        CheckConstraint(
            f"answer_content IS NULL OR length(answer_content) <= {ANSWER_MAX_LENGTH}",
            name="answer_max_length",
        ),
        CheckConstraint(
            "(recipient_player_id IS NOT NULL AND recipient_team_id IS NULL) "
            "OR (recipient_player_id IS NULL AND recipient_team_id IS NOT NULL)",
            name="exactly_one_recipient",
        ),
        CheckConstraint(
            "(answer_content IS NULL AND answered_at IS NULL) "
            "OR (answer_content IS NOT NULL AND answered_at IS NOT NULL)",
            name="answer_state_complete",
        ),
        CheckConstraint(
            "pending_match_id IS NULL OR answer_content IS NULL",
            name="pending_question_unanswered",
        ),
        UniqueConstraint("pending_match_id", name="uq_questions_pending_match_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(String(QUESTION_MAX_LENGTH), nullable=False)
    answer_content: Mapped[str | None] = mapped_column(
        String(ANSWER_MAX_LENGTH),
        nullable=True,
    )
    answer_author_player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    pending_match_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    match: Mapped["Match"] = relationship(
        "Match",
        back_populates="questions",
        foreign_keys=[match_id],
    )
    author: Mapped["Player | None"] = relationship("Player", foreign_keys=[author_player_id])
    recipient_player: Mapped["Player | None"] = relationship(
        "Player",
        foreign_keys=[recipient_player_id],
    )
    recipient_team: Mapped["Team | None"] = relationship("Team", foreign_keys=[recipient_team_id])
    answer_author: Mapped["Player | None"] = relationship(
        "Player",
        foreign_keys=[answer_author_player_id],
    )
