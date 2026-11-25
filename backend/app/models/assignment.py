"""Secret character assignment for a match.

An assignment targets exactly one owner: a player in individual mode or a team
in team mode. The database enforces that rule, that characters are not reused
within a match, and that one owner does not receive multiple characters.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UTCDateTime, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.match import Match
    from app.models.player import Player
    from app.models.team import Team


class Assignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            "(player_id IS NOT NULL AND team_id IS NULL) "
            "OR (player_id IS NULL AND team_id IS NOT NULL)",
            name="exactly_one_owner",
        ),
        UniqueConstraint("match_id", "character_id", name="uq_assignments_match_id_character_id"),
        UniqueConstraint("match_id", "player_id", name="uq_assignments_match_id_player_id"),
        UniqueConstraint("match_id", "team_id", name="uq_assignments_match_id_team_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("characters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=True,
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    match: Mapped["Match"] = relationship("Match", back_populates="assignments")
    character: Mapped["Character"] = relationship("Character")
    player: Mapped["Player | None"] = relationship("Player")
    team: Mapped["Team | None"] = relationship("Team")
