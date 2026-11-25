"""Full multi-client gameplay over the real REST and WebSocket endpoints.

These tests deliberately use independent WebSocket connections (one per player),
the same HTTP endpoints the browser uses, and the database only for optional
inspection. Secrets are learned the way a legitimate client would learn an
opponent's character: from the opponent's personalized match state.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from tests.api_helpers import auth_headers, create_room, join_room

PNG_PIXEL = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _token(member: dict[str, Any]) -> str:
    return member["credentials"]["session_token"]


def _ws_url(code: str, token: str) -> str:
    return f"/ws/rooms/{code}?token={token}"


def _open(client: TestClient, code: str, token: str) -> Any:
    return client.websocket_connect(_ws_url(code, token))


def _expect(socket: Any, event: str) -> dict[str, Any]:
    message = socket.receive_json()
    assert message["event"] == event, message
    return message


def _send(
    socket: Any,
    event: str,
    payload: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    socket.send_json({"event": event, "payload": payload or {}, **extra})


def _drain_connect(socket: Any) -> dict[str, Any]:
    snapshot = socket.receive_json()
    assert snapshot["event"] == "room.state", snapshot
    _expect(socket, "player.connected")
    return snapshot


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
    character_ids = []
    for index in range(characters):
        response = client.post(
            f"/api/rooms/{room_id}/characters",
            headers=auth_headers(_token(members[index % len(members)])),
            data={
                "name": f"Char{index}",
                "franchise": "Test",
                "category": "anime",
                "attributes": "{}",
            },
            files={"image": ("c.png", PNG_PIXEL, "image/png")},
        )
        assert response.status_code == 201, response.text
        character_ids.append(response.json()["id"])
    return {
        "host": host,
        "members": members,
        "room_id": room_id,
        "code": code,
        "character_ids": character_ids,
    }


def _state(client: TestClient, token: str, match_id: str) -> dict[str, Any]:
    response = client.get(f"/api/matches/{match_id}/state", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def _history(client: TestClient, token: str, match_id: str, suffix: str = "") -> dict[str, Any]:
    response = client.get(
        f"/api/matches/{match_id}/history{suffix}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _secret_seen_by_opponent(
    client: TestClient,
    opponent_token: str,
    match_id: str,
    *,
    owner_id: str,
) -> str:
    """Read the viewer's own secret from an opponent's personalized state."""
    opponent_state = _state(client, opponent_token, match_id)
    return next(
        entry["character"]["id"]
        for entry in opponent_state["opponents"]
        if entry["owner_id"] == owner_id
    )


def _start_match(socket: Any, request_id: str = "start-1") -> dict[str, Any]:
    _send(socket, "match.start", request_id=request_id)
    _expect(socket, "match.started")
    return _expect(socket, "match.state")


def test_individual_match_complete_flow_with_reconnect(client: TestClient) -> None:
    ctx = _setup_room(client)
    host, guest = ctx["members"]
    host_token, guest_token = _token(host), _token(guest)
    host_id, guest_id = host["player"]["id"], guest["player"]["id"]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            guest_snapshot = guest_socket.receive_json()
            assert guest_snapshot["event"] == "room.state", guest_snapshot
            _expect(guest_socket, "player.connected")
            _expect(host_socket, "player.connected")

            host_state = _start_match(host_socket)
            _expect(guest_socket, "match.started")
            match_id = host_state["payload"]["match"]["id"]

            # Each player sees only the opponent, never an entry for themselves.
            host_opponents = host_state["payload"]["opponents"]
            assert [entry["owner_id"] for entry in host_opponents] == [guest_id]
            guest_state = _state(client, guest_token, match_id)
            assert [entry["owner_id"] for entry in guest_state["opponents"]] == [host_id]

            host_secret = _secret_seen_by_opponent(client, guest_token, match_id, owner_id=host_id)
            guest_secret = _secret_seen_by_opponent(client, host_token, match_id, owner_id=guest_id)
            assert host_secret not in json.dumps(host_state)
            assert guest_secret not in json.dumps(guest_state)
            assert host_state["payload"]["identity_revealed"] is False
            assert guest_state["identity_revealed"] is False

            # Reconnect one client during the active match; state is restored.
            guest_socket.close()
            _expect(host_socket, "player.disconnected")
            with _open(client, ctx["code"], guest_token) as reconnected:
                restored = reconnected.receive_json()
                assert restored["event"] == "match.state", restored
                assert restored["payload"]["match"]["id"] == match_id
                assert restored["payload"]["self"]["player_id"] == guest_id
                assert restored["payload"]["identity_assigned"] is True
                _expect(reconnected, "player.connected")
                _expect(host_socket, "player.connected")
                guest_socket = reconnected  # type: ignore[assignment]

                # Both participants see the recorded history after reconnecting.
                active_history = _history(client, host_token, match_id)
                events = active_history["events"]
                assert [event["sequence_number"] for event in events] == [1, 2]
                assert [event["event_type"] for event in events] == [
                    "match_created",
                    "match_started",
                ]
                page = _history(client, host_token, match_id, "?limit=1")
                assert page["has_more"] is True
                assert page["next_after_sequence"] == 1
                second_page = _history(client, host_token, match_id, "?limit=10&after_sequence=1")
                assert [event["sequence_number"] for event in second_page["events"]] == [2]

                # One question/answer exchange on the active turn.
                current_state = _state(client, host_token, match_id)
                host_is_asker = current_state["match"]["current_turn_id"] == host_id
                asker_socket, recipient_socket = (
                    (host_socket, guest_socket) if host_is_asker else (guest_socket, host_socket)
                )
                asker_token = host_token if host_is_asker else guest_token
                recipient_token = guest_token if host_is_asker else host_token
                recipient_id = guest_id if host_is_asker else host_id

                _send(
                    asker_socket,
                    "question.submit",
                    {"content": "Is your character human?", "recipient_player_id": recipient_id},
                    request_id="question-1",
                )
                question = _expect(recipient_socket, "question.received")
                assert question["payload"]["recipient_player_id"] == recipient_id
                _send(
                    recipient_socket,
                    "answer.submit",
                    {"content": "Yes.", "question_id": question["payload"]["question_id"]},
                    request_id="answer-1",
                )
                assert _expect(asker_socket, "answer.received")["payload"]["answer"] == "Yes."
                assert _expect(asker_socket, "match.turn_changed")["payload"]["current_turn_id"]
                assert _expect(recipient_socket, "match.turn_changed")["payload"]["current_turn_id"]

                # An incorrect guess by the asker is private, allowed outside the
                # turn, and leaves the match active with the same turn.
                before_guess = _state(client, asker_token, match_id)
                wrong_character = before_guess["opponents"][0]["character"]["id"]
                _send(
                    asker_socket,
                    "guess.submit",
                    {"character_id": wrong_character},
                    request_id="wrong-1",
                )
                assert _expect(asker_socket, "guess.incorrect")["payload"]["correct"] is False
                after_wrong = _state(client, asker_token, match_id)
                assert after_wrong["match"]["status"] == "active"
                assert (
                    after_wrong["match"]["current_turn_id"]
                    == (before_guess["match"]["current_turn_id"])
                )
                # The opponent receives no guess event.
                _send(recipient_socket, "room.get_state", request_id="no-guess-broadcast")
                assert _expect(recipient_socket, "room.state")["request_id"] == (
                    "no-guess-broadcast"
                )

                # A correct guess ends the match for every connected client.
                own_secret = _secret_seen_by_opponent(
                    client,
                    recipient_token,
                    match_id,
                    owner_id=host_id if host_is_asker else guest_id,
                )
                _send(
                    asker_socket,
                    "guess.submit",
                    {"character_id": own_secret},
                    request_id="correct-1",
                )
                for socket in (asker_socket, recipient_socket):
                    finished = _expect(socket, "match.finished")
                    assert finished["payload"]["winner_player_id"] == (
                        host_id if host_is_asker else guest_id
                    )
                    assert finished["payload"]["reason"] == "correct_guess"

                # Replaying the same request id and retrying under a new id are
                # both rejected without appending events.
                finished_history = _history(client, host_token, match_id)
                final_sequence = finished_history["events"][-1]["sequence_number"]
                _send(
                    asker_socket,
                    "guess.submit",
                    {"character_id": own_secret},
                    request_id="correct-1",
                )
                assert _expect(asker_socket, "error")["payload"]["code"] == "duplicate_request"
                _send(
                    asker_socket,
                    "guess.submit",
                    {"character_id": own_secret},
                    request_id="correct-2",
                )
                assert _expect(asker_socket, "error")["payload"]["code"] == "not_found"
                assert (
                    _history(client, host_token, match_id)["events"][-1]["sequence_number"]
                    == final_sequence
                )

                final_state = _state(client, host_token, match_id)
                assert final_state["match"]["status"] == "finished"
                assert final_state["match"]["phase"] == "finished"
                assert final_state["match"]["winner_player_id"] == (
                    host_id if host_is_asker else guest_id
                )
                assert final_state["identity_revealed"] is False

                history_text = json.dumps(_history(client, host_token, match_id))
                # A correct guess deliberately omits the guessed character, so
                # the winner's own secret never enters the event history.
                assert own_secret not in history_text
                assert host_token not in history_text
                assert guest_token not in history_text
                event_types = [event["event_type"] for event in finished_history["events"]]
                assert event_types[:5] == [
                    "match_created",
                    "match_started",
                    "question_sent",
                    "answer_sent",
                    "guess_submitted",
                ]
                assert event_types[-3:] == [
                    "guess_submitted",
                    "guess_correct",
                    "match_finished",
                ]

    # After completion a fresh connection gets the room lobby, and history stays
    # readable through REST while the WebSocket match lookup reports no active match.
    with _open(client, ctx["code"], host_token) as finished_socket:
        snapshot = finished_socket.receive_json()
        assert snapshot["event"] == "room.state", snapshot
        _expect(finished_socket, "player.connected")
        _send(finished_socket, "match.get_state", request_id="after-finish")
        assert _expect(finished_socket, "error")["payload"]["code"] == "not_found"
        assert _history(client, host_token, match_id)["events"]


def _team_setup(client: TestClient) -> dict[str, Any]:
    ctx = _setup_room(client, settings={"game_mode": "team"})
    host_token = _token(ctx["host"])

    def create_team(name: str) -> dict[str, Any]:
        response = client.post(
            f"/api/rooms/{ctx['room_id']}/teams",
            headers=auth_headers(host_token),
            json={"name": name},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def assign(player_id: str, team_id: str) -> None:
        response = client.put(
            f"/api/rooms/{ctx['room_id']}/players/{player_id}/team",
            headers=auth_headers(host_token),
            json={"team_id": team_id},
        )
        assert response.status_code == 200, response.text

    team_one = create_team("Alpha")
    team_two = create_team("Beta")
    assign(ctx["host"]["player"]["id"], team_one["id"])
    assign(ctx["members"][1]["player"]["id"], team_two["id"])
    ctx["teams"] = (team_one, team_two)
    return ctx


def test_team_match_complete_flow_hides_own_team_secret(client: TestClient) -> None:
    ctx = _team_setup(client)
    host, guest = ctx["members"]
    host_token, guest_token = _token(host), _token(guest)
    team_one, team_two = ctx["teams"]

    with _open(client, ctx["code"], host_token) as host_socket:
        _drain_connect(host_socket)
        with _open(client, ctx["code"], guest_token) as guest_socket:
            assert guest_socket.receive_json()["event"] == "room.state"
            _expect(guest_socket, "player.connected")
            _expect(host_socket, "player.connected")

            host_state = _start_match(host_socket, "team-start")
            _expect(guest_socket, "match.started")
            match_id = host_state["payload"]["match"]["id"]

            # Team-mode participants are teams, and each state excludes the
            # viewer's own team entry.
            assert [entry["owner_id"] for entry in host_state["payload"]["opponents"]] == [
                team_two["id"]
            ]
            guest_state = _state(client, guest_token, match_id)
            assert [entry["owner_id"] for entry in guest_state["opponents"]] == [team_one["id"]]
            host_team_secret = _secret_seen_by_opponent(
                client, guest_token, match_id, owner_id=team_one["id"]
            )
            guest_team_secret = _secret_seen_by_opponent(
                client, host_token, match_id, owner_id=team_two["id"]
            )
            assert host_team_secret not in json.dumps(host_state)
            assert guest_team_secret not in json.dumps(guest_state)

            current_state = _state(client, host_token, match_id)
            host_team_asks = current_state["match"]["current_turn_id"] == team_one["id"]
            asker_socket, recipient_socket = (
                (host_socket, guest_socket) if host_team_asks else (guest_socket, host_socket)
            )
            asker_token = host_token if host_team_asks else guest_token
            recipient_token = guest_token if host_team_asks else host_token
            opponent_team_id = team_two["id"] if host_team_asks else team_one["id"]
            own_team_id = team_one["id"] if host_team_asks else team_two["id"]

            _send(
                asker_socket,
                "question.submit",
                {
                    "content": "Is your team's character from a game?",
                    "recipient_team_id": opponent_team_id,
                },
                request_id="team-question",
            )
            question = _expect(recipient_socket, "question.received")
            assert question["payload"]["recipient_team_id"] == opponent_team_id
            _send(
                recipient_socket,
                "answer.submit",
                {"content": "No, an anime.", "question_id": question["payload"]["question_id"]},
                request_id="team-answer",
            )
            assert _expect(asker_socket, "answer.received")["payload"]["answer"] == (
                "No, an anime."
            )
            _expect(asker_socket, "match.turn_changed")
            _expect(recipient_socket, "match.turn_changed")

            wrong_character = _state(client, asker_token, match_id)["opponents"][0]["character"][
                "id"
            ]
            _send(
                asker_socket,
                "guess.submit",
                {"character_id": wrong_character},
                request_id="team-wrong",
            )
            assert _expect(asker_socket, "guess.incorrect")["payload"]["correct"] is False
            assert _state(client, asker_token, match_id)["match"]["status"] == "active"

            own_team_secret = _secret_seen_by_opponent(
                client, recipient_token, match_id, owner_id=own_team_id
            )
            _send(
                asker_socket,
                "guess.submit",
                {"character_id": own_team_secret},
                request_id="team-correct",
            )
            for socket in (asker_socket, recipient_socket):
                finished = _expect(socket, "match.finished")
                assert finished["payload"]["winner_team_id"] == own_team_id
                assert finished["payload"]["winner_player_id"] is None

            final_state = _state(client, host_token, match_id)
            assert final_state["match"]["status"] == "finished"
            assert final_state["match"]["winner_team_id"] == own_team_id
            assert final_state["identity_revealed"] is False

            history = _history(client, host_token, match_id)
            sequences = [event["sequence_number"] for event in history["events"]]
            assert sequences == list(range(1, len(sequences) + 1))
            assert history["events"][-1]["event_type"] == "match_finished"
            history_text = json.dumps(history)
            assert own_team_secret not in history_text
            assert host_token not in history_text
            assert guest_token not in history_text
