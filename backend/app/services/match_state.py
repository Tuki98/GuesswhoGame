"""Player-specific match serialization.

Only this module decides what a participant may see. It never copies the
authenticated participant's own assignment into any visible collection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.matches import match_phase
from app.models import (
    Assignment,
    CharacterCategory,
    GameMode,
    Match,
    MatchStatus,
    Player,
    Question,
    Room,
    Team,
)
from app.repositories.assignments import AssignmentRepository
from app.repositories.players import PlayerRepository
from app.repositories.questions import QuestionRepository
from app.repositories.rooms import RoomRepository
from app.repositories.teams import TeamRepository

OwnerKind = Literal["player", "team"]


@dataclass(frozen=True, slots=True)
class CharacterSnapshot:
    id: uuid.UUID
    name: str
    franchise: str | None
    category: CharacterCategory
    image_path: str
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MatchParticipant:
    id: uuid.UUID
    name: str
    kind: OwnerKind
    is_connected: bool
    member_player_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class MatchInfo:
    id: uuid.UUID
    room_id: uuid.UUID
    mode: GameMode
    status: MatchStatus
    phase: str
    turn_index: int
    current_turn_id: uuid.UUID | None
    current_turn_kind: OwnerKind
    current_turn_name: str | None
    participant_count: int
    started_at: datetime | None
    finished_at: datetime | None
    winner_player_id: uuid.UUID | None
    winner_team_id: uuid.UUID | None
    winner_name: str | None


@dataclass(frozen=True, slots=True)
class VisibleCharacter:
    owner_id: uuid.UUID
    owner_kind: OwnerKind
    owner_name: str
    character: CharacterSnapshot


@dataclass(frozen=True, slots=True)
class AnswerView:
    content: str
    author_player_id: uuid.UUID | None
    author_nickname: str | None
    answered_at: datetime


@dataclass(frozen=True, slots=True)
class QuestionView:
    id: uuid.UUID
    author_player_id: uuid.UUID | None
    author_nickname: str | None
    recipient_player_id: uuid.UUID | None
    recipient_team_id: uuid.UUID | None
    recipient_name: str | None
    content: str
    asked_at: datetime
    answer: AnswerView | None
    can_answer: bool


@dataclass(frozen=True, slots=True)
class MatchSelfView:
    player_id: uuid.UUID
    nickname: str
    team_id: uuid.UUID | None
    team_name: str | None
    is_your_turn: bool
    can_ask: bool


@dataclass(frozen=True, slots=True)
class MatchDetailsView:
    match: MatchInfo
    participants: tuple[MatchParticipant, ...]


@dataclass(frozen=True, slots=True)
class MatchStateView:
    match: MatchInfo
    self_view: MatchSelfView
    identity_assigned: bool
    identity_revealed: bool
    opponents: tuple[VisibleCharacter, ...]
    participants: tuple[MatchParticipant, ...]
    pending_question: QuestionView | None
    question_history: tuple[QuestionView, ...]
    allowed_recipient_ids: tuple[uuid.UUID, ...]


def turn_order(match: Match) -> list[uuid.UUID]:
    raw = match.configuration.get("turn_order", [])
    if not isinstance(raw, list):
        return []
    order: list[uuid.UUID] = []
    for value in raw:
        try:
            order.append(uuid.UUID(str(value)))
        except ValueError:
            continue
    return order


def turn_kind(match: Match) -> OwnerKind:
    configured = match.configuration.get("turn_kind")
    if configured == "team":
        return "team"
    if configured == "player":
        return "player"
    return "team" if match.mode is GameMode.TEAM else "player"


def active_owner_id(match: Match) -> uuid.UUID | None:
    order = turn_order(match)
    if not order:
        return None
    return order[match.turn_index % len(order)]


class MatchStateService:
    """Build read models without ever returning ORM assignments."""

    def __init__(self, session: Session) -> None:
        self.rooms = RoomRepository(session)
        self.players = PlayerRepository(session)
        self.teams = TeamRepository(session)
        self.assignments = AssignmentRepository(session)
        self.questions = QuestionRepository(session)

    def details(self, match: Match, player: Player) -> MatchDetailsView:
        room = self._room(match)
        context = self._context(match, room)
        info = self._info(match, context)
        return MatchDetailsView(match=info, participants=context.participants)

    def state(self, match: Match, player: Player) -> MatchStateView:
        room = self._room(match)
        context = self._context(match, room)
        info = self._info(match, context)

        own_owner_id, own_kind, own_team_id = self._own_owner(match, player)
        pending = (
            self.questions.get_pending(match.id) if match.status is MatchStatus.ACTIVE else None
        )

        is_active = match.status is MatchStatus.ACTIVE
        is_your_turn = is_active and info.current_turn_id == own_owner_id
        can_ask = is_your_turn and pending is None

        opponents = tuple(
            visible
            for visible in context.visible
            if not (visible.owner_id == own_owner_id and visible.owner_kind == own_kind)
        )

        can_answer = (
            is_active
            and pending is not None
            and (
                (own_kind == "player" and pending.recipient_player_id == own_owner_id)
                or (own_kind == "team" and pending.recipient_team_id == own_team_id)
            )
        )

        allowed_recipients: tuple[uuid.UUID, ...] = ()
        if can_ask:
            allowed_recipients = tuple(
                participant.id
                for participant in context.participants
                if not (participant.id == own_owner_id and participant.kind == own_kind)
            )

        history = tuple(
            self._question_view(question, can_answer=False, names=context.names)
            for question in self.questions.list_by_match(match.id)
            if question.answer_content is not None and question.answered_at is not None
        )

        team = context.teams_by_id.get(own_team_id) if own_team_id else None
        self_view = MatchSelfView(
            player_id=player.id,
            nickname=player.nickname,
            team_id=own_team_id,
            team_name=team.name if team else None,
            is_your_turn=is_your_turn,
            can_ask=can_ask,
        )

        return MatchStateView(
            match=info,
            self_view=self_view,
            identity_assigned=True,
            identity_revealed=False,
            opponents=opponents,
            participants=context.participants,
            pending_question=(
                self._question_view(pending, can_answer=can_answer, names=context.names)
                if pending is not None
                else None
            ),
            question_history=history,
            allowed_recipient_ids=allowed_recipients,
        )

    # -- context --------------------------------------------------------------

    def _context(self, match: Match, room: Room) -> _MatchContext:
        assignments = self.assignments.list_by_match(match.id)
        players = self.players.list_by_room(room.id)
        teams = self.teams.list_by_room(room.id)
        players_by_id = {player.id: player for player in players}
        teams_by_id = {team.id: team for team in teams}
        names: dict[uuid.UUID, str] = {player.id: player.nickname for player in players} | {
            team.id: team.name for team in teams
        }

        participants: list[MatchParticipant] = []
        visible: list[VisibleCharacter] = []
        kind = turn_kind(match)

        if kind == "player":
            ordered_ids = [
                owner_id
                for owner_id in turn_order(match)
                if any(assignment.player_id == owner_id for assignment in assignments)
            ]
            for assignment in assignments:
                if assignment.player_id is None or assignment.player_id in ordered_ids:
                    continue
                ordered_ids.append(assignment.player_id)
            for owner_id in ordered_ids:
                owner = players_by_id.get(owner_id)
                if owner is None:
                    continue
                assignment = next(item for item in assignments if item.player_id == owner_id)
                participants.append(
                    MatchParticipant(
                        id=owner.id,
                        name=owner.nickname,
                        kind="player",
                        is_connected=owner.is_connected,
                        member_player_ids=(owner.id,),
                    )
                )
                visible.append(self._visible(owner.id, "player", owner.nickname, assignment))
        else:
            member_map: dict[uuid.UUID, list[Player]] = {}
            for member in players:
                if member.team_id is not None:
                    member_map.setdefault(member.team_id, []).append(member)

            ordered_team_ids = [
                owner_id
                for owner_id in turn_order(match)
                if any(assignment.team_id == owner_id for assignment in assignments)
            ]
            for assignment in assignments:
                if assignment.team_id is None or assignment.team_id in ordered_team_ids:
                    continue
                ordered_team_ids.append(assignment.team_id)

            for owner_id in ordered_team_ids:
                team = teams_by_id.get(owner_id)
                if team is None:
                    continue
                assignment = next(item for item in assignments if item.team_id == owner_id)
                members = member_map.get(team.id, [])
                participants.append(
                    MatchParticipant(
                        id=team.id,
                        name=team.name,
                        kind="team",
                        is_connected=any(member.is_connected for member in members),
                        member_player_ids=tuple(member.id for member in members),
                    )
                )
                visible.append(self._visible(team.id, "team", team.name, assignment))

        return _MatchContext(
            players_by_id=players_by_id,
            teams_by_id=teams_by_id,
            participants=tuple(participants),
            visible=tuple(visible),
            names=names,
        )

    def _info(self, match: Match, context: _MatchContext) -> MatchInfo:
        kind = turn_kind(match)
        current_id = active_owner_id(match)
        winner_name: str | None = None
        if match.winner_id is not None:
            winner_name = context.names.get(match.winner_id)
        elif match.winner_team_id is not None:
            winner_name = context.names.get(match.winner_team_id)

        return MatchInfo(
            id=match.id,
            room_id=match.room_id,
            mode=match.mode,
            status=match.status,
            phase=match_phase(match.status),
            turn_index=match.turn_index,
            current_turn_id=current_id,
            current_turn_kind=kind,
            current_turn_name=context.names.get(current_id) if current_id else None,
            participant_count=len(context.participants),
            started_at=match.started_at,
            finished_at=match.finished_at,
            winner_player_id=match.winner_id,
            winner_team_id=match.winner_team_id,
            winner_name=winner_name,
        )

    def _own_owner(
        self,
        match: Match,
        player: Player,
    ) -> tuple[uuid.UUID, OwnerKind, uuid.UUID | None]:
        if turn_kind(match) == "team":
            if player.team_id is None:
                return player.id, "team", None
            return player.team_id, "team", player.team_id
        return player.id, "player", player.team_id

    def _question_view(
        self,
        question: Question,
        *,
        can_answer: bool,
        names: dict[uuid.UUID, str],
    ) -> QuestionView:
        answer = None
        if question.answer_content is not None and question.answered_at is not None:
            answer = AnswerView(
                content=question.answer_content,
                author_player_id=question.answer_author_player_id,
                author_nickname=(
                    names.get(question.answer_author_player_id)
                    if question.answer_author_player_id
                    else None
                ),
                answered_at=question.answered_at,
            )

        recipient_id = question.recipient_player_id or question.recipient_team_id
        return QuestionView(
            id=question.id,
            author_player_id=question.author_player_id,
            author_nickname=(
                names.get(question.author_player_id) if question.author_player_id else None
            ),
            recipient_player_id=question.recipient_player_id,
            recipient_team_id=question.recipient_team_id,
            recipient_name=names.get(recipient_id) if recipient_id else None,
            content=question.content,
            asked_at=question.created_at,
            answer=answer,
            can_answer=can_answer,
        )

    @staticmethod
    def _visible(
        owner_id: uuid.UUID,
        owner_kind: OwnerKind,
        owner_name: str,
        assignment: Assignment,
    ) -> VisibleCharacter:
        character = assignment.character
        return VisibleCharacter(
            owner_id=owner_id,
            owner_kind=owner_kind,
            owner_name=owner_name,
            character=CharacterSnapshot(
                id=character.id,
                name=character.name,
                franchise=character.franchise,
                category=character.category,
                image_path=character.image_path,
                attributes=dict(character.attributes),
            ),
        )

    def _room(self, match: Match) -> Room:
        room = self.rooms.get(match.room_id)
        # A match always belongs to an existing room (FK); defensive fallback
        # keeps the type checker honest without hiding application errors.
        if room is None:  # pragma: no cover - database invariant
            raise RuntimeError("Match references a missing room.")
        return room


@dataclass(frozen=True, slots=True)
class _MatchContext:
    players_by_id: dict[uuid.UUID, Player]
    teams_by_id: dict[uuid.UUID, Team]
    participants: tuple[MatchParticipant, ...]
    visible: tuple[VisibleCharacter, ...]
    names: dict[uuid.UUID, str]
