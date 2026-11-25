"""Tests for content-based image validation and WebP re-encoding."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

import pytest
from PIL import Image

from app.core import images
from app.core.images import (
    ImageTooLargeError,
    ImageValidationError,
    validate_and_normalize_image,
)
from tests.image_helpers import image_bytes


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_allowed_formats_are_reencoded_as_webp(image_format: str) -> None:
    normalized = validate_and_normalize_image(BytesIO(image_bytes(image_format)))

    with Image.open(BytesIO(normalized.data)) as stored:
        assert stored.format == "WEBP"
        assert stored.size == (normalized.width, normalized.height)
        assert stored.size == (64, 64)


def test_rgba_transparency_is_preserved() -> None:
    normalized = validate_and_normalize_image(
        BytesIO(image_bytes("PNG", mode="RGBA", color=(10, 20, 30, 0)))
    )

    with Image.open(BytesIO(normalized.data)) as stored:
        assert stored.mode == "RGBA"


def test_large_images_are_thumbnail_bounded() -> None:
    normalized = validate_and_normalize_image(BytesIO(image_bytes("PNG", size=(2000, 1000))))

    assert (normalized.width, normalized.height) == (1600, 800)
    with Image.open(BytesIO(normalized.data)) as stored:
        assert stored.size == (1600, 800)


def test_pixel_limit_is_enforced_before_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(ImageValidationError, match="dimensions"):
        validate_and_normalize_image(BytesIO(image_bytes("PNG", size=(20, 20))))


def test_pixel_limit_accepts_images_at_the_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 100)

    normalized = validate_and_normalize_image(BytesIO(image_bytes("PNG", size=(10, 10))))

    assert normalized.width == 10


def test_empty_and_non_image_content_is_rejected() -> None:
    with pytest.raises(ImageValidationError, match="empty"):
        validate_and_normalize_image(BytesIO(b""))
    with pytest.raises(ImageValidationError):
        validate_and_normalize_image(BytesIO(b"this is not an image"))


def test_unsupported_but_real_image_formats_are_rejected() -> None:
    gif = image_bytes("GIF")

    with pytest.raises(ImageValidationError, match="Unsupported image format"):
        validate_and_normalize_image(BytesIO(gif))


def test_byte_limit_rejects_oversized_streams() -> None:
    data = image_bytes("PNG", size=(64, 64))

    with pytest.raises(ImageTooLargeError, match="limit"):
        validate_and_normalize_image(BytesIO(data), max_bytes=50)


def test_stream_is_read_in_bounded_chunks() -> None:
    payload = image_bytes("PNG")

    class GuardedStream(BytesIO):
        def read(self, size: int = -1) -> bytes:
            if size < 0:
                raise AssertionError("image validation must stream with a size limit")
            assert size <= 64 * 1024
            return super().read(size)

    normalized = validate_and_normalize_image(GuardedStream(payload))

    assert normalized.data


def test_source_position_is_reset_before_reading() -> None:
    payload = image_bytes("PNG")
    source: BinaryIO = BytesIO(payload)
    source.read(10)

    normalized = validate_and_normalize_image(source)

    assert normalized.width == 64


def test_empty_reencoded_output_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = image_bytes("PNG")

    def save_nothing(_image: Image.Image, _output: BytesIO, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(Image.Image, "save", save_nothing)

    with pytest.raises(ImageValidationError, match="could not be processed"):
        validate_and_normalize_image(BytesIO(payload))


def test_reencoded_output_must_still_fit_the_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = image_bytes("PNG")

    def save_huge(
        _image: Image.Image,
        output: BytesIO,
        **_kwargs: object,
    ) -> None:
        output.write(b"x" * 2_000)

    monkeypatch.setattr(Image.Image, "save", save_huge)

    with pytest.raises(ImageTooLargeError, match="limit"):
        validate_and_normalize_image(BytesIO(payload), max_bytes=1_000)
