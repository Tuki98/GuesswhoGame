"""Reusable authorization checks for room operations."""

from __future__ import annotations

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models import Player, Room


def ensure_room_member(room: Room, player: Player) -> None:
    """Reject access to rooms the authenticated player does not belong to.

    A generic not-found response avoids revealing whether a room exists.
    """
    if player.room_id != room.id:
        raise NotFoundError("Room not found.")


def ensure_room_host(room: Room, player: Player) -> None:
    """Require the authenticated player to be the room host."""
    if room.host_player_id != player.id:
        raise PermissionDeniedError("Only the room host can perform this action.")
