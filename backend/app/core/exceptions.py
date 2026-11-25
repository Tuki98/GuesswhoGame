"""Framework-independent application exceptions.

Domain and service layers raise these errors; the HTTP layer translates them
into a consistent JSON envelope. They deliberately depend neither on FastAPI
nor on Starlette.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue


class AppError(Exception):
    """Base class for expected application errors."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: JsonValue | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        self.headers = dict(headers) if headers else None
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    default_message = "The request could not be processed."


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_required"
    default_message = "Valid credentials are required."


class InvalidSessionError(AuthenticationError):
    """Generic authentication failure that never reveals token state."""

    code = "invalid_session"
    default_message = "Your session is invalid or has expired."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"
    default_message = "You are not allowed to perform this action."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with the current state."


class DomainValidationError(AppError):
    status_code = 422
    code = "validation_error"
    default_message = "The request contains invalid data."


class RateLimitedError(AppError):
    status_code = 429
    code = "too_many_requests"
    default_message = "Too many requests. Try again later."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    default_message = "The service is temporarily unavailable."
