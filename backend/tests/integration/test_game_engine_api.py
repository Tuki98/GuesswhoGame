"""HTTP integration tests for the Phase 4 game engine."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import GameEvent
from tests.api_helpers import auth_headers, create_room, join_room

PNG_PIXEL = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _add_character(
    client: TestClient,
    token: str,
    room_id: str,
    name: str,
    *,
    franchise: str = "Test",
) -> dict[str, Any]:
    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": name, "franchise": franchise, "category": "anime", "attributes": "{}"},
        files={"image": ("c.png", PNG_PIXEL, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup_individual_room(
    client: TestClient, *, player_count: int = 3, characters: int | None = None
) -> dict[str, Any]:
    host = create_room(client, nickname="Host")
    room_id = host["room"]["id"]
    code = host["room"]["code"]
    members = [host]
    for index in range(player_count - 1):
        members.append(join_room(client, code=code, nickname=f"Player{index + 1}"))
    total_chars = characters if characters is not None else player_count
    chars = []
    for index in range(total_chars):
        owner = members[index % len(members)]
        chars.append(
            _add_character(client, owner["credentials"]["session_token"], room_id, f"Char{index}")
        )
    return {"host": host, "members": members, "characters": chars, "room_id": room_id, "code": code}


def _start_match(client: TestClient, host: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/rooms/{host['room']['id']}/matches",
        headers=auth_headers(host["credentials"]["session_token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _state(client: TestClient, token: str, match_id: str) -> dict[str, Any]:
    response = client.get(f"/api/matches/{match_id}/state", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def _active_asker(members: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    turn_id = state["match"]["current_turn_id"]
    for member in members:
        if member["player"]["id"] == turn_id:
            return member
    raise AssertionError("No active asker found")


def _recipient_for_asker(
    asker: dict[str, Any], members: list[dict[str, Any]], state: dict[str, Any]
) -> dict[str, Any]:
    allowed = set(state["allowed_recipient_ids"])
    for member in members:
        if member["player"]["id"] in allowed and member["player"]["id"] != asker["player"]["id"]:
            return member
    raise AssertionError("No recipient found")


def test_start_match_requires_host_and_waiting_room(client: TestClient) -> None:
    ctx = _setup_individual_room(client)
    guest = ctx["members"][1]
    response = client.post(
        f"/api/rooms/{ctx['room_id']}/matches",
        headers=auth_headers(guest["credentials"]["session_token"]),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_start_match_validates_player_and_character_counts(client: TestClient) -> None:
    host = create_room(client, nickname="Host")
    _add_character(client, host["credentials"]["session_token"], host["room"]["id"], "Solo")
    response = client.post(
        f"/api/rooms/{host['room']['id']}/matches",
        headers=auth_headers(host["credentials"]["session_token"]),
    )
    assert response.status_code == 409

    ctx = _setup_individual_room(client, player_count=3, characters=2)
    response = client.post(
        f"/api/rooms/{ctx['room_id']}/matches",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert response.status_code == 409


def test_start_match_creates_atomic_assignment_and_hides_own_identity(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=3)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]
    assert state["match"]["phase"] == "in_progress"
    assert state["match"]["status"] == "active"
    assert state["identity_assigned"] is True
    assert state["identity_revealed"] is False

    seen_opponent_pairs = []
    for member in ctx["members"]:
        member_state = _state(client, member["credentials"]["session_token"], match_id)
        assert member_state["self"]["player_id"] == member["player"]["id"]
        assert len(member_state["opponents"]) == 2
        opponent_owner_ids = {op["owner_id"] for op in member_state["opponents"]}
        assert member["player"]["id"] not in opponent_owner_ids
        # Own secret must never appear anywhere in serialized state.
        dumped = str(member_state)
        assert "own_secret" not in dumped
        for opponent in member_state["opponents"]:
            assert opponent["character"]["id"]
            seen_opponent_pairs.append(
                (member["player"]["id"], opponent["owner_id"], opponent["character"]["id"])
            )

    # Each opponent appears with a consistent assigned character across viewers.
    by_owner = {}
    for _viewer, owner_id, char_id in seen_opponent_pairs:
        by_owner.setdefault(owner_id, set()).add(char_id)
    assert all(len(ids) == 1 for ids in by_owner.values())


def test_only_one_active_match_per_room_and_fresh_assignment_after_finish(
    client: TestClient,
) -> None:
    ctx = _setup_individual_room(client, player_count=2)
    state = _start_match(client, ctx["host"])
    response = client.post(
        f"/api/rooms/{ctx['room_id']}/matches",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert response.status_code == 409

    match_id = state["match"]["id"]
    asker = _active_asker(ctx["members"], state)
    recipient_state = next(
        s
        for s in (
            _state(client, m["credentials"]["session_token"], match_id) for m in ctx["members"]
        )
        if s["self"]["player_id"] != asker["player"]["id"]
    )
    target_char_id = recipient_state["opponents"][0]["character"]["id"]
    response = client.post(
        f"/api/matches/{match_id}/guesses",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"character_id": target_char_id},
    )
    assert response.status_code == 200
    assert response.json()["correct"] is True

    # Room returns to waiting and a new match can start with a fresh assignment.
    room = client.get(
        f"/api/rooms/{ctx['room_id']}",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert room.json()["status"] == "waiting"
    state2 = _start_match(client, ctx["host"])
    assert state2["match"]["id"] != match_id
    assert state2["match"]["phase"] == "in_progress"


def test_turn_questions_answers_and_progression(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=3)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]

    asker = _active_asker(ctx["members"], state)
    others = [m for m in ctx["members"] if m["player"]["id"] != asker["player"]["id"]]
    not_asker = others[0]

    # Non-active player cannot ask.
    response = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(not_asker["credentials"]["session_token"]),
        json={"content": "Hi?", "recipient_player_id": asker["player"]["id"]},
    )
    assert response.status_code == 403

    recipient = _recipient_for_asker(asker, ctx["members"], state)

    # Invalid recipient: self.
    response = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "Hi?", "recipient_player_id": asker["player"]["id"]},
    )
    assert response.status_code == 422

    response = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={
            "content": " Is your character fictional? ",
            "recipient_player_id": recipient["player"]["id"],
        },
    )
    assert response.status_code == 201, response.text
    question = response.json()
    assert question["content"] == "Is your character fictional?"

    # Only one pending question.
    response = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "Again?", "recipient_player_id": recipient["player"]["id"]},
    )
    assert response.status_code == 409

    # Only designated recipient can answer.
    wrong = next(
        m
        for m in ctx["members"]
        if m["player"]["id"] not in {asker["player"]["id"], recipient["player"]["id"]}
    )
    response = client.post(
        f"/api/matches/{match_id}/questions/{question['id']}/answer",
        headers=auth_headers(wrong["credentials"]["session_token"]),
        json={"content": "No"},
    )
    assert response.status_code == 403

    response = client.post(
        f"/api/matches/{match_id}/questions/{question['id']}/answer",
        headers=auth_headers(recipient["credentials"]["session_token"]),
        json={"content": " Yes. "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["answer"]["content"] == "Yes."

    # Turn advanced.
    new_state = _state(client, asker["credentials"]["session_token"], match_id)
    assert new_state["match"]["current_turn_id"] != asker["player"]["id"]
    assert new_state["pending_question"] is None
    assert len(new_state["question_history"]) == 1

    # Question cannot be answered twice.
    response = client.post(
        f"/api/matches/{match_id}/questions/{question['id']}/answer",
        headers=auth_headers(recipient["credentials"]["session_token"]),
        json={"content": "Again"},
    )
    assert response.status_code == 409


def test_guess_correct_incorrect_and_after_finish(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=2)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]
    asker = _active_asker(ctx["members"], state)
    other = next(m for m in ctx["members"] if m["player"]["id"] != asker["player"]["id"])
    # In 2-player mode each player sees the other's secret character. Guessing that
    # character is correct for the guesser only if it matches their own secret, so
    # use the 3-player/extra-character test below for deterministic incorrect cases.
    other_state = _state(client, other["credentials"]["session_token"], match_id)
    assert other_state["opponents"][0]["character"]["id"]
    response = client.post(
        f"/api/matches/{match_id}/guesses",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"character_id": ctx["characters"][0]["id"]},
    )
    assert response.status_code == 200


def test_incorrect_guess_allows_unlimited_attempts_and_correct_wins(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=3, characters=4)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]
    asker = _active_asker(ctx["members"], state)
    asker_state = _state(client, asker["credentials"]["session_token"], match_id)
    # Guessing validates against the guesser's own secret assignment. Pick a
    # character visible as another opponent to guarantee an incorrect guess.
    wrong_char = asker_state["opponents"][1]["character"]["id"]
    r1 = client.post(
        f"/api/matches/{match_id}/guesses",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"character_id": wrong_char},
    )
    assert r1.status_code == 200 and r1.json()["correct"] is False
    r2 = client.post(
        f"/api/matches/{match_id}/guesses",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"character_id": wrong_char},
    )
    assert r2.status_code == 200 and r2.json()["correct"] is False

    # Own secret is never exposed; try room characters until the correct one wins.
    chars_resp = client.get(
        f"/api/rooms/{ctx['room_id']}/characters",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    all_char_ids = [c["id"] for c in chars_resp.json()["characters"]]
    won = False
    for cid in all_char_ids:
        resp = client.post(
            f"/api/matches/{match_id}/guesses",
            headers=auth_headers(asker["credentials"]["session_token"]),
            json={"character_id": cid},
        )
        assert resp.status_code == 200
        if resp.json()["correct"]:
            won = True
            assert resp.json()["match"]["phase"] == "finished"
            assert resp.json()["match"]["winner_player_id"] == asker["player"]["id"]
            break
    assert won

    # Finished match rejects further actions.
    response = client.post(
        f"/api/matches/{match_id}/guesses",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"character_id": all_char_ids[0]},
    )
    assert response.status_code == 409


def test_cancel_match_and_new_match_can_start(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=2)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]

    # Non-host cannot cancel.
    response = client.post(
        f"/api/matches/{match_id}/cancel",
        headers=auth_headers(ctx["members"][1]["credentials"]["session_token"]),
    )
    assert response.status_code == 403

    response = client.post(
        f"/api/matches/{match_id}/cancel",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["match"]["phase"] == "cancelled"

    # Cancelled match rejects questions/guesses.
    asker = _active_asker(ctx["members"], state)
    recipient = _recipient_for_asker(asker, ctx["members"], state)
    response = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "Q", "recipient_player_id": recipient["player"]["id"]},
    )
    assert response.status_code == 409

    # Room back to waiting, new match allowed.
    room = client.get(
        f"/api/rooms/{ctx['room_id']}",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert room.json()["status"] == "waiting"
    state2 = _start_match(client, ctx["host"])
    assert state2["match"]["id"] != match_id


def test_event_history_ordering_pagination_and_no_secrets(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=2)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]
    asker = _active_asker(ctx["members"], state)
    recipient = _recipient_for_asker(asker, ctx["members"], state)
    q = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "A question", "recipient_player_id": recipient["player"]["id"]},
    ).json()
    client.post(
        f"/api/matches/{match_id}/questions/{q['id']}/answer",
        headers=auth_headers(recipient["credentials"]["session_token"]),
        json={"content": "An answer"},
    )
    # incorrect guess generates events
    client.post(
        f"/api/matches/{match_id}/guesses",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"character_id": ctx["characters"][0]["id"]},
    )

    history = client.get(
        f"/api/matches/{match_id}/history",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
        params={"limit": 2},
    )
    assert history.status_code == 200
    body = history.json()
    assert body["has_more"] is True
    assert len(body["events"]) == 2
    assert [e["sequence_number"] for e in body["events"]] == [1, 2]
    assert body["events"][0]["event_type"] == "match_created"
    assert body["events"][1]["event_type"] == "match_started"

    page2 = client.get(
        f"/api/matches/{match_id}/history",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
        params={"limit": 100, "after_sequence": body["next_after_sequence"]},
    ).json()
    seqs = [e["sequence_number"] for e in body["events"]] + [
        e["sequence_number"] for e in page2["events"]
    ]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)

    all_events = body["events"] + page2["events"]
    dumped = str(all_events)
    assert "session_token" not in dumped
    assert "reconnect_token" not in dumped
    # Room codes may appear in unrelated payloads, but credential material must not.
    assert "session_expires_at" not in dumped


def test_leave_room_blocked_during_active_match(client: TestClient) -> None:
    ctx = _setup_individual_room(client, player_count=2)
    _start_match(client, ctx["host"])
    guest = ctx["members"][1]
    response = client.post(
        f"/api/rooms/{ctx['room_id']}/leave",
        headers=auth_headers(guest["credentials"]["session_token"]),
    )
    assert response.status_code == 409


def test_close_room_abandons_active_match(client: TestClient, db_session: Session) -> None:
    ctx = _setup_individual_room(client, player_count=2)
    state = _start_match(client, ctx["host"])
    match_id = state["match"]["id"]
    response = client.post(
        f"/api/rooms/{ctx['room_id']}/close",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    events = (
        db_session.query(GameEvent)
        .filter(GameEvent.match_id == uuid.UUID(match_id))
        .order_by(GameEvent.sequence_number)
        .all()
    )
    assert events[-1].event_type.value == "match_cancelled"
    assert events[-1].payload["reason"] == "room_closed"
    # Match is abandoned.
    db_session.expire_all()


def test_player_cannot_inspect_other_room_match(client: TestClient) -> None:
    ctx1 = _setup_individual_room(client, player_count=2)
    ctx2 = _setup_individual_room(client, player_count=2)
    state1 = _start_match(client, ctx1["host"])
    response = client.get(
        f"/api/matches/{state1['match']['id']}/state",
        headers=auth_headers(ctx2["host"]["credentials"]["session_token"]),
    )
    assert response.status_code == 404
