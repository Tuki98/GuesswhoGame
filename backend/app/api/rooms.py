"""Room creation, lobby, membership, and host administration endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import (
    AppSettingsDep,
    ConnectionManagerDep,
    CurrentPlayerDep,
    DbSessionDep,
)
from app.api.mappers import credentials_response, player_response, room_response, team_response
from app.schemas.rooms import (
    CreateRoomRequest,
    JoinRoomRequest,
    PlayerListResponse,
    RoomResponse,
    RoomSessionResponse,
    UpdateRoomSettingsRequest,
)
from app.schemas.teams import (
    AssignTeamRequest,
    AssignTeamResponse,
    CreateTeamRequest,
    TeamListResponse,
    TeamResponse,
)
from app.services.rooms import RoomService
from app.services.teams import TeamService
from app.websockets.protocol import (
    PLAYER_JOINED_EVENT,
    PLAYER_LEFT_EVENT,
    ROOM_UPDATED_EVENT,
    WebSocketEvent,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post(
    "",
    response_model=RoomSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a private room",
)
def create_room(
    payload: CreateRoomRequest,
    session: DbSessionDep,
    settings: AppSettingsDep,
) -> RoomSessionResponse:
    membership = RoomService(session, settings).create_room(
        nickname=payload.nickname,
        configuration=payload.settings,
    )
    return RoomSessionResponse(
        room=room_response(
            membership.room,
            membership.configuration,
            membership.player_count,
        ),
        player=player_response(membership.player, membership.room),
        credentials=credentials_response(membership.issued),
    )


@router.post(
    "/join",
    response_model=RoomSessionResponse,
    summary="Join a room by invitation code",
)
async def join_room(
    payload: JoinRoomRequest,
    session: DbSessionDep,
    settings: AppSettingsDep,
    manager: ConnectionManagerDep,
) -> RoomSessionResponse:
    membership = RoomService(session, settings).join_room(
        code=payload.code,
        nickname=payload.nickname,
    )
    public_player = player_response(membership.player, membership.room)
    await manager.broadcast_room(
        membership.room.id,
        WebSocketEvent(
            event=PLAYER_JOINED_EVENT,
            payload=public_player.model_dump(mode="json"),
        ),
    )
    return RoomSessionResponse(
        room=room_response(
            membership.room,
            membership.configuration,
            membership.player_count,
        ),
        player=public_player,
        credentials=credentials_response(membership.issued),
    )


@router.get(
    "/{room_id}",
    response_model=RoomResponse,
    summary="Get public room information",
)
def get_room(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
) -> RoomResponse:
    view = RoomService(session, settings).get_room(room_id, player)
    return room_response(view.room, view.configuration, view.player_count)


@router.get(
    "/{room_id}/players",
    response_model=PlayerListResponse,
    summary="List room participants",
)
def list_players(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
) -> PlayerListResponse:
    service = RoomService(session, settings)
    room = service.get_room(room_id, player).room
    players = service.list_players(room_id, player)
    return PlayerListResponse(players=[player_response(member, room) for member in players])


@router.patch(
    "/{room_id}/settings",
    response_model=RoomResponse,
    summary="Update room settings (host only)",
)
async def update_settings(
    room_id: uuid.UUID,
    payload: UpdateRoomSettingsRequest,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    manager: ConnectionManagerDep,
) -> RoomResponse:
    view = RoomService(session, settings).update_settings(
        room_id=room_id,
        player=player,
        updates=payload.model_dump(exclude_none=True),
    )
    response = room_response(view.room, view.configuration, view.player_count)
    await manager.broadcast_room(
        view.room.id,
        WebSocketEvent(
            event=ROOM_UPDATED_EVENT,
            payload=response.model_dump(mode="json"),
        ),
    )
    return response


@router.delete(
    "/{room_id}/players/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a participant (host only)",
)
async def remove_player(
    room_id: uuid.UUID,
    player_id: uuid.UUID,
    session: DbSessionDep,
    actor: CurrentPlayerDep,
    settings: AppSettingsDep,
    manager: ConnectionManagerDep,
) -> None:
    RoomService(session, settings).remove_player(room_id, actor, player_id)
    await manager.broadcast_room(
        room_id,
        WebSocketEvent(event=PLAYER_LEFT_EVENT, payload={"player_id": str(player_id)}),
    )


@router.post(
    "/{room_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave a room",
)
async def leave_room(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    manager: ConnectionManagerDep,
) -> None:
    RoomService(session, settings).leave_room(room_id, player)
    await manager.broadcast_room(
        room_id,
        WebSocketEvent(event=PLAYER_LEFT_EVENT, payload={"player_id": str(player.id)}),
    )


@router.post(
    "/{room_id}/close",
    response_model=RoomResponse,
    summary="Close a room (host only)",
)
async def close_room(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    manager: ConnectionManagerDep,
) -> RoomResponse:
    view = RoomService(session, settings).close_room(room_id, player)
    response = room_response(view.room, view.configuration, view.player_count)
    await manager.broadcast_room(
        view.room.id,
        WebSocketEvent(
            event=ROOM_UPDATED_EVENT,
            payload=response.model_dump(mode="json"),
        ),
    )
    return response


@router.post(
    "/{room_id}/teams",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team in a waiting room (host only)",
)
def create_team(
    room_id: uuid.UUID,
    payload: CreateTeamRequest,
    session: DbSessionDep,
    player: CurrentPlayerDep,
) -> TeamResponse:
    service = TeamService(session)
    view = service.create_team(room_id, player, payload.name)
    room = service.rooms.get(room_id)
    assert room is not None
    return team_response(view, room)


@router.get(
    "/{room_id}/teams",
    response_model=TeamListResponse,
    summary="List room teams",
)
def list_teams(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
) -> TeamListResponse:
    service = TeamService(session)
    views = service.list_teams(room_id, player)
    room = service.rooms.get(room_id)
    assert room is not None
    return TeamListResponse(teams=[team_response(view, room) for view in views])


@router.put(
    "/{room_id}/players/{player_id}/team",
    response_model=AssignTeamResponse,
    summary="Assign a player to a team or remove their team (host only)",
)
def assign_team(
    room_id: uuid.UUID,
    player_id: uuid.UUID,
    payload: AssignTeamRequest,
    session: DbSessionDep,
    actor: CurrentPlayerDep,
) -> AssignTeamResponse:
    service = TeamService(session)
    view = service.assign_player(room_id, actor, player_id, payload.team_id)
    if view is None:
        return AssignTeamResponse(player_id=player_id, team=None)
    room = service.rooms.get(room_id)
    assert room is not None
    return AssignTeamResponse(player_id=player_id, team=team_response(view, room))
