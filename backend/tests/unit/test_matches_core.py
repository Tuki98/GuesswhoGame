"""Unit tests for the secure assignment algorithm and core validators."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

import pytest

from app.core.matches import (
    AssignmentTarget,
    MatchAssignmentError,
    MatchValidationError,
    match_phase,
    normalize_answer_content,
    normalize_question_content,
    secure_assign,
)
from app.models.enums import MatchStatus


@dataclass(frozen=True)
class FakeCharacter:
    id: uuid.UUID


def _characters(count: int) -> list[FakeCharacter]:
    return [FakeCharacter(id=uuid.uuid4()) for _ in range(count)]


def test_match_phase_mapping_preserves_existing_statuses() -> None:
    assert match_phase(MatchStatus.PENDING) == "created"
    assert match_phase(MatchStatus.ACTIVE) == "in_progress"
    assert match_phase(MatchStatus.FINISHED) == "finished"
    assert match_phase(MatchStatus.ABANDONED) == "cancelled"
    assert match_phase(MatchStatus.PAUSED) == "in_progress"


def test_question_and_answer_normalization_and_limits() -> None:
    assert normalize_question_content("  Is it blue?  ") == "Is it blue?"
    assert normalize_answer_content("  Yes.  ") == "Yes."
    with pytest.raises(MatchValidationError):
        normalize_question_content("   ")
    with pytest.raises(MatchValidationError):
        normalize_question_content("x" * 501)
    with pytest.raises(MatchValidationError):
        normalize_answer_content("")
    with pytest.raises(MatchValidationError):
        normalize_answer_content("y" * 1001)


def test_secure_assign_returns_deranged_unique_mapping() -> None:
    chars = _characters(4)
    targets = [
        AssignmentTarget(owner_id=uuid.uuid4(), forbidden_character_ids=frozenset())
        for _ in range(4)
    ]
    assignment = secure_assign(targets, chars, rng=random.Random(7))

    assert set(assignment) == {target.owner_id for target in targets}
    assigned_ids = [character.id for character in assignment.values()]
    assert len(assigned_ids) == len(set(assigned_ids))
    assert set(assigned_ids).issubset({character.id for character in chars})


def test_secure_assign_never_uses_forbidden_contributed_character() -> None:
    chars = _characters(3)
    owners = [uuid.uuid4() for _ in range(3)]
    # Force a constraint: owner 0 cannot receive chars[0], others unrestricted.
    targets = [
        AssignmentTarget(owner_id=owners[0], forbidden_character_ids=frozenset({chars[0].id})),
        AssignmentTarget(owner_id=owners[1], forbidden_character_ids=frozenset()),
        AssignmentTarget(owner_id=owners[2], forbidden_character_ids=frozenset()),
    ]
    for seed in range(50):
        assignment = secure_assign(targets, chars, rng=random.Random(seed))
        assert assignment[owners[0]].id != chars[0].id


def test_secure_assign_finds_derangement_when_only_one_solution_exists() -> None:
    chars = _characters(3)
    owners = [uuid.uuid4() for _ in range(3)]
    # Each owner is forbidden from one character in a cycle; only the rotation works.
    targets = [
        AssignmentTarget(
            owner_id=owners[0], forbidden_character_ids=frozenset({chars[0].id, chars[1].id})
        ),
        AssignmentTarget(
            owner_id=owners[1], forbidden_character_ids=frozenset({chars[1].id, chars[2].id})
        ),
        AssignmentTarget(
            owner_id=owners[2], forbidden_character_ids=frozenset({chars[2].id, chars[0].id})
        ),
    ]
    assignment = secure_assign(targets, chars, rng=random.Random(0))
    assert assignment[owners[0]].id == chars[2].id
    assert assignment[owners[1]].id == chars[0].id
    assert assignment[owners[2]].id == chars[1].id


def test_secure_assign_rejects_insufficient_characters() -> None:
    chars = _characters(2)
    targets = [
        AssignmentTarget(owner_id=uuid.uuid4(), forbidden_character_ids=frozenset())
        for _ in range(3)
    ]
    with pytest.raises(MatchAssignmentError):
        secure_assign(targets, chars, rng=random.Random(1))


def test_secure_assign_rejects_impossible_derangement() -> None:
    chars = _characters(2)
    owner = uuid.uuid4()
    targets = [
        AssignmentTarget(owner_id=owner, forbidden_character_ids=frozenset({c.id for c in chars})),
        AssignmentTarget(owner_id=uuid.uuid4(), forbidden_character_ids=frozenset()),
    ]
    with pytest.raises(MatchAssignmentError):
        secure_assign(targets, chars, rng=random.Random(1))


def test_secure_assign_is_randomized() -> None:
    chars = _characters(6)
    targets = [
        AssignmentTarget(owner_id=uuid.uuid4(), forbidden_character_ids=frozenset())
        for _ in range(6)
    ]
    baseline = secure_assign(targets, chars, rng=random.Random(1))
    differs = any(
        [c.id for c in secure_assign(targets, chars, rng=random.Random(seed)).values()]
        != [c.id for c in baseline.values()]
        for seed in range(2, 10)
    )
    assert differs
    assert set(baseline) == {target.owner_id for target in targets}
