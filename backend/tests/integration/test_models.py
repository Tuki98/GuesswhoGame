"""Tests for persistence models, constraints, and cascade behaviour."""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_session_token
from app.database.base import utc_now
from app.models import (
    Assignment,
    GameEvent,
    GameEventType,
    GameMode,
    Match,
    MatchStatus,
    Player,
    Room,
)
from tests.factories import (
    TEST_SECRET,
    make_assignment,
    make_character,
    make_event,
    make_match,
    make_player,
    make_room,
    make_team,
)


def test_room_player_round_trip_preserves_utc_timestamps(db_session: Session) -> None:
    room = make_room(db_session, code="GTC-ROOM")
    player = make_player(db_session, room, nickname="Alice", is_host=True)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(Player, player.id)

    assert stored is not None
    assert stored.room.code == "GTC-ROOM"
    assert stored.room.host is not None
    assert stored.room.host.id == player.id
    assert stored.joined_at.tzinfo is UTC
    assert stored.last_seen_at.tzinfo is UTC


def test_room_code_is_globally_unique(db_session: Session) -> None:
    make_room(db_session, code="GTC-DUP")

    with pytest.raises(IntegrityError):
        make_room(db_session, code="GTC-DUP")

    db_session.rollback()


def test_nickname_is_unique_only_within_a_room(db_session: Session) -> None:
    first_room = make_room(db_session, code="GTC-A")
    second_room = make_room(db_session, code="GTC-B")
    make_player(db_session, first_room, nickname="Alice")
    make_player(db_session, second_room, nickname="Alice")

    with pytest.raises(IntegrityError):
        make_player(db_session, first_room, nickname="Alice")

    db_session.rollback()


def test_nickname_key_is_unique_case_insensitively_within_a_room(
    db_session: Session,
) -> None:
    room = make_room(db_session)
    make_player(db_session, room, nickname="Alice")

    with pytest.raises(IntegrityError):
        make_player(db_session, room, nickname="ALICE")

    db_session.rollback()


def test_case_variant_nicknames_are_allowed_in_different_rooms(
    db_session: Session,
) -> None:
    first_room = make_room(db_session, code="GTC-A")
    second_room = make_room(db_session, code="GTC-B")
    make_player(db_session, first_room, nickname="Alice")
    make_player(db_session, second_room, nickname="ALICE")
    db_session.commit()

    assert db_session.query(Player).count() == 2


def test_session_token_hash_is_unique_across_players(db_session: Session) -> None:
    first_room = make_room(db_session, code="GTC-A")
    second_room = make_room(db_session, code="GTC-B")
    shared_token = "same-token"
    make_player(db_session, first_room, nickname="Alice", token=shared_token)

    with pytest.raises(IntegrityError):
        make_player(db_session, second_room, nickname="Bob", token=shared_token)

    db_session.rollback()


def test_player_requires_existing_room(db_session: Session) -> None:
    player = Player(
        room_id=uuid.uuid4(),
        nickname="Ghost",
        nickname_key="ghost",
        session_token_hash=hash_session_token("token", secret_key=TEST_SECRET),
        session_expires_at=utc_now(),
    )
    db_session.add(player)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_room_configuration_changes_are_tracked(db_session: Session) -> None:
    room = make_room(db_session)
    room.configuration["max_players"] = 8
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(Room, room.id)

    assert stored is not None
    assert stored.configuration == {"max_players": 8}


def test_character_attributes_changes_are_tracked(db_session: Session) -> None:
    room = make_room(db_session)
    character = make_character(db_session, room, attributes={"hair": "blonde"})
    character.attributes["hair"] = "black"
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(type(character), character.id)

    assert stored is not None
    assert stored.attributes == {"hair": "black"}


def test_assignment_requires_exactly_one_owner(db_session: Session) -> None:
    room = make_room(db_session)
    character = make_character(db_session, room)
    match = make_match(db_session, room)

    with pytest.raises(IntegrityError):
        make_assignment(db_session, match, character)

    db_session.rollback()


def test_assignment_rejects_both_owners(db_session: Session) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room)
    team = make_team(db_session, room)
    character = make_character(db_session, room)
    match = make_match(db_session, room, mode=GameMode.TEAM)

    with pytest.raises(IntegrityError):
        make_assignment(db_session, match, character, player=player, team=team)

    db_session.rollback()


def test_character_cannot_be_assigned_twice_in_a_match(db_session: Session) -> None:
    room = make_room(db_session)
    first_player = make_player(db_session, room, nickname="Alice")
    second_player = make_player(db_session, room, nickname="Bob")
    character = make_character(db_session, room)
    match = make_match(db_session, room)
    make_assignment(db_session, match, character, player=first_player)

    with pytest.raises(IntegrityError):
        make_assignment(db_session, match, character, player=second_player)

    db_session.rollback()


def test_player_cannot_receive_two_characters_in_a_match(db_session: Session) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room)
    first_character = make_character(db_session, room, name="Naruto")
    second_character = make_character(db_session, room, name="Goku")
    match = make_match(db_session, room)
    make_assignment(db_session, match, first_character, player=player)

    with pytest.raises(IntegrityError):
        make_assignment(db_session, match, second_character, player=player)

    db_session.rollback()


def test_team_cannot_receive_two_characters_in_a_match(db_session: Session) -> None:
    room = make_room(db_session)
    team = make_team(db_session, room)
    first_character = make_character(db_session, room, name="Naruto")
    second_character = make_character(db_session, room, name="Goku")
    match = make_match(db_session, room, mode=GameMode.TEAM)
    make_assignment(db_session, match, first_character, team=team)

    with pytest.raises(IntegrityError):
        make_assignment(db_session, match, second_character, team=team)

    db_session.rollback()


def test_match_can_assign_one_character_per_player_and_team(db_session: Session) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room)
    team = make_team(db_session, room)
    player_character = make_character(db_session, room, name="Naruto")
    team_character = make_character(db_session, room, name="Goku")
    match = make_match(db_session, room, mode=GameMode.TEAM)

    make_assignment(db_session, match, player_character, player=player)
    make_assignment(db_session, match, team_character, team=team)
    db_session.commit()

    assert db_session.query(Assignment).filter_by(match_id=match.id).count() == 2


def test_match_rejects_two_winners(db_session: Session) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room)
    team = make_team(db_session, room)
    match = make_match(db_session, room, mode=GameMode.TEAM)
    match.winner_id = player.id
    match.winner_team_id = team.id

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_match_rejects_negative_turn_index(db_session: Session) -> None:
    room = make_room(db_session)
    match = make_match(db_session, room)
    match.turn_index = -1

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_event_sequence_is_unique_per_match(db_session: Session) -> None:
    room = make_room(db_session)
    match = make_match(db_session, room)
    make_event(db_session, match, sequence_number=1)

    with pytest.raises(IntegrityError):
        make_event(db_session, match, sequence_number=1)

    db_session.rollback()


def test_event_sequence_must_be_positive(db_session: Session) -> None:
    room = make_room(db_session)
    match = make_match(db_session, room)

    with pytest.raises(IntegrityError):
        make_event(db_session, match, sequence_number=0)

    db_session.rollback()


def test_event_sequences_are_independent_between_matches(db_session: Session) -> None:
    room = make_room(db_session)
    first_match = make_match(db_session, room)
    second_match = make_match(db_session, room)

    make_event(db_session, first_match, sequence_number=1)
    make_event(db_session, second_match, sequence_number=1)
    db_session.commit()

    assert db_session.query(GameEvent).filter_by(sequence_number=1).count() == 2


def test_room_deletion_cascades_to_owned_rows(db_session: Session) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)
    character = make_character(db_session, room, contributed_by=player)
    match = make_match(db_session, room)
    make_assignment(db_session, match, character, player=player)
    make_event(db_session, match)
    db_session.commit()

    db_session.delete(room)
    db_session.commit()

    assert db_session.query(Room).count() == 0
    assert db_session.query(Player).count() == 0
    assert db_session.query(type(character)).count() == 0
    assert db_session.query(Match).count() == 0
    assert db_session.query(Assignment).count() == 0
    assert db_session.query(GameEvent).count() == 0


def test_assigned_character_cannot_be_deleted(db_session: Session) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room)
    character = make_character(db_session, room)
    match = make_match(db_session, room)
    make_assignment(db_session, match, character, player=player)
    db_session.commit()

    db_session.delete(character)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_match_defaults_and_enums(db_session: Session) -> None:
    room = make_room(db_session)
    match = make_match(db_session, room, status=MatchStatus.PENDING)

    assert match.mode is GameMode.INDIVIDUAL
    assert match.status is MatchStatus.PENDING
    assert match.turn_index == 0
    assert match.configuration == {}
    assert match.started_at is None


def test_game_event_accepts_known_event_type(db_session: Session) -> None:
    room = make_room(db_session)
    match = make_match(db_session, room)
    event = make_event(db_session, match, event_type=GameEventType.GUESS_INCORRECT)
    db_session.commit()

    assert event.event_type is GameEventType.GUESS_INCORRECT
