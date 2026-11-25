"""Character collection business logic.

The service owns all validation, authorization, and transaction boundaries for
room characters. Route handlers only translate HTTP payloads into a
:class:`CharacterService` call and map the result back to a response schema.
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from typing import Any, BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.characters import (
    CharacterValidationError,
    character_uniqueness_keys,
    normalize_category,
    normalize_character_name,
    normalize_franchise,
    validate_attributes,
)
from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.core.image_download import ImageDownloader, ImageDownloadError
from app.core.images import (
    ImageValidationError,
    NormalizedImage,
    validate_and_normalize_image,
)
from app.core.media import MediaError, MediaStorage
from app.core.url_safety import UnsafeUrlError
from app.models import Character, CharacterCategory, Player, Room, RoomStatus
from app.repositories.characters import CharacterRepository
from app.repositories.rooms import RoomRepository
from app.services.permissions import ensure_room_member

logger = logging.getLogger(__name__)


class CharacterService:
    """Coordinates the room character collection. No HTTP dependencies."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        storage: MediaStorage,
        downloader: ImageDownloader,
    ) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage
        self.downloader = downloader
        self.rooms = RoomRepository(session)
        self.characters = CharacterRepository(session)

    # -- reads ----------------------------------------------------------------

    def list_characters(self, room_id: uuid.UUID, player: Player) -> list[Character]:
        room = self._member_room(room_id, player)
        return self.characters.list_by_room(room.id)

    def get_character(
        self,
        room_id: uuid.UUID,
        character_id: uuid.UUID,
        player: Player,
    ) -> Character:
        room = self._member_room(room_id, player)
        return self._room_character(room, character_id)

    # -- writes ---------------------------------------------------------------

    def create_character(
        self,
        room_id: uuid.UUID,
        player: Player,
        *,
        name: str,
        franchise: str | None,
        category: CharacterCategory | str,
        attributes: dict[str, Any] | None,
        image: BinaryIO | None = None,
        image_url: str | None = None,
    ) -> Character:
        """Add a validated character and its locally stored image.

        The contributor is always the authenticated player. Image bytes are
        validated and re-encoded before the row is inserted; if the database
        transaction fails, the freshly stored file is removed again.
        """
        room = self._member_room(room_id, player)
        self._require_waiting(room, "Characters can only be added while the room is waiting.")

        normalized_name, normalized_franchise = self._normalize_identity(name, franchise)
        normalized_category = self._normalize_category(category)
        normalized_attributes = self._normalize_attributes(attributes)
        name_key, franchise_key = character_uniqueness_keys(
            normalized_name,
            normalized_franchise,
        )

        if self.characters.name_keys_exist(room.id, name_key, franchise_key):
            raise ConflictError("This character already exists in this room.")

        normalized_image = self._normalize_image(image=image, image_url=image_url)

        try:
            stored = self.storage.save_character_image(normalized_image.data)
        except MediaError as exc:
            raise ServiceUnavailableError("The character image could not be stored.") from exc

        character = Character(
            room_id=room.id,
            name=normalized_name,
            name_key=name_key,
            franchise=normalized_franchise,
            franchise_key=franchise_key,
            category=normalized_category,
            image_path=stored.relative_path,
            attributes=normalized_attributes,
            contributed_by=player.id,
        )

        try:
            self.session.add(character)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            self._remove_stored_image(stored.relative_path)
            raise ConflictError("This character already exists in this room.") from exc
        except Exception:
            self.session.rollback()
            self._remove_stored_image(stored.relative_path)
            raise

        return character

    def delete_character(
        self,
        room_id: uuid.UUID,
        character_id: uuid.UUID,
        player: Player,
    ) -> None:
        """Delete a character when the room is waiting.

        The host may remove any character; every other member may remove only
        the characters they contributed. The contributor is never taken from
        client input.
        """
        room = self._member_room(room_id, player)
        self._require_waiting(
            room,
            "Characters can only be removed while the room is waiting.",
        )

        character = self._room_character(room, character_id)
        if player.id != room.host_player_id and character.contributed_by != player.id:
            raise PermissionDeniedError(
                "Only the host or the character's contributor can remove it."
            )

        image_path = character.image_path
        try:
            self.session.delete(character)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        # Delete the file only after the row is gone. A missing file is fine;
        # a filesystem error must not turn a successful database deletion into
        # an error response, so it is logged instead.
        try:
            self.storage.delete(image_path)
        except MediaError:
            logger.warning("Could not remove character image %s", image_path, exc_info=True)

    # -- validation helpers ---------------------------------------------------

    def _normalize_image(
        self,
        *,
        image: BinaryIO | None,
        image_url: str | None,
    ) -> NormalizedImage:
        if (image is None) == (image_url is None):
            raise DomainValidationError(
                "Provide exactly one image source: an image upload or an image URL."
            )

        if image is not None:
            return self._validate_image_stream(image)

        assert image_url is not None
        try:
            data = self.downloader.download(image_url)
        except (UnsafeUrlError, ImageDownloadError, ImageValidationError) as exc:
            raise DomainValidationError(str(exc)) from exc
        return self._validate_image_stream(BytesIO(data))

    def _validate_image_stream(self, source: BinaryIO) -> NormalizedImage:
        try:
            return validate_and_normalize_image(
                source,
                max_bytes=self.settings.image_max_bytes,
            )
        except ImageValidationError as exc:
            raise DomainValidationError(str(exc)) from exc

    @staticmethod
    def _normalize_identity(name: str, franchise: str | None) -> tuple[str, str | None]:
        try:
            return normalize_character_name(name), normalize_franchise(franchise)
        except CharacterValidationError as exc:
            raise DomainValidationError(str(exc)) from exc

    @staticmethod
    def _normalize_category(category: CharacterCategory | str) -> CharacterCategory:
        try:
            return normalize_category(category)
        except CharacterValidationError as exc:
            raise DomainValidationError(str(exc)) from exc

    @staticmethod
    def _normalize_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
        try:
            return validate_attributes(attributes)
        except CharacterValidationError as exc:
            raise DomainValidationError(str(exc)) from exc

    # -- room helpers ---------------------------------------------------------

    def _member_room(self, room_id: uuid.UUID, player: Player) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise NotFoundError("Room not found.")
        ensure_room_member(room, player)
        return room

    def _room_character(self, room: Room, character_id: uuid.UUID) -> Character:
        character = self.characters.get(character_id)
        if character is None or character.room_id != room.id:
            raise NotFoundError("Character not found.")
        return character

    @staticmethod
    def _require_waiting(room: Room, message: str) -> None:
        if room.status is not RoomStatus.WAITING:
            raise ConflictError(message)

    def _remove_stored_image(self, relative_path: str) -> None:
        try:
            self.storage.delete(relative_path)
        except MediaError:
            logger.warning("Could not clean up character image %s", relative_path, exc_info=True)
