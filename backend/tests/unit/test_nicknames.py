"""Unit tests for nickname normalization and uniqueness keys."""

from __future__ import annotations

import pytest

from app.core.nicknames import (
    MAX_NICKNAME_LENGTH,
    MIN_NICKNAME_LENGTH,
    NicknameError,
    nickname_key,
    normalize_nickname,
)


def test_nickname_is_trimmed_and_internal_whitespace_is_collapsed() -> None:
    assert normalize_nickname("   Alice    Smith  ") == "Alice Smith"
    assert normalize_nickname("Bob   The   Builder") == "Bob The Builder"


def test_nickname_preserves_display_case_and_international_characters() -> None:
    assert normalize_nickname("José") == "José"
    assert normalize_nickname("李雷") == "李雷"
    assert normalize_nickname("Bjørn") == "Bjørn"


def test_nickname_is_nfkc_normalized() -> None:
    # Full-width Latin letters normalize to their ASCII equivalents.
    assert normalize_nickname("Ａｌｉｃｅ") == "Alice"  # noqa: RUF001


def test_nickname_length_bounds_are_inclusive() -> None:
    shortest = "a" * MIN_NICKNAME_LENGTH
    longest = "a" * MAX_NICKNAME_LENGTH

    assert normalize_nickname(shortest) == shortest
    assert normalize_nickname(longest) == longest


@pytest.mark.parametrize(
    "nickname",
    ["", "   ", "\t\n", "a", "a" * (MAX_NICKNAME_LENGTH + 1)],
)
def test_invalid_nickname_lengths_are_rejected(nickname: str) -> None:
    with pytest.raises(NicknameError):
        normalize_nickname(nickname)


@pytest.mark.parametrize("nickname", ["Bad\u0000Name", "Bad\nName", "Bad\tName", "Bad\u200bName"])
def test_control_and_unsupported_characters_are_rejected(nickname: str) -> None:
    with pytest.raises(NicknameError):
        normalize_nickname(nickname)


def test_non_text_input_is_rejected() -> None:
    with pytest.raises(NicknameError):
        normalize_nickname(123)  # type: ignore[arg-type]


def test_nickname_key_is_case_insensitive_and_unicode_aware() -> None:
    assert nickname_key("Alice") == nickname_key("alice")
    assert nickname_key("ALICE") == "alice"
    assert nickname_key("Straße") == nickname_key("STRASSE")
    assert nickname_key("José") == nickname_key("JOSÉ")
