"""In-memory WebSocket connection manager for the single-process MVP."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.websockets.protocol import PLAYER_DISCONNECTED_EVENT, WebSocketEvent

HEARTBEAT_INTERVAL_SECONDS = 30.0


@dataclass(slots=True)
class ActiveConnection:
    """Bookkeeping for one live WebSocket connection."""

    connection_id: str
    player_id: uuid.UUID
    room_id: uuid.UUID
    team_id: uuid.UUID | None
    websocket: WebSocket
    heartbeat_task: asyncio.Task[None] | None = None


class ConnectionManager:
    """Track live connections for room broadcasts and personalized sends.

    The MVP runs a single Uvicorn worker, so an in-memory registry is sufficient.
    It is intentionally not shared between processes; horizontal scaling would
    require a shared backend such as Redis or PostgreSQL, which is out of scope
    for Phase 5.
    """

    def __init__(self) -> None:
        self._connections: dict[str, ActiveConnection] = {}
        self._by_player: dict[uuid.UUID, set[str]] = {}
        self._by_room: dict[uuid.UUID, set[str]] = {}
        self._by_team: dict[uuid.UUID, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        *,
        player_id: uuid.UUID,
        room_id: uuid.UUID,
        team_id: uuid.UUID | None,
        websocket: WebSocket,
    ) -> str:
        """Register a live connection and start its heartbeat task."""
        connection_id = uuid.uuid4().hex
        connection = ActiveConnection(
            connection_id=connection_id,
            player_id=player_id,
            room_id=room_id,
            team_id=team_id,
            websocket=websocket,
        )
        connection.heartbeat_task = asyncio.create_task(self._heartbeat(connection_id))
        async with self._lock:
            self._connections[connection_id] = connection
            self._by_player.setdefault(player_id, set()).add(connection_id)
            self._by_room.setdefault(room_id, set()).add(connection_id)
            if team_id is not None:
                self._by_team.setdefault(team_id, set()).add(connection_id)
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Remove a connection and emit presence events when needed."""
        connection = await self._take(connection_id)
        if connection is None:
            return

        task = connection.heartbeat_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        remaining = self._by_player.get(connection.player_id)
        if remaining is not None and not remaining:
            await self.broadcast_room(
                connection.room_id,
                WebSocketEvent(
                    event=PLAYER_DISCONNECTED_EVENT,
                    payload={
                        "player_id": str(connection.player_id),
                        "room_id": str(connection.room_id),
                    },
                ),
            )

    async def _take(self, connection_id: str) -> ActiveConnection | None:
        """Atomically remove and unregister a connection."""
        async with self._lock:
            connection = self._connections.pop(connection_id, None)
            if connection is None:
                return None
            self._by_player.setdefault(connection.player_id, set()).discard(connection_id)
            self._by_room.setdefault(connection.room_id, set()).discard(connection_id)
            if connection.team_id is not None:
                self._by_team.setdefault(connection.team_id, set()).discard(connection_id)
        return connection

    def connections_for_player(self, player_id: uuid.UUID) -> tuple[str, ...]:
        """Return all live connection ids for a player."""
        return tuple(sorted(self._by_player.get(player_id, set())))

    def connections_for_room(self, room_id: uuid.UUID) -> tuple[str, ...]:
        """Return all live connection ids for a room."""
        return tuple(sorted(self._by_room.get(room_id, set())))

    async def send(self, connection_id: str, event: WebSocketEvent) -> bool:
        """Send one event to a connection; return False when it is unusable.

        A closed socket and a transport failure are both treated as a stale
        connection: it is unregistered (emitting a presence event when it was
        the player's last connection) and ``False`` is returned to the caller.
        """
        connection: ActiveConnection | None = None
        async with self._lock:
            connection = self._connections.get(connection_id)
        if connection is None:
            return False
        if connection.websocket.client_state != WebSocketState.CONNECTED:
            await self.disconnect(connection_id)
            return False
        try:
            await connection.websocket.send_text(json.dumps(event.as_dict()))
        except Exception:
            await self.disconnect(connection_id)
            return False
        return True

    async def send_to_player(self, player_id: uuid.UUID, event: WebSocketEvent) -> list[str]:
        """Send an event to every live connection of a player."""
        failed: list[str] = []
        async with self._lock:
            connection_ids = tuple(self._by_player.get(player_id, set()))
        for connection_id in connection_ids:
            if not await self.send(connection_id, event):
                failed.append(connection_id)
        return failed

    async def send_to_team(self, team_id: uuid.UUID, event: WebSocketEvent) -> list[str]:
        """Send an event to every live connection of a team."""
        failed: list[str] = []
        async with self._lock:
            connection_ids = tuple(self._by_team.get(team_id, set()))
        for connection_id in connection_ids:
            if not await self.send(connection_id, event):
                failed.append(connection_id)
        return failed

    async def broadcast_room(self, room_id: uuid.UUID, event: WebSocketEvent) -> int:
        """Send an event to every live connection in a room."""
        sent = 0
        async with self._lock:
            connection_ids = tuple(self._by_room.get(room_id, set()))
        for connection_id in connection_ids:
            if await self.send(connection_id, event):
                sent += 1
        return sent

    async def _heartbeat(self, connection_id: str) -> None:
        """Periodically send a heartbeat envelope until the connection dies."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            async with self._lock:
                connection = self._connections.get(connection_id)
            if connection is None:
                return
            if connection.websocket.client_state != WebSocketState.CONNECTED:
                return
            if not await self.send(
                connection_id,
                WebSocketEvent(event="connection.heartbeat", payload={}),
            ):
                return
