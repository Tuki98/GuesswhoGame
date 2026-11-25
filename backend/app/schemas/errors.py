"""Schemas describing the consistent API error envelope."""

from __future__ import annotations

from pydantic import BaseModel, JsonValue


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: JsonValue | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
