"""Aggregate API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import characters, health, matches, rooms, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(rooms.router)
api_router.include_router(characters.router)
api_router.include_router(sessions.router)
api_router.include_router(matches.router)
