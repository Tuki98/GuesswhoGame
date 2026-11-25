"""Tests for character normalization, categories, and attribute validation."""

from __future__ import annotations

import pytest

from app.core.characters import (
    MAX_ATTRIBUTE_KEYS,
    MAX_ATTRIBUTES_BYTES,
    CharacterValidationError,
    character_key,
    character_uniqueness_keys,
    coerce_stored_category,
    normalize_category,
    normalize_character_name,
    normalize_franchise,
    validate_attributes,
)
from app.models import CharacterCategory


def test_name_normalization_uses_nfkc_and_collapses_whitespace() -> None:
    assert normalize_character_name("  Poke\u0301mon\t\n  Ash  ") == "Pokémon Ash"
    assert character_key("  POKÉMON   Ash ") == "pokémon ash"
    assert character_key("Straße") == "strasse"


def test_missing_and_blank_franchises_share_the_same_key() -> None:
    assert character_uniqueness_keys("Naruto", None) == ("naruto", "")
    assert character_uniqueness_keys("Naruto", "   ") == ("naruto", "")
    assert character_uniqueness_keys("Naruto", "Naruto") == ("naruto", "naruto")


def test_unicode_equivalents_share_detection_keys() -> None:
    composed = character_uniqueness_keys("Pokémon", "Pokémon")
    decomposed = character_uniqueness_keys("Poke\u0301mon", "Poke\u0301mon")

    assert composed == decomposed == ("pokémon", "pokémon")


@pytest.mark.parametrize(
    "value",
    ["", "   ", "\x00bad", "\u200bbad", "a" * 81],
)
def test_invalid_names_are_rejected(value: str) -> None:
    with pytest.raises(CharacterValidationError):
        normalize_character_name(value)


def test_names_are_trimmed_before_the_length_check() -> None:
    assert normalize_character_name(f"  {'a' * 80}  ") == "a" * 80


def test_franchise_blank_becomes_missing_and_bad_values_are_rejected() -> None:
    assert normalize_franchise(None) is None
    assert normalize_franchise("  \t ") is None
    assert normalize_franchise("  Final   Fantasy ") == "Final Fantasy"

    with pytest.raises(CharacterValidationError):
        normalize_franchise("bad\x00value")
    with pytest.raises(CharacterValidationError):
        normalize_franchise("a" * 81)
    with pytest.raises(CharacterValidationError):
        normalize_franchise(42)  # type: ignore[arg-type]


def test_category_accepts_enum_values_and_common_text_forms() -> None:
    assert normalize_category("anime") is CharacterCategory.ANIME
    assert normalize_category(" VIDEO_GAMES ") is CharacterCategory.VIDEO_GAMES
    assert normalize_category(CharacterCategory.OTHER) is CharacterCategory.OTHER

    with pytest.raises(CharacterValidationError):
        normalize_category("board games")
    with pytest.raises(CharacterValidationError):
        normalize_category(3)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, CharacterCategory.OTHER),
        ("", CharacterCategory.OTHER),
        ("anime", CharacterCategory.ANIME),
        ("Video Games", CharacterCategory.VIDEO_GAMES),
        ("video-game", CharacterCategory.VIDEO_GAMES),
        ("television series", CharacterCategory.TV),
        ("tv", CharacterCategory.TV),
        ("Internet-Personalities", CharacterCategory.INTERNET_PERSONALITIES),
        ("mystery", CharacterCategory.OTHER),
    ],
)
def test_legacy_categories_are_coerced(raw: str | None, expected: CharacterCategory) -> None:
    assert coerce_stored_category(raw) is expected


def test_attributes_default_to_an_empty_copy() -> None:
    first = validate_attributes(None)
    second = validate_attributes(None)

    assert first == {}
    assert first is not second


def test_attributes_are_returned_as_a_new_mapping() -> None:
    original = {"hair": "black", "nested": {"rank": 2}}
    validated = validate_attributes(original)

    assert validated == original
    assert validated is not original
    assert validated["nested"] is original["nested"]


def test_attributes_are_bounded_by_key_count_and_serialized_size() -> None:
    too_many = {str(index): index for index in range(MAX_ATTRIBUTE_KEYS + 1)}
    with pytest.raises(CharacterValidationError):
        validate_attributes(too_many)

    too_large = {"data": "x" * (MAX_ATTRIBUTES_BYTES + 1)}
    with pytest.raises(CharacterValidationError):
        validate_attributes(too_large)


def test_attributes_reject_non_objects_and_non_json_numbers() -> None:
    with pytest.raises(CharacterValidationError):
        validate_attributes(["not", "an", "object"])  # type: ignore[arg-type]
    with pytest.raises(CharacterValidationError):
        validate_attributes({"score": float("nan")})
    with pytest.raises(CharacterValidationError):
        validate_attributes({"score": float("inf")})
