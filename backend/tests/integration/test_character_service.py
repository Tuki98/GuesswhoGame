"""Service-level character tests for transaction and cleanup behavior."""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.core.media import MediaError, MediaStorage
from app.models import Character, CharacterCategory, RoomStatus
from app.services.characters import CharacterService
from tests.factories import make_player, make_room
from tests.fake_http import FakeImageServer
from tests.image_helpers import image_bytes


@pytest.fixture
def storage(settings: Settings) -> MediaStorage:
    return MediaStorage(settings.media_root, settings.media_url_prefix)


@pytest.fixture
def service(
    db_session: Session,
    settings: Settings,
    storage: MediaStorage,
) -> CharacterService:
    return CharacterService(
        db_session,
        settings,
        storage,
        FakeImageServer().downloader(max_bytes=settings.image_max_bytes),
    )


def _stored_images(settings: Settings) -> list[Path]:
    directory = settings.media_root / "characters"
    return sorted(directory.glob("*.webp")) if directory.exists() else []


def _create(
    service: CharacterService,
    room_id: uuid.UUID,
    player: object,
    *,
    name: str = "Naruto",
    franchise: str | None = "Naruto",
    image: BinaryIO | None = None,
    image_url: str | None = None,
):
    return service.create_character(
        room_id,
        player,  # type: ignore[arg-type]
        name=name,
        franchise=franchise,
        category=CharacterCategory.ANIME,
        attributes={"village": "Leaf"},
        image=image,
        image_url=image_url,
    )


def test_create_persists_normalized_character_and_file(
    service: CharacterService,
    db_session: Session,
    settings: Settings,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    character = service.create_character(
        room.id,
        player,
        name="  Naruto  ",
        franchise="  Naruto  ",
        category="anime",
        attributes={"village": "Leaf"},
        image=BytesIO(image_bytes()),
    )

    assert character.contributed_by == player.id
    assert character.name == "Naruto"
    assert character.name_key == "naruto"
    assert character.franchise_key == "naruto"
    assert character.category is CharacterCategory.ANIME
    assert character.image_path.startswith("characters/")
    assert len(_stored_images(settings)) == 1


def test_image_source_is_required_and_must_be_unambiguous(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    with pytest.raises(DomainValidationError):
        _create(service, room.id, player)

    with pytest.raises(DomainValidationError):
        _create(
            service,
            room.id,
            player,
            image=BytesIO(image_bytes()),
            image_url="http://images.example.com/image.png",
        )


def test_invalid_fields_are_domain_validation_errors(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    with pytest.raises(DomainValidationError, match="name"):
        _create(service, room.id, player, name="   ")
    with pytest.raises(DomainValidationError, match="category"):
        service.create_character(
            room.id,
            player,
            name="Naruto",
            franchise=None,
            category="board games",
            attributes={},
            image=BytesIO(image_bytes()),
        )
    with pytest.raises(DomainValidationError, match="Attributes"):
        service.create_character(
            room.id,
            player,
            name="Naruto",
            franchise=None,
            category="anime",
            attributes={"data": "x" * 20_000},
            image=BytesIO(image_bytes()),
        )


def test_download_failures_become_domain_validation_errors(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    with pytest.raises(DomainValidationError, match="non-public"):
        _create(
            service,
            room.id,
            player,
            image_url="http://127.0.0.1/image.png",
        )


def test_storage_failure_is_a_service_unavailable_error(
    service: CharacterService,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    def fail_store(_data: bytes) -> None:
        raise MediaError("disk full")

    monkeypatch.setattr(service.storage, "save_character_image", fail_store)

    with pytest.raises(ServiceUnavailableError):
        _create(
            service,
            room.id,
            player,
            image=BytesIO(image_bytes()),
        )


def test_commit_failure_removes_the_new_file(
    service: CharacterService,
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    def fail_commit() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        _create(
            service,
            room.id,
            player,
            image=BytesIO(image_bytes()),
        )

    assert _stored_images(settings) == []


def test_cleanup_failure_does_not_mask_the_database_error(
    service: CharacterService,
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)

    def fail_commit() -> None:
        raise RuntimeError("database unavailable")

    def fail_delete(_path: str) -> bool:
        raise MediaError("permission denied")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(service.storage, "delete", fail_delete)

    with pytest.raises(RuntimeError, match="database unavailable"):
        _create(
            service,
            room.id,
            player,
            image=BytesIO(image_bytes()),
        )

    assert len(_stored_images(settings)) == 1


def test_unique_constraint_race_removes_the_new_file(
    service: CharacterService,
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)
    db_session.commit()
    _create(
        service,
        room.id,
        player,
        image=BytesIO(image_bytes()),
    )
    assert len(_stored_images(settings)) == 1

    monkeypatch.setattr(service.characters, "name_keys_exist", lambda *_args: False)

    with pytest.raises(ConflictError):
        _create(
            service,
            room.id,
            player,
            image=BytesIO(image_bytes()),
        )

    assert len(_stored_images(settings)) == 1


def test_delete_commit_failure_keeps_the_row_and_file(
    service: CharacterService,
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)
    character = _create(
        service,
        room.id,
        player,
        image=BytesIO(image_bytes()),
    )
    character_id = character.id
    assert len(_stored_images(settings)) == 1

    def fail_commit() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.delete_character(room.id, character_id, player)

    assert db_session.get(Character, character_id) is not None
    assert len(_stored_images(settings)) == 1


def test_delete_media_failure_still_deletes_the_row(
    service: CharacterService,
    db_session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = make_room(db_session)
    player = make_player(db_session, room, is_host=True)
    character = _create(
        service,
        room.id,
        player,
        image=BytesIO(image_bytes()),
    )
    character_id = character.id

    def fail_delete(_path: str) -> bool:
        raise MediaError("permission denied")

    monkeypatch.setattr(service.storage, "delete", fail_delete)

    service.delete_character(room.id, character_id, player)

    assert db_session.get(Character, character_id) is None
    assert len(_stored_images(settings)) == 1


def test_delete_permissions_cover_host_contributor_and_others(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    host = make_player(db_session, room, nickname="Host", is_host=True)
    contributor = make_player(db_session, room, nickname="Contributor")
    other = make_player(db_session, room, nickname="Other")

    first = _create(
        service,
        room.id,
        contributor,
        name="Naruto",
        image=BytesIO(image_bytes()),
    )
    with pytest.raises(PermissionDeniedError):
        service.delete_character(room.id, first.id, other)

    service.delete_character(room.id, first.id, contributor)

    second = _create(
        service,
        room.id,
        contributor,
        name="Goku",
        image=BytesIO(image_bytes()),
    )
    service.delete_character(room.id, second.id, host)

    orphaned = Character(
        room_id=room.id,
        name="Luffy",
        name_key="luffy",
        franchise=None,
        franchise_key="",
        category=CharacterCategory.ANIME,
        image_path="characters/missing.webp",
        attributes={},
        contributed_by=None,
    )
    db_session.add(orphaned)
    db_session.commit()

    with pytest.raises(PermissionDeniedError):
        service.delete_character(room.id, orphaned.id, other)

    service.delete_character(room.id, orphaned.id, host)


def test_non_members_cannot_read_or_write(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    host = make_player(db_session, room, is_host=True)
    other_room = make_room(db_session, code="GTC-OTHER")
    outsider = make_player(db_session, other_room, nickname="Outsider", is_host=True)
    character = _create(
        service,
        room.id,
        host,
        image=BytesIO(image_bytes()),
    )

    with pytest.raises(NotFoundError):
        service.list_characters(room.id, outsider)
    with pytest.raises(NotFoundError):
        service.get_character(room.id, character.id, outsider)
    with pytest.raises(NotFoundError):
        service.delete_character(room.id, character.id, outsider)
    with pytest.raises(NotFoundError):
        _create(
            service,
            room.id,
            outsider,
            image=BytesIO(image_bytes()),
        )


def test_characters_cannot_be_read_across_rooms(
    service: CharacterService,
    db_session: Session,
) -> None:
    first_room = make_room(db_session, code="GTC-FIRST")
    second_room = make_room(db_session, code="GTC-SECOND")
    first_host = make_player(db_session, first_room, is_host=True)
    second_host = make_player(db_session, second_room, nickname="Second", is_host=True)
    character = _create(
        service,
        first_room.id,
        first_host,
        image=BytesIO(image_bytes()),
    )

    with pytest.raises(NotFoundError):
        service.get_character(second_room.id, character.id, second_host)


def test_creation_and_deletion_are_frozen_after_start(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    host = make_player(db_session, room, is_host=True)
    character = _create(
        service,
        room.id,
        host,
        image=BytesIO(image_bytes()),
    )
    db_session.commit()

    room.status = RoomStatus.IN_PROGRESS
    db_session.commit()

    with pytest.raises(ConflictError):
        _create(
            service,
            room.id,
            host,
            name="Goku",
            image=BytesIO(image_bytes()),
        )
    with pytest.raises(ConflictError):
        service.delete_character(room.id, character.id, host)


def test_missing_room_and_character_are_not_found(
    service: CharacterService,
    db_session: Session,
) -> None:
    room = make_room(db_session)
    host = make_player(db_session, room, is_host=True)

    with pytest.raises(NotFoundError):
        service.list_characters(uuid.uuid4(), host)
    with pytest.raises(NotFoundError):
        service.get_character(room.id, uuid.uuid4(), host)
