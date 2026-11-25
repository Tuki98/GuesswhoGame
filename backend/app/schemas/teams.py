"""Request and response schemas for waiting-room team management."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.rooms import PublicPlayerResponse


class CreateTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)


class TeamResponse(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    name: str
    members: list[PublicPlayerResponse]


class TeamListResponse(BaseModel):
    teams: list[TeamResponse]


class AssignTeamRequest(BaseModel):
    """Set a player's team. ``team_id`` may be null to remove them from a team."""

    model_config = ConfigDict(extra="forbid")

    team_id: uuid.UUID | None


class AssignTeamResponse(BaseModel):
    player_id: uuid.UUID
    team: TeamResponse | None = None
