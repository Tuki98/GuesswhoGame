"""Unit tests for validated room configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.room_config import (
    DEFAULT_MAX_PLAYERS,
    MAX_MAX_PLAYERS,
    MIN_MAX_PLAYERS,
    RoomConfig,
)
from app.models.enums import GameMode


def test_room_config_defaults() -> None:
    config = RoomConfig()

    assert config.max_players == DEFAULT_MAX_PLAYERS
    assert config.game_mode is GameMode.INDIVIDUAL


def test_room_config_accepts_boundaries() -> None:
    assert RoomConfig(max_players=MIN_MAX_PLAYERS).max_players == MIN_MAX_PLAYERS
    assert RoomConfig(max_players=MAX_MAX_PLAYERS).max_players == MAX_MAX_PLAYERS


@pytest.mark.parametrize("max_players", [MIN_MAX_PLAYERS - 1, MAX_MAX_PLAYERS + 1])
def test_room_config_rejects_out_of_range_capacity(max_players: int) -> None:
    with pytest.raises(ValidationError):
        RoomConfig(max_players=max_players)


def test_room_config_rejects_unknown_settings() -> None:
    with pytest.raises(ValidationError):
        RoomConfig.model_validate({"unknown": True})


def test_room_config_is_immutable() -> None:
    config = RoomConfig()

    with pytest.raises(ValidationError):
        config.max_players = 4  # type: ignore[misc]
