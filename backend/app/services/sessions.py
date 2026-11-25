"""Session credential issuance, authentication, and reconnection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import InvalidSessionError
from app.core.security import generate_session_token, hash_session_token
from app.database.base import utc_now
from app.models import Player, Room
from app.repositories.players import PlayerRepository


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Newly minted credentials. Raw tokens are only exposed at issuance."""

    session_token: str
    session_token_hash: str
    session_expires_at: datetime
    reconnect_token: str
    reconnect_token_hash: str
    reconnect_expires_at: datetime


@dataclass(frozen=True, slots=True)
class ReconnectedSession:
    room: Room
    player: Player
    issued: IssuedSession


def issue_session(settings: Settings, *, now: datetime | None = None) -> IssuedSession:
    """Create a new session/reconnect credential pair and its persisted hashes."""
    issued_at = now or utc_now()
    secret = settings.secret_key.get_secret_value()

    session_token = generate_session_token()
    reconnect_token = generate_session_token()

    return IssuedSession(
        session_token=session_token,
        session_token_hash=hash_session_token(session_token, secret_key=secret),
        session_expires_at=issued_at + timedelta(hours=settings.session_token_ttl_hours),
        reconnect_token=reconnect_token,
        reconnect_token_hash=hash_session_token(reconnect_token, secret_key=secret),
        reconnect_expires_at=issued_at + timedelta(hours=settings.reconnect_token_ttl_hours),
    )


class SessionService:
    """Authenticate bearer tokens and rotate credentials on reconnection."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.players = PlayerRepository(session)
        self._secret = settings.secret_key.get_secret_value()

    def authenticate(self, token: str) -> Player:
        """Return the player for a valid, unexpired session token."""
        if not token:
            raise InvalidSessionError()

        token_hash = hash_session_token(token, secret_key=self._secret)
        player = self.players.get_by_session_hash(token_hash)
        if player is None or player.session_expires_at <= utc_now():
            raise InvalidSessionError()
        return player

    def reconnect(self, reconnect_token: str) -> ReconnectedSession:
        """Restore a player session using the dedicated reconnect credential.

        Both credentials are rotated in a single compare-and-swap update. If two
        clients race with the same reconnect credential, only one rotation can
        succeed, so only one active session remains.
        """
        now = utc_now()
        if not reconnect_token:
            raise InvalidSessionError()

        old_hash = hash_session_token(reconnect_token, secret_key=self._secret)
        player = self.players.get_by_reconnect_hash(old_hash)
        if (
            player is None
            or player.reconnect_expires_at is None
            or player.reconnect_expires_at <= now
        ):
            raise InvalidSessionError()

        room = player.room
        issued = issue_session(self.settings, now=now)

        result = cast(
            "CursorResult[Any]",
            self.session.execute(
                update(Player)
                .where(Player.id == player.id, Player.reconnect_token_hash == old_hash)
                .values(
                    session_token_hash=issued.session_token_hash,
                    session_expires_at=issued.session_expires_at,
                    reconnect_token_hash=issued.reconnect_token_hash,
                    reconnect_expires_at=issued.reconnect_expires_at,
                    is_connected=True,
                    last_seen_at=now,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise InvalidSessionError()

        self.session.commit()
        self.session.refresh(player)
        return ReconnectedSession(room=room, player=player, issued=issued)
