"""Tests for session token generation and hashing."""

from __future__ import annotations

import string

import pytest

from app.core.security import (
    TOKEN_HASH_HEX_LENGTH,
    generate_session_token,
    hash_session_token,
    verify_session_token,
)

SECRET = "unit-test-secret-key-0123456789abcdef"


def test_generated_tokens_have_expected_shape() -> None:
    token = generate_session_token()

    assert len(token) >= 40
    assert set(token) <= set(string.ascii_letters + string.digits + "-_")


def test_generated_tokens_are_unique() -> None:
    tokens = {generate_session_token() for _ in range(200)}

    assert len(tokens) == 200


def test_hash_is_deterministic_hex_digest() -> None:
    token = "a-session-token"
    first = hash_session_token(token, secret_key=SECRET)
    second = hash_session_token(token, secret_key=SECRET)

    assert first == second
    assert len(first) == TOKEN_HASH_HEX_LENGTH
    int(first, 16)
    assert token not in first


def test_hash_depends_on_server_secret() -> None:
    token = "a-session-token"

    assert hash_session_token(token, secret_key=SECRET) != hash_session_token(
        token, secret_key="different-secret"
    )


def test_verify_accepts_matching_token() -> None:
    token = generate_session_token()
    token_hash = hash_session_token(token, secret_key=SECRET)

    assert verify_session_token(token, token_hash, secret_key=SECRET) is True


@pytest.mark.parametrize("wrong_token", ["", "wrong", "a" * 100])
def test_verify_rejects_invalid_token(wrong_token: str) -> None:
    token_hash = hash_session_token("correct-token", secret_key=SECRET)

    assert verify_session_token(wrong_token, token_hash, secret_key=SECRET) is False


def test_verify_rejects_hash_from_another_secret() -> None:
    token = "a-session-token"
    token_hash = hash_session_token(token, secret_key="other-secret")

    assert verify_session_token(token, token_hash, secret_key=SECRET) is False


def test_verify_rejects_malformed_hash() -> None:
    assert verify_session_token("token", "not-a-valid-hash", secret_key=SECRET) is False


def test_empty_inputs_are_rejected_by_hasher() -> None:
    with pytest.raises(ValueError, match="token"):
        hash_session_token("", secret_key=SECRET)
    with pytest.raises(ValueError, match="Secret key"):
        hash_session_token("token", secret_key="")


def test_hash_length_matches_player_column_contract() -> None:
    assert TOKEN_HASH_HEX_LENGTH == 64
