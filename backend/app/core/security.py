"""Session token generation and hashing utilities.

Session tokens are opaque bearer credentials. Only a keyed hash of the token is
ever persisted; the raw token is returned to the player once and is never
logged or stored by the backend.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_BYTES = 32
TOKEN_HASH_HEX_LENGTH = hashlib.sha256().digest_size * 2
_HASH_CONTEXT = b"guess-the-character:session-token:v1"

ROOM_CODE_PREFIX = "GTC-"
ROOM_CODE_LENGTH = 4
# Ambiguous characters (I, O, 0, 1) are excluded so codes are easy to share.
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_session_token() -> str:
    """Generate a cryptographically random, URL-safe session token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def generate_room_code() -> str:
    """Generate a short, human-readable, cryptographically random room code."""
    random_part = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
    return f"{ROOM_CODE_PREFIX}{random_part}"


def hash_session_token(token: str, *, secret_key: str) -> str:
    """Return a deterministic HMAC-SHA256 hex digest for ``token``.

    The server-side secret provides keyed hashing so a leaked database alone is
    not enough to verify or forge session tokens.
    """
    if not token:
        raise ValueError("Session token must not be empty.")
    if not secret_key:
        raise ValueError("Secret key must not be empty.")

    message = _HASH_CONTEXT + b":" + token.encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_session_token(token: str, token_hash: str, *, secret_key: str) -> bool:
    """Validate a presented token against a stored hash in constant time."""
    if not token or not token_hash:
        return False

    expected = hash_session_token(token, secret_key=secret_key)
    return hmac.compare_digest(expected, token_hash)
