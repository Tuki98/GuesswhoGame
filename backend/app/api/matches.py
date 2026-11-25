"""Match lifecycle, turn, question, guess, and history endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPlayerDep, DbSessionDep, MediaStorageDep
from app.api.mappers import (
    event_response,
    match_details_response,
    match_info_response,
    match_state_response,
    question_response,
)
from app.schemas.matches import (
    AnswerQuestionRequest,
    AskQuestionRequest,
    GuessResultResponse,
    MatchDetailsResponse,
    MatchHistoryResponse,
    MatchStateResponse,
    QuestionResponse,
    SubmitGuessRequest,
)
from app.services.matches import MatchService

router = APIRouter(tags=["matches"])


@router.post(
    "/rooms/{room_id}/matches",
    response_model=MatchStateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a match in a room (host only)",
)
def start_match(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    storage: MediaStorageDep,
) -> MatchStateResponse:
    state = MatchService(session).start_match(room_id, player)
    return match_state_response(state, storage)


@router.get(
    "/matches/{match_id}",
    response_model=MatchDetailsResponse,
    summary="Get match details",
)
def get_match(
    match_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
) -> MatchDetailsResponse:
    details = MatchService(session).get_details(match_id, player)
    return match_details_response(details)


@router.get(
    "/matches/{match_id}/state",
    response_model=MatchStateResponse,
    summary="Get the player-specific match state",
)
def get_match_state(
    match_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    storage: MediaStorageDep,
) -> MatchStateResponse:
    state = MatchService(session).get_state(match_id, player)
    return match_state_response(state, storage)


@router.post(
    "/matches/{match_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask a question on the active turn",
)
def ask_question(
    match_id: uuid.UUID,
    payload: AskQuestionRequest,
    session: DbSessionDep,
    player: CurrentPlayerDep,
) -> QuestionResponse:
    question = MatchService(session).ask_question(
        match_id,
        player,
        content=payload.content,
        recipient_player_id=payload.recipient_player_id,
        recipient_team_id=payload.recipient_team_id,
    )
    return question_response(question)


@router.post(
    "/matches/{match_id}/questions/{question_id}/answer",
    response_model=QuestionResponse,
    summary="Answer a pending question",
)
def answer_question(
    match_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: AnswerQuestionRequest,
    session: DbSessionDep,
    player: CurrentPlayerDep,
) -> QuestionResponse:
    question = MatchService(session).answer_question(
        match_id,
        question_id,
        player,
        content=payload.content,
    )
    return question_response(question)


@router.post(
    "/matches/{match_id}/guesses",
    response_model=GuessResultResponse,
    summary="Submit a character guess",
)
def submit_guess(
    match_id: uuid.UUID,
    payload: SubmitGuessRequest,
    session: DbSessionDep,
    player: CurrentPlayerDep,
) -> GuessResultResponse:
    outcome = MatchService(session).submit_guess(
        match_id,
        player,
        character_id=payload.character_id,
    )
    return GuessResultResponse(
        correct=outcome.correct,
        match=match_info_response(outcome.match),
    )


@router.post(
    "/matches/{match_id}/cancel",
    response_model=MatchStateResponse,
    summary="Cancel a match (host only)",
)
def cancel_match(
    match_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    storage: MediaStorageDep,
) -> MatchStateResponse:
    MatchService(session).cancel_match(match_id, player)
    state = MatchService(session).get_state(match_id, player)
    return match_state_response(state, storage)


@router.get(
    "/matches/{match_id}/history",
    response_model=MatchHistoryResponse,
    summary="List match events in ascending sequence order",
)
def get_match_history(
    match_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    limit: int = Query(default=50, ge=1, le=100),
    after_sequence: int | None = Query(default=None, ge=1),
) -> MatchHistoryResponse:
    page = MatchService(session).get_history(
        match_id,
        player,
        limit=limit,
        after_sequence=after_sequence,
    )
    return MatchHistoryResponse(
        events=[event_response(event) for event in page.events],
        has_more=page.has_more,
        next_after_sequence=page.next_after_sequence,
    )
