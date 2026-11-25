"""Game-engine business logic: start, turns, questions, guesses, and events.

Transactions are intentionally short and every state change is paired with its
event row before ``commit``. SQLite serializes writers, so compare-and-swap
``UPDATE ... WHERE status = ...`` statements (not ``SELECT FOR UPDATE``) provide
the concurrency guarantees described in the Phase 4 report.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.matches import (
    AssignmentTarget,
    MatchAssignmentError,
    MatchValidationError,
    normalize_answer_content,
    normalize_question_content,
    secure_assign,
)
from app.core.room_config import RoomConfig
from app.database.base import utc_now
from app.models import (
    Assignment,
    Character,
    GameEvent,
    GameEventType,
    GameMode,
    Match,
    MatchStatus,
    Player,
    Question,
    Room,
    RoomStatus,
    Team,
)
from app.repositories.assignments import AssignmentRepository
from app.repositories.characters import CharacterRepository
from app.repositories.game_events import GameEventRepository
from app.repositories.matches import MatchRepository
from app.repositories.players import PlayerRepository
from app.repositories.questions import QuestionRepository
from app.repositories.rooms import RoomRepository
from app.repositories.teams import TeamRepository
from app.services.match_state import (
    MatchDetailsView,
    MatchInfo,
    MatchStateService,
    MatchStateView,
    active_owner_id,
)
from app.services.permissions import ensure_room_host, ensure_room_member
from app.services.teams import TeamView


@dataclass(frozen=True, slots=True)
class GuessOutcome:
    correct: bool
    match: MatchInfo


@dataclass(frozen=True, slots=True)
class MatchHistoryPage:
    events: tuple[GameEvent, ...]
    has_more: bool
    next_after_sequence: int | None


class MatchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.rooms = RoomRepository(session)
        self.players = PlayerRepository(session)
        self.teams = TeamRepository(session)
        self.characters = CharacterRepository(session)
        self.matches = MatchRepository(session)
        self.assignments = AssignmentRepository(session)
        self.questions = QuestionRepository(session)
        self.events = GameEventRepository(session)
        self.state_service = MatchStateService(session)

    # -- lifecycle ------------------------------------------------------------

    def start_match(self, room_id: uuid.UUID, player: Player) -> MatchStateView:
        room = self._member_room(room_id, player)
        ensure_room_host(room, player)
        if room.status is not RoomStatus.WAITING:
            raise ConflictError("A match can only be started while the room is waiting.")

        configuration = self._configuration(room)
        try:
            # The transition is the lock: a concurrent start cannot also move
            # the room out of ``waiting`` and then create assignments.
            if not self.rooms.transition_status(
                room.id,
                expected=RoomStatus.WAITING,
                new=RoomStatus.IN_PROGRESS,
            ):
                raise ConflictError("A match can only be started while the room is waiting.")
            if self.matches.active_for_room(room.id) is not None:
                raise ConflictError("This room already has an active match.")

            players = self.players.list_by_room(room.id)
            characters = self.characters.list_by_room(room.id)
            teams = self.teams.list_by_room(room.id)
            targets, turn_order = self._prepare_assignment(
                configuration,
                players,
                characters,
                teams,
            )
            assigned = secure_assign(targets, characters)
            now = utc_now()
            match = Match(
                room_id=room.id,
                mode=configuration.game_mode,
                status=MatchStatus.ACTIVE,
                turn_index=0,
                event_sequence=2,
                configuration={
                    "turn_order": [str(owner_id) for owner_id in turn_order],
                    "turn_kind": "team" if configuration.game_mode is GameMode.TEAM else "player",
                },
                started_at=now,
            )
            self.session.add(match)
            self.session.flush()

            for owner_id, character in assigned.items():
                if configuration.game_mode is GameMode.TEAM:
                    self.session.add(
                        Assignment(
                            match_id=match.id,
                            character_id=character.id,
                            team_id=owner_id,
                        )
                    )
                else:
                    self.session.add(
                        Assignment(
                            match_id=match.id,
                            character_id=character.id,
                            player_id=owner_id,
                        )
                    )

            self.session.add_all(
                [
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.MATCH_CREATED,
                        payload={
                            "mode": configuration.game_mode.value,
                            "participant_count": len(targets),
                        },
                        sequence_number=1,
                    ),
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.MATCH_STARTED,
                        payload={
                            "mode": configuration.game_mode.value,
                            "participant_count": len(targets),
                            "turn_order": [str(owner_id) for owner_id in turn_order],
                        },
                        sequence_number=2,
                    ),
                ]
            )
            self.session.commit()
        except (ConflictError, DomainValidationError):
            self.session.rollback()
            raise
        except MatchAssignmentError as exc:
            self.session.rollback()
            raise ConflictError("The characters could not be assigned to the players.") from exc
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("The match could not be started.") from exc
        except Exception:
            self.session.rollback()
            raise

        return self.state_service.state(match, player)

    def cancel_match(self, match_id: uuid.UUID, player: Player) -> Match:
        match = self._load_match(match_id, player)
        room = self._room(match)
        ensure_room_host(room, player)
        if match.status not in (MatchStatus.PENDING, MatchStatus.ACTIVE):
            raise ConflictError("Only a pending or active match can be cancelled.")

        try:
            if not abandon_match(
                self.session,
                match,
                actor_player_id=player.id,
                reason="host_cancelled",
            ):
                raise ConflictError("The match is no longer cancellable.")
            self.rooms.transition_status(
                room.id,
                expected=RoomStatus.IN_PROGRESS,
                new=RoomStatus.WAITING,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(match)
        return match

    # -- reads ----------------------------------------------------------------

    def get_details(self, match_id: uuid.UUID, player: Player) -> MatchDetailsView:
        match = self._load_match(match_id, player)
        return self.state_service.details(match, player)

    def get_state(self, match_id: uuid.UUID, player: Player) -> MatchStateView:
        match = self._load_match(match_id, player)
        self._require_participant(match, player)
        return self.state_service.state(match, player)

    def get_history(
        self,
        match_id: uuid.UUID,
        player: Player,
        *,
        limit: int = 50,
        after_sequence: int | None = None,
    ) -> MatchHistoryPage:
        self._load_match(match_id, player)
        rows = self.events.list_page(
            match_id,
            limit=limit,
            after_sequence=after_sequence,
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        next_after = page[-1].sequence_number if has_more and page else None
        return MatchHistoryPage(
            events=tuple(page),
            has_more=has_more,
            next_after_sequence=next_after,
        )

    # -- questions and answers ------------------------------------------------

    def ask_question(
        self,
        match_id: uuid.UUID,
        player: Player,
        *,
        content: str,
        recipient_player_id: uuid.UUID | None,
        recipient_team_id: uuid.UUID | None,
    ) -> Question:
        try:
            normalized = normalize_question_content(content)
        except MatchValidationError as exc:
            raise DomainValidationError(str(exc)) from exc

        match = self._load_match(match_id, player)
        if match.status is not MatchStatus.ACTIVE:
            raise ConflictError("Questions can only be asked in an active match.")
        owner_id, owner_kind, _ = self._require_participant(match, player)

        if active_owner_id(match) != owner_id:
            raise PermissionDeniedError("It is not your turn to ask a question.")

        recipient = self._validate_recipient(
            match,
            player,
            owner_id=owner_id,
            owner_kind=owner_kind,
            recipient_player_id=recipient_player_id,
            recipient_team_id=recipient_team_id,
        )
        if self.questions.get_pending(match.id) is not None:
            raise ConflictError("There is already an unanswered question in this match.")

        try:
            sequence = self.matches.allocate_event_sequence(
                match.id,
                require_status=MatchStatus.ACTIVE,
            )
            if sequence is None:
                raise ConflictError("The match is no longer active.")

            question = Question(
                match_id=match.id,
                author_player_id=player.id,
                recipient_player_id=recipient.player_id,
                recipient_team_id=recipient.team_id,
                content=normalized,
                pending_match_id=match.id,
            )
            self.session.add(question)
            self.session.flush()
            self.session.add(
                GameEvent(
                    match_id=match.id,
                    actor_player_id=player.id,
                    event_type=GameEventType.QUESTION_SENT,
                    payload={
                        "question_id": str(question.id),
                        "recipient_player_id": (
                            str(recipient.player_id) if recipient.player_id else None
                        ),
                        "recipient_team_id": (
                            str(recipient.team_id) if recipient.team_id else None
                        ),
                        "content": normalized,
                    },
                    sequence_number=sequence,
                )
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("There is already an unanswered question in this match.") from exc
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(question)
        return question

    def answer_question(
        self,
        match_id: uuid.UUID,
        question_id: uuid.UUID,
        player: Player,
        *,
        content: str,
    ) -> Question:
        try:
            normalized = normalize_answer_content(content)
        except MatchValidationError as exc:
            raise DomainValidationError(str(exc)) from exc

        match = self._load_match(match_id, player)
        if match.status is not MatchStatus.ACTIVE:
            raise ConflictError("Questions can only be answered in an active match.")
        owner_id, owner_kind, _ = self._require_participant(match, player)

        question = self.questions.get(question_id)
        if question is None or question.match_id != match.id:
            raise NotFoundError("Question not found.")
        if question.pending_match_id != match.id or question.answer_content is not None:
            raise ConflictError("This question has already been answered.")

        authorized = (owner_kind == "player" and question.recipient_player_id == owner_id) or (
            owner_kind == "team" and question.recipient_team_id == owner_id
        )
        if not authorized:
            raise PermissionDeniedError("Only the designated recipient can answer this question.")

        try:
            sequence = self.matches.allocate_event_sequence(
                match.id,
                require_status=MatchStatus.ACTIVE,
            )
            if sequence is None:
                raise ConflictError("The match is no longer active.")

            if not self.questions.mark_answered(
                question.id,
                match.id,
                answer_content=normalized,
                answer_author_player_id=player.id,
                answered_at=utc_now(),
            ):
                raise ConflictError("This question has already been answered.")
            if not self.matches.advance_turn(match.id):
                raise ConflictError("The match is no longer active.")

            self.session.add(
                GameEvent(
                    match_id=match.id,
                    actor_player_id=player.id,
                    event_type=GameEventType.ANSWER_SENT,
                    payload={
                        "question_id": str(question.id),
                        "answer": normalized,
                    },
                    sequence_number=sequence,
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(question)
        return question

    # -- guessing -------------------------------------------------------------

    def submit_guess(
        self,
        match_id: uuid.UUID,
        player: Player,
        *,
        character_id: uuid.UUID,
    ) -> GuessOutcome:
        match = self._load_match(match_id, player)
        if match.status is not MatchStatus.ACTIVE:
            raise ConflictError("Guesses can only be submitted in an active match.")
        owner_id, owner_kind, _ = self._require_participant(match, player)
        self_assignment = self._assignment_for(match, owner_id, owner_kind)
        if self_assignment is None:  # pragma: no cover - participant check guarantees it
            raise PermissionDeniedError("You are not participating in this match.")

        character = self.characters.get(character_id)
        if character is None or character.room_id != match.room_id:
            raise NotFoundError("Character not found.")

        correct = self_assignment.character_id == character.id
        if not correct:
            self._record_incorrect_guess(match, player, character)
        else:
            self._record_correct_guess(match, player, owner_id, owner_kind)

        # Serialize through the state service so guess responses always carry
        # accurate match information instead of ORM placeholders.
        return GuessOutcome(correct=correct, match=self.state_service.state(match, player).match)

    def _record_incorrect_guess(
        self,
        match: Match,
        player: Player,
        character: Character,
    ) -> None:
        try:
            sequence = self.matches.allocate_event_sequence(
                match.id,
                count=2,
                require_status=MatchStatus.ACTIVE,
            )
            if sequence is None:
                raise ConflictError("The match is no longer active.")

            payload: dict[str, Any] = {
                "character_id": str(character.id),
                "guesser_player_id": str(player.id),
                "correct": False,
            }
            self.session.add_all(
                [
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.GUESS_SUBMITTED,
                        payload=payload,
                        sequence_number=sequence - 1,
                    ),
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.GUESS_INCORRECT,
                        payload=payload,
                        sequence_number=sequence,
                    ),
                ]
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _record_correct_guess(
        self,
        match: Match,
        player: Player,
        owner_id: uuid.UUID,
        owner_kind: str,
    ) -> None:
        winner_player_id = player.id if owner_kind == "player" else None
        winner_team_id = owner_id if owner_kind == "team" else None
        try:
            sequence = self.matches.finish_with_winner(
                match.id,
                winner_player_id=winner_player_id,
                winner_team_id=winner_team_id,
                finished_at=utc_now(),
                event_count=3,
            )
            if sequence is None:
                raise ConflictError("The match has already finished.")

            self.rooms.transition_status(
                match.room_id,
                expected=RoomStatus.IN_PROGRESS,
                new=RoomStatus.WAITING,
            )
            winner_fields = {
                "winner_player_id": (str(winner_player_id) if winner_player_id else None),
                "winner_team_id": str(winner_team_id) if winner_team_id else None,
            }
            self.session.add_all(
                [
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.GUESS_SUBMITTED,
                        # Deliberately omit the guessed character: for a correct
                        # guess it is the winner's own secret identity.
                        payload={
                            "guesser_player_id": str(player.id),
                            "guesser_team_id": (str(owner_id) if owner_kind == "team" else None),
                            "correct": True,
                        },
                        sequence_number=sequence - 2,
                    ),
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.GUESS_CORRECT,
                        payload=winner_fields,
                        sequence_number=sequence - 1,
                    ),
                    GameEvent(
                        match_id=match.id,
                        actor_player_id=player.id,
                        event_type=GameEventType.MATCH_FINISHED,
                        payload={**winner_fields, "reason": "correct_guess"},
                        sequence_number=sequence,
                    ),
                ]
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(match)

    # -- start helpers --------------------------------------------------------

    def _prepare_assignment(
        self,
        configuration: RoomConfig,
        players: list[Player],
        characters: list[Character],
        teams: list[Team],
    ) -> tuple[list[AssignmentTarget], list[uuid.UUID]]:
        if configuration.game_mode is GameMode.TEAM:
            return self._prepare_team_assignment(players, characters, teams)

        if len(players) < 2:
            raise ConflictError("At least two players are required to start a match.")
        if len(characters) < len(players):
            raise ConflictError(
                "The room needs at least as many characters as players before starting."
            )

        targets = [
            AssignmentTarget(
                owner_id=player.id,
                forbidden_character_ids=frozenset(
                    character.id
                    for character in characters
                    if character.contributed_by == player.id
                ),
            )
            for player in players
        ]
        return targets, [player.id for player in players]

    def _prepare_team_assignment(
        self,
        players: list[Player],
        characters: list[Character],
        teams: list[Team],
    ) -> tuple[list[AssignmentTarget], list[uuid.UUID]]:
        if len(teams) < 2:
            raise ConflictError("Team mode requires at least two teams.")
        if len(characters) < len(teams):
            raise ConflictError(
                "The room needs at least as many characters as teams before starting."
            )

        team_ids = {team.id for team in teams}
        if any(member.team_id is None for member in players):
            raise ConflictError("Every player must join a team before the match can start.")
        if any(member.team_id not in team_ids for member in players):
            raise ConflictError("Every player must belong to a team in this room.")

        members_by_team: dict[uuid.UUID, list[uuid.UUID]] = {team.id: [] for team in teams}
        for member in players:
            assert member.team_id is not None
            members_by_team[member.team_id].append(member.id)

        if any(not member_ids for member_ids in members_by_team.values()):
            raise ConflictError("Every team must have at least one player before starting.")

        targets = [
            AssignmentTarget(
                owner_id=team.id,
                forbidden_character_ids=frozenset(
                    character.id
                    for character in characters
                    if character.contributed_by in members_by_team[team.id]
                ),
            )
            for team in teams
        ]
        return targets, [team.id for team in teams]

    # -- validation helpers ---------------------------------------------------

    def _validate_recipient(
        self,
        match: Match,
        player: Player,
        *,
        owner_id: uuid.UUID,
        owner_kind: str,
        recipient_player_id: uuid.UUID | None,
        recipient_team_id: uuid.UUID | None,
    ) -> _Recipient:
        if match.mode is GameMode.TEAM:
            if recipient_player_id is not None or recipient_team_id is None:
                raise DomainValidationError("Choose an opposing team as the recipient.")
            if recipient_team_id == owner_id:
                raise DomainValidationError("A team cannot ask itself a question.")
            assignment = self.assignments.get_for_team(match.id, recipient_team_id)
            if assignment is None:
                raise DomainValidationError("The recipient is not participating in this match.")
            return _Recipient(team_id=recipient_team_id)

        if recipient_team_id is not None or recipient_player_id is None:
            raise DomainValidationError("Choose another player as the recipient.")
        if recipient_player_id == player.id:
            raise DomainValidationError("A player cannot ask themselves a question.")
        assignment = self.assignments.get_for_player(match.id, recipient_player_id)
        if assignment is None:
            raise DomainValidationError("The recipient is not participating in this match.")
        return _Recipient(player_id=recipient_player_id)

    def _require_participant(
        self,
        match: Match,
        player: Player,
    ) -> tuple[uuid.UUID, str, Assignment]:
        if match.mode is GameMode.TEAM:
            if player.team_id is None:
                raise PermissionDeniedError("You are not participating in this match.")
            assignment = self.assignments.get_for_team(match.id, player.team_id)
            if assignment is None:
                raise PermissionDeniedError("You are not participating in this match.")
            return player.team_id, "team", assignment

        assignment = self.assignments.get_for_player(match.id, player.id)
        if assignment is None:
            raise PermissionDeniedError("You are not participating in this match.")
        return player.id, "player", assignment

    def _assignment_for(
        self,
        match: Match,
        owner_id: uuid.UUID,
        owner_kind: str,
    ) -> Assignment | None:
        if owner_kind == "team":
            return self.assignments.get_for_team(match.id, owner_id)
        return self.assignments.get_for_player(match.id, owner_id)

    def _load_match(self, match_id: uuid.UUID, player: Player) -> Match:
        match = self.matches.get(match_id)
        if match is None or match.room_id != player.room_id:
            raise NotFoundError("Match not found.")
        return match

    def _member_room(self, room_id: uuid.UUID, player: Player) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found.")
        ensure_room_member(room, player)
        return room

    def _room(self, match: Match) -> Room:
        room = self.rooms.get(match.room_id)
        if room is None:  # pragma: no cover - database invariant
            raise NotFoundError("Room not found.")
        return room

    @staticmethod
    def _configuration(room: Room) -> RoomConfig:
        try:
            return RoomConfig.model_validate(room.configuration or {})
        except Exception as exc:  # pragma: no cover - configuration is validated on write
            raise ConflictError("The room configuration is invalid.") from exc


@dataclass(frozen=True, slots=True)
class _Recipient:
    player_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


def abandon_match(
    session: Session,
    match: Match,
    *,
    actor_player_id: uuid.UUID,
    reason: str,
) -> bool:
    """Cancel a pending/active match and append its event in the caller's transaction."""
    sequence = MatchRepository(session).cancel_if_open(match.id, finished_at=utc_now())
    if sequence is None:
        return False
    session.add(
        GameEvent(
            match_id=match.id,
            actor_player_id=actor_player_id,
            event_type=GameEventType.MATCH_CANCELLED,
            payload={
                "reason": reason,
                "cancelled_by_player_id": str(actor_player_id),
            },
            sequence_number=sequence,
        )
    )
    session.refresh(match)
    return True


def abandon_active_match(
    session: Session,
    room: Room,
    *,
    actor_player_id: uuid.UUID,
    reason: str,
) -> Match | None:
    """Abandon whichever match is currently open for a room, if any."""
    match = MatchRepository(session).active_for_room(room.id)
    if match is None:
        return None
    return (
        match
        if abandon_match(
            session,
            match,
            actor_player_id=actor_player_id,
            reason=reason,
        )
        else None
    )


# ``TeamView`` is re-exported for the team API mapper and keeps the service
# module's public surface explicit.
__all__ = [
    "GuessOutcome",
    "MatchHistoryPage",
    "MatchService",
    "TeamView",
    "abandon_active_match",
    "abandon_match",
]
