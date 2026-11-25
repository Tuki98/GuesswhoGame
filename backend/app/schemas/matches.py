"""Request and response schemas for the Phase 4 game engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CharacterCategory, GameMode, MatchStatus


class StartMatchRequest(BaseModel):
    """Empty body; the room and host come from the path/session."""

    model_config = ConfigDict(extra="forbid")


class AskQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)
    recipient_player_id: uuid.UUID | None = None
    recipient_team_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _exactly_one_recipient(self) -> AskQuestionRequest:
        has_player = self.recipient_player_id is not None
        has_team = self.recipient_team_id is not None
        if has_player == has_team:
            raise ValueError(
                "Provide exactly one recipient: recipient_player_id or recipient_team_id."
            )
        return self


class AnswerQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=1000)


class SubmitGuessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: uuid.UUID


class MatchInfoResponse(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    mode: GameMode
    status: MatchStatus
    phase: str
    turn_index: int
    current_turn_id: uuid.UUID | None
    current_turn_kind: Literal["player", "team"]
    current_turn_name: str | None
    participant_count: int
    started_at: datetime | None
    finished_at: datetime | None
    winner_player_id: uuid.UUID | None
    winner_team_id: uuid.UUID | None
    winner_name: str | None


class MatchParticipantResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: Literal["player", "team"]
    is_connected: bool
    member_player_ids: list[uuid.UUID]


class MatchCharacterResponse(BaseModel):
    """Visible character information. Never used for a player's own secret."""

    id: uuid.UUID
    name: str
    franchise: str | None
    category: CharacterCategory
    image_url: str
    attributes: dict[str, Any]


class VisibleCharacterResponse(BaseModel):
    owner_id: uuid.UUID
    owner_kind: Literal["player", "team"]
    owner_name: str
    character: MatchCharacterResponse


class AnswerResponse(BaseModel):
    content: str
    author_player_id: uuid.UUID | None
    author_nickname: str | None
    answered_at: datetime


class QuestionResponse(BaseModel):
    id: uuid.UUID
    author_player_id: uuid.UUID | None
    author_nickname: str | None
    recipient_player_id: uuid.UUID | None
    recipient_team_id: uuid.UUID | None
    recipient_name: str | None
    content: str
    asked_at: datetime
    answer: AnswerResponse | None = None
    can_answer: bool = False


class MatchSelfResponse(BaseModel):
    player_id: uuid.UUID
    nickname: str
    team_id: uuid.UUID | None
    team_name: str | None
    is_your_turn: bool
    can_ask: bool


class MatchDetailsResponse(BaseModel):
    match: MatchInfoResponse
    participants: list[MatchParticipantResponse]


class MatchStateResponse(BaseModel):
    match: MatchInfoResponse
    self: MatchSelfResponse
    identity_assigned: bool
    identity_revealed: bool
    opponents: list[VisibleCharacterResponse]
    participants: list[MatchParticipantResponse]
    pending_question: QuestionResponse | None
    question_history: list[QuestionResponse]
    allowed_recipient_ids: list[uuid.UUID]


class GuessResultResponse(BaseModel):
    correct: bool
    match: MatchInfoResponse


class EventResponse(BaseModel):
    id: uuid.UUID
    match_id: uuid.UUID
    actor_player_id: uuid.UUID | None
    event_type: str
    payload: dict[str, Any]
    sequence_number: int
    created_at: datetime


class MatchHistoryResponse(BaseModel):
    events: list[EventResponse]
    has_more: bool
    next_after_sequence: int | None = None
