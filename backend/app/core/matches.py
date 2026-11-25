"""Pure game-engine helpers: input normalization and secure assignment.

This module deliberately has no database or HTTP dependencies so the assignment
algorithm can be tested (and reasoned about) independently.
"""

from __future__ import annotations

import random
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from app.models.enums import MatchStatus

QUESTION_MAX_LENGTH = 500
ANSWER_MAX_LENGTH = 1000


class MatchValidationError(ValueError):
    """A request value is not acceptable for the game engine."""


class MatchAssignmentError(ValueError):
    """No valid secret-character assignment exists for the participants."""


class CharacterLike(Protocol):
    id: uuid.UUID


CharacterT = TypeVar("CharacterT", bound=CharacterLike)


@dataclass(frozen=True, slots=True)
class AssignmentTarget:
    """One participant that must receive a character.

    ``forbidden_character_ids`` contains characters the participant
    contributed. Excluding them produces a derangement: no participant receives
    an identity they supplied, and therefore no participant can ever see their
    own contribution as their secret.
    """

    owner_id: uuid.UUID
    forbidden_character_ids: frozenset[uuid.UUID]


def normalize_question_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise MatchValidationError("Question content cannot be empty.")
    if len(normalized) > QUESTION_MAX_LENGTH:
        raise MatchValidationError(
            f"Question content cannot exceed {QUESTION_MAX_LENGTH} characters."
        )
    return normalized


def normalize_answer_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise MatchValidationError("Answer content cannot be empty.")
    if len(normalized) > ANSWER_MAX_LENGTH:
        raise MatchValidationError(f"Answer content cannot exceed {ANSWER_MAX_LENGTH} characters.")
    return normalized


_PHASE_BY_STATUS: dict[MatchStatus, str] = {
    MatchStatus.PENDING: "created",
    MatchStatus.ACTIVE: "in_progress",
    MatchStatus.PAUSED: "in_progress",
    MatchStatus.FINISHED: "finished",
    MatchStatus.ABANDONED: "cancelled",
}


def match_phase(status: MatchStatus) -> str:
    """Translate the persisted status into the Phase 4 lifecycle vocabulary.

    The Phase 1 schema already used ``pending``/``active``/``finished``/
    ``abandoned``. Those values are preserved instead of migrating the enum;
    API responses expose this clearer lifecycle name alongside the raw status.
    """
    return _PHASE_BY_STATUS[status]


def secure_assign(
    targets: Sequence[AssignmentTarget],
    characters: Sequence[CharacterT],
    *,
    rng: random.Random | None = None,
) -> dict[uuid.UUID, CharacterT]:
    """Return an injective, deranged owner -> character mapping.

    A randomized bipartite maximum matching is used rather than repeated
    shuffling. It always finds an assignment when one exists and uses
    :class:`secrets.SystemRandom` so the result cannot be predicted from
    application state.
    """
    if not targets:
        raise MatchAssignmentError("At least one participant is required.")
    if len(characters) < len(targets):
        raise MatchAssignmentError("Not enough unique characters for every participant.")

    source = rng or secrets.SystemRandom()
    shuffled_characters = list(characters)
    shuffled_targets = list(targets)
    source.shuffle(shuffled_characters)
    source.shuffle(shuffled_targets)

    adjacency: list[list[int]] = []
    for target in shuffled_targets:
        candidates = [
            index
            for index, character in enumerate(shuffled_characters)
            if character.id not in target.forbidden_character_ids
        ]
        if not candidates:
            raise MatchAssignmentError(
                "A participant has no character that they did not contribute."
            )
        source.shuffle(candidates)
        adjacency.append(candidates)

    target_for_character: dict[int, int] = {}

    def augment(target_index: int, seen: set[int]) -> bool:
        for character_index in adjacency[target_index]:
            if character_index in seen:
                continue
            seen.add(character_index)
            incumbent = target_for_character.get(character_index)
            if incumbent is None or augment(incumbent, seen):
                target_for_character[character_index] = target_index
                return True
        return False

    for target_index in range(len(shuffled_targets)):
        if not augment(target_index, set()):
            raise MatchAssignmentError("No valid derangement exists for the available characters.")

    assignment = {
        shuffled_targets[target_index].owner_id: shuffled_characters[character_index]
        for character_index, target_index in target_for_character.items()
    }
    if len(assignment) != len(targets):
        raise MatchAssignmentError("Could not assign a unique character to every participant.")
    return assignment
