"""Security, edge-case, and service-behavior tests for the game engine."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.models import Assignment, GameEvent, Match, Player, RoomStatus
from app.services.matches import MatchService
from tests.api_helpers import auth_headers, create_room, get_player, join_room
from tests.factories import make_character, make_player, make_room

PNG_PIXEL = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _add_character(client: TestClient, token: str, room_id: str, name: str) -> dict[str, Any]:
    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": name, "franchise": "F", "category": "anime", "attributes": "{}"},
        files={"image": ("c.png", PNG_PIXEL, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup(client: TestClient, n: int = 3) -> dict[str, Any]:
    host = create_room(client, nickname="Host")
    room_id = host["room"]["id"]
    members = [host]
    for i in range(n - 1):
        members.append(join_room(client, code=host["room"]["code"], nickname=f"P{i}"))
    for i, m in enumerate(members):
        _add_character(client, m["credentials"]["session_token"], room_id, f"C{i}")
    start = client.post(
        f"/api/rooms/{room_id}/matches", headers=auth_headers(host["credentials"]["session_token"])
    )
    assert start.status_code == 201
    return {
        "host": host,
        "members": members,
        "room_id": room_id,
        "state": start.json(),
        "match_id": start.json()["match"]["id"],
    }


def test_own_secret_never_appears_and_assignment_table_not_exposed(client: TestClient) -> None:
    ctx = _setup(client, 3)
    match_id = ctx["match_id"]
    for member in ctx["members"]:
        resp = client.get(
            f"/api/matches/{match_id}/state",
            headers=auth_headers(member["credentials"]["session_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Explicitly ensure no assignment-table-like fields leak into state.
        assert "character_id_to_owner" not in resp.text
        assert body["identity_assigned"] is True
        assert body["identity_revealed"] is False
        # Own player/team identity block must not contain secret character fields
        self_block = body["self"]
        assert "character" not in self_block
        assert "secret" not in str(self_block).lower()

    details = client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert "assignments" not in details.text.lower()


def test_history_contains_no_credentials(client: TestClient) -> None:
    ctx = _setup(client, 2)
    history = client.get(
        f"/api/matches/{ctx['match_id']}/history",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    ).json()
    text = str(history).lower()
    assert "session_token" not in text
    assert "reconnect_token" not in text
    assert "token_hash" not in text


def test_guess_outside_active_turn_is_allowed(client: TestClient) -> None:
    ctx = _setup(client, 3)
    # Find a member who is not the active asker.
    active_id = ctx["state"]["match"]["current_turn_id"]
    other = next(m for m in ctx["members"] if m["player"]["id"] != active_id)
    chars = client.get(
        f"/api/rooms/{ctx['room_id']}/characters",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    ).json()["characters"]
    # submit guess as non-active player (allowed anytime)
    resp = client.post(
        f"/api/matches/{ctx['match_id']}/guesses",
        headers=auth_headers(other["credentials"]["session_token"]),
        json={"character_id": chars[0]["id"]},
    )
    assert resp.status_code == 200


def test_disconnected_player_does_not_break_turn_state(
    client: TestClient, db_session: Session
) -> None:
    ctx = _setup(client, 3)
    match_id = ctx["match_id"]
    active_id = uuid.UUID(ctx["state"]["match"]["current_turn_id"])
    active = get_player(db_session, str(active_id))
    active.is_connected = False
    db_session.commit()

    state = client.get(
        f"/api/matches/{match_id}/state",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    ).json()
    assert state["match"]["current_turn_id"] == str(active_id)
    # Disconnected players keep their turn/session state in this phase.
    asker = next(m for m in ctx["members"] if m["player"]["id"] == str(active_id))
    recipient = next(m for m in ctx["members"] if m["player"]["id"] != str(active_id))
    resp = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "Still works?", "recipient_player_id": recipient["player"]["id"]},
    )
    assert resp.status_code == 201


def test_start_assignment_failure_rolls_back_match_and_room(
    db_session: Session, settings: Settings
) -> None:
    # Impossible derangement: host contributed both characters, so host cannot
    # receive either while guest can receive only one; no valid matching exists.
    room = make_room(db_session, code="GTC-ROLL")
    host = make_player(db_session, room, nickname="Host", is_host=True)
    make_player(db_session, room, nickname="Guest")
    make_character(db_session, room, name="A", contributed_by=host)
    make_character(db_session, room, name="B", contributed_by=host)
    db_session.commit()

    service = MatchService(db_session)
    with pytest.raises(ConflictError):
        service.start_match(room.id, host)

    db_session.rollback()
    db_session.expire_all()
    # No match/assignment/event created and room still waiting.
    assert db_session.query(Match).count() == 0
    assert db_session.query(Assignment).count() == 0
    assert db_session.query(GameEvent).count() == 0
    refreshed_room = db_session.get(type(room), room.id)
    assert refreshed_room is not None
    assert refreshed_room.status == RoomStatus.WAITING


def test_finished_match_rejects_questions_answers_and_cancellation(client: TestClient) -> None:
    ctx = _setup(client, 2)
    match_id = ctx["match_id"]
    chars = client.get(
        f"/api/rooms/{ctx['room_id']}/characters",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    ).json()["characters"]
    # win
    winner = ctx["members"][0]
    for char in chars:
        resp = client.post(
            f"/api/matches/{match_id}/guesses",
            headers=auth_headers(winner["credentials"]["session_token"]),
            json={"character_id": char["id"]},
        )
        if resp.json().get("correct"):
            break
    asker = ctx["members"][0]
    other = ctx["members"][1]
    q = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "Q", "recipient_player_id": other["player"]["id"]},
    )
    assert q.status_code == 409
    cancel = client.post(
        f"/api/matches/{match_id}/cancel",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert cancel.status_code == 409


def test_service_start_persists_unique_derangement(db_session: Session) -> None:
    room = make_room(db_session, code="GTC-4E2")
    host = make_player(db_session, room, nickname="Host", is_host=True)
    guest = make_player(db_session, room, nickname="Guest")
    expert = make_player(db_session, room, nickname="Expert")
    characters = [
        make_character(db_session, room, name=f"C{index}", contributed_by=owner)
        for index, owner in enumerate((host, guest, expert))
    ]
    db_session.commit()

    state = MatchService(db_session).start_match(room.id, host)
    db_session.expire_all()
    match = db_session.get(Match, state.match.id)
    assignments = db_session.query(Assignment).filter(Assignment.match_id == match.id).all()
    assert len(assignments) == 3
    assigned_character_ids = {assignment.character_id for assignment in assignments}
    assert len(assigned_character_ids) == 3
    for assignment in assignments:
        assert assignment.character_id in {character.id for character in characters}
        if assignment.player_id is not None:
            owner = db_session.get(Player, assignment.player_id)
            assert owner is not None
            assert assignment.character.contributed_by != owner.id
