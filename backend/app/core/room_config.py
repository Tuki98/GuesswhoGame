"""Validated room configuration persisted in ``rooms.configuration``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GameMode

DEFAULT_MAX_PLAYERS = 8
MIN_MAX_PLAYERS = 2
MAX_MAX_PLAYERS = 16


class RoomConfig(BaseModel):
    """Typed, immutable room settings.

    Unknown keys are rejected so configuration cannot silently accumulate
    unimplemented options.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_players: int = Field(
        default=DEFAULT_MAX_PLAYERS,
        ge=MIN_MAX_PLAYERS,
        le=MAX_MAX_PLAYERS,
    )
    game_mode: GameMode = GameMode.INDIVIDUAL
