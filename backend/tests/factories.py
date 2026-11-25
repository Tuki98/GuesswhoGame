"""Factory helpers for persistence tests."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.characters import character_uniqueness_keys
from app.core.nicknames import nickname_key
from app.core.security import hash_session_token
from app.database.base import utc_now
from app.models import (
    Assignment,
    Character,
    CharacterCategory,
    GameEvent,
    GameEventType,
    GameMode,
    Match,
    MatchStatus,
    Player,
    Room,
    Team,
)

TEST_SECRET = "test-secret-key-for-tests-only-0123456789"


def make_room(session: Session, *, code: str = "GTC-TEST") -> Room:
    room = Room(code=code)
    session.add(room)
    session.flush()
    return room


def make_player(
    session: Session,
    room: Room,
    *,
    nickname: str = "Alice",
    token: str | None = None,
    is_host: bool = False,
    expires_in_hours: int = 24,
) -> Player:
    now = utc_now()
    player = Player(
        room_id=room.id,
        nickname=nickname,
        nickname_key=nickname_key(nickname),
        session_token_hash=hash_session_token(
            token or f"token-{uuid.uuid4()}", secret_key=TEST_SECRET
        ),
        session_expires_at=now + timedelta(hours=expires_in_hours),
        joined_at=now,
        last_seen_at=now,
    )
    session.add(player)
    session.flush()
    if is_host:
        room.host_player_id = player.id
        session.flush()
    return player


def make_team(session: Session, room: Room, *, name: str = "Team Red") -> Team:
    team = Team(room_id=room.id, name=name)
    session.add(team)
    session.flush()
    return team


def make_character(
    session: Session,
    room: Room,
    *,
    name: str = "Naruto",
    franchise: str | None = "Naruto",
    category: CharacterCategory = CharacterCategory.ANIME,
    contributed_by: Player | None = None,
    attributes: dict[str, Any] | None = None,
) -> Character:
    name_key, franchise_key = character_uniqueness_keys(name, franchise)
    character = Character(
        room_id=room.id,
        name=name,
        name_key=name_key,
        franchise=franchise,
        franchise_key=franchise_key,
        category=category,
        image_path=f"characters/{uuid.uuid4()}.webp",
        attributes=attributes or {},
        contributed_by=contributed_by.id if contributed_by else None,
    )
    session.add(character)
    session.flush()
    return character


def make_match(
    session: Session,
    room: Room,
    *,
    mode: GameMode = GameMode.INDIVIDUAL,
    status: MatchStatus = MatchStatus.ACTIVE,
) -> Match:
    match = Match(
        room_id=room.id,
        mode=mode,
        status=status,
        started_at=utc_now() if status is not MatchStatus.PENDING else None,
    )
    session.add(match)
    session.flush()
    return match


def make_assignment(
    session: Session,
    match: Match,
    character: Character,
    *,
    player: Player | None = None,
    team: Team | None = None,
) -> Assignment:
    assignment = Assignment(
        match_id=match.id,
        character_id=character.id,
        player_id=player.id if player else None,
        team_id=team.id if team else None,
    )
    session.add(assignment)
    session.flush()
    return assignment


def make_event(
    session: Session,
    match: Match,
    *,
    event_type: GameEventType = GameEventType.GAME_STARTED,
    sequence_number: int = 1,
) -> GameEvent:
    event = GameEvent(
        match_id=match.id,
        event_type=event_type,
        sequence_number=sequence_number,
        payload={},
    )
    session.add(event)
    session.flush()
    return event
