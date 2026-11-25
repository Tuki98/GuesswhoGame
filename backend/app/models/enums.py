"""Enumerations shared by persistence models and future game logic."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class RoomStatus(StrEnum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class GameMode(StrEnum):
    INDIVIDUAL = "individual"
    TEAM = "team"


class CharacterCategory(StrEnum):
    """Supported character sources.

    Values are lowercase snake_case to match the rest of the persisted enums.
    The display labels live in the API documentation and frontend.
    """

    ANIME = "anime"
    MANGA = "manga"
    VIDEO_GAMES = "video_games"
    MOVIES = "movies"
    TV = "tv"
    CARTOONS = "cartoons"
    COMICS = "comics"
    INTERNET_PERSONALITIES = "internet_personalities"
    OTHER = "other"


class MatchStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    FINISHED = "finished"
    ABANDONED = "abandoned"


class GameEventType(StrEnum):
    """Persisted and broadcast game/room events.

    Stored as text (not a native database enum) so the schema works identically
    on SQLite and adds a CHECK constraint for type safety.
    """

    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_DISCONNECTED = "player_disconnected"
    PLAYER_RECONNECTED = "player_reconnected"
    ROOM_UPDATED = "room_updated"
    ROOM_CLOSED = "room_closed"

    MATCH_CREATED = "match_created"
    MATCH_STARTED = "match_started"
    MATCH_FINISHED = "match_finished"
    MATCH_CANCELLED = "match_cancelled"

    CHARACTER_ADDED = "character_added"
    CHARACTER_REMOVED = "character_removed"
    CHARACTER_COLLECTION_UPDATED = "character_collection_updated"

    GAME_STARTED = "game_started"
    GAME_PAUSED = "game_paused"
    GAME_RESUMED = "game_resumed"
    TURN_CHANGED = "turn_changed"
    QUESTION_SENT = "question_sent"
    QUESTION_RECEIVED = "question_received"
    ANSWER_SENT = "answer_sent"
    ANSWER_RECEIVED = "answer_received"
    GUESS_SUBMITTED = "guess_submitted"
    GUESS_INCORRECT = "guess_incorrect"
    GUESS_CORRECT = "guess_correct"
    GAME_FINISHED = "game_finished"

    STATE_RESYNCHRONIZED = "state_resynchronized"
    EVENT_ACKNOWLEDGED = "event_acknowledged"
    SERVER_ERROR = "server_error"


def enum_column_type(enum_class: type[StrEnum], name: str) -> SAEnum:
    """Build a portable, validated VARCHAR-backed enum column type."""
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
        length=32,
    )
