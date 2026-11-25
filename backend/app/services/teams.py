"""Team formation inside a waiting room."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.models import Player, Room, RoomStatus, Team
from app.repositories.players import PlayerRepository
from app.repositories.rooms import RoomRepository
from app.repositories.teams import TeamRepository
from app.services.permissions import ensure_room_host, ensure_room_member

TEAM_NAME_MAX_LENGTH = 40


@dataclass(frozen=True, slots=True)
class TeamView:
    team: Team
    members: list[Player]


class TeamService:
    """Host-managed team creation and membership for team matches."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.rooms = RoomRepository(session)
        self.players = PlayerRepository(session)
        self.teams = TeamRepository(session)

    def create_team(self, room_id: uuid.UUID, player: Player, name: str) -> TeamView:
        room = self._member_room(room_id, player)
        ensure_room_host(room, player)
        self._require_waiting(room)

        normalized = self._normalize_name(name)
        if self.teams.name_exists(room.id, normalized):
            raise ConflictError("A team with that name already exists in this room.")

        team = Team(room_id=room.id, name=normalized)
        try:
            self.session.add(team)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("A team with that name already exists in this room.") from exc

        return TeamView(team=team, members=[])

    def list_teams(self, room_id: uuid.UUID, player: Player) -> list[TeamView]:
        room = self._member_room(room_id, player)
        return [
            TeamView(team=team, members=self.players.list_by_team(team.id))
            for team in self.teams.list_by_room(room.id)
        ]

    def assign_player(
        self,
        room_id: uuid.UUID,
        actor: Player,
        target_player_id: uuid.UUID,
        team_id: uuid.UUID | None,
    ) -> TeamView | None:
        room = self._member_room(room_id, actor)
        ensure_room_host(room, actor)
        self._require_waiting(room)

        target = self.players.get(target_player_id)
        if target is None or target.room_id != room.id:
            raise NotFoundError("Player not found.")

        if team_id is None:
            target.team_id = None
            self.session.commit()
            return None

        team = self.teams.get(team_id)
        if team is None or team.room_id != room.id:
            raise NotFoundError("Team not found.")

        target.team_id = team.id
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("The player could not be assigned to that team.") from exc

        return TeamView(team=team, members=self.players.list_by_team(team.id))

    # -- helpers --------------------------------------------------------------

    def _member_room(self, room_id: uuid.UUID, player: Player) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found.")
        ensure_room_member(room, player)
        return room

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise DomainValidationError("Team name cannot be empty.")
        if len(normalized) > TEAM_NAME_MAX_LENGTH:
            raise DomainValidationError(
                f"Team name cannot exceed {TEAM_NAME_MAX_LENGTH} characters."
            )
        return normalized

    @staticmethod
    def _require_waiting(room: Room) -> None:
        if room.status is not RoomStatus.WAITING:
            raise ConflictError("Teams can only be managed while the room is waiting.")
