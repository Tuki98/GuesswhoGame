"""Character text normalization, categories, and duplicate keys."""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from app.models.enums import CharacterCategory

MIN_CHARACTER_NAME_LENGTH = 1
MAX_CHARACTER_NAME_LENGTH = 80
MAX_FRANCHISE_LENGTH = 80
MAX_ATTRIBUTE_KEYS = 50
MAX_ATTRIBUTES_BYTES = 16_384


class CharacterValidationError(ValueError):
    """Raised when character input is malformed or outside allowed bounds."""


def _collapse(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def normalize_character_name(raw: str) -> str:
    """Return the canonical display name for a character."""
    if not isinstance(raw, str):
        raise CharacterValidationError("Character name must be text.")

    normalized = _collapse(raw)
    if not normalized:
        raise CharacterValidationError("Character name must not be empty.")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise CharacterValidationError("Character name contains unsupported control characters.")
    if len(normalized) > MAX_CHARACTER_NAME_LENGTH:
        raise CharacterValidationError(
            f"Character name must be at most {MAX_CHARACTER_NAME_LENGTH} characters long."
        )
    return normalized


def normalize_franchise(raw: str | None) -> str | None:
    """Return the canonical display franchise, treating blank input as missing."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise CharacterValidationError("Franchise must be text.")

    normalized = _collapse(raw)
    if not normalized:
        return None
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise CharacterValidationError("Franchise contains unsupported control characters.")
    if len(normalized) > MAX_FRANCHISE_LENGTH:
        raise CharacterValidationError(
            f"Franchise must be at most {MAX_FRANCHISE_LENGTH} characters long."
        )
    return normalized


def character_key(value: str) -> str:
    """Return the case-folded duplicate-detection key for a name or franchise."""
    return _collapse(value).casefold()


def character_uniqueness_keys(name: str, franchise: str | None) -> tuple[str, str]:
    """Return the (name, franchise) keys used for uniqueness within a room.

    Missing and blank franchises both map to an empty key so the database unique
    constraint treats them consistently.
    """
    return character_key(name), character_key(franchise or "")


def normalize_category(category: CharacterCategory | str) -> CharacterCategory:
    """Validate a category supplied by the API."""
    if isinstance(category, CharacterCategory):
        return category
    if not isinstance(category, str):
        raise CharacterValidationError("Category must be text.")
    try:
        return CharacterCategory(category.strip().lower())
    except ValueError as exc:
        raise CharacterValidationError("Unsupported character category.") from exc


def coerce_stored_category(raw: str | None) -> CharacterCategory:
    """Map a Phase 1 free-text category to a supported category.

    Unknown, blank, and legacy labels become ``other``. This is only used by the
    schema migration; the API requires an explicit supported value.
    """
    if not raw:
        return CharacterCategory.OTHER
    value = " ".join(raw.strip().lower().replace("-", " ").split()).replace(" ", "_")
    aliases = {
        "anime": CharacterCategory.ANIME,
        "manga": CharacterCategory.MANGA,
        "video_game": CharacterCategory.VIDEO_GAMES,
        "video_games": CharacterCategory.VIDEO_GAMES,
        "game": CharacterCategory.VIDEO_GAMES,
        "games": CharacterCategory.VIDEO_GAMES,
        "movie": CharacterCategory.MOVIES,
        "movies": CharacterCategory.MOVIES,
        "tv": CharacterCategory.TV,
        "television": CharacterCategory.TV,
        "television_series": CharacterCategory.TV,
        "tv_series": CharacterCategory.TV,
        "cartoon": CharacterCategory.CARTOONS,
        "cartoons": CharacterCategory.CARTOONS,
        "comic": CharacterCategory.COMICS,
        "comics": CharacterCategory.COMICS,
        "internet_personality": CharacterCategory.INTERNET_PERSONALITIES,
        "internet_personalities": CharacterCategory.INTERNET_PERSONALITIES,
        "influencer": CharacterCategory.INTERNET_PERSONALITIES,
        "other": CharacterCategory.OTHER,
    }
    return aliases.get(value, CharacterCategory.OTHER)


def validate_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    """Validate optional free-form attributes and bound their serialized size."""
    if attributes is None:
        return {}
    if not isinstance(attributes, dict):
        raise CharacterValidationError("Attributes must be a JSON object.")
    if len(attributes) > MAX_ATTRIBUTE_KEYS:
        raise CharacterValidationError(f"Attributes may contain at most {MAX_ATTRIBUTE_KEYS} keys.")
    try:
        serialized = json.dumps(
            attributes,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CharacterValidationError("Attributes must contain valid JSON values.") from exc
    if len(serialized.encode("utf-8")) > MAX_ATTRIBUTES_BYTES:
        raise CharacterValidationError(
            f"Attributes must be at most {MAX_ATTRIBUTES_BYTES} bytes when serialized."
        )
    return dict(attributes)
