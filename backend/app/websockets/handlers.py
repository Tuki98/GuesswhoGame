"""WebSocket event handlers for the Phase 5 real-time layer.

Handlers translate validated WebSocket envelopes into existing service calls.
No game rules live here: every operation delegates to the room, character, and
match services so REST and WebSocket share validation and transaction rules.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.api.mappers import match_state_response, room_response
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.image_download import ImageDownloader
from app.core.media import MediaStorage
from app.models import Match, Player, Room
from app.repositories.matches import MatchRepository
from app.services.characters import CharacterService
from app.services.matches import MatchService
from app.services.rooms import RoomService
from app.websockets.manager import ConnectionManager
from app.websockets.protocol import (
    ANSWER_RECEIVED_EVENT,
    CHARACTER_ADDED_EVENT,
    CHARACTER_DELETED_EVENT,
    GUESS_INCORRECT_EVENT,
    MATCH_CANCELLED_EVENT,
    MATCH_FINISHED_EVENT,
    MATCH_STARTED_EVENT,
    MATCH_STATE_EVENT,
    MATCH_TURN_CHANGED_EVENT,
    PLAYER_READY_CHANGED_EVENT,
    QUESTION_RECEIVED_EVENT,
    ROOM_STATE_EVENT,
    WebSocketEvent,
)

ERROR_EVENT = "error"


@dataclass(frozen=True, slots=True)
class WsContext:
    """Per-connection dependencies shared by the event handlers."""

    manager: ConnectionManager
    session: Session
    settings: Settings
    player: Player
    room: Room


_HandlerResult = WebSocketEvent | None
_Handler = Callable[[WsContext, dict[str, Any]], Awaitable[_HandlerResult]]


def _error_event(request_id: str | None, *, code: str, message: str) -> WebSocketEvent:
    """Build a structured error event for an outgoing error frame."""
    return WebSocketEvent(
        event=ERROR_EVENT,
        payload={"code": code, "message": message},
        request_id=request_id,
    )


def _active_match(ctx: WsContext) -> Match:
    """Return the active match for the connection's room."""
    match = MatchRepository(ctx.session).active_for_room(ctx.room.id)
    if match is None:
        raise NotFoundError("No active match.")
    return match


def _storage(ctx: WsContext) -> MediaStorage:
    return MediaStorage(ctx.settings.media_root, ctx.settings.media_url_prefix)


def _downloader(ctx: WsContext) -> ImageDownloader:
    return ImageDownloader(
        timeout=ctx.settings.image_download_timeout_seconds,
        max_bytes=ctx.settings.image_max_bytes,
    )


async def _handle_room_state(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent:
    """Return the caller's personalized room state."""
    view = RoomService(ctx.session, ctx.settings).get_room(ctx.room.id, ctx.player)
    return WebSocketEvent(
        event=ROOM_STATE_EVENT,
        payload=room_response(view.room, view.configuration, view.player_count).model_dump(
            mode="json",
        ),
    )


async def _handle_match_state(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent:
    """Return the caller's personalized match state."""
    state = MatchService(ctx.session).get_state(_active_match(ctx).id, ctx.player)
    return WebSocketEvent(
        event=MATCH_STATE_EVENT,
        payload=match_state_response(state, _storage(ctx)).model_dump(mode="json"),
    )


async def _handle_match_start(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent:
    """Start the match, notify the room, and return the caller's state view."""
    state = MatchService(ctx.session).start_match(ctx.room.id, ctx.player)
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=MATCH_STARTED_EVENT,
            payload={"match_id": str(state.match.id), "status": state.match.status.value},
        ),
    )
    return WebSocketEvent(
        event=MATCH_STATE_EVENT,
        payload=match_state_response(state, _storage(ctx)).model_dump(mode="json"),
    )


async def _handle_player_ready(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent | None:
    """Accept a readiness change and broadcast it to the room."""
    ready = bool(payload.get("ready"))
    target_player_id = payload.get("target_player_id")
    RoomService(ctx.session, ctx.settings).set_player_ready(
        ctx.room.id,
        ctx.player,
        ready=ready,
        target_player_id=target_player_id,
    )
    target = ctx.player
    if target_player_id is not None:
        loaded = ctx.session.get(Player, target_player_id)
        # The room service already verified the target belongs to this room.
        assert loaded is not None
        target = loaded
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=PLAYER_READY_CHANGED_EVENT,
            payload={
                "player_id": str(target.id),
                "nickname": target.nickname,
                "ready": ready,
            },
        ),
    )
    return None


async def _handle_character_add(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent | None:
    """Add a character through the character service and notify the room."""
    character = CharacterService(
        ctx.session,
        ctx.settings,
        _storage(ctx),
        _downloader(ctx),
    ).create_character(
        ctx.room.id,
        ctx.player,
        name=str(payload.get("name") or ""),
        franchise=payload.get("franchise") if isinstance(payload.get("franchise"), str) else None,
        category=str(payload.get("category") or "anime"),
        attributes=payload.get("attributes") or {},
        image_url=payload.get("image_url") if isinstance(payload.get("image_url"), str) else None,
    )
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=CHARACTER_ADDED_EVENT,
            payload={"character_id": str(character.id), "name": character.name},
        ),
    )
    return None


async def _handle_character_delete(
    ctx: WsContext, payload: dict[str, Any]
) -> WebSocketEvent | None:
    """Delete a character through the character service and notify the room."""
    character_id = uuid.UUID(str(payload.get("character_id") or ""))
    CharacterService(
        ctx.session,
        ctx.settings,
        _storage(ctx),
        _downloader(ctx),
    ).delete_character(ctx.room.id, character_id, ctx.player)
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=CHARACTER_DELETED_EVENT,
            payload={"character_id": str(character_id)},
        ),
    )
    return None


async def _handle_question_submit(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent | None:
    """Persist a question through the match service and notify the recipient."""
    content = str(payload.get("content") or "")
    recipient_player_id = payload.get("recipient_player_id")
    recipient_team_id = payload.get("recipient_team_id")
    question = MatchService(ctx.session).ask_question(
        _active_match(ctx).id,
        ctx.player,
        content=content,
        recipient_player_id=recipient_player_id if recipient_player_id is not None else None,
        recipient_team_id=recipient_team_id if recipient_team_id is not None else None,
    )
    event = WebSocketEvent(
        event=QUESTION_RECEIVED_EVENT,
        payload={
            "question_id": str(question.id),
            "content": question.content,
            "author_player_id": (
                str(question.author_player_id) if question.author_player_id else None
            ),
            "recipient_player_id": (
                str(question.recipient_player_id) if question.recipient_player_id else None
            ),
            "recipient_team_id": (
                str(question.recipient_team_id) if question.recipient_team_id else None
            ),
        },
    )
    if question.recipient_team_id is not None:
        await ctx.manager.send_to_team(question.recipient_team_id, event)
    elif question.recipient_player_id is not None:
        await ctx.manager.send_to_player(question.recipient_player_id, event)
    return None


async def _handle_answer_submit(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent | None:
    """Persist an answer through the match service and notify the room."""
    content = str(payload.get("content") or "")
    question_id = uuid.UUID(str(payload.get("question_id") or ""))
    match_id = _active_match(ctx).id
    question = MatchService(ctx.session).answer_question(
        match_id,
        question_id,
        ctx.player,
        content=content,
    )
    if question.author_player_id is not None:
        await ctx.manager.send_to_player(
            question.author_player_id,
            WebSocketEvent(
                event=ANSWER_RECEIVED_EVENT,
                payload={
                    "question_id": str(question.id),
                    "answer": question.answer_content,
                    "author_player_id": (
                        str(question.answer_author_player_id)
                        if question.answer_author_player_id
                        else None
                    ),
                },
            ),
        )
    state = MatchService(ctx.session).get_state(match_id, ctx.player)
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=MATCH_TURN_CHANGED_EVENT,
            payload={
                "current_turn_id": (
                    str(state.match.current_turn_id) if state.match.current_turn_id else None
                ),
            },
        ),
    )
    return None


async def _handle_guess_submit(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent | None:
    """Submit a guess through the match service and relay the outcome."""
    character_id = uuid.UUID(str(payload.get("character_id") or ""))
    outcome = MatchService(ctx.session).submit_guess(
        _active_match(ctx).id,
        ctx.player,
        character_id=character_id,
    )
    if not outcome.correct:
        return WebSocketEvent(
            event=GUESS_INCORRECT_EVENT,
            payload={"character_id": str(character_id), "correct": False},
        )
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=MATCH_FINISHED_EVENT,
            payload={
                "winner_player_id": (
                    str(outcome.match.winner_player_id) if outcome.match.winner_player_id else None
                ),
                "winner_team_id": (
                    str(outcome.match.winner_team_id) if outcome.match.winner_team_id else None
                ),
                "reason": "correct_guess",
            },
        ),
    )
    return None


async def _handle_match_cancel(ctx: WsContext, payload: dict[str, Any]) -> WebSocketEvent | None:
    """Cancel the active match through the match service and notify the room."""
    MatchService(ctx.session).cancel_match(_active_match(ctx).id, ctx.player)
    await ctx.manager.broadcast_room(
        ctx.room.id,
        WebSocketEvent(
            event=MATCH_CANCELLED_EVENT,
            payload={"reason": "host_cancelled"},
        ),
    )
    return None


def personalized_state_event(ctx: WsContext) -> WebSocketEvent:
    """Build the personalized state snapshot for a freshly connected player."""
    match = MatchRepository(ctx.session).active_for_room(ctx.room.id)
    if match is not None:
        state = MatchService(ctx.session).get_state(match.id, ctx.player)
        return WebSocketEvent(
            event=MATCH_STATE_EVENT,
            payload=match_state_response(state, _storage(ctx)).model_dump(mode="json"),
        )
    view = RoomService(ctx.session, ctx.settings).get_room(ctx.room.id, ctx.player)
    return WebSocketEvent(
        event=ROOM_STATE_EVENT,
        payload=room_response(view.room, view.configuration, view.player_count).model_dump(
            mode="json",
        ),
    )


_HANDLERS: dict[str, _Handler] = {
    "room.get_state": _handle_room_state,
    "player.set_ready": _handle_player_ready,
    "character.add": _handle_character_add,
    "character.delete": _handle_character_delete,
    "match.start": _handle_match_start,
    "match.get_state": _handle_match_state,
    "question.submit": _handle_question_submit,
    "answer.submit": _handle_answer_submit,
    "guess.submit": _handle_guess_submit,
    "match.cancel": _handle_match_cancel,
}


async def dispatch(
    ctx: WsContext,
    event: str,
    payload: dict[str, Any],
    *,
    request_id: str | None,
) -> WebSocketEvent | None:
    """Dispatch one validated WebSocket event to its handler."""
    handler = _HANDLERS.get(event)
    if handler is None:
        return _error_event(
            request_id,
            code="unknown_event",
            message=f"Unsupported event: {event}.",
        )
    return await handler(ctx, payload)
