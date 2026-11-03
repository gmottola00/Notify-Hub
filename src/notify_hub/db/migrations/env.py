"""Alembic environment. The URL always comes from :func:`notify_hub.db.migrate.alembic_config`."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from notify_hub.db import models  # noqa: F401 - registers the tables on Base.metadata
from notify_hub.db.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        # SQLite cannot ALTER most things in place; batch mode rebuilds the table.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
