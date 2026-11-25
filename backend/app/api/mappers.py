"""Map domain/service objects to public API response schemas."""

from __future__ import annotations

from app.core.media import MediaStorage
from app.core.room_config import RoomConfig
from app.models import Character, GameEvent, Player, Question, Room
from app.schemas.characters import CharacterResponse
from app.schemas.matches import (
    AnswerResponse,
    EventResponse,
    MatchCharacterResponse,
    MatchDetailsResponse,
    MatchInfoResponse,
    MatchParticipantResponse,
    MatchSelfResponse,
    MatchStateResponse,
    QuestionResponse,
    VisibleCharacterResponse,
)
from app.schemas.rooms import (
    PublicPlayerResponse,
    RoomResponse,
    SessionCredentialsResponse,
)
from app.schemas.teams import TeamResponse
from app.services.match_state import (
    MatchDetailsView,
    MatchInfo,
    MatchStateView,
    QuestionView,
)
from app.services.sessions import IssuedSession
from app.services.teams import TeamView


def player_response(player: Player, room: Room) -> PublicPlayerResponse:
    return PublicPlayerResponse(
        id=player.id,
        nickname=player.nickname,
        is_host=room.host_player_id == player.id,
        is_connected=player.is_connected,
        is_ready=player.is_ready,
        joined_at=player.joined_at,
    )


def room_response(
    room: Room,
    configuration: RoomConfig,
    player_count: int,
) -> RoomResponse:
    return RoomResponse(
        id=room.id,
        code=room.code,
        status=room.status,
        host_player_id=room.host_player_id,
        settings=configuration,
        player_count=player_count,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def character_response(
    character: Character,
    storage: MediaStorage,
) -> CharacterResponse:
    """Expose the public media URL rather than the stored filesystem path."""
    return CharacterResponse(
        id=character.id,
        room_id=character.room_id,
        name=character.name,
        franchise=character.franchise,
        category=character.category,
        image_url=storage.public_url(character.image_path),
        attributes=character.attributes,
        contributed_by=character.contributed_by,
        created_at=character.created_at,
    )


def credentials_response(issued: IssuedSession) -> SessionCredentialsResponse:
    return SessionCredentialsResponse(
        session_token=issued.session_token,
        session_expires_at=issued.session_expires_at,
        reconnect_token=issued.reconnect_token,
        reconnect_expires_at=issued.reconnect_expires_at,
    )


def team_response(view: TeamView, room: Room) -> TeamResponse:
    return TeamResponse(
        id=view.team.id,
        room_id=view.team.room_id,
        name=view.team.name,
        members=[player_response(member, room) for member in view.members],
    )


def match_info_response(match: MatchInfo) -> MatchInfoResponse:
    """Serialize the player-facing match view.

    The service always supplies a fully populated :class:`MatchInfo`; callers
    never receive raw ORM entities through API responses.
    """
    return MatchInfoResponse(
        id=match.id,
        room_id=match.room_id,
        mode=match.mode,
        status=match.status,
        phase=match.phase,
        turn_index=match.turn_index,
        current_turn_id=match.current_turn_id,
        current_turn_kind=match.current_turn_kind,
        current_turn_name=match.current_turn_name,
        participant_count=match.participant_count,
        started_at=match.started_at,
        finished_at=match.finished_at,
        winner_player_id=match.winner_player_id,
        winner_team_id=match.winner_team_id,
        winner_name=match.winner_name,
    )


def question_view_response(view: QuestionView, storage: MediaStorage) -> QuestionResponse:
    return QuestionResponse(
        id=view.id,
        author_player_id=view.author_player_id,
        author_nickname=view.author_nickname,
        recipient_player_id=view.recipient_player_id,
        recipient_team_id=view.recipient_team_id,
        recipient_name=view.recipient_name,
        content=view.content,
        asked_at=view.asked_at,
        answer=(
            AnswerResponse(
                content=view.answer.content,
                author_player_id=view.answer.author_player_id,
                author_nickname=view.answer.author_nickname,
                answered_at=view.answer.answered_at,
            )
            if view.answer
            else None
        ),
        can_answer=view.can_answer,
    )


def question_response(question: Question) -> QuestionResponse:
    """Serialize a freshly mutated Question ORM object."""
    answer = None
    if question.answer_content is not None and question.answered_at is not None:
        answer = AnswerResponse(
            content=question.answer_content,
            author_player_id=question.answer_author_player_id,
            author_nickname=(question.answer_author.nickname if question.answer_author else None),
            answered_at=question.answered_at,
        )
    return QuestionResponse(
        id=question.id,
        author_player_id=question.author_player_id,
        author_nickname=question.author.nickname if question.author else None,
        recipient_player_id=question.recipient_player_id,
        recipient_team_id=question.recipient_team_id,
        recipient_name=(
            question.recipient_player.nickname
            if question.recipient_player
            else question.recipient_team.name
            if question.recipient_team
            else None
        ),
        content=question.content,
        asked_at=question.created_at,
        answer=answer,
        can_answer=False,
    )


def match_details_response(details: MatchDetailsView) -> MatchDetailsResponse:
    return MatchDetailsResponse(
        match=match_info_response(details.match),
        participants=[
            MatchParticipantResponse(
                id=participant.id,
                name=participant.name,
                kind=participant.kind,
                is_connected=participant.is_connected,
                member_player_ids=list(participant.member_player_ids),
            )
            for participant in details.participants
        ],
    )


def match_state_response(state: MatchStateView, storage: MediaStorage) -> MatchStateResponse:
    return MatchStateResponse(
        match=match_info_response(state.match),
        **{
            "self": MatchSelfResponse(
                player_id=state.self_view.player_id,
                nickname=state.self_view.nickname,
                team_id=state.self_view.team_id,
                team_name=state.self_view.team_name,
                is_your_turn=state.self_view.is_your_turn,
                can_ask=state.self_view.can_ask,
            )
        },
        identity_assigned=state.identity_assigned,
        identity_revealed=state.identity_revealed,
        opponents=[
            VisibleCharacterResponse(
                owner_id=opponent.owner_id,
                owner_kind=opponent.owner_kind,
                owner_name=opponent.owner_name,
                character=MatchCharacterResponse(
                    id=opponent.character.id,
                    name=opponent.character.name,
                    franchise=opponent.character.franchise,
                    category=opponent.character.category,
                    image_url=storage.public_url(opponent.character.image_path),
                    attributes=opponent.character.attributes,
                ),
            )
            for opponent in state.opponents
        ],
        participants=[
            MatchParticipantResponse(
                id=participant.id,
                name=participant.name,
                kind=participant.kind,
                is_connected=participant.is_connected,
                member_player_ids=list(participant.member_player_ids),
            )
            for participant in state.participants
        ],
        pending_question=(
            question_view_response(state.pending_question, storage)
            if state.pending_question
            else None
        ),
        question_history=[
            question_view_response(question, storage) for question in state.question_history
        ],
        allowed_recipient_ids=list(state.allowed_recipient_ids),
    )


def event_response(event: GameEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        match_id=event.match_id,
        actor_player_id=event.actor_player_id,
        event_type=event.event_type.value
        if hasattr(event.event_type, "value")
        else str(event.event_type),
        payload=event.payload,
        sequence_number=event.sequence_number,
        created_at=event.created_at,
    )
