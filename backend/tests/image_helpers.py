"""In-memory image fixtures used by Phase 3 tests."""

from __future__ import annotations

from io import BytesIO

from PIL import Image


def image_bytes(
    image_format: str = "PNG",
    *,
    size: tuple[int, int] = (64, 64),
    color: tuple[int, ...] = (220, 30, 40),
    mode: str = "RGB",
) -> bytes:
    """Return a real image encoded in the requested Pillow format."""
    if mode == "RGBA" and len(color) == 3:
        color = (*color, 255)
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()
