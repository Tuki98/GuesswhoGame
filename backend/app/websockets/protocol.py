"""WebSocket message envelope schemas and event names for the real-time layer."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Upper bound for a single inbound JSON message (envelope + payload). The game
# engine only accepts small free-text values, so anything larger is rejected.
MAX_MESSAGE_BYTES = 8192


class WebSocketIncomingMessage(BaseModel):
    """Envelope used by clients for every incoming WebSocket event."""

    model_config = ConfigDict(extra="forbid")

    event: str
    request_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WebSocketEvent(BaseModel):
    """Envelope used for every outgoing WebSocket message."""

    model_config = ConfigDict(extra="forbid")

    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    event_id: str | None = None
    sequence_number: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize without emitting empty optional members."""
        data: dict[str, Any] = {"event": self.event, "payload": self.payload}
        if self.request_id is not None:
            data["request_id"] = self.request_id
        if self.event_id is not None:
            data["event_id"] = self.event_id
        if self.sequence_number is not None:
            data["sequence_number"] = self.sequence_number
        return data


class WebSocketErrorPayload(BaseModel):
    """Structured error details carried by outgoing ``error`` events."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class WebSocketEmptyPayload(BaseModel):
    """Payload for events that carry no additional data."""

    model_config = ConfigDict(extra="forbid")


class PlayerSetReadyPayload(BaseModel):
    """Payload for the ``player.set_ready`` event."""

    model_config = ConfigDict(extra="forbid")

    ready: bool
    target_player_id: uuid.UUID | None = None


class CharacterAddPayload(BaseModel):
    """Payload for the ``character.add`` event (binary uploads stay REST-only)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    franchise: str | None = None
    category: str = "anime"
    attributes: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = None


class CharacterDeletePayload(BaseModel):
    """Payload for the ``character.delete`` event."""

    model_config = ConfigDict(extra="forbid")

    character_id: uuid.UUID


class QuestionSubmitPayload(BaseModel):
    """Payload for the ``question.submit`` event."""

    model_config = ConfigDict(extra="forbid")

    content: str
    recipient_player_id: uuid.UUID | None = None
    recipient_team_id: uuid.UUID | None = None


class AnswerSubmitPayload(BaseModel):
    """Payload for the ``answer.submit`` event."""

    model_config = ConfigDict(extra="forbid")

    content: str
    question_id: uuid.UUID


class GuessSubmitPayload(BaseModel):
    """Payload for the ``guess.submit`` event."""

    model_config = ConfigDict(extra="forbid")

    character_id: uuid.UUID


ROOM_STATE_EVENT = "room.state"
ROOM_UPDATED_EVENT = "room.updated"
PLAYER_JOINED_EVENT = "player.joined"
PLAYER_LEFT_EVENT = "player.left"
PLAYER_CONNECTED_EVENT = "player.connected"
PLAYER_DISCONNECTED_EVENT = "player.disconnected"
PLAYER_READY_CHANGED_EVENT = "player.ready_changed"
CHARACTER_ADDED_EVENT = "character.added"
CHARACTER_DELETED_EVENT = "character.deleted"
MATCH_STARTED_EVENT = "match.started"
MATCH_STATE_EVENT = "match.state"
MATCH_TURN_CHANGED_EVENT = "match.turn_changed"
QUESTION_RECEIVED_EVENT = "question.received"
ANSWER_RECEIVED_EVENT = "answer.received"
GUESS_INCORRECT_EVENT = "guess.incorrect"
MATCH_FINISHED_EVENT = "match.finished"
MATCH_CANCELLED_EVENT = "match.cancelled"

SUPPORTED_INCOMING_EVENTS = frozenset(
    {
        "room.get_state",
        "player.set_ready",
        "character.add",
        "character.delete",
        "match.start",
        "match.get_state",
        "question.submit",
        "answer.submit",
        "guess.submit",
        "match.cancel",
    }
)

PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "room.get_state": WebSocketEmptyPayload,
    "match.start": WebSocketEmptyPayload,
    "match.get_state": WebSocketEmptyPayload,
    "match.cancel": WebSocketEmptyPayload,
    "player.set_ready": PlayerSetReadyPayload,
    "character.add": CharacterAddPayload,
    "character.delete": CharacterDeletePayload,
    "question.submit": QuestionSubmitPayload,
    "answer.submit": AnswerSubmitPayload,
    "guess.submit": GuessSubmitPayload,
}


def new_event_id() -> str:
    """Return a server-generated event id for state-change notifications."""
    return uuid.uuid4().hex
