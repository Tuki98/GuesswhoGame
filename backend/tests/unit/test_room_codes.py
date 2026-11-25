"""Unit tests for invitation-code generation."""

from __future__ import annotations

import re

from app.core.security import (
    ROOM_CODE_ALPHABET,
    ROOM_CODE_LENGTH,
    ROOM_CODE_PREFIX,
    generate_room_code,
)

CODE_PATTERN = re.compile(rf"^{re.escape(ROOM_CODE_PREFIX)}[A-Z2-9]{{{ROOM_CODE_LENGTH}}}$")


def test_room_code_has_expected_format() -> None:
    code = generate_room_code()

    assert CODE_PATTERN.fullmatch(code)
    assert code.startswith(ROOM_CODE_PREFIX)


def test_room_codes_do_not_contain_ambiguous_characters() -> None:
    forbidden = {"I", "O", "0", "1"}
    codes = [generate_room_code() for _ in range(200)]

    assert all(not (forbidden & set(code)) for code in codes)
    assert all(
        set(code.removeprefix(ROOM_CODE_PREFIX)) <= set(ROOM_CODE_ALPHABET) for code in codes
    )


def test_room_codes_are_random() -> None:
    codes = {generate_room_code() for _ in range(200)}

    assert len(codes) > 150
