"""Helpers shared by HTTP-level Phase 2 tests."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Player


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_room(
    client: TestClient,
    *,
    nickname: str = "Host",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"nickname": nickname}
    if settings is not None:
        payload["settings"] = settings

    response = client.post("/api/rooms", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def join_room(
    client: TestClient,
    *,
    code: str,
    nickname: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/rooms/join",
        json={"code": code, "nickname": nickname},
    )
    assert response.status_code == 200, response.text
    return response.json()


def get_player(db_session: Session, player_id: str) -> Player:
    player = db_session.get(Player, uuid.UUID(player_id))
    assert player is not None
    return player
