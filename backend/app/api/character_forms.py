"""Request parsing for the character create endpoint.

FastAPI cannot bind a single route parameter that accepts both a JSON body and
a multipart form with a file, so this module performs the small amount of
content-type dispatch. Pydantic and request-validation errors are re-raised as
``RequestValidationError`` so the application's standard 422 error envelope is
used instead of a 500.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from app.schemas.characters import CreateCharacterRequest

_MULTIPART_TYPE = "multipart/form-data"
_JSON_TYPES = {"application/json", "application/merge-patch+json"}
_TEXT_FIELDS = ("name", "franchise", "category")


@dataclass(frozen=True, slots=True)
class CharacterSubmission:
    payload: CreateCharacterRequest
    upload: UploadFile | None


def _invalid(
    location: tuple[str | int, ...],
    message: str,
    error_type: str = "value_error",
) -> RequestValidationError:
    return RequestValidationError([{"loc": list(location), "msg": message, "type": error_type}])


def _content_type(request: Request) -> str:
    header = request.headers.get("content-type", "")
    return header.split(";", 1)[0].strip().lower()


async def parse_character_submission(
    request: Request,
    *,
    max_part_bytes: int,
) -> CharacterSubmission:
    """Parse a JSON or multipart character submission."""
    content_type = _content_type(request)
    if content_type in _JSON_TYPES:
        return await _parse_json(request)
    if content_type == _MULTIPART_TYPE:
        return await _parse_multipart(request, max_part_bytes=max_part_bytes)
    raise _invalid(
        ("body",),
        "Use application/json or multipart/form-data for character submissions.",
    )


async def _parse_json(request: Request) -> CharacterSubmission:
    try:
        raw = await request.json()
    except ValueError as exc:
        raise _invalid(("body",), "Request body must contain valid JSON.", "json_invalid") from exc

    if not isinstance(raw, dict):
        raise _invalid(("body",), "Request body must be a JSON object.", "type_error")

    try:
        payload = CreateCharacterRequest.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    if not payload.image_url or not payload.image_url.strip():
        raise _invalid(
            ("body", "image_url"),
            "An image_url is required when submitting JSON.",
            "missing",
        )
    return CharacterSubmission(payload=payload, upload=None)


async def _parse_multipart(
    request: Request,
    *,
    max_part_bytes: int,
) -> CharacterSubmission:
    try:
        form = await request.form(max_part_size=max_part_bytes)
    except (StarletteHTTPException, MultiPartException, ValueError) as exc:
        message = exc.detail if isinstance(exc, StarletteHTTPException) else str(exc)
        raise _invalid(("body",), message or "Invalid multipart request.") from exc

    upload: UploadFile | None = None
    try:
        values: dict[str, object] = {}
        for field in _TEXT_FIELDS:
            value = form.get(field)
            if value is None:
                continue
            if not isinstance(value, str):
                raise _invalid((field,), "Expected a text value.", "type_error")
            values[field] = value

        attributes_value = form.get("attributes")
        if attributes_value is not None:
            if not isinstance(attributes_value, str):
                raise _invalid(("attributes",), "Expected a JSON text value.", "type_error")
            if attributes_value.strip():
                try:
                    values["attributes"] = json.loads(attributes_value)
                except json.JSONDecodeError as exc:
                    raise _invalid(
                        ("attributes",),
                        "Attributes must be valid JSON.",
                        "json_invalid",
                    ) from exc

        image_url_value = form.get("image_url")
        if image_url_value is not None:
            if not isinstance(image_url_value, str):
                raise _invalid(("image_url",), "Expected a text value.", "type_error")
            if image_url_value.strip():
                values["image_url"] = image_url_value

        upload_value = form.get("image")
        if upload_value is not None:
            if not isinstance(upload_value, UploadFile):
                raise _invalid(("image",), "Expected an image file.", "type_error")
            upload = upload_value

        has_url = bool(values.get("image_url"))
        if upload is not None and has_url:
            raise _invalid(
                ("body",),
                "Provide exactly one image source: an image file or an image_url.",
            )
        if upload is None and not has_url:
            raise _invalid(
                ("body",),
                "Provide one image source: an image file or an image_url.",
                "missing",
            )

        try:
            payload = CreateCharacterRequest.model_validate(values)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
    except Exception:
        # The route never receives the form on a parse error, so close every
        # spooled upload here to avoid leaking temporary files.
        await form.close()
        raise

    # Unknown file fields are ignored, but their handles still need closing.
    for _key, value in form.multi_items():
        if isinstance(value, UploadFile) and value is not upload:
            await value.close()

    return CharacterSubmission(payload=payload, upload=upload)
