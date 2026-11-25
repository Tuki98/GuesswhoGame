"""Nickname input normalization shared by API, services, and tests.

The display form keeps the player's capitalization and international
characters. The lookup key is normalized with NFKC and Unicode case folding so
that visually equivalent names cannot join the same room twice.
"""

from __future__ import annotations

import unicodedata

MIN_NICKNAME_LENGTH = 2
MAX_NICKNAME_LENGTH = 24


class NicknameError(ValueError):
    """Raised when a nickname is empty, malformed, or outside allowed bounds."""


def normalize_nickname(raw: str) -> str:
    """Return the canonical display form of a nickname.

    - NFKC normalization for consistent Unicode representation
    - rejects control/format characters and other unsupported code points
    - trims and collapses internal whitespace
    - enforces 2-24 code points
    """
    if not isinstance(raw, str):
        raise NicknameError("Nickname must be text.")

    normalized = unicodedata.normalize("NFKC", raw).strip()
    if not normalized:
        raise NicknameError("Nickname must not be empty.")

    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise NicknameError("Nickname contains unsupported control characters.")

    collapsed = " ".join(normalized.split())
    if len(collapsed) < MIN_NICKNAME_LENGTH:
        raise NicknameError(f"Nickname must be at least {MIN_NICKNAME_LENGTH} characters long.")
    if len(collapsed) > MAX_NICKNAME_LENGTH:
        raise NicknameError(f"Nickname must be at most {MAX_NICKNAME_LENGTH} characters long.")
    return collapsed


def nickname_key(normalized_nickname: str) -> str:
    """Return the case-insensitive uniqueness key for a normalized nickname."""
    return unicodedata.normalize("NFKC", normalized_nickname).casefold()
