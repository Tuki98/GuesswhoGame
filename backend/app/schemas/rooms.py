"""Request and response schemas for room and session management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.nicknames import normalize_nickname
from app.core.room_config import MAX_MAX_PLAYERS, MIN_MAX_PLAYERS, RoomConfig
from app.models.enums import GameMode, RoomStatus

Nickname = Annotated[str, AfterValidator(normalize_nickname)]


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: Nickname
    settings: RoomConfig = Field(default_factory=RoomConfig)


class JoinRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=16)
    nickname: Nickname


class UpdateRoomSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_players: int | None = Field(
        default=None,
        ge=MIN_MAX_PLAYERS,
        le=MAX_MAX_PLAYERS,
    )
    game_mode: GameMode | None = None

    @model_validator(mode="after")
    def _require_at_least_one_change(self) -> UpdateRoomSettingsRequest:
        if self.max_players is None and self.game_mode is None:
            raise ValueError("At least one setting must be provided.")
        return self


class PublicPlayerResponse(BaseModel):
    """Player fields safe to expose to other room participants."""

    id: uuid.UUID
    nickname: str
    is_host: bool
    is_connected: bool
    is_ready: bool
    joined_at: datetime


class RoomResponse(BaseModel):
    id: uuid.UUID
    code: str
    status: RoomStatus
    host_player_id: uuid.UUID | None
    settings: RoomConfig
    player_count: int
    created_at: datetime
    updated_at: datetime


class SessionCredentialsResponse(BaseModel):
    """Raw credentials. Returned only when a session is created or rotated."""

    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (scheme name, not a secret)
    session_token: str
    session_expires_at: datetime
    reconnect_token: str
    reconnect_expires_at: datetime


class RoomSessionResponse(BaseModel):
    room: RoomResponse
    player: PublicPlayerResponse
    credentials: SessionCredentialsResponse


class ReconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reconnect_token: str = Field(min_length=1, max_length=512)


class ReconnectResponse(BaseModel):
    room: RoomResponse
    player: PublicPlayerResponse
    credentials: SessionCredentialsResponse


class PlayerListResponse(BaseModel):
    players: list[PublicPlayerResponse]
