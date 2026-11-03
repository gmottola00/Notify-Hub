"""FastAPI application.

The lifespan migrates the database, loads the VAPID key and builds the service.
A missing or broken key stops the boot: a hub that cannot sign is not ready,
and Kubernetes should say so rather than accept subscriptions it cannot serve.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from notify_hub.api.routes import router
from notify_hub.db.migrate import upgrade_head
from notify_hub.logging import configure_logging, get_logger
from notify_hub.push import Sender, WebPushSender, load_vapid, public_key
from notify_hub.service import NotifyService
from notify_hub.settings import get_settings

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    if settings.vapid_private_key is None:
        raise RuntimeError("NOTIFY_VAPID_PRIVATE_KEY is not set (PEM, EC P-256)")
    vapid = load_vapid(settings.vapid_private_key.get_secret_value())

    await asyncio.to_thread(upgrade_head, settings.database_url)

    override: Sender | None = getattr(app.state, "sender_override", None)
    sender = override or WebPushSender(vapid, settings.vapid_subject, timeout=settings.push_timeout)
    service = NotifyService.from_url(
        settings.database_url,
        sender,
        default_ttl=settings.default_ttl,
        concurrency=settings.send_concurrency,
    )

    app.state.settings = settings
    app.state.service = service
    app.state.public_key = public_key(vapid)
    if not settings.apps:
        logger.warning("notify.no_apps", hint="NOTIFY_APPS is empty: every /v1 call will be 401")
    logger.info("notify.ready", apps=sorted(settings.apps), subject=settings.vapid_subject)
    yield
    await service.aclose()
    logger.info("notify.stopped")


def create_app(*, sender: Sender | None = None) -> FastAPI:
    """Build the ASGI app. ``sender`` replaces the real push delivery; tests only."""
    app = FastAPI(title="notify-hub", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    app.state.sender_override = sender
    return app


app = create_app()

__all__ = ["app", "create_app"]
