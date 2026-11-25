"""Alembic environment configured from application settings.

The database URL comes from the Alembic config when explicitly provided
(useful for tests and one-off commands), otherwise from ``Settings``.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registers all model metadata)
from app.core.config import get_settings
from app.database.base import Base, UTCDateTime

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve the migration target URL, preferring an explicit Alembic value."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return get_settings().database_url


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render project-specific types so generated migrations stay self-contained."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from app.database.base import UTCDateTime")
        return "UTCDateTime()"
    return False


def _configure_context(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=kwargs.get("connection") is not None
        and kwargs["connection"].dialect.name == "sqlite",
        render_item=render_item,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Emit migration SQL without a database connection."""
    _configure_context(
        url=get_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _configure_context(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
