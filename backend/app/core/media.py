"""Safe local storage for validated character images."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

CHARACTERS_SUBDIRECTORY = "characters"
_TEMP_PREFIX = ".upload-"


class MediaError(ValueError):
    """Raised when media cannot be stored or removed safely."""


@dataclass(frozen=True, slots=True)
class StoredImage:
    relative_path: str
    absolute_path: Path
    byte_size: int


class MediaStorage:
    """Store generated filenames under a configured media root.

    Every path is derived server-side. Callers never supply a filename, and
    deletion verifies that the resolved target stays inside the characters
    directory, which also blocks symlink escapes.
    """

    def __init__(self, root: Path, url_prefix: str) -> None:
        self.root = Path(root)
        self.url_prefix = url_prefix.rstrip("/")
        self.characters_directory = self.root / CHARACTERS_SUBDIRECTORY

    def ensure_ready(self) -> None:
        self.characters_directory.mkdir(parents=True, exist_ok=True)

    def save_character_image(self, data: bytes) -> StoredImage:
        """Persist validated WebP bytes under a random filename."""
        if not data:
            raise MediaError("Cannot store an empty image.")

        self.ensure_ready()
        filename = f"{uuid.uuid4().hex}.webp"
        relative_path = f"{CHARACTERS_SUBDIRECTORY}/{filename}"
        destination = self.characters_directory / filename
        temp_path = self.characters_directory / f"{_TEMP_PREFIX}{uuid.uuid4().hex}.tmp"

        try:
            temp_path.write_bytes(data)
            os.replace(temp_path, destination)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise MediaError("The image could not be stored.") from exc

        return StoredImage(
            relative_path=relative_path,
            absolute_path=destination,
            byte_size=len(data),
        )

    def delete(self, relative_path: str) -> bool:
        """Delete a stored image if it is safely inside the characters directory.

        Returns ``True`` when a file was removed. Missing files are treated as
        success so cleanup is idempotent.
        """
        target = self._resolve_character_path(relative_path)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise MediaError("The image could not be removed.") from exc
        return True

    def public_url(self, relative_path: str) -> str:
        """Build a browser-visible URL without exposing the filesystem root."""
        return f"{self.url_prefix}/{relative_path.lstrip('/')}"

    def _resolve_character_path(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise MediaError("Invalid media path.")

        root = self.characters_directory.resolve()
        target = (self.root / candidate).resolve()
        if not target.is_relative_to(root):
            raise MediaError("Invalid media path.")
        return target
