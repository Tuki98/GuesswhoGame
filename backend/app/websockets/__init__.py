"""WebSocket transport components for the Phase 5 real-time layer."""

from app.websockets import handlers
from app.websockets.manager import ConnectionManager
from app.websockets.protocol import (
    ANSWER_RECEIVED_EVENT,
    CHARACTER_ADDED_EVENT,
    CHARACTER_DELETED_EVENT,
    GUESS_INCORRECT_EVENT,
    MATCH_CANCELLED_EVENT,
    MATCH_FINISHED_EVENT,
    MATCH_STARTED_EVENT,
    MATCH_STATE_EVENT,
    PLAYER_READY_CHANGED_EVENT,
    QUESTION_RECEIVED_EVENT,
    ROOM_STATE_EVENT,
    WebSocketEvent,
    WebSocketIncomingMessage,
)

__all__ = [
    "ANSWER_RECEIVED_EVENT",
    "CHARACTER_ADDED_EVENT",
    "CHARACTER_DELETED_EVENT",
    "GUESS_INCORRECT_EVENT",
    "MATCH_CANCELLED_EVENT",
    "MATCH_FINISHED_EVENT",
    "MATCH_STARTED_EVENT",
    "MATCH_STATE_EVENT",
    "PLAYER_READY_CHANGED_EVENT",
    "QUESTION_RECEIVED_EVENT",
    "ROOM_STATE_EVENT",
    "ConnectionManager",
    "WebSocketEvent",
    "WebSocketIncomingMessage",
    "handlers",
]
