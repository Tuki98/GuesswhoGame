"""End-to-end WebSocket tests for the Phase 5 real-time layer."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.database.base import utc_now
from app.models import Assignment, GameEvent, Player
from app.websockets import handlers as handlers_module
from tests.api_helpers import auth_headers, create_room, join_room

PNG_PIXEL = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeDownloader:
    """Deterministic downloader stand-in so character adds never hit the network."""

    def download(self, url: str) -> bytes:
        assert url
        return PNG_PIXEL


def _ws_url(code: str, token: str | None) -> str:
    if token is None:
        return f"/ws/rooms/{code}"
    return f"/ws/rooms/{code}?token={token}"


def _add_character(
    client: TestClient,
    token: str,
    room_id: str,
    name: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": name, "franchise": "Test", "category": "anime", "attributes": "{}"},
        files={"image": ("c.png", PNG_PIXEL, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup_room(
    client: TestClient,
    *,
    players: int = 2,
    characters: int = 2,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    host = create_room(client, nickname="Host", settings=settings)
    room_id = host["room"]["id"]
    code = host["room"]["code"]
    members = [host]
    for index in range(players - 1):
        members.append(join_room(client, code=code, nickname=f"Player{index + 1}"))
    created = [
        _add_character(
            client,
            members[index % len(members)]["credentials"]["session_token"],
            room_id,
            f"Char{index}",
        )
        for index in range(characters)
    ]
    return {
        "host": host,
        "members": members,
        "characters": created,
        "room_id": room_id,
        "code": code,
    }


def _token(member: dict[str, Any]) -> str:
    return member["credentials"]["session_token"]


def _open(client: TestClient, code: str, token: str) -> Any:
    return client.websocket_connect(_ws_url(code, token))


def _drain_snapshot(socket: Any) -> dict[str, Any]:
    message = socket.receive_json()
    assert message["event"] == "room.state", message
    return message


def _drain_connect(socket: Any, *, presence: bool = True) -> dict[str, Any]:
    snapshot = _drain_snapshot(socket)
    if presence:
        connected = socket.receive_json()
        assert connected["event"] == "player.connected", connected
    return snapshot


def _expect(socket: Any, event: str) -> dict[str, Any]:
    message = socket.receive_json()
    assert message["event"] == event, message
    return message


def _send(socket: Any, event: str, payload: dict[str, Any] | None = None, **extra: Any) -> None:
    socket.send_json({"event": event, "payload": payload or {}, **extra})


def _state(client: TestClient, token: str, match_id: str) -> dict[str, Any]:
    response = client.get(f"/api/matches/{match_id}/state", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def _room(client: TestClient, room_id: str, token: str) -> dict[str, Any]:
    response = client.get(f"/api/rooms/{room_id}", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def _start_match_ws(
    socket: Any,
    *,
    request_id: str = "start-1",
) -> dict[str, Any]:
    _send(socket, "match.start", request_id=request_id)
    _expect(socket, "match.started")
    return _expect(socket, "match.state")


def _event_count(session: Session, match_id: str) -> int:
    session.expire_all()
    return int(
        session.scalar(
            select(func.count())
            .select_from(GameEvent)
            .where(GameEvent.match_id == uuid.UUID(match_id))
        )
        or 0
    )


# -- authentication ---------------------------------------------------------


def test_valid_connection_receives_personalized_room_state(client: TestClient) -> None:
    ctx = _setup_room(client)
    token = _token(ctx["host"])

    with _open(client, ctx["code"], token) as socket:
        snapshot = _drain_connect(socket)

    assert snapshot["event"] == "room.state"
    assert snapshot["payload"]["id"] == ctx["room_id"]
    assert token not in json.dumps(snapshot)


@pytest.mark.parametrize("token_factory", [lambda ctx: None, lambda ctx: "not-a-real-token"])
def test_missing_or_invalid_credentials_are_rejected_before_accept(
    client: TestClient,
    token_factory: Any,
) -> None:
    ctx = _setup_room(client)

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        _open(client, ctx["code"], token_factory(ctx)),
    ):
        pass

    assert exc_info.value.code == 1008


def test_expired_session_is_rejected(client: TestClient, db_session: Session) -> None:
    ctx = _setup_room(client)
    player_id = uuid.UUID(ctx["host"]["player"]["id"])

    player = db_session.get(Player, player_id)
    assert player is not None
    player.session_expires_at = utc_now() - timedelta(hours=1)
    db_session.commit()

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        _open(client, ctx["code"], _token(ctx["host"])),
    ):
        pass

    assert exc_info.value.code == 1008


def test_non_member_and_unknown_room_are_rejected(client: TestClient) -> None:
    first = _setup_room(client)
    second = _setup_room(client)

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        _open(client, first["code"], _token(second["host"])),
    ):
        # Valid token from another room, same code of the first room.
        pass
    assert exc_info.value.code == 1008

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        _open(client, "NOPE00", _token(first["host"])),
    ):
        pass
    assert exc_info.value.code == 1008


def test_reconnect_restores_state_without_duplicate_players(
    client: TestClient,
    db_session: Session,
) -> None:
    ctx = _setup_room(client)
    token = _token(ctx["host"])

    with _open(client, ctx["code"], token) as socket:
        _drain_connect(socket)

    with _open(client, ctx["code"], token) as socket:
        snapshot = _drain_connect(socket)

    assert snapshot["event"] == "room.state"
    assert snapshot["payload"]["player_count"] == 2

    db_session.expire_all()
    stored = db_session.scalar(
        select(func.count()).select_from(Player).where(Player.room_id == uuid.UUID(ctx["room_id"]))
    )
    assert stored == 2


def test_multiple_tabs_for_one_player_are_independent(client: TestClient) -> None:
    ctx = _setup_room(client)
    token = _token(ctx["host"])

    with _open(client, ctx["code"], token) as first:
        _drain_connect(first)
        with _open(client, ctx["code"], token) as second:
            # No duplicate ``player.connected`` for the second tab.
            _drain_snapshot(second)
            _send(second, "room.get_state", request_id="tab-2")
            reply = _expect(second, "room.state")
            assert reply["request_id"] == "tab-2"

            _send(first, "room.get_state", request_id="tab-1")
            assert _expect(first, "room.state")["request_id"] == "tab-1"


# -- protocol ---------------------------------------------------------------


def test_valid_message_round_trip_echoes_request_id(client: TestClient) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        _send(socket, "room.get_state", request_id="room-1")
        reply = _expect(socket, "room.state")
        assert reply["request_id"] == "room-1"
        assert reply["payload"]["code"] == ctx["code"]


def test_response_without_request_id_omits_the_field(client: TestClient) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        socket.send_json({"event": "room.get_state", "payload": {}})
        reply = _expect(socket, "room.state")
        assert "request_id" not in reply


def test_unknown_event_returns_structured_error(client: TestClient) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        _send(socket, "room.destroy_everything", request_id="bad-1")
        error = _expect(socket, "error")
        assert error["request_id"] == "bad-1"
        assert error["payload"]["code"] == "unknown_event"


def test_malformed_json_and_binary_frames_are_rejected(client: TestClient) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)

        socket.send_text("{this is not json")
        assert _expect(socket, "error")["payload"]["code"] == "invalid_message"

        socket.send_bytes(b'{"event": "room.get_state"}')
        assert _expect(socket, "error")["payload"]["code"] == "invalid_message"

        # The connection remains usable.
        _send(socket, "room.get_state", request_id="after-errors")
        assert _expect(socket, "room.state")["request_id"] == "after-errors"


@pytest.mark.parametrize(
    "message",
    [
        {"event": "player.set_ready", "payload": {"ready": True, "unexpected": 1}},
        {"event": "character.delete", "payload": {}},
        {"event": "guess.submit", "payload": {"character_id": "not-a-uuid"}},
    ],
)
def test_invalid_payloads_return_structured_errors(
    client: TestClient,
    message: dict[str, Any],
) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        socket.send_json({**message, "request_id": "payload-1"})
        error = _expect(socket, "error")
        assert error["request_id"] == "payload-1"
        assert error["payload"]["code"] == "invalid_payload"


def test_oversized_messages_are_rejected(client: TestClient) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        oversized = json.dumps({"event": "question.submit", "payload": {"content": "x" * 9000}})
        socket.send_text(oversized)
        error = _expect(socket, "error")
        assert error["payload"]["code"] == "message_too_large"


def test_duplicate_request_id_is_ignored(client: TestClient) -> None:
    ctx = _setup_room(client)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)

        _send(socket, "player.set_ready", {"ready": True}, request_id="dedupe-1")
        changed = _expect(socket, "player.ready_changed")
        assert changed["payload"]["ready"] is True

        _send(socket, "player.set_ready", {"ready": True}, request_id="dedupe-1")
        error = _expect(socket, "error")
        assert error["request_id"] == "dedupe-1"
        assert error["payload"]["code"] == "duplicate_request"

        # No second broadcast was emitted.
        _send(socket, "room.get_state", request_id="after-dedupe")
        assert _expect(socket, "room.state")["request_id"] == "after-dedupe"


# -- room and presence ------------------------------------------------------


def test_presence_tracks_tabs_and_last_disconnect(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])
    host_id = ctx["host"]["player"]["id"]

    with _open(client, ctx["code"], host_token) as host_one:
        _drain_connect(host_one)
        with _open(client, ctx["code"], guest_token) as guest:
            _drain_connect(guest)
            assert (
                _expect(host_one, "player.connected")["payload"]["player_id"]
                == (ctx["members"][1]["player"]["id"])
            )

            with _open(client, ctx["code"], host_token) as host_two:
                # A second tab does not re-announce the player.
                _drain_snapshot(host_two)

                # Closing one tab is not a disconnect.
                host_one.close()
                _send(host_two, "player.set_ready", {"ready": True}, request_id="presence")
                changed = _expect(guest, "player.ready_changed")
                assert changed["payload"]["player_id"] == host_id

                # Closing the final tab is.
                host_two.close()
                disconnected = _expect(guest, "player.disconnected")
                assert disconnected["payload"]["player_id"] == host_id


def test_rest_membership_and_settings_changes_notify_websockets(client: TestClient) -> None:
    host = create_room(client, nickname="Host")
    host_token = host["credentials"]["session_token"]

    with _open(client, host["room"]["code"], host_token) as host_socket:
        _drain_connect(host_socket)

        guest = join_room(client, code=host["room"]["code"], nickname="Guest")
        joined = _expect(host_socket, "player.joined")
        assert joined["payload"]["id"] == guest["player"]["id"]
        assert joined["payload"]["nickname"] == "Guest"
        assert "session_token" not in json.dumps(joined)

        settings_response = client.patch(
            f"/api/rooms/{host['room']['id']}/settings",
            headers=auth_headers(host_token),
            json={"max_players": 4},
        )
        assert settings_response.status_code == 200, settings_response.text
        updated = _expect(host_socket, "room.updated")
        assert updated["payload"]["settings"]["max_players"] == 4

        left = client.post(
            f"/api/rooms/{host['room']['id']}/leave",
            headers=auth_headers(guest["credentials"]["session_token"]),
        )
        assert left.status_code == 204, left.text
        assert (
            _expect(host_socket, "player.left")["payload"]["player_id"] == (guest["player"]["id"])
        )


def test_ready_changes_broadcast_and_persist(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest = ctx["members"][1]
    guest_id = guest["player"]["id"]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], _token(guest)) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            _send(
                host_socket,
                "player.set_ready",
                {"ready": True, "target_player_id": guest_id},
                request_id="ready-guest",
            )
            for socket in (host_socket, guest_socket):
                message = _expect(socket, "player.ready_changed")
                assert message["payload"]["player_id"] == guest_id
                assert message["payload"]["ready"] is True

            players = client.get(
                f"/api/rooms/{ctx['room_id']}/players",
                headers=auth_headers(_token(guest)),
            )
            assert players.status_code == 200, players.text
            ready = {row["id"]: row["is_ready"] for row in players.json()["players"]}
            assert ready[guest_id] is True


def test_removed_member_socket_loses_room_access(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest = ctx["members"][1]
    guest_token = _token(guest)

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            removed = client.delete(
                f"/api/rooms/{ctx['room_id']}/players/{guest['player']['id']}",
                headers=auth_headers(host_token),
            )
            assert removed.status_code == 204, removed.text
            for socket in (host_socket, guest_socket):
                assert (
                    _expect(socket, "player.left")["payload"]["player_id"]
                    == (guest["player"]["id"])
                )

            _send(guest_socket, "room.get_state", request_id="stale-member")
            error = _expect(guest_socket, "error")
            assert error["payload"]["code"] == "not_found"


def test_rest_character_changes_notify_room(client: TestClient) -> None:
    ctx = _setup_room(client, characters=1)
    host_token = _token(ctx["host"])

    with _open(client, ctx["code"], host_token) as socket:
        _drain_connect(socket)

        created = _add_character(client, host_token, ctx["room_id"], "REST Hero")
        added = _expect(socket, "character.added")
        assert added["payload"]["character_id"] == created["id"]

        deleted = client.delete(
            f"/api/rooms/{ctx['room_id']}/characters/{created['id']}",
            headers=auth_headers(host_token),
        )
        assert deleted.status_code == 204, deleted.text
        assert _expect(socket, "character.deleted")["payload"]["character_id"] == (created["id"])


def test_non_host_cannot_change_another_players_readiness(client: TestClient) -> None:
    ctx = _setup_room(client)
    guest = ctx["members"][1]

    with _open(client, ctx["code"], _token(guest)) as socket:
        _drain_connect(socket)
        _send(
            socket,
            "player.set_ready",
            {"ready": True, "target_player_id": ctx["host"]["player"]["id"]},
            request_id="forbidden",
        )
        error = _expect(socket, "error")
        assert error["payload"]["code"] == "permission_denied"


# -- characters -------------------------------------------------------------


def test_character_add_and_delete_notifications(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(handlers_module, "_downloader", lambda ctx: FakeDownloader())
    ctx = _setup_room(client, characters=1)
    host_token = _token(ctx["host"])
    guest = ctx["members"][1]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], _token(guest)) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            _send(
                host_socket,
                "character.add",
                {
                    "name": "WS Hero",
                    "franchise": "Tests",
                    "category": "anime",
                    "image_url": "https://example.test/hero.png",
                },
                request_id="add-1",
            )
            for socket in (host_socket, guest_socket):
                added = _expect(socket, "character.added")
                assert added["payload"]["name"] == "WS Hero"
            character_id = added["payload"]["character_id"]

            listing = client.get(
                f"/api/rooms/{ctx['room_id']}/characters",
                headers=auth_headers(_token(guest)),
            )
            assert listing.status_code == 200, listing.text
            assert any(row["id"] == character_id for row in listing.json()["characters"])

            # A non-contributor cannot delete the host's character.
            _send(
                guest_socket,
                "character.delete",
                {"character_id": character_id},
                request_id="delete-forbidden",
            )
            error = _expect(guest_socket, "error")
            assert error["payload"]["code"] == "permission_denied"

            _send(
                host_socket,
                "character.delete",
                {"character_id": character_id},
                request_id="delete-1",
            )
            for socket in (host_socket, guest_socket):
                deleted = _expect(socket, "character.deleted")
                assert deleted["payload"]["character_id"] == character_id


def test_character_add_without_an_image_is_rejected(client: TestClient) -> None:
    ctx = _setup_room(client, characters=1)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        _send(socket, "character.add", {"name": "No Image"}, request_id="no-image")
        error = _expect(socket, "error")
        assert error["payload"]["code"] == "validation_error"


# -- matches ----------------------------------------------------------------


def test_match_start_requires_host_and_notifies_room(client: TestClient) -> None:
    ctx = _setup_room(client)
    guest = ctx["members"][1]

    with _open(client, ctx["code"], _token(guest)) as guest_socket:
        _drain_connect(guest_socket)
        _send(guest_socket, "match.start", request_id="not-host")
        error = _expect(guest_socket, "error")
        assert error["payload"]["code"] == "permission_denied"

    with _open(client, ctx["code"], _token(ctx["host"])) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], _token(guest)) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            _send(host_socket, "match.start", request_id="start-ok")
            started = _expect(host_socket, "match.started")
            state = _expect(host_socket, "match.state")
            assert state["request_id"] == "start-ok"
            assert started["payload"]["match_id"] == state["payload"]["match"]["id"]
            assert state["payload"]["identity_assigned"] is True
            assert state["payload"]["self"]["player_id"] == ctx["host"]["player"]["id"]

            guest_started = _expect(guest_socket, "match.started")
            assert guest_started["payload"]["match_id"] == state["payload"]["match"]["id"]

            room = _room(client, ctx["room_id"], _token(guest))
            assert room["status"] == "in_progress"


def test_match_start_rejects_insufficient_characters(client: TestClient) -> None:
    ctx = _setup_room(client, players=2, characters=1)
    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        _send(socket, "match.start", request_id="too-few")
        error = _expect(socket, "error")
        assert error["payload"]["code"] == "conflict"


def test_question_and_answer_flow_is_recipient_scoped(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest = ctx["members"][1]
    guest_token = _token(guest)

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            state = _start_match_ws(host_socket)
            _expect(guest_socket, "match.started")
            match_id = state["payload"]["match"]["id"]

            asker_socket, recipient_socket = (
                (host_socket, guest_socket)
                if state["payload"]["self"]["is_your_turn"]
                else (guest_socket, host_socket)
            )
            asker_player_id = state["payload"]["match"]["current_turn_id"]
            asker_token = (
                host_token if asker_player_id == ctx["host"]["player"]["id"] else guest_token
            )
            recipient_id = (
                guest["player"]["id"]
                if asker_player_id == ctx["host"]["player"]["id"]
                else ctx["host"]["player"]["id"]
            )

            asker_state = _state(client, asker_token, match_id)
            assert recipient_id in asker_state["allowed_recipient_ids"]

            _send(
                asker_socket,
                "question.submit",
                {
                    "content": "Is your character from a cartoon?",
                    "recipient_player_id": recipient_id,
                },
                request_id="question-1",
            )
            question = _expect(recipient_socket, "question.received")
            assert question["payload"]["content"] == "Is your character from a cartoon?"
            assert question["payload"]["recipient_player_id"] == recipient_id

            # The asker receives no copy of the private question event.
            _send(asker_socket, "room.get_state", request_id="asker-sync")
            assert _expect(asker_socket, "room.state")["request_id"] == "asker-sync"

            _send(
                recipient_socket,
                "answer.submit",
                {"content": "Yes.", "question_id": question["payload"]["question_id"]},
                request_id="answer-1",
            )
            answer = _expect(asker_socket, "answer.received")
            assert answer["payload"]["answer"] == "Yes."
            assert _expect(asker_socket, "match.turn_changed")["payload"]["current_turn_id"]
            assert _expect(recipient_socket, "match.turn_changed")["payload"]["current_turn_id"]

            # Only the designated recipient can answer.
            _send(
                asker_socket,
                "answer.submit",
                {"content": "No.", "question_id": question["payload"]["question_id"]},
                request_id="answer-forbidden",
            )
            error = _expect(asker_socket, "error")
            assert error["payload"]["code"] in {"conflict", "permission_denied"}


def test_incorrect_guess_is_private_and_persists_two_events(
    client: TestClient,
    db_session: Session,
) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")
            state = _start_match_ws(host_socket)
            _expect(guest_socket, "match.started")
            match_id = state["payload"]["match"]["id"]
            host_state = _state(client, host_token, match_id)
            # The character visible as an opponent is never the viewer's own secret.
            wrong_character = host_state["opponents"][0]["character"]["id"]

            before = _event_count(db_session, match_id)
            _send(
                host_socket,
                "guess.submit",
                {"character_id": wrong_character},
                request_id="guess-1",
            )
            outcome = _expect(host_socket, "guess.incorrect")
            assert outcome["payload"]["correct"] is False
            assert _event_count(db_session, match_id) == before + 2

            # No match.finished broadcast reached the opponent.
            _send(host_socket, "room.get_state", request_id="after-guess")
            assert _expect(host_socket, "room.state")["request_id"] == "after-guess"
            _send(guest_socket, "room.get_state", request_id="guest-sync")
            assert _expect(guest_socket, "room.state")["request_id"] == "guest-sync"

            match_state = _state(client, host_token, match_id)
            assert match_state["match"]["status"] == "active"


def test_correct_guess_finishes_match_for_everyone_without_duplicate_events(
    client: TestClient,
    db_session: Session,
) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])
    host_id = ctx["host"]["player"]["id"]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")
            state = _start_match_ws(host_socket)
            _expect(guest_socket, "match.started")
            match_id = state["payload"]["match"]["id"]

            guest_state = _state(client, guest_token, match_id)
            own_secret = next(
                opponent["character"]["id"]
                for opponent in guest_state["opponents"]
                if opponent["owner_id"] == host_id
            )

            before = _event_count(db_session, match_id)
            _send(
                host_socket,
                "guess.submit",
                {"character_id": own_secret},
                request_id="win-1",
            )
            for socket in (host_socket, guest_socket):
                finished = _expect(socket, "match.finished")
                assert finished["payload"]["winner_player_id"] == host_id
                assert finished["payload"]["reason"] == "correct_guess"
            assert _event_count(db_session, match_id) == before + 3

            # Retrying the same request must not create another game event.
            _send(
                host_socket,
                "guess.submit",
                {"character_id": own_secret},
                request_id="win-1",
            )
            error = _expect(host_socket, "error")
            assert error["payload"]["code"] == "duplicate_request"
            assert _event_count(db_session, match_id) == before + 3

            room = _room(client, ctx["room_id"], host_token)
            assert room["status"] == "waiting"


def test_match_cancel_broadcasts_to_room_and_requires_host(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")
            _start_match_ws(host_socket)
            _expect(guest_socket, "match.started")

            _send(guest_socket, "match.cancel", request_id="cancel-forbidden")
            error = _expect(guest_socket, "error")
            assert error["payload"]["code"] == "permission_denied"

            _send(host_socket, "match.cancel", request_id="cancel-1")
            for socket in (host_socket, guest_socket):
                cancelled = _expect(socket, "match.cancelled")
                assert cancelled["payload"]["reason"] == "host_cancelled"

            assert _room(client, ctx["room_id"], host_token)["status"] == "waiting"


# -- security and synchronization -------------------------------------------


def test_no_own_secret_or_token_is_ever_sent(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])
    host_id = ctx["host"]["player"]["id"]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            _send(host_socket, "match.start", request_id="start-security")
            received = [
                _expect(host_socket, "match.started"),
                _expect(host_socket, "match.state"),
            ]
            _expect(guest_socket, "match.started")
            match_id = received[1]["payload"]["match"]["id"]

            guest_state = _state(client, guest_token, match_id)
            own_secret = next(
                opponent["character"]["id"]
                for opponent in guest_state["opponents"]
                if opponent["owner_id"] == host_id
            )

            for message in received:
                serialized = json.dumps(message)
                assert own_secret not in serialized
                assert host_token not in serialized
                assert guest_token not in serialized


def test_reconnect_during_match_restores_personalized_match_state(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")
            state = _start_match_ws(host_socket)
            _expect(guest_socket, "match.started")
            match_id = state["payload"]["match"]["id"]

    with _open(client, ctx["code"], host_token) as reconnected:
        snapshot = reconnected.receive_json()
        assert snapshot["event"] == "match.state"
        assert reconnected.receive_json()["event"] == "player.connected"
        assert snapshot["payload"]["match"]["id"] == match_id
        assert snapshot["payload"]["self"]["player_id"] == ctx["host"]["player"]["id"]
        assert snapshot["payload"]["identity_assigned"] is True

        _send(reconnected, "match.get_state", request_id="sync-1")
        refreshed = _expect(reconnected, "match.state")
        assert refreshed["request_id"] == "sync-1"
        assert refreshed["payload"]["match"]["id"] == match_id


def test_team_question_visibility_hides_own_team_secret(
    client: TestClient,
    db_session: Session,
) -> None:
    ctx = _setup_room(client, settings={"game_mode": "team"})
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])
    room_id = ctx["room_id"]

    def create_team(name: str) -> dict[str, Any]:
        response = client.post(
            f"/api/rooms/{room_id}/teams",
            headers=auth_headers(host_token),
            json={"name": name},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def assign(player_id: str, team_id: str) -> None:
        response = client.put(
            f"/api/rooms/{room_id}/players/{player_id}/team",
            headers=auth_headers(host_token),
            json={"team_id": team_id},
        )
        assert response.status_code == 200, response.text

    team_one = create_team("Alpha")
    team_two = create_team("Beta")
    assign(ctx["host"]["player"]["id"], team_one["id"])
    assign(ctx["members"][1]["player"]["id"], team_two["id"])

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")

            _send(host_socket, "match.start", request_id="team-start")
            started = _expect(host_socket, "match.started")
            state = _expect(host_socket, "match.state")
            _expect(guest_socket, "match.started")
            match_id = state["payload"]["match"]["id"]
            assert started["payload"]["status"] == "active"

            db_session.expire_all()
            own_assignment = db_session.scalar(
                select(Assignment).where(
                    Assignment.match_id == uuid.UUID(match_id),
                    Assignment.team_id == uuid.UUID(team_one["id"]),
                )
            )
            assert own_assignment is not None
            assert str(own_assignment.character_id) not in json.dumps(state)

            asker_is_host = state["payload"]["match"]["current_turn_id"] == team_one["id"]
            asker_socket, recipient_socket = (
                (host_socket, guest_socket) if asker_is_host else (guest_socket, host_socket)
            )
            opponent_team = team_two["id"] if asker_is_host else team_one["id"]

            _send(
                asker_socket,
                "question.submit",
                {"content": "Is it a hero?", "recipient_team_id": opponent_team},
                request_id="team-question",
            )
            question = _expect(recipient_socket, "question.received")
            assert question["payload"]["recipient_team_id"] == opponent_team

            _send(asker_socket, "room.get_state", request_id="team-sync")
            assert _expect(asker_socket, "room.state")["request_id"] == "team-sync"


def test_persisted_event_sequence_is_ordered_and_gapless(client: TestClient) -> None:
    ctx = _setup_room(client)
    host_token = _token(ctx["host"])
    guest_token = _token(ctx["members"][1])
    host_player_id = ctx["host"]["player"]["id"]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            _drain_connect(guest_socket)
            _expect(host_socket, "player.connected")
            state = _start_match_ws(host_socket)
            _expect(guest_socket, "match.started")
            match_id = state["payload"]["match"]["id"]

            asker_is_host = state["payload"]["match"]["current_turn_id"] == host_player_id
            asker_socket, recipient_socket = (
                (host_socket, guest_socket) if asker_is_host else (guest_socket, host_socket)
            )
            recipient_id = ctx["members"][1]["player"]["id"] if asker_is_host else host_player_id

            _send(
                asker_socket,
                "question.submit",
                {"content": "A question?", "recipient_player_id": recipient_id},
                request_id="seq-question",
            )
            question = _expect(recipient_socket, "question.received")
            _send(
                recipient_socket,
                "answer.submit",
                {"content": "An answer.", "question_id": question["payload"]["question_id"]},
                request_id="seq-answer",
            )
            _expect(asker_socket, "answer.received")
            _expect(asker_socket, "match.turn_changed")
            _expect(recipient_socket, "match.turn_changed")

    history = client.get(
        f"/api/matches/{match_id}/history",
        headers=auth_headers(host_token),
    )
    assert history.status_code == 200, history.text
    events = history.json()["events"]
    sequences = [event["sequence_number"] for event in events]
    assert sequences == list(range(1, len(events) + 1))
    event_types = [event["event_type"] for event in events]
    assert event_types[:4] == [
        "match_created",
        "match_started",
        "question_sent",
        "answer_sent",
    ]


def test_unexpected_handler_failure_returns_internal_error(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    ctx = _setup_room(client)

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(handlers_module, "dispatch", boom)

    with _open(client, ctx["code"], _token(ctx["host"])) as socket:
        _drain_connect(socket)
        _send(socket, "room.get_state", request_id="boom")
        error = _expect(socket, "error")
        assert error["payload"]["code"] == "internal_error"
