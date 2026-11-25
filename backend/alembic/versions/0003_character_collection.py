"""Phase 3 character collection keys, categories, and uniqueness.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.characters import character_key, coerce_stored_category
from app.database.base import NAMING_CONVENTION

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHARACTER_KEY_LENGTH = 240
CATEGORY_VALUES = (
    "anime",
    "manga",
    "video_games",
    "movies",
    "tv",
    "cartoons",
    "comics",
    "internet_personalities",
    "other",
)

characters_table = sa.table(
    "characters",
    sa.column("id", sa.Uuid()),
    sa.column("room_id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("name_key", sa.String()),
    sa.column("franchise", sa.String()),
    sa.column("franchise_key", sa.String()),
    sa.column("category", sa.String()),
)


def _category_type() -> sa.Enum:
    return sa.Enum(
        *CATEGORY_VALUES,
        name="character_category",
        native_enum=False,
        create_constraint=True,
        length=32,
    )


def _backfill_character_keys() -> None:
    """Derive duplicate-detection keys and normalize legacy categories.

    Phase 1 had no uniqueness rule, so two rows in the same room may normalize
    to the same key pair. Rows are preserved and later duplicates receive a
    numeric suffix on the name key; the display name and franchise are
    untouched.
    """
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            characters_table.c.id,
            characters_table.c.room_id,
            characters_table.c.name,
            characters_table.c.franchise,
            characters_table.c.category,
        )
    ).all()

    used_keys: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        base_name_key = character_key(row.name)[:CHARACTER_KEY_LENGTH] or "character"
        franchise_key = character_key(row.franchise or "")[:CHARACTER_KEY_LENGTH]

        room_keys = used_keys.setdefault(str(row.room_id), set())
        name_key = base_name_key
        suffix = 2
        while (name_key, franchise_key) in room_keys:
            tail = f"-{suffix}"
            name_key = f"{base_name_key[: CHARACTER_KEY_LENGTH - len(tail)]}{tail}"
            suffix += 1
        room_keys.add((name_key, franchise_key))

        connection.execute(
            sa.update(characters_table)
            .where(characters_table.c.id == row.id)
            .values(
                name_key=name_key,
                franchise_key=franchise_key,
                category=coerce_stored_category(row.category).value,
            )
        )


def upgrade() -> None:
    """Add normalized keys, required categories, and room-scoped uniqueness."""
    op.add_column(
        "characters",
        sa.Column("name_key", sa.String(length=CHARACTER_KEY_LENGTH), nullable=True),
    )
    op.add_column(
        "characters",
        sa.Column("franchise_key", sa.String(length=CHARACTER_KEY_LENGTH), nullable=True),
    )

    _backfill_character_keys()

    with op.batch_alter_table(
        "characters",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.alter_column(
            "name_key",
            existing_type=sa.String(length=CHARACTER_KEY_LENGTH),
            nullable=False,
        )
        batch_op.alter_column(
            "franchise_key",
            existing_type=sa.String(length=CHARACTER_KEY_LENGTH),
            nullable=False,
        )
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=40),
            type_=_category_type(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_characters_room_id_name_key_franchise_key",
            ["room_id", "name_key", "franchise_key"],
        )


def downgrade() -> None:
    """Remove Phase 3 keys and return categories to nullable free text."""
    with op.batch_alter_table(
        "characters",
        schema=None,
        naming_convention=NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_characters_room_id_name_key_franchise_key",
            type_="unique",
        )
        # The batch naming convention adds the ``ck_characters_`` prefix, so
        # the raw enum constraint name is supplied here.
        batch_op.drop_constraint("character_category", type_="check")
        batch_op.alter_column(
            "category",
            existing_type=_category_type(),
            type_=sa.String(length=40),
            nullable=True,
        )
        batch_op.drop_column("franchise_key")
        batch_op.drop_column("name_key")
