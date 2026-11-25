"""Health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import AppSettingsDep, DbSessionDep
from app.core.exceptions import ServiceUnavailableError
from app.schemas.errors import ErrorResponse
from app.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Liveness check",
)
def health(settings: AppSettingsDep) -> HealthResponse:
    """Report that the application process is running."""
    return HealthResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    responses={
        503: {
            "model": ErrorResponse,
            "description": "The database is unavailable.",
        }
    },
)
def readiness(session: DbSessionDep) -> ReadinessResponse:
    """Verify that the application can reach its database."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database readiness check failed: %s", type(exc).__name__)
        raise ServiceUnavailableError("Database is not available.") from exc
    return ReadinessResponse()
