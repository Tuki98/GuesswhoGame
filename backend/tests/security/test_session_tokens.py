"""Security tests for session token storage."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import generate_session_token, hash_session_token, verify_session_token
from app.models import Player
from tests.factories import TEST_SECRET, make_player, make_room


def test_player_persists_only_a_hashed_session_token(db_session: Session) -> None:
    token = generate_session_token()
    room = make_room(db_session)
    player = make_player(db_session, room, token=token)
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(Player, player.id)

    assert stored is not None
    assert stored.session_token_hash != token
    assert token not in stored.session_token_hash
    assert stored.session_token_hash == hash_session_token(token, secret_key=TEST_SECRET)
    assert verify_session_token(token, stored.session_token_hash, secret_key=TEST_SECRET)


def test_hashing_the_same_token_without_the_server_secret_fails(db_session: Session) -> None:
    token = generate_session_token()
    room = make_room(db_session)
    player = make_player(db_session, room, token=token)
    db_session.commit()

    assert (
        verify_session_token(token, player.session_token_hash, secret_key="attacker-secret")
        is False
    )


def test_health_and_openapi_do_not_expose_the_server_secret(client: TestClient) -> None:
    health_response = client.get("/api/health")
    openapi_response = client.get("/openapi.json")

    assert TEST_SECRET not in health_response.text
    assert TEST_SECRET not in openapi_response.text
