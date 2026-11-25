"""Phase 4 game-engine persistence: questions and match event sequencing.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.database.base import UTCDateTime

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_EVENT_TYPES = (
    "player_joined",
    "player_left",
    "player_disconnected",
    "player_reconnected",
    "room_updated",
    "room_closed",
    "character_added",
    "character_removed",
    "character_collection_updated",
    "game_started",
    "game_paused",
    "game_resumed",
    "turn_changed",
    "question_sent",
    "question_received",
    "answer_sent",
    "answer_received",
    "guess_submitted",
    "guess_incorrect",
    "guess_correct",
    "game_finished",
    "state_resynchronized",
    "event_acknowledged",
    "server_error",
)
_NEW_EVENT_TYPES = (
    "player_joined",
    "player_left",
    "player_disconnected",
    "player_reconnected",
    "room_updated",
    "room_closed",
    "match_created",
    "match_started",
    "match_finished",
    "match_cancelled",
    "character_added",
    "character_removed",
    "character_collection_updated",
    "game_started",
    "game_paused",
    "game_resumed",
    "turn_changed",
    "question_sent",
    "question_received",
    "answer_sent",
    "answer_received",
    "guess_submitted",
    "guess_incorrect",
    "guess_correct",
    "game_finished",
    "state_resynchronized",
    "event_acknowledged",
    "server_error",
)


def _event_type(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values,
        name="game_event_type",
        native_enum=False,
        create_constraint=True,
        length=32,
    )


def upgrade() -> None:
    """Add per-match event counters and the question/answer table."""
    with op.batch_alter_table("game_events", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=_event_type(_OLD_EVENT_TYPES),
            type_=_event_type(_NEW_EVENT_TYPES),
            existing_nullable=False,
        )

    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "event_sequence_non_negative",
            "event_sequence >= 0",
        )

    op.create_table(
        "questions",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("author_player_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_player_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_team_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("answer_content", sa.String(length=1000), nullable=True),
        sa.Column("answer_author_player_id", sa.Uuid(), nullable=True),
        sa.Column("answered_at", UTCDateTime(), nullable=True),
        sa.Column("pending_match_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "length(trim(content)) > 0",
            name=op.f("ck_questions_content_not_blank"),
        ),
        sa.CheckConstraint(
            "length(content) <= 500",
            name=op.f("ck_questions_content_max_length"),
        ),
        sa.CheckConstraint(
            "answer_content IS NULL OR length(trim(answer_content)) > 0",
            name=op.f("ck_questions_answer_not_blank"),
        ),
        sa.CheckConstraint(
            "answer_content IS NULL OR length(answer_content) <= 1000",
            name=op.f("ck_questions_answer_max_length"),
        ),
        sa.CheckConstraint(
            "(recipient_player_id IS NOT NULL AND recipient_team_id IS NULL) "
            "OR (recipient_player_id IS NULL AND recipient_team_id IS NOT NULL)",
            name=op.f("ck_questions_exactly_one_recipient"),
        ),
        sa.CheckConstraint(
            "(answer_content IS NULL AND answered_at IS NULL) "
            "OR (answer_content IS NOT NULL AND answered_at IS NOT NULL)",
            name=op.f("ck_questions_answer_state_complete"),
        ),
        sa.CheckConstraint(
            "pending_match_id IS NULL OR answer_content IS NULL",
            name=op.f("ck_questions_pending_question_unanswered"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_questions_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_player_id"],
            ["players.id"],
            name=op.f("fk_questions_author_player_id_players"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_player_id"],
            ["players.id"],
            name=op.f("fk_questions_recipient_player_id_players"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_team_id"],
            ["teams.id"],
            name=op.f("fk_questions_recipient_team_id_teams"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["answer_author_player_id"],
            ["players.id"],
            name=op.f("fk_questions_answer_author_player_id_players"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pending_match_id"],
            ["matches.id"],
            name=op.f("fk_questions_pending_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        sa.UniqueConstraint(
            "pending_match_id",
            name="uq_questions_pending_match_id",
        ),
    )
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_questions_match_id"), ["match_id"], unique=False)


def downgrade() -> None:
    """Remove question persistence, the event counter, and new event types."""
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_questions_match_id"))

    op.drop_table("questions")

    with op.batch_alter_table("matches", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_matches_event_sequence_non_negative"),
            type_="check",
        )
        batch_op.drop_column("event_sequence")

    # New event types must be removed before the old CHECK constraint is
    # restored; the application never downgrades with rows of those types.
    op.execute("DELETE FROM game_events WHERE event_type IN ('match_created', 'match_started', 'match_finished', 'match_cancelled')")
    with op.batch_alter_table("game_events", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=_event_type(_NEW_EVENT_TYPES),
            type_=_event_type(_OLD_EVENT_TYPES),
            existing_nullable=False,
        )
