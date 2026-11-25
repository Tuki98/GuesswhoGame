"""Session reconnection endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AppSettingsDep, DbSessionDep
from app.api.mappers import credentials_response, player_response, room_response
from app.schemas.rooms import ReconnectRequest, ReconnectResponse
from app.services.rooms import RoomService
from app.services.sessions import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post(
    "/reconnect",
    response_model=ReconnectResponse,
    summary="Restore a player session",
)
def reconnect(
    payload: ReconnectRequest,
    session: DbSessionDep,
    settings: AppSettingsDep,
) -> ReconnectResponse:
    reconnected = SessionService(session, settings).reconnect(payload.reconnect_token)
    view = RoomService(session, settings).get_room(reconnected.room.id, reconnected.player)
    return ReconnectResponse(
        room=room_response(view.room, view.configuration, view.player_count),
        player=player_response(reconnected.player, view.room),
        credentials=credentials_response(reconnected.issued),
    )
