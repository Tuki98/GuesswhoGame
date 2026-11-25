"""Team-mode and team-management integration tests for the game engine."""

from __future__ import annotations

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


def _add_character(client: TestClient, token: str, room_id: str, name: str) -> dict[str, Any]:
    response = client.post(
        f"/api/rooms/{room_id}/characters",
        headers=auth_headers(token),
        data={"name": name, "franchise": "F", "category": "anime", "attributes": "{}"},
        files={"image": ("c.png", PNG_PIXEL, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _setup_team_room(client: TestClient) -> dict[str, Any]:
    host = create_room(client, nickname="Host", settings={"max_players": 8, "game_mode": "team"})
    room_id = host["room"]["id"]
    code = host["room"]["code"]
    members = [host]
    for name in ["A2", "B1", "B2"]:
        members.append(join_room(client, code=code, nickname=name))
    # 4 players, 2 teams of 2, 2+ chars
    chars = []
    for index, member in enumerate(members):
        chars.append(
            _add_character(client, member["credentials"]["session_token"], room_id, f"Char{index}")
        )
    htok = host["credentials"]["session_token"]
    t1 = client.post(
        f"/api/rooms/{room_id}/teams", headers=auth_headers(htok), json={"name": "Alpha"}
    ).json()
    t2 = client.post(
        f"/api/rooms/{room_id}/teams", headers=auth_headers(htok), json={"name": "Beta"}
    ).json()
    # assign: host+A2 -> Alpha, B1+B2 -> Beta
    assignments = [
        (members[0]["player"]["id"], t1["id"]),
        (members[1]["player"]["id"], t1["id"]),
        (members[2]["player"]["id"], t2["id"]),
        (members[3]["player"]["id"], t2["id"]),
    ]
    for pid, tid in assignments:
        resp = client.put(
            f"/api/rooms/{room_id}/players/{pid}/team",
            headers=auth_headers(htok),
            json={"team_id": tid},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["team"]["id"] == tid
    teams = client.get(f"/api/rooms/{room_id}/teams", headers=auth_headers(htok)).json()["teams"]
    return {
        "host": host,
        "members": members,
        "room_id": room_id,
        "teams": teams,
        "t1": t1,
        "t2": t2,
        "characters": chars,
    }


def test_team_management_requires_host_and_waiting_room(client: TestClient) -> None:
    host = create_room(client, nickname="Host", settings={"game_mode": "team"})
    guest = join_room(client, code=host["room"]["code"], nickname="Guest")
    room_id = host["room"]["id"]
    response = client.post(
        f"/api/rooms/{room_id}/teams",
        headers=auth_headers(guest["credentials"]["session_token"]),
        json={"name": "Nope"},
    )
    assert response.status_code == 403


def test_team_start_validation(client: TestClient) -> None:
    host = create_room(client, nickname="Host", settings={"game_mode": "team"})
    room_id = host["room"]["id"]
    guest = join_room(client, code=host["room"]["code"], nickname="Guest")
    for m, name in [(host, "C1"), (guest, "C2")]:
        _add_character(client, m["credentials"]["session_token"], room_id, name)
    htok = host["credentials"]["session_token"]
    # only one team
    t1 = client.post(
        f"/api/rooms/{room_id}/teams", headers=auth_headers(htok), json={"name": "Solo"}
    ).json()
    client.put(
        f"/api/rooms/{room_id}/players/{host['player']['id']}/team",
        headers=auth_headers(htok),
        json={"team_id": t1["id"]},
    )
    client.put(
        f"/api/rooms/{room_id}/players/{guest['player']['id']}/team",
        headers=auth_headers(htok),
        json={"team_id": t1["id"]},
    )
    response = client.post(f"/api/rooms/{room_id}/matches", headers=auth_headers(htok))
    assert response.status_code == 409

    # proper two teams but unassigned player case: create third player/team setup
    ctx = _setup_team_room(client)
    # unassign one player
    client.put(
        f"/api/rooms/{ctx['room_id']}/players/{ctx['members'][3]['player']['id']}/team",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
        json={"team_id": None},
    )
    response = client.post(
        f"/api/rooms/{ctx['room_id']}/matches",
        headers=auth_headers(ctx["host"]["credentials"]["session_token"]),
    )
    assert response.status_code == 409


def test_team_mode_flow_turns_answers_guesses_and_victory(client: TestClient) -> None:
    ctx = _setup_team_room(client)
    room_id = ctx["room_id"]
    htok = ctx["host"]["credentials"]["session_token"]
    start = client.post(f"/api/rooms/{room_id}/matches", headers=auth_headers(htok))
    assert start.status_code == 201, start.text
    state = start.json()
    match_id = state["match"]["id"]
    assert state["match"]["mode"] == "team"
    assert state["match"]["current_turn_kind"] == "team"

    # Each member sees opponents as the other team only, and never own team secret.
    for member in ctx["members"]:
        ms = client.get(
            f"/api/matches/{match_id}/state",
            headers=auth_headers(member["credentials"]["session_token"]),
        ).json()
        assert ms["self"]["team_id"] is not None
        assert len(ms["opponents"]) == 1
        assert ms["opponents"][0]["owner_kind"] == "team"
        assert ms["opponents"][0]["owner_id"] != ms["self"]["team_id"]
        # no own identity leakage
        assert ms["identity_revealed"] is False
        state_text = client.get(
            f"/api/matches/{match_id}/state",
            headers=auth_headers(member["credentials"]["session_token"]),
        ).text
        assert '"character"' not in state_text.split('"self"')[1].split('"opponents"')[0]

    # Find active team and any member of it to ask
    active_team_id = state["match"]["current_turn_id"]
    team_members = [
        m
        for m in ctx["members"]
        if any(
            t
            for t in ctx["teams"]
            if t["id"] == active_team_id
            and any(mem["id"] == m["player"]["id"] for mem in t["members"])
        )
    ]
    other_team_id = next(t["id"] for t in ctx["teams"] if t["id"] != active_team_id)
    asker = team_members[0]
    question = client.post(
        f"/api/matches/{match_id}/questions",
        headers=auth_headers(asker["credentials"]["session_token"]),
        json={"content": "Team question?", "recipient_team_id": other_team_id},
    )
    assert question.status_code == 201, question.text

    # Any member of recipient team can answer (pick second member)
    recipient_members = [
        m
        for m in ctx["members"]
        if any(
            t
            for t in ctx["teams"]
            if t["id"] == other_team_id
            and any(mem["id"] == m["player"]["id"] for mem in t["members"])
        )
    ]
    answer = client.post(
        f"/api/matches/{match_id}/questions/{question.json()['id']}/answer",
        headers=auth_headers(recipient_members[1]["credentials"]["session_token"]),
        json={"content": "Team answer"},
    )
    assert answer.status_code == 200, answer.text

    # Turn advanced to other team
    new_state = client.get(
        f"/api/matches/{match_id}/state",
        headers=auth_headers(asker["credentials"]["session_token"]),
    ).json()
    assert new_state["match"]["current_turn_id"] == other_team_id

    # Any member of a team can submit a correct guess and win for the team.
    chars = client.get(f"/api/rooms/{room_id}/characters", headers=auth_headers(htok)).json()[
        "characters"
    ]
    winner = recipient_members[0]
    won = False
    for char in chars:
        resp = client.post(
            f"/api/matches/{match_id}/guesses",
            headers=auth_headers(winner["credentials"]["session_token"]),
            json={"character_id": char["id"]},
        )
        assert resp.status_code == 200
        if resp.json()["correct"]:
            assert resp.json()["match"]["winner_team_id"] == other_team_id
            assert resp.json()["match"]["winner_player_id"] is None
            won = True
            break
    assert won
