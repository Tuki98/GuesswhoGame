"""Image content validation and normalization using Pillow.

Uploaded and downloaded bytes are untrusted. They are streamed through a size
cap, decoded, checked against a pixel cap, and re-encoded as WebP before being
persisted. Re-encoding strips metadata and ensures the stored bytes are a real
image rather than a polyglot or a renamed non-image file.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 1600
WEBP_QUALITY = 85
_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
_READ_CHUNK_BYTES = 64 * 1024
_SPOOL_BYTES = 1024 * 1024


class ImageValidationError(ValueError):
    """Raised when image bytes are missing, malformed, or unsupported."""


class ImageTooLargeError(ImageValidationError):
    """Raised when an image exceeds the configured byte limit."""


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    data: bytes
    width: int
    height: int


def _spool_source(source: BinaryIO, max_bytes: int) -> tempfile.SpooledTemporaryFile[bytes]:
    """Copy a stream into a bounded temporary file without unbounded memory use."""
    # Ownership is transferred to the caller, which closes it in a ``finally``.
    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES, mode="w+b")  # noqa: SIM115
    total = 0
    try:
        while chunk := source.read(_READ_CHUNK_BYTES):
            total += len(chunk)
            if total > max_bytes:
                raise ImageTooLargeError(
                    f"Image exceeds the {max_bytes // (1024 * 1024)} MB limit."
                )
            spool.write(chunk)
        if total == 0:
            raise ImageValidationError("Image file is empty.")
        spool.seek(0)
        return spool
    except Exception:
        spool.close()
        raise


def validate_and_normalize_image(
    source: BinaryIO,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> NormalizedImage:
    """Validate image bytes and return a bounded, re-encoded WebP image."""
    source.seek(0)
    spool = _spool_source(source, max_bytes)
    try:
        try:
            with Image.open(spool) as header:
                image_format = header.format
                width, height = header.size
                if image_format not in _ALLOWED_FORMATS:
                    raise ImageValidationError("Unsupported image format. Use JPEG, PNG, or WebP.")
                if width <= 0 or height <= 0:
                    raise ImageValidationError("Image has invalid dimensions.")
                if width * height > MAX_IMAGE_PIXELS:
                    raise ImageValidationError("Image dimensions are too large.")

            spool.seek(0)
            with Image.open(spool) as opened:
                opened.load()
                opened.seek(0)
                if opened.mode in {"RGBA", "LA"} or (
                    opened.mode == "P" and "transparency" in opened.info
                ):
                    working = opened.convert("RGBA")
                else:
                    working = opened.convert("RGB")
                working.thumbnail(
                    (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                    Image.Resampling.LANCZOS,
                )

                output = BytesIO()
                working.save(output, format="WEBP", quality=WEBP_QUALITY, method=4)
                data = output.getvalue()
                output_width, output_height = working.size
        except ImageValidationError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
            raise ImageValidationError("The file is not a valid JPEG, PNG, or WebP image.") from exc

        if not data:
            raise ImageValidationError("Image could not be processed.")
        if len(data) > max_bytes:
            raise ImageTooLargeError(f"Image exceeds the {max_bytes // (1024 * 1024)} MB limit.")
        return NormalizedImage(data=data, width=output_width, height=output_height)
    finally:
        spool.close()
