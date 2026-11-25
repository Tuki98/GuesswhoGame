"""Import every model so SQLAlchemy and Alembic see the complete metadata."""

from app.models.assignment import Assignment
from app.models.character import Character
from app.models.enums import (
    CharacterCategory,
    GameEventType,
    GameMode,
    MatchStatus,
    RoomStatus,
)
from app.models.game_event import GameEvent
from app.models.match import Match
from app.models.player import Player
from app.models.question import Question
from app.models.room import Room
from app.models.team import Team

__all__ = [
    "Assignment",
    "Character",
    "CharacterCategory",
    "GameEvent",
    "GameEventType",
    "GameMode",
    "Match",
    "MatchStatus",
    "Player",
    "Question",
    "Room",
    "RoomStatus",
    "Team",
]
