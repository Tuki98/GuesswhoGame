"""Database engine, session factory, and FastAPI session dependency."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _ensure_sqlite_directory(database_url: str) -> None:
    """Create the parent directory for file-backed SQLite databases."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database = url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return

    path = Path(database)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_foreign_keys(
    dbapi_connection: sqlite3.Connection,
    _connection_record: object,
) -> None:
    """SQLite disables foreign key enforcement by default; enable it per connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def build_engine(database_url: str) -> Engine:
    """Create an engine with project-wide connection settings."""
    url = make_url(database_url)
    engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
    connect_args: dict[str, Any] = {}

    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if url.database in (None, "", ":memory:"):
            engine_kwargs["poolclass"] = StaticPool
        else:
            _ensure_sqlite_directory(database_url)

    engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)

    if url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    return engine


class Database:
    """Owns the SQLAlchemy engine and session factory for one application instance."""

    def __init__(self, database_url: str) -> None:
        self.engine = build_engine(database_url)
        self.session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a transactional session scope."""
        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    database: Database = request.app.state.database
    with database.session() as session:
        yield session
