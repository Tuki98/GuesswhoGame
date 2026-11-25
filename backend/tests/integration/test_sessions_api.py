"""HTTP integration tests for secure session reconnection and rotation."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.models import Player, Room
from tests.api_helpers import auth_headers, create_room, get_player, join_room
from tests.factories import make_team


def reconnect(client: TestClient, token: str):  # type: ignore[no-untyped-def]
    return client.post("/api/sessions/reconnect", json={"reconnect_token": token})


def test_reconnect_rotates_credentials_and_preserves_identity(
    client: TestClient,
    db_session: Session,
) -> None:
    host = create_room(client, nickname="Alice")
    player = get_player(db_session, host["player"]["id"])
    player.session_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = reconnect(client, host["credentials"]["reconnect_token"])

    assert response.status_code == 200
    body = response.json()
    assert body["player"]["id"] == host["player"]["id"]
    assert body["player"]["nickname"] == "Alice"
    assert body["room"]["id"] == host["room"]["id"]

    credentials = body["credentials"]
    assert credentials["session_token"] != host["credentials"]["session_token"]
    assert credentials["reconnect_token"] != host["credentials"]["reconnect_token"]

    # The new session works and the old credentials are both invalid.
    assert (
        client.get(
            f"/api/rooms/{host['room']['id']}",
            headers=auth_headers(credentials["session_token"]),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/rooms/{host['room']['id']}",
            headers=auth_headers(host["credentials"]["session_token"]),
        ).status_code
        == 401
    )
    assert reconnect(client, host["credentials"]["reconnect_token"]).status_code == 401


def test_reconnect_does_not_create_duplicate_players(
    client: TestClient,
    db_session: Session,
) -> None:
    host = create_room(client)
    join_room(client, code=host["room"]["code"], nickname="Bob")

    response = reconnect(client, host["credentials"]["reconnect_token"])

    assert response.status_code == 200
    assert response.json()["room"]["player_count"] == 2
    count = db_session.scalar(select(func.count()).select_from(Player))
    assert count == 2


def test_reconnect_preserves_team_membership(client: TestClient, db_session: Session) -> None:
    host = create_room(client)
    player = get_player(db_session, host["player"]["id"])
    room = db_session.get(Room, player.room_id)
    assert room is not None
    team = make_team(db_session, room, name="Team Red")
    player.team_id = team.id
    player.is_connected = False
    old_last_seen = utc_now() - timedelta(hours=1)
    player.last_seen_at = old_last_seen
    db_session.commit()

    response = reconnect(client, host["credentials"]["reconnect_token"])

    assert response.status_code == 200
    db_session.expire_all()
    restored = get_player(db_session, host["player"]["id"])
    assert restored.team_id == team.id
    assert restored.is_connected is True
    assert restored.last_seen_at > old_last_seen
    assert response.json()["player"]["is_connected"] is True


def test_reconnect_with_invalid_credential_is_rejected(client: TestClient) -> None:
    response = reconnect(client, "not-a-reconnect-token")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"
    assert response.headers["www-authenticate"] == "Bearer"


def test_reconnect_with_expired_credential_is_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    host = create_room(client)
    player = get_player(db_session, host["player"]["id"])
    player.reconnect_expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = reconnect(client, host["credentials"]["reconnect_token"])

    assert response.status_code == 401


def test_reconnect_after_room_is_closed(client: TestClient) -> None:
    host = create_room(client)
    headers = auth_headers(host["credentials"]["session_token"])
    client.post(f"/api/rooms/{host['room']['id']}/close", headers=headers)

    response = reconnect(client, host["credentials"]["reconnect_token"])

    assert response.status_code == 200
    assert response.json()["room"]["status"] == "closed"


def test_racing_reconnects_only_rotate_once(client: TestClient) -> None:
    host = create_room(client)
    token = host["credentials"]["reconnect_token"]

    first = reconnect(client, token)
    second = reconnect(client, token)

    assert first.status_code == 200
    assert second.status_code == 401


def test_reconnect_requires_a_credential(client: TestClient) -> None:
    response = client.post("/api/sessions/reconnect", json={})

    assert response.status_code == 422


def test_reconnect_response_never_exposes_hashes(client: TestClient) -> None:
    host = create_room(client)

    response = reconnect(client, host["credentials"]["reconnect_token"])
    body = response.json()

    assert "session_token_hash" not in body["player"]
    assert "reconnect_token_hash" not in body["player"]
    assert body["room"]["id"] == host["room"]["id"]
    assert uuid.UUID(body["player"]["id"]) == uuid.UUID(host["player"]["id"])
