"""Engine and session factory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(url: str) -> AsyncEngine:
    """Create the async engine, with SQLite foreign keys switched on."""
    engine = create_async_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def sync_url(url: str) -> str:
    """The synchronous twin of an async URL, for Alembic.

    ``postgresql+psycopg`` is both, so only SQLite needs rewriting.

    Example:
        >>> sync_url("sqlite+aiosqlite:///./notify.db")
        'sqlite:///./notify.db'
    """
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


__all__ = ["build_engine", "build_sessionmaker", "sync_url"]
