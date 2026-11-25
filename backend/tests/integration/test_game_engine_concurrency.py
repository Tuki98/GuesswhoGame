"""Concurrency tests for the Phase 4 game-engine operations."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.database.base import Base
from app.database.session import Database
from app.models import GameEvent, Match, MatchStatus, Player, Question, Room, RoomStatus
from app.repositories.assignments import AssignmentRepository
from app.services.matches import GuessOutcome, MatchService
from tests.factories import make_character, make_player, make_room


def _setup_room(session: Session, *, player_count: int) -> tuple[Room, list[Player]]:
    """Create a room with a host, guests, and one contributed character each."""
    room = make_room(session, code=f"GTC-C{uuid.uuid4().hex[:6]}")
    players = [
        make_player(session, room, nickname=f"P{index}", is_host=index == 0)
        for index in range(player_count)
    ]
    for index, owner in enumerate(players):
        make_character(session, room, name=f"Char{index}", contributed_by=owner)
    session.commit()
    return room, players


def test_concurrent_match_starts_create_single_match(tmp_path: Path) -> None:
    """Two simultaneous start requests must produce exactly one match."""
    database = Database(f"sqlite:///{(tmp_path / 'game_conc_start.db').as_posix()}")
    Base.metadata.create_all(database.engine)

    room_id: uuid.UUID
    host_id: uuid.UUID
    with database.session() as session:
        room, players = _setup_room(session, player_count=3)
        room_id = room.id
        host_id = players[0].id

    barrier = threading.Barrier(2)
    outcomes: list[BaseException | None] = []
    lock = threading.Lock()

    def attempt_start() -> None:
        outcome: BaseException | None = None
        with database.session() as session:
            barrier.wait()
            player = session.get(Player, host_id)
            if player is not None:
                try:
                    MatchService(session).start_match(room_id, player)
                except Exception as exc:
                    outcome = exc
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt_start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)

    with database.session() as session:
        match_count = session.scalar(select(func.count()).select_from(Match))
        room_row = session.get(Room, room_id)
        room_status = room_row.status if room_row is not None else None

    succeeded = [outcome for outcome in outcomes if outcome is None]
    failed = [outcome for outcome in outcomes if outcome is not None]
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert isinstance(failed[0], ConflictError)
    assert match_count == 1
    assert room_status is RoomStatus.IN_PROGRESS
    database.dispose()


def test_concurrent_answers_for_one_question_accept_single_answer(tmp_path: Path) -> None:
    """Two simultaneous answers for one pending question: exactly one wins."""
    database = Database(f"sqlite:///{(tmp_path / 'game_conc_answer.db').as_posix()}")
    Base.metadata.create_all(database.engine)

    room_id: uuid.UUID
    recipient_id: uuid.UUID
    match_id: uuid.UUID
    question_id: uuid.UUID
    with database.session() as session:
        room, players = _setup_room(session, player_count=3)
        room_id = room.id
        recipient_id = players[1].id
        match_id = MatchService(session).start_match(room_id, players[0]).match.id
        question = MatchService(session).ask_question(
            match_id,
            players[0],
            content="Is it an anime?",
            recipient_player_id=recipient_id,
            recipient_team_id=None,
        )
        question_id = question.id

    barrier = threading.Barrier(2)
    outcomes: list[BaseException | None] = []
    lock = threading.Lock()

    def attempt_answer(content: str) -> None:
        outcome: BaseException | None = None
        with database.session() as session:
            barrier.wait()
            player = session.get(Player, recipient_id)
            if player is not None:
                try:
                    MatchService(session).answer_question(
                        match_id,
                        question_id,
                        player,
                        content=content,
                    )
                except Exception as exc:
                    outcome = exc
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=attempt_answer, args=("First answer",)),
        threading.Thread(target=attempt_answer, args=("Second answer",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)

    with database.session() as session:
        question_row = session.get(Question, question_id)
        match_row = session.get(Match, match_id)
        turn_index = match_row.turn_index if match_row is not None else None

    succeeded = [outcome for outcome in outcomes if outcome is None]
    failed = [outcome for outcome in outcomes if outcome is not None]
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert isinstance(failed[0], ConflictError)
    assert question_row is not None
    assert question_row.answer_content is not None
    assert turn_index == 1
    database.dispose()


def test_concurrent_correct_guesses_record_single_winner(tmp_path: Path) -> None:
    """Two simultaneous correct guesses must produce exactly one winner."""
    database = Database(f"sqlite:///{(tmp_path / 'game_conc_guess.db').as_posix()}")
    Base.metadata.create_all(database.engine)

    room_id: uuid.UUID
    host_id: uuid.UUID
    other_id: uuid.UUID
    match_id: uuid.UUID
    host_character_id: uuid.UUID
    other_character_id: uuid.UUID
    with database.session() as session:
        room, players = _setup_room(session, player_count=3)
        room_id = room.id
        host_id = players[0].id
        other_id = players[1].id
        match_id = MatchService(session).start_match(room_id, players[0]).match.id
        assignments = AssignmentRepository(session).list_by_match(match_id)
        assigned: dict[uuid.UUID, uuid.UUID] = {
            assignment.player_id: assignment.character_id  # type: ignore[misc]
            for assignment in assignments
            if assignment.player_id is not None
        }
        host_character_id = assigned[host_id]
        other_character_id = assigned[other_id]

    barrier = threading.Barrier(2)
    outcomes: list[GuessOutcome | BaseException | None] = []
    lock = threading.Lock()

    def attempt_guess(player_id: uuid.UUID, character_id: uuid.UUID) -> None:
        outcome: GuessOutcome | BaseException | None = None
        with database.session() as session:
            barrier.wait()
            player = session.get(Player, player_id)
            if player is None:
                outcome = ConflictError("player missing")
            else:
                try:
                    results = MatchService(session).submit_guess(
                        match_id,
                        player,
                        character_id=character_id,
                    )
                    outcome = results
                except Exception as exc:
                    outcome = exc
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=attempt_guess, args=(host_id, host_character_id)),
        threading.Thread(target=attempt_guess, args=(other_id, other_character_id)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)

    correct = [
        outcome for outcome in outcomes if isinstance(outcome, GuessOutcome) and outcome.correct
    ]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(correct) == 1
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], ConflictError)

    with database.session() as session:
        match_row = session.get(Match, match_id)
        events = session.scalars(
            select(GameEvent)
            .where(GameEvent.match_id == match_id)
            .order_by(GameEvent.sequence_number)
        ).all()

    assert match_row is not None
    assert match_row.status is MatchStatus.FINISHED
    assert match_row.winner_id is not None or match_row.winner_team_id is not None
    sequences = [event.sequence_number for event in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)
    database.dispose()
