"""Translate exceptions into the single public JSON error envelope."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_CODE_BY_STATUS: dict[int, str] = {
    400: "bad_request",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "service_unavailable",
}

_MESSAGE_BY_STATUS: dict[int, str] = {
    400: "The request could not be processed.",
    401: "Valid credentials are required.",
    403: "You are not allowed to perform this action.",
    404: "The requested resource was not found.",
    405: "The HTTP method is not allowed for this resource.",
    409: "The request conflicts with the current state.",
    422: "The request contains invalid data.",
    429: "Too many requests. Try again later.",
    500: "An unexpected error occurred.",
    503: "The service is temporarily unavailable.",
}


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    if error.status_code >= 500:
        logger.error("Application error: %s", error.message, exc_info=error)
    else:
        logger.info("Client error %s: %s", error.code, error.message)

    headers = dict(error.headers or {})
    if error.status_code == 401:
        headers.setdefault("WWW-Authenticate", "Bearer")

    return _error_response(
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        details=error.details,
        headers=headers or None,
    )


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    validation_error = cast(RequestValidationError, exc)
    details = [
        {
            "location": list(item["loc"]),
            "message": item["msg"],
            "type": item["type"],
        }
        for item in validation_error.errors()
    ]
    return _error_response(
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        details=details,
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    http_error = cast(StarletteHTTPException, exc)
    status_code = http_error.status_code
    message = http_error.detail if isinstance(http_error.detail, str) else None
    details = None if isinstance(http_error.detail, str) else http_error.detail

    return _error_response(
        status_code=status_code,
        code=_CODE_BY_STATUS.get(status_code, "http_error"),
        message=message or _MESSAGE_BY_STATUS.get(status_code, "The request failed."),
        details=details,
        headers=dict(http_error.headers) if http_error.headers else None,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled error while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return _error_response(
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers for domain, validation, HTTP, and unexpected errors."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
