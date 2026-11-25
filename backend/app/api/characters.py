"""Room character collection endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.api.character_forms import parse_character_submission
from app.api.deps import (
    AppSettingsDep,
    ConnectionManagerDep,
    CurrentPlayerDep,
    DbSessionDep,
    ImageDownloaderDep,
    MediaStorageDep,
)
from app.api.mappers import character_response
from app.schemas.characters import (
    CharacterListResponse,
    CharacterResponse,
    CreateCharacterRequest,
)
from app.services.characters import CharacterService
from app.websockets.protocol import CHARACTER_ADDED_EVENT, CHARACTER_DELETED_EVENT, WebSocketEvent

router = APIRouter(prefix="/rooms/{room_id}/characters", tags=["characters"])

_FORM_SCHEMA = {
    "type": "object",
    "required": ["name", "category"],
    "properties": {
        "name": {"type": "string", "maxLength": 80},
        "franchise": {"type": "string", "maxLength": 80, "nullable": True},
        "category": {"type": "string"},
        "attributes": {
            "type": "string",
            "description": "A JSON object serialized as text.",
        },
        "image": {"type": "string", "format": "binary"},
        "image_url": {"type": "string", "maxLength": 2048},
    },
}


@router.post(
    "",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a character to a waiting room",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": CreateCharacterRequest.model_json_schema(),
                },
                "multipart/form-data": {"schema": _FORM_SCHEMA},
            },
        }
    },
)
async def create_character(
    room_id: uuid.UUID,
    request: Request,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    storage: MediaStorageDep,
    downloader: ImageDownloaderDep,
    manager: ConnectionManagerDep,
) -> CharacterResponse:
    submission = await parse_character_submission(
        request,
        max_part_bytes=settings.image_max_bytes + 1024 * 1024,
    )
    try:
        character = CharacterService(session, settings, storage, downloader).create_character(
            room_id=room_id,
            player=player,
            name=submission.payload.name,
            franchise=submission.payload.franchise,
            category=submission.payload.category,
            attributes=submission.payload.attributes,
            image=submission.upload.file if submission.upload is not None else None,
            image_url=submission.payload.image_url,
        )
    finally:
        if submission.upload is not None:
            await submission.upload.close()
    await manager.broadcast_room(
        room_id,
        WebSocketEvent(
            event=CHARACTER_ADDED_EVENT,
            payload={"character_id": str(character.id), "name": character.name},
        ),
    )
    return character_response(character, storage)


@router.get(
    "",
    response_model=CharacterListResponse,
    summary="List a room's characters",
)
def list_characters(
    room_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    storage: MediaStorageDep,
    downloader: ImageDownloaderDep,
) -> CharacterListResponse:
    characters = CharacterService(
        session,
        settings,
        storage,
        downloader,
    ).list_characters(room_id, player)
    return CharacterListResponse(
        characters=[character_response(character, storage) for character in characters]
    )


@router.get(
    "/{character_id}",
    response_model=CharacterResponse,
    summary="Get character details",
)
def get_character(
    room_id: uuid.UUID,
    character_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    storage: MediaStorageDep,
    downloader: ImageDownloaderDep,
) -> CharacterResponse:
    character = CharacterService(
        session,
        settings,
        storage,
        downloader,
    ).get_character(room_id, character_id, player)
    return character_response(character, storage)


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a character (host or contributor)",
)
async def delete_character(
    room_id: uuid.UUID,
    character_id: uuid.UUID,
    session: DbSessionDep,
    player: CurrentPlayerDep,
    settings: AppSettingsDep,
    storage: MediaStorageDep,
    downloader: ImageDownloaderDep,
    manager: ConnectionManagerDep,
) -> None:
    CharacterService(session, settings, storage, downloader).delete_character(
        room_id,
        character_id,
        player,
    )
    await manager.broadcast_room(
        room_id,
        WebSocketEvent(
            event=CHARACTER_DELETED_EVENT,
            payload={"character_id": str(character_id)},
        ),
    )
