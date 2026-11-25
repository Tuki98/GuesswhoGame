"""Tests for safe local image storage and path containment."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.media import MediaError, MediaStorage
from tests.image_helpers import image_bytes


def test_save_generates_unique_server_side_webp_paths(tmp_path: Path) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")
    first = storage.save_character_image(b"first")
    second = storage.save_character_image(b"second")

    assert first.relative_path.startswith("characters/")
    assert first.relative_path.endswith(".webp")
    assert first.relative_path != second.relative_path
    assert first.absolute_path.read_bytes() == b"first"
    assert second.absolute_path.read_bytes() == b"second"
    assert first.absolute_path.parent == tmp_path / "media" / "characters"


def test_public_url_never_contains_the_filesystem_root(tmp_path: Path) -> None:
    storage = MediaStorage(tmp_path / "media", "/media/")

    assert storage.public_url("characters/example.webp") == "/media/characters/example.webp"
    assert str(tmp_path) not in storage.public_url("characters/example.webp")


def test_delete_removes_files_and_is_idempotent(tmp_path: Path) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")
    stored = storage.save_character_image(image_bytes())

    assert storage.delete(stored.relative_path) is True
    assert not stored.absolute_path.exists()
    assert storage.delete(stored.relative_path) is False


@pytest.mark.parametrize(
    "relative_path",
    [
        "../escape.webp",
        "characters/../../escape.webp",
        "other/escape.webp",
        "/absolute/escape.webp",
    ],
)
def test_delete_rejects_paths_outside_the_characters_directory(
    tmp_path: Path,
    relative_path: str,
) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")

    with pytest.raises(MediaError, match="Invalid media path"):
        storage.delete(relative_path)


def test_absolute_windows_path_is_rejected(tmp_path: Path) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")

    with pytest.raises(MediaError, match="Invalid media path"):
        storage.delete(str(tmp_path / "escape.webp"))


def test_empty_images_are_not_stored(tmp_path: Path) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")

    with pytest.raises(MediaError, match="empty"):
        storage.save_character_image(b"")


def test_storage_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")

    def fail_write(self: Path, data: bytes) -> int:
        del self, data
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write)

    with pytest.raises(MediaError, match="could not be stored"):
        storage.save_character_image(b"data")


def test_delete_failure_is_wrapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MediaStorage(tmp_path / "media", "/media")
    stored = storage.save_character_image(b"data")

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:
        del self, missing_ok
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    with pytest.raises(MediaError, match="could not be removed"):
        storage.delete(stored.relative_path)
