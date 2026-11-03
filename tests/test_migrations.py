"""The migrations and the models agree."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from notify_hub.db import models  # noqa: F401 - registers the tables
from notify_hub.db.base import Base
from notify_hub.db.migrate import upgrade_head
from notify_hub.db.session import sync_url
from notify_hub.settings import get_settings


def test_models_match_migrations() -> None:
    """A model change without a revision fails here: run ``make db-revision MSG=...``."""
    url = get_settings().database_url
    upgrade_head(url)
    upgrade_head(url)  # idempotent
    with create_engine(sync_url(url)).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
