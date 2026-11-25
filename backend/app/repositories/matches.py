"""Match queries and atomic state transitions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus

OPEN_STATUSES = (MatchStatus.PENDING, MatchStatus.ACTIVE, MatchStatus.PAUSED)


class MatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, match_id: uuid.UUID) -> Match | None:
        return self.session.get(Match, match_id)

    def active_for_room(self, room_id: uuid.UUID) -> Match | None:
        """Return the single playable match for a room, if there is one."""
        return self.session.scalar(
            select(Match)
            .where(Match.room_id == room_id, Match.status.in_(OPEN_STATUSES))
            .order_by(Match.created_at.desc())
            .limit(1)
        )

    def allocate_event_sequence(
        self,
        match_id: uuid.UUID,
        *,
        count: int = 1,
        require_status: MatchStatus | None = None,
    ) -> int | None:
        """Atomically reserve ``count`` event sequence numbers.

        The UPDATE is the compare-and-swap: it only succeeds while the match is
        in the expected status. SQLite serializes writers, so two concurrent
        callers cannot observe the same counter value. The returned value is the
        last reserved sequence number.
        """
        statement = update(Match).where(Match.id == match_id)
        if require_status is not None:
            statement = statement.where(Match.status == require_status)
        statement = statement.values(event_sequence=Match.event_sequence + count)
        statement = statement.execution_options(synchronize_session=False)

        result = cast("CursorResult[Any]", self.session.execute(statement))
        if result.rowcount != 1:
            return None
        return self.session.scalar(select(Match.event_sequence).where(Match.id == match_id))

    def finish_with_winner(
        self,
        match_id: uuid.UUID,
        *,
        winner_player_id: uuid.UUID | None,
        winner_team_id: uuid.UUID | None,
        finished_at: datetime,
        event_count: int,
    ) -> int | None:
        """Finish an active match exactly once and reserve finish events."""
        statement = (
            update(Match)
            .where(Match.id == match_id, Match.status == MatchStatus.ACTIVE)
            .values(
                status=MatchStatus.FINISHED,
                winner_id=winner_player_id,
                winner_team_id=winner_team_id,
                finished_at=finished_at,
                event_sequence=Match.event_sequence + event_count,
            )
            .execution_options(synchronize_session=False)
        )
        result = cast("CursorResult[Any]", self.session.execute(statement))
        if result.rowcount != 1:
            return None
        return self.session.scalar(select(Match.event_sequence).where(Match.id == match_id))

    def cancel_if_open(
        self,
        match_id: uuid.UUID,
        *,
        finished_at: datetime,
        event_count: int = 1,
    ) -> int | None:
        """Cancel a pending/active match exactly once.

        A concurrent finish (correct guess) makes this UPDATE match no row, so a
        match can never be both finished and cancelled.
        """
        statement = (
            update(Match)
            .where(
                Match.id == match_id, Match.status.in_((MatchStatus.PENDING, MatchStatus.ACTIVE))
            )
            .values(
                status=MatchStatus.ABANDONED,
                finished_at=finished_at,
                event_sequence=Match.event_sequence + event_count,
            )
            .execution_options(synchronize_session=False)
        )
        result = cast("CursorResult[Any]", self.session.execute(statement))
        if result.rowcount != 1:
            return None
        return self.session.scalar(select(Match.event_sequence).where(Match.id == match_id))

    def advance_turn(self, match_id: uuid.UUID) -> bool:
        """Move to the next turn only while the match is active."""
        statement = (
            update(Match)
            .where(Match.id == match_id, Match.status == MatchStatus.ACTIVE)
            .values(turn_index=Match.turn_index + 1)
            .execution_options(synchronize_session=False)
        )
        result = cast("CursorResult[Any]", self.session.execute(statement))
        return result.rowcount == 1
