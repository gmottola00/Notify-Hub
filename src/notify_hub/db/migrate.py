"""Run the Alembic migrations from inside the application.

The lifespan calls :func:`upgrade_head` before anything touches the database, so
a fresh Postgres and a fresh SQLite file both come up at the latest schema. The
config is built in code — no dependency on an ``alembic.ini`` next to the
process — so it works the same from a wheel, an editable install or a container.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from notify_hub.db.session import sync_url

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", sync_url(url).replace("%", "%%"))
    return cfg


def upgrade_head(url: str) -> None:
    """Bring the schema at ``url`` to the latest revision. A no-op when already there."""
    command.upgrade(alembic_config(url), "head")


__all__ = ["alembic_config", "upgrade_head"]
