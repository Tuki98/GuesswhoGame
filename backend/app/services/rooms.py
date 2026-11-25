"""Room lifecycle and participant management business logic."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.nicknames import NicknameError, nickname_key, normalize_nickname
from app.core.room_config import RoomConfig
from app.core.security import generate_room_code
from app.database.base import utc_now
from app.models import Player, Room, RoomStatus
from app.repositories.matches import MatchRepository
from app.repositories.players import PlayerRepository
from app.repositories.rooms import RoomRepository
from app.services.matches import abandon_active_match
from app.services.permissions import ensure_room_host, ensure_room_member
from app.services.sessions import IssuedSession, issue_session

MAX_ROOM_CODE_ATTEMPTS = 8


@dataclass(frozen=True, slots=True)
class RoomView:
    room: Room
    configuration: RoomConfig
    player_count: int


@dataclass(frozen=True, slots=True)
class RoomMembership(RoomView):
    player: Player
    issued: IssuedSession


def normalize_room_code(code: str) -> str:
    """Normalize a user-entered invitation code before lookup."""
    return code.strip().upper()


class RoomService:
    """Coordinates room transactions. It has no HTTP or FastAPI dependencies."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.rooms = RoomRepository(session)
        self.players = PlayerRepository(session)
        self.matches = MatchRepository(session)

    # -- creation and joining -------------------------------------------------

    def create_room(self, nickname: str, configuration: RoomConfig) -> RoomMembership:
        """Create a room and its host player atomically.

        Invitation-code and credential collisions are retried by rolling back the
        entire attempt, so a failed attempt can never leave a partial room.
        """
        normalized_nickname = self._normalize_nickname(nickname)
        key = nickname_key(normalized_nickname)
        stored_configuration = configuration.model_dump(mode="json")

        for _ in range(MAX_ROOM_CODE_ATTEMPTS):
            code = generate_room_code()
            if self.rooms.code_exists(code):
                continue

            try:
                room = Room(
                    code=code,
                    status=RoomStatus.WAITING,
                    configuration=stored_configuration,
                )
                self.session.add(room)
                self.session.flush()

                issued = issue_session(self.settings)
                player = self._new_player(
                    room=room,
                    nickname=normalized_nickname,
                    nickname_key_value=key,
                    issued=issued,
                )
                self.session.add(player)
                self.session.flush()

                room.host_player_id = player.id
                self.session.flush()
                self.session.commit()
            except IntegrityError:
                # Most likely the generated code or token hash was taken in a
                # concurrent request; retry the complete atomic attempt.
                self.session.rollback()
                continue
            except Exception:
                self.session.rollback()
                raise

            return RoomMembership(
                room=room,
                configuration=configuration,
                player_count=1,
                player=player,
                issued=issued,
            )

        raise ConflictError("Could not create a room. Please try again.")

    def join_room(self, code: str, nickname: str) -> RoomMembership:
        """Join a waiting room by invitation code."""
        room = self.rooms.get_by_code(normalize_room_code(code))
        if room is None:
            raise NotFoundError("Room not found.")

        if room.status is not RoomStatus.WAITING:
            raise ConflictError("This room is not accepting new players.")

        configuration = self._configuration(room)
        if self.rooms.count_players(room.id) >= configuration.max_players:
            raise ConflictError("This room is full.")

        normalized_nickname = self._normalize_nickname(nickname)
        key = nickname_key(normalized_nickname)
        if self.players.nickname_key_exists(room.id, key):
            raise ConflictError("That nickname is already in use in this room.")

        issued = issue_session(self.settings)
        player = self._new_player(
            room=room,
            nickname=normalized_nickname,
            nickname_key_value=key,
            issued=issued,
        )

        try:
            self.session.add(player)
            self.session.flush()

            # The write above serializes SQLite writers. Re-reading the status and
            # re-counting after the insert make both checks safe under concurrent
            # joins; the earlier reads happened before this transaction's write.
            current_status = self.session.scalar(select(Room.status).where(Room.id == room.id))
            if current_status is not RoomStatus.WAITING:
                self.session.rollback()
                raise ConflictError("This room is not accepting new players.")

            player_count = self.rooms.count_players(room.id)
            if player_count > configuration.max_players:
                self.session.rollback()
                raise ConflictError("This room is full.")

            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("That nickname is already in use in this room.") from exc
        except ConflictError:
            raise
        except Exception:
            self.session.rollback()
            raise

        return RoomMembership(
            room=room,
            configuration=configuration,
            player_count=player_count,
            player=player,
            issued=issued,
        )

    # -- reads ----------------------------------------------------------------

    def get_room(self, room_id: uuid.UUID, player: Player) -> RoomView:
        room = self._member_room(room_id, player)
        return self._view(room)

    def list_players(self, room_id: uuid.UUID, player: Player) -> list[Player]:
        room = self._member_room(room_id, player)
        return self.players.list_by_room(room.id)

    # -- host administration --------------------------------------------------

    def update_settings(
        self,
        room_id: uuid.UUID,
        player: Player,
        updates: Mapping[str, Any],
    ) -> RoomView:
        room = self._member_room(room_id, player)
        ensure_room_host(room, player)
        self._require_waiting(room, "Room settings can only be changed while waiting.")

        current = self._configuration(room)
        merged = {**current.model_dump(mode="json"), **updates}
        try:
            configuration = RoomConfig.model_validate(merged)
        except ValidationError as exc:
            raise DomainValidationError("Invalid room settings.") from exc

        player_count = self.rooms.count_players(room.id)
        if configuration.max_players < player_count:
            raise ConflictError(
                "The maximum player count cannot be lower than the current player count."
            )

        room.configuration = configuration.model_dump(mode="json")
        self.session.commit()
        return RoomView(room=room, configuration=configuration, player_count=player_count)

    def set_player_ready(
        self,
        room_id: uuid.UUID,
        actor: Player,
        *,
        ready: bool,
        target_player_id: uuid.UUID | None = None,
    ) -> RoomView:
        """Set a participant's readiness while the room is waiting.

        The host may set the readiness of any participant; a participant may set
        their own. The change is broadcast by the WebSocket layer as a
        ``player.ready_changed`` room event.
        """
        room = self._member_room(room_id, actor)
        self._require_waiting(room, "Player readiness can only be set while the room is waiting.")
        target_id = actor.id if target_player_id is None else target_player_id
        target = self.players.get(target_id)
        if target is None or target.room_id != room.id:
            raise NotFoundError("Player not found.")
        if actor.id != room.host_player_id and actor.id != target.id:
            raise PermissionDeniedError(
                "Only the host or the player themselves can change readiness."
            )
        target.is_ready = ready
        self.session.commit()
        return self._view(room)

    def remove_player(
        self,
        room_id: uuid.UUID,
        actor: Player,
        target_player_id: uuid.UUID,
    ) -> None:
        room = self._member_room(room_id, actor)
        ensure_room_host(room, actor)
        self._require_waiting(room, "Players can only be removed while the room is waiting.")

        target = self.players.get(target_player_id)
        if target is None or target.room_id != room.id:
            raise NotFoundError("Player not found.")
        if target.id == room.host_player_id:
            raise ConflictError("The host cannot be removed from the room.")

        self.session.delete(target)
        self.session.commit()

    def leave_room(self, room_id: uuid.UUID, player: Player) -> None:
        room = self._member_room(room_id, player)
        if player.id == room.host_player_id:
            raise ConflictError("The host cannot leave the room. Close the room instead.")
        if self.matches.active_for_room(room.id) is not None:
            raise ConflictError("You cannot leave while a match is in progress.")

        self.session.delete(player)
        self.session.commit()

    def close_room(self, room_id: uuid.UUID, player: Player) -> RoomView:
        room = self._member_room(room_id, player)
        ensure_room_host(room, player)
        if room.status is RoomStatus.CLOSED:
            raise ConflictError("This room is already closed.")

        # Closing a room with an active match abandons the match so the room's
        # lifecycle and event history remain consistent. The transition and the
        # event are committed together.
        if self.matches.active_for_room(room.id) is not None:
            abandon_active_match(
                self.session,
                room,
                actor_player_id=player.id,
                reason="room_closed",
            )

        room.status = RoomStatus.CLOSED
        self.session.commit()
        return self._view(room)

    # -- helpers --------------------------------------------------------------

    def _member_room(self, room_id: uuid.UUID, player: Player) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found.")
        ensure_room_member(room, player)
        return room

    def _configuration(self, room: Room) -> RoomConfig:
        return RoomConfig.model_validate(room.configuration or {})

    def _view(self, room: Room) -> RoomView:
        return RoomView(
            room=room,
            configuration=self._configuration(room),
            player_count=self.rooms.count_players(room.id),
        )

    def _new_player(
        self,
        *,
        room: Room,
        nickname: str,
        nickname_key_value: str,
        issued: IssuedSession,
    ) -> Player:
        now = utc_now()
        return Player(
            room_id=room.id,
            nickname=nickname,
            nickname_key=nickname_key_value,
            session_token_hash=issued.session_token_hash,
            session_expires_at=issued.session_expires_at,
            reconnect_token_hash=issued.reconnect_token_hash,
            reconnect_expires_at=issued.reconnect_expires_at,
            is_connected=True,
            joined_at=now,
            last_seen_at=now,
        )

    @staticmethod
    def _normalize_nickname(nickname: str) -> str:
        try:
            return normalize_nickname(nickname)
        except NicknameError as exc:
            raise DomainValidationError(str(exc)) from exc

    @staticmethod
    def _require_waiting(room: Room, message: str) -> None:
        if room.status is not RoomStatus.WAITING:
            raise ConflictError(message)
