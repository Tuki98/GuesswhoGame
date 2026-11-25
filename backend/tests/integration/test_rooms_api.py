"""HTTP integration tests for room creation, joining, and administration."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_session_token
from app.database.base import utc_now
from app.models import Room, RoomStatus
from tests.api_helpers import auth_headers, create_room, get_player, join_room
from tests.factories import TEST_SECRET


def test_create_room_returns_host_membership_and_credentials(client: TestClient) -> None:
    body = create_room(client, nickname="Alice")

    room = body["room"]
    assert room["status"] == "waiting"
    assert room["code"].startswith("GTC-")
    assert room["player_count"] == 1
    assert room["settings"] == {"max_players": 8, "game_mode": "individual"}
    assert room["host_player_id"] == body["player"]["id"]

    assert body["player"]["nickname"] == "Alice"
    assert body["player"]["is_host"] is True
    assert body["player"]["is_connected"] is True
    assert body["player"]["is_ready"] is False

    credentials = body["credentials"]
    assert credentials["token_type"] == "bearer"
    assert credentials["session_token"]
    assert credentials["reconnect_token"]
    assert credentials["session_token"] != credentials["reconnect_token"]
    assert credentials["session_expires_at"]
    assert credentials["reconnect_expires_at"]


def test_created_invitation_codes_are_unique(client: TestClient) -> None:
    codes = {create_room(client, nickname=f"Host {index}")["room"]["code"] for index in range(8)}

    assert len(codes) == 8


def test_create_room_accepts_custom_settings(client: TestClient) -> None:
    body = create_room(
        client,
        settings={"max_players": 4, "game_mode": "team"},
    )

    assert body["room"]["settings"] == {"max_players": 4, "game_mode": "team"}


def test_create_room_rejects_invalid_nickname(client: TestClient) -> None:
    response = client.post("/api/rooms", json={"nickname": "a"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_create_room_rejects_invalid_settings(client: TestClient) -> None:
    response = client.post(
        "/api/rooms",
        json={"nickname": "Alice", "settings": {"max_players": 1}},
    )

    assert response.status_code == 422


def test_create_room_rejects_unknown_settings(client: TestClient) -> None:
    response = client.post(
        "/api/rooms",
        json={"nickname": "Alice", "settings": {"spectators": True}},
    )

    assert response.status_code == 422


def test_join_room_returns_new_membership(client: TestClient) -> None:
    host = create_room(client)
    body = join_room(client, code=host["room"]["code"], nickname="Bob")

    assert body["room"]["player_count"] == 2
    assert body["player"]["nickname"] == "Bob"
    assert body["player"]["is_host"] is False
    assert body["player"]["id"] != host["player"]["id"]
    assert body["credentials"]["session_token"] != host["credentials"]["session_token"]


def test_join_normalizes_invitation_code(client: TestClient) -> None:
    host = create_room(client)
    code = host["room"]["code"]

    body = join_room(client, code=f"  {code.lower()}  ", nickname="Bob")

    assert body["room"]["id"] == host["room"]["id"]


def test_join_normalizes_nickname(client: TestClient) -> None:
    host = create_room(client, nickname="Alice")

    body = join_room(client, code=host["room"]["code"], nickname="  Bob    Smith  ")

    assert body["player"]["nickname"] == "Bob Smith"


def test_join_unknown_code_returns_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/rooms/join",
        json={"code": "GTC-NOPE", "nickname": "Bob"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_join_rejects_duplicate_nickname(client: TestClient) -> None:
    host = create_room(client, nickname="Alice")

    response = client.post(
        "/api/rooms/join",
        json={"code": host["room"]["code"], "nickname": "Alice"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_join_rejects_case_insensitive_duplicate_nickname(client: TestClient) -> None:
    host = create_room(client, nickname="Alice")

    response = client.post(
        "/api/rooms/join",
        json={"code": host["room"]["code"], "nickname": "aLiCe"},
    )

    assert response.status_code == 409


def test_join_rejects_invalid_nickname(client: TestClient) -> None:
    host = create_room(client)

    response = client.post(
        "/api/rooms/join",
        json={"code": host["room"]["code"], "nickname": "Bad\nName"},
    )

    assert response.status_code == 422


def test_join_rejects_full_room(client: TestClient) -> None:
    host = create_room(client, settings={"max_players": 2})
    join_room(client, code=host["room"]["code"], nickname="Bob")

    response = client.post(
        "/api/rooms/join",
        json={"code": host["room"]["code"], "nickname": "Carol"},
    )

    assert response.status_code == 409
    assert "full" in response.json()["error"]["message"].lower()

    room = client.get(
        f"/api/rooms/{host['room']['id']}",
        headers=auth_headers(host["credentials"]["session_token"]),
    )
    assert room.json()["player_count"] == 2


def test_join_rejects_closed_room(client: TestClient) -> None:
    host = create_room(client)
    headers = auth_headers(host["credentials"]["session_token"])
    client.post(f"/api/rooms/{host['room']['id']}/close", headers=headers)

    response = client.post(
        "/api/rooms/join",
        json={"code": host["room"]["code"], "nickname": "Bob"},
    )

    assert response.status_code == 409


def test_join_rejects_in_progress_room(client: TestClient, db_session: Session) -> None:
    host = create_room(client)
    room = db_session.get(Room, uuid.UUID(host["room"]["id"]))
    assert room is not None
    room.status = RoomStatus.IN_PROGRESS
    db_session.commit()

    response = client.post(
        "/api/rooms/join",
        json={"code": host["room"]["code"], "nickname": "Bob"},
    )

    assert response.status_code == 409


def test_get_room_returns_public_lobby(client: TestClient) -> None:
    host = create_room(client)
    join_room(client, code=host["room"]["code"], nickname="Bob")
    headers = auth_headers(host["credentials"]["session_token"])

    response = client.get(f"/api/rooms/{host['room']['id']}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == host["room"]["id"]
    assert body["player_count"] == 2
    assert "session_token" not in body
    assert host["credentials"]["session_token"] not in response.text


def test_get_room_requires_authentication(client: TestClient) -> None:
    host = create_room(client)

    response = client.get(f"/api/rooms/{host['room']['id']}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"
    assert response.headers["www-authenticate"] == "Bearer"


def test_get_room_rejects_non_member(client: TestClient) -> None:
    first = create_room(client, nickname="Alice")
    second = create_room(client, nickname="Bob")

    response = client.get(
        f"/api/rooms/{second['room']['id']}",
        headers=auth_headers(first["credentials"]["session_token"]),
    )

    assert response.status_code == 404


def test_list_players_returns_public_fields(client: TestClient) -> None:
    host = create_room(client, nickname="Alice")
    join_room(client, code=host["room"]["code"], nickname="Bob")
    headers = auth_headers(host["credentials"]["session_token"])

    response = client.get(
        f"/api/rooms/{host['room']['id']}/players",
        headers=headers,
    )

    assert response.status_code == 200
    players = response.json()["players"]
    assert [player["nickname"] for player in players] == ["Alice", "Bob"]
    assert [player["is_host"] for player in players] == [True, False]
    assert all("session_token" not in player for player in players)


def test_host_updates_room_settings(client: TestClient) -> None:
    host = create_room(client, nickname="Alice")
    headers = auth_headers(host["credentials"]["session_token"])

    response = client.patch(
        f"/api/rooms/{host['room']['id']}/settings",
        json={"max_players": 6},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["settings"] == {"max_players": 6, "game_mode": "individual"}


def test_non_host_cannot_update_settings(client: TestClient) -> None:
    host = create_room(client)
    guest = join_room(client, code=host["room"]["code"], nickname="Bob")

    response = client.patch(
        f"/api/rooms/{host['room']['id']}/settings",
        json={"max_players": 6},
        headers=auth_headers(guest["credentials"]["session_token"]),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_settings_update_requires_a_change(client: TestClient) -> None:
    host = create_room(client)

    response = client.patch(
        f"/api/rooms/{host['room']['id']}/settings",
        json={},
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 422


def test_settings_capacity_cannot_drop_below_player_count(client: TestClient) -> None:
    host = create_room(client, nickname="Alice")
    join_room(client, code=host["room"]["code"], nickname="Bob")
    join_room(client, code=host["room"]["code"], nickname="Carol")

    response = client.patch(
        f"/api/rooms/{host['room']['id']}/settings",
        json={"max_players": 2},
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 409


def test_host_removes_participant_and_revokes_their_session(client: TestClient) -> None:
    host = create_room(client)
    guest = join_room(client, code=host["room"]["code"], nickname="Bob")
    host_headers = auth_headers(host["credentials"]["session_token"])

    response = client.delete(
        f"/api/rooms/{host['room']['id']}/players/{guest['player']['id']}",
        headers=host_headers,
    )

    assert response.status_code == 204

    revoked = client.get(
        f"/api/rooms/{host['room']['id']}",
        headers=auth_headers(guest["credentials"]["session_token"]),
    )
    assert revoked.status_code == 401

    room = client.get(f"/api/rooms/{host['room']['id']}", headers=host_headers)
    assert room.json()["player_count"] == 1


def test_non_host_cannot_remove_participant(client: TestClient) -> None:
    host = create_room(client)
    guest = join_room(client, code=host["room"]["code"], nickname="Bob")
    other = join_room(client, code=host["room"]["code"], nickname="Carol")

    response = client.delete(
        f"/api/rooms/{host['room']['id']}/players/{other['player']['id']}",
        headers=auth_headers(guest["credentials"]["session_token"]),
    )

    assert response.status_code == 403


def test_host_cannot_remove_themselves(client: TestClient) -> None:
    host = create_room(client)

    response = client.delete(
        f"/api/rooms/{host['room']['id']}/players/{host['player']['id']}",
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 409


def test_removing_unknown_player_returns_not_found(client: TestClient) -> None:
    host = create_room(client)

    response = client.delete(
        f"/api/rooms/{host['room']['id']}/players/{uuid.uuid4()}",
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 404


def test_non_host_leaves_room_and_loses_access(client: TestClient) -> None:
    host = create_room(client)
    guest = join_room(client, code=host["room"]["code"], nickname="Bob")
    guest_headers = auth_headers(guest["credentials"]["session_token"])

    response = client.post(
        f"/api/rooms/{host['room']['id']}/leave",
        headers=guest_headers,
    )

    assert response.status_code == 204
    assert client.get(f"/api/rooms/{host['room']['id']}", headers=guest_headers).status_code == 401


def test_host_cannot_leave_room(client: TestClient) -> None:
    host = create_room(client)

    response = client.post(
        f"/api/rooms/{host['room']['id']}/leave",
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 409


def test_host_closes_room(client: TestClient) -> None:
    host = create_room(client)
    headers = auth_headers(host["credentials"]["session_token"])

    response = client.post(f"/api/rooms/{host['room']['id']}/close", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_non_host_cannot_close_room(client: TestClient) -> None:
    host = create_room(client)
    guest = join_room(client, code=host["room"]["code"], nickname="Bob")

    response = client.post(
        f"/api/rooms/{host['room']['id']}/close",
        headers=auth_headers(guest["credentials"]["session_token"]),
    )

    assert response.status_code == 403


def test_closing_a_closed_room_conflicts(client: TestClient) -> None:
    host = create_room(client)
    headers = auth_headers(host["credentials"]["session_token"])
    client.post(f"/api/rooms/{host['room']['id']}/close", headers=headers)

    response = client.post(f"/api/rooms/{host['room']['id']}/close", headers=headers)

    assert response.status_code == 409


def test_settings_and_removal_blocked_outside_waiting(
    client: TestClient, db_session: Session
) -> None:
    host = create_room(client)
    guest = join_room(client, code=host["room"]["code"], nickname="Bob")
    room = db_session.get(Room, uuid.UUID(host["room"]["id"]))
    assert room is not None
    room.status = RoomStatus.IN_PROGRESS
    db_session.commit()
    headers = auth_headers(host["credentials"]["session_token"])

    settings = client.patch(
        f"/api/rooms/{host['room']['id']}/settings",
        json={"max_players": 6},
        headers=headers,
    )
    removal = client.delete(
        f"/api/rooms/{host['room']['id']}/players/{guest['player']['id']}",
        headers=headers,
    )

    assert settings.status_code == 409
    assert removal.status_code == 409


def test_host_can_close_in_progress_room(client: TestClient, db_session: Session) -> None:
    host = create_room(client)
    room = db_session.get(Room, uuid.UUID(host["room"]["id"]))
    assert room is not None
    room.status = RoomStatus.IN_PROGRESS
    db_session.commit()

    response = client.post(
        f"/api/rooms/{host['room']['id']}/close",
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_expired_session_is_rejected(client: TestClient, db_session: Session) -> None:
    host = create_room(client)
    player = get_player(db_session, host["player"]["id"])
    player.session_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = client.get(
        f"/api/rooms/{host['room']['id']}",
        headers=auth_headers(host["credentials"]["session_token"]),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"


def test_invalid_and_malformed_tokens_are_rejected(client: TestClient) -> None:
    host = create_room(client)

    for value in ("not-a-real-token", "Bearer", "Basic abc"):
        response = client.get(
            f"/api/rooms/{host['room']['id']}",
            headers={"Authorization": value},
        )
        assert response.status_code == 401


def test_raw_tokens_are_not_persisted(client: TestClient, db_session: Session) -> None:
    host = create_room(client)
    player = get_player(db_session, host["player"]["id"])

    session_token = host["credentials"]["session_token"]
    reconnect_token = host["credentials"]["reconnect_token"]

    assert player.session_token_hash != session_token
    assert player.session_token_hash == hash_session_token(session_token, secret_key=TEST_SECRET)
    assert player.reconnect_token_hash == hash_session_token(
        reconnect_token, secret_key=TEST_SECRET
    )
    assert len(player.session_token_hash) == 64
