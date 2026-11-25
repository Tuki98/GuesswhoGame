"""Request and response schemas for a room's character collection."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CharacterCategory


class CreateCharacterRequest(BaseModel):
    """JSON character submission.

    Multipart submissions use the same field names plus an ``image`` file part.
    ``image_url`` is optional at the schema level because the route enforces
    that exactly one image source is present.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    franchise: str | None = Field(default=None, max_length=80)
    category: CharacterCategory
    attributes: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = Field(default=None, max_length=2048)


class CharacterResponse(BaseModel):
    """Public character fields. Internal filesystem paths are never exposed."""

    id: uuid.UUID
    room_id: uuid.UUID
    name: str
    franchise: str | None
    category: CharacterCategory
    image_url: str
    attributes: dict[str, Any]
    contributed_by: uuid.UUID | None
    created_at: datetime


class CharacterListResponse(BaseModel):
    characters: list[CharacterResponse]
