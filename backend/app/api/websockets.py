"""WebSocket endpoint for room-scoped real-time communication."""

from __future__ import annotations

import contextlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket
from sqlalchemy.orm import Session

from app.api.deps import (
    WsAppSettingsDep,
    WsConnectionManagerDep,
    WsDatabaseDep,
)
from app.core.config import Settings
from app.core.exceptions import AppError, InvalidSessionError
from app.models import Player, Room
from app.repositories.rooms import RoomRepository
from app.services.sessions import SessionService
from app.websockets import handlers
from app.websockets.protocol import (
    MAX_MESSAGE_BYTES,
    PAYLOAD_MODELS,
    PLAYER_CONNECTED_EVENT,
    SUPPORTED_INCOMING_EVENTS,
    WebSocketEvent,
    WebSocketIncomingMessage,
)

router = APIRouter(prefix="/ws", tags=["websockets"])


def _error_event(code: str, message: str, *, request_id: str | None = None) -> WebSocketEvent:
    """Build a structured error frame for the current connection."""
    return WebSocketEvent(
        event="error",
        payload={"code": code, "message": message},
        request_id=request_id,
    )


def _authenticate_and_authorize(
    session: Session,
    settings: Settings,
    room_code: str,
    token: str | None,
) -> tuple[Player, Room] | None:
    """Resolve the session and room, returning ``None`` for any rejection.

    The same generic rejection covers a missing token, an invalid session, a
    missing room, and a non-member, so the endpoint never reveals whether a room
    exists or whose token was supplied.
    """
    if not token:
        return None
    try:
        player = SessionService(session, settings).authenticate(token)
    except InvalidSessionError:
        return None
    room = RoomRepository(session).get_by_code(room_code.strip().upper())
    if room is None or player.room_id != room.id:
        return None
    return player, room


def _decode_message(
    raw: str,
) -> tuple[WebSocketIncomingMessage | None, WebSocketEvent | None]:
    """Validate an inbound envelope, returning either the message or an error."""
    try:
        envelope = WebSocketIncomingMessage.model_validate(json.loads(raw))
    except ValueError:
        return None, _error_event("invalid_message", "Malformed WebSocket message.")
    if envelope.event not in SUPPORTED_INCOMING_EVENTS:
        return None, _error_event(
            "unknown_event",
            f"Unsupported event: {envelope.event}.",
            request_id=envelope.request_id,
        )
    return envelope, None


def _decode_payload(
    envelope: WebSocketIncomingMessage,
) -> tuple[dict[str, Any], WebSocketEvent | None]:
    """Validate the event-specific payload, returning either it or an error."""
    model = PAYLOAD_MODELS.get(envelope.event)
    if model is None:
        return dict(envelope.payload), None
    try:
        return model.model_validate(envelope.payload).model_dump(), None
    except ValueError:
        return {}, _error_event(
            "invalid_payload",
            "The event payload is invalid.",
            request_id=envelope.request_id,
        )


def _load_member(
    session: Session,
    player_id: uuid.UUID,
    room_id: uuid.UUID,
) -> tuple[Player, Room] | None:
    """Reload the connection's member from a fresh session."""
    player = session.get(Player, player_id)
    room = session.get(Room, room_id)
    if player is None or room is None or player.room_id != room.id:
        return None
    return player, room


@router.websocket("/rooms/{room_code}")
async def websocket_room(
    room_code: str,
    websocket: WebSocket,
    database: WsDatabaseDep,
    settings: WsAppSettingsDep,
    manager: WsConnectionManagerDep,
) -> None:
    """Authenticate, register, and dispatch real-time events for a room."""
    with database.session() as session:
        resolved = _authenticate_and_authorize(
            session,
            settings,
            room_code,
            websocket.query_params.get("token"),
        )
        if resolved is None:
            # Reject before the socket is accepted. No token, room, or error
            # detail is sent on an unauthenticated connection.
            await websocket.close(code=1008)
            return
        player, room = resolved
        player_id = player.id
        room_id = room.id
        team_id = player.team_id
        nickname = player.nickname

    await websocket.accept()

    had_connections = bool(manager.connections_for_player(player_id))
    connection_id = await manager.connect(
        player_id=player_id,
        room_id=room_id,
        team_id=team_id,
        websocket=websocket,
    )
    seen_request_ids: set[str] = set()
    try:
        with database.session() as session:
            member = _load_member(session, player_id, room_id)
            assert member is not None  # authenticated immediately above
            current_player, current_room = member
            snapshot = handlers.personalized_state_event(
                handlers.WsContext(
                    manager=manager,
                    session=session,
                    settings=settings,
                    player=current_player,
                    room=current_room,
                )
            )
        if not await manager.send(connection_id, snapshot):
            return
        if not had_connections:
            await manager.broadcast_room(
                room_id,
                WebSocketEvent(
                    event=PLAYER_CONNECTED_EVENT,
                    payload={"player_id": str(player_id), "nickname": nickname},
                ),
            )

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            raw = message.get("text")
            if raw is None:
                await manager.send(
                    connection_id,
                    _error_event("invalid_message", "Only JSON text messages are supported."),
                )
                continue
            if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await manager.send(
                    connection_id,
                    _error_event("message_too_large", "Message exceeds the size limit."),
                )
                return

            envelope, error = _decode_message(raw)
            if error is not None:
                await manager.send(connection_id, error)
                continue
            assert envelope is not None  # the error branch continued above

            payload, payload_error = _decode_payload(envelope)
            if payload_error is not None:
                await manager.send(connection_id, payload_error)
                continue

            if envelope.request_id is not None:
                if envelope.request_id in seen_request_ids:
                    await manager.send(
                        connection_id,
                        _error_event(
                            "duplicate_request",
                            "Duplicate request ignored.",
                            request_id=envelope.request_id,
                        ),
                    )
                    continue
                seen_request_ids.add(envelope.request_id)

            # Each request uses a short-lived session so a long-lived socket
            # never serves stale ORM state or a removed membership.
            with database.session() as session:
                member = _load_member(session, player_id, room_id)
                if member is None:
                    await manager.send(
                        connection_id,
                        _error_event(
                            "not_found",
                            "You are no longer a member of this room.",
                        ),
                    )
                    return
                current_player, current_room = member
                try:
                    response = await handlers.dispatch(
                        handlers.WsContext(
                            manager=manager,
                            session=session,
                            settings=settings,
                            player=current_player,
                            room=current_room,
                        ),
                        envelope.event,
                        payload,
                        request_id=envelope.request_id,
                    )
                except AppError as exc:
                    response = _error_event(
                        exc.code,
                        exc.message,
                        request_id=envelope.request_id,
                    )
                if response is not None:
                    if response.request_id is None:
                        response.request_id = envelope.request_id
                    await manager.send(connection_id, response)
    except Exception:
        # Unexpected transport or application failure: notify and drop the
        # connection without leaking internals to the client.
        with contextlib.suppress(Exception):
            await manager.send(connection_id, _error_event("internal_error", "Unexpected error."))
    finally:
        await manager.disconnect(connection_id)
