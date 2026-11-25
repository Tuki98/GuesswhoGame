"""Player queries used by session and room services."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Player


class PlayerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, player_id: uuid.UUID) -> Player | None:
        return self.session.get(Player, player_id)

    def get_by_session_hash(self, token_hash: str) -> Player | None:
        return self.session.scalar(select(Player).where(Player.session_token_hash == token_hash))

    def get_by_reconnect_hash(self, token_hash: str) -> Player | None:
        return self.session.scalar(select(Player).where(Player.reconnect_token_hash == token_hash))

    def list_by_room(self, room_id: uuid.UUID) -> list[Player]:
        return list(
            self.session.scalars(
                select(Player)
                .where(Player.room_id == room_id)
                .order_by(Player.joined_at, Player.nickname_key)
            )
        )

    def list_by_team(self, team_id: uuid.UUID) -> list[Player]:
        return list(
            self.session.scalars(
                select(Player)
                .where(Player.team_id == team_id)
                .order_by(Player.joined_at, Player.nickname_key)
            )
        )

    def nickname_key_exists(self, room_id: uuid.UUID, key: str) -> bool:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Player)
                .where(Player.room_id == room_id, Player.nickname_key == key)
            )
            or 0
        ) > 0
