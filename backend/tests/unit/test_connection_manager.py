"""Unit tests for the in-memory WebSocket connection manager."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from starlette.websockets import WebSocketState

from app.websockets import manager as manager_module
from app.websockets.manager import ConnectionManager
from app.websockets.protocol import WebSocketEvent

PLAYER_A = uuid.uuid4()
PLAYER_B = uuid.uuid4()
ROOM = uuid.uuid4()
OTHER_ROOM = uuid.uuid4()
TEAM = uuid.uuid4()


class FakeWebSocket:
    """Minimal stand-in for Starlette's WebSocket used by the manager."""

    def __init__(self, *, fail: bool = False) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.fail = fail
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, data: str) -> None:
        if self.fail:
            raise RuntimeError("socket is broken")
        self.sent.append(json.loads(data))

    def events(self) -> list[str]:
        return [message["event"] for message in self.sent]


def _event(name: str = "room.updated") -> WebSocketEvent:
    return WebSocketEvent(event=name, payload={"ok": True})


def test_connect_registers_player_room_and_team() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket()
        connection_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=TEAM,
            websocket=socket,
        )

        assert manager.connections_for_player(PLAYER_A) == (connection_id,)
        assert manager.connections_for_room(ROOM) == (connection_id,)
        assert await manager.send_to_team(TEAM, _event()) == []
        assert socket.events() == ["room.updated"]

        await manager.disconnect(connection_id)

    asyncio.run(scenario())


def test_disconnect_is_idempotent_and_cleans_indexes() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket()
        connection_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=socket,
        )

        await manager.disconnect(connection_id)
        await manager.disconnect(connection_id)
        await manager.disconnect("unknown")

        assert manager.connections_for_player(PLAYER_A) == ()
        assert manager.connections_for_room(ROOM) == ()
        assert await manager.send(connection_id, _event()) is False

    asyncio.run(scenario())


def test_multiple_tabs_share_presence_until_last_disconnect() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        observer = FakeWebSocket()
        observer_id = await manager.connect(
            player_id=PLAYER_B,
            room_id=ROOM,
            team_id=None,
            websocket=observer,
        )

        first = FakeWebSocket()
        second = FakeWebSocket()
        first_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=first,
        )
        second_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=second,
        )
        assert set(manager.connections_for_player(PLAYER_A)) == {first_id, second_id}

        await manager.disconnect(first_id)
        observer.sent.clear()
        assert observer.events() == []

        await manager.disconnect(second_id)
        assert observer.events() == ["player.disconnected"]
        assert observer.sent[0]["payload"]["player_id"] == str(PLAYER_A)

        await manager.disconnect(observer_id)

    asyncio.run(scenario())


def test_room_broadcast_reaches_only_room_members() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        socket_a = FakeWebSocket()
        socket_b = FakeWebSocket()
        outsider = FakeWebSocket()
        await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=socket_a,
        )
        await manager.connect(
            player_id=PLAYER_B,
            room_id=ROOM,
            team_id=None,
            websocket=socket_b,
        )
        await manager.connect(
            player_id=PLAYER_A,
            room_id=OTHER_ROOM,
            team_id=None,
            websocket=outsider,
        )

        sent = await manager.broadcast_room(ROOM, _event("character.added"))

        assert sent == 2
        assert socket_a.events() == ["character.added"]
        assert socket_b.events() == ["character.added"]
        assert outsider.events() == []

    asyncio.run(scenario())


def test_send_to_player_isolates_other_players() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        target = FakeWebSocket()
        other = FakeWebSocket()
        target_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=target,
        )
        await manager.connect(
            player_id=PLAYER_B,
            room_id=ROOM,
            team_id=None,
            websocket=other,
        )

        assert await manager.send_to_player(PLAYER_A, _event("question.received")) == []
        assert target.events() == ["question.received"]
        assert other.events() == []
        assert await manager.send_to_player(uuid.uuid4(), _event()) == []
        assert target_id in manager.connections_for_player(PLAYER_A)

    asyncio.run(scenario())


def test_send_to_team_only_reaches_team_connections() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        teammate = FakeWebSocket()
        solo = FakeWebSocket()
        await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=TEAM,
            websocket=teammate,
        )
        await manager.connect(
            player_id=PLAYER_B,
            room_id=ROOM,
            team_id=None,
            websocket=solo,
        )

        assert await manager.send_to_team(TEAM, _event("question.received")) == []
        assert teammate.events() == ["question.received"]
        assert solo.events() == []

    asyncio.run(scenario())


def test_failed_send_unregisters_stale_connection() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        observer = FakeWebSocket()
        observer_id = await manager.connect(
            player_id=PLAYER_B,
            room_id=ROOM,
            team_id=None,
            websocket=observer,
        )
        broken = FakeWebSocket(fail=True)
        connection_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=broken,
        )

        assert await manager.send(connection_id, _event()) is False
        assert manager.connections_for_player(PLAYER_A) == ()
        assert manager.connections_for_room(ROOM) == (observer_id,)
        assert observer.events() == ["player.disconnected"]

    asyncio.run(scenario())


def test_closed_socket_is_cleaned_up_without_sending() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket()
        connection_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=socket,
        )
        socket.client_state = WebSocketState.DISCONNECTED

        assert await manager.send(connection_id, _event()) is False
        assert socket.sent == []
        assert manager.connections_for_player(PLAYER_A) == ()

    asyncio.run(scenario())


def test_failed_broadcast_reports_and_removes_only_stale_socket() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        good = FakeWebSocket()
        bad = FakeWebSocket(fail=True)
        await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=good,
        )
        bad_id = await manager.connect(
            player_id=PLAYER_B,
            room_id=ROOM,
            team_id=None,
            websocket=bad,
        )

        sent = await manager.broadcast_room(ROOM, _event("room.updated"))

        assert sent == 1
        assert set(good.events()) == {"room.updated", "player.disconnected"}
        assert bad_id not in manager.connections_for_room(ROOM)

    asyncio.run(scenario())


def test_stale_cleanup_never_removes_newer_connection() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        old = FakeWebSocket()
        old_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=old,
        )
        await manager.disconnect(old_id)

        replacement = FakeWebSocket()
        new_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=replacement,
        )

        # A late failure for the stale id must not touch the replacement.
        assert await manager.send(old_id, _event()) is False
        assert manager.connections_for_player(PLAYER_A) == (new_id,)
        assert await manager.send(new_id, _event("room.state")) is True
        assert replacement.events() == ["room.state"]

    asyncio.run(scenario())


def test_concurrent_connect_and_disconnect_keep_indexes_consistent() -> None:
    async def scenario() -> None:
        manager = ConnectionManager()
        sockets = [FakeWebSocket() for _ in range(10)]

        connection_ids = await asyncio.gather(
            *(
                manager.connect(
                    player_id=PLAYER_A if index % 2 == 0 else PLAYER_B,
                    room_id=ROOM,
                    team_id=TEAM if index % 3 == 0 else None,
                    websocket=socket,
                )
                for index, socket in enumerate(sockets)
            )
        )
        assert len(set(connection_ids)) == 10
        assert len(manager.connections_for_room(ROOM)) == 10

        await asyncio.gather(*(manager.disconnect(cid) for cid in connection_ids[:5]))
        assert len(manager.connections_for_room(ROOM)) == 5

        await asyncio.gather(*(manager.disconnect(cid) for cid in connection_ids[5:]))
        assert manager.connections_for_room(ROOM) == ()
        assert manager.connections_for_player(PLAYER_A) == ()
        assert manager.connections_for_player(PLAYER_B) == ()

    asyncio.run(scenario())


def test_heartbeat_sends_periodic_connection_events(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(manager_module, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket()
        connection_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=socket,
        )
        await asyncio.sleep(0.05)
        assert socket.events()
        assert all(event == "connection.heartbeat" for event in socket.events())
        await manager.disconnect(connection_id)
        count = len(socket.sent)
        await asyncio.sleep(0.05)
        assert len(socket.sent) == count

    asyncio.run(scenario())


def test_heartbeat_stops_for_disconnected_socket(monkeypatch: Any) -> None:
    monkeypatch.setattr(manager_module, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket()
        connection_id = await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=socket,
        )
        socket.client_state = WebSocketState.DISCONNECTED
        await asyncio.sleep(0.05)
        assert socket.sent == []
        await manager.disconnect(connection_id)

    asyncio.run(scenario())


def test_heartbeat_failure_cleans_up_connection(monkeypatch: Any) -> None:
    monkeypatch.setattr(manager_module, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    async def scenario() -> None:
        manager = ConnectionManager()
        socket = FakeWebSocket(fail=True)
        await manager.connect(
            player_id=PLAYER_A,
            room_id=ROOM,
            team_id=None,
            websocket=socket,
        )
        await asyncio.sleep(0.05)
        assert manager.connections_for_player(PLAYER_A) == ()
        assert manager.connections_for_room(ROOM) == ()

    asyncio.run(scenario())
