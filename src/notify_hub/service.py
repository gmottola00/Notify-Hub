"""Subscriptions and fan-out. Every method is scoped to one app: no call reads or touches another app's rows."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from notify_hub.db.models import Subscription, utcnow
from notify_hub.db.session import build_engine, build_sessionmaker
from notify_hub.logging import get_logger
from notify_hub.push import Message, Outcome, Sender, Target, topic_from_tag
from notify_hub.schemas import NotifyIn, NotifyResult, SubscriptionIn

logger = get_logger(__name__)


class EndpointTaken(Exception):
    """The endpoint is registered by another app. Endpoints are per subscription, so this is a mistake or a probe."""


class NotifyService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        sender: Sender,
        *,
        default_ttl: int = 86_400,
        concurrency: int = 10,
        engine: AsyncEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._sender = sender
        self._default_ttl = default_ttl
        self._concurrency = concurrency
        self._engine = engine

    @classmethod
    def from_url(cls, url: str, sender: Sender, **kwargs: Any) -> NotifyService:
        engine = build_engine(url)
        return cls(build_sessionmaker(engine), sender, engine=engine, **kwargs)

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    # --- subscriptions -------------------------------------------------------

    async def subscribe(self, app: str, sub: SubscriptionIn) -> Subscription:
        """Insert, or refresh the keys and label of an endpoint already known. Idempotent."""
        endpoint = str(sub.endpoint)
        async with self._sessions() as session, session.begin():
            row = await session.scalar(select(Subscription).where(Subscription.endpoint == endpoint))
            if row is not None and row.app != app:
                raise EndpointTaken(endpoint)
            if row is None:
                row = Subscription(app=app, endpoint=endpoint, failures=0, created_at=utcnow())
                session.add(row)
                logger.info("subscription.added", app=app, label=sub.label)
            row.p256dh = sub.keys.p256dh
            row.auth = sub.keys.auth
            row.label = sub.label
            row.failures = 0
        return row

    async def unsubscribe(self, app: str, endpoint: str) -> bool:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                delete(Subscription).where(Subscription.app == app, Subscription.endpoint == endpoint)
            )
        removed = bool(getattr(result, "rowcount", 0))
        if removed:
            logger.info("subscription.removed", app=app, reason="client")
        return removed

    async def devices(self, app: str) -> list[Subscription]:
        async with self._sessions() as session:
            rows = await session.scalars(select(Subscription).where(Subscription.app == app).order_by(Subscription.id))
            return list(rows)

    # --- delivery ------------------------------------------------------------

    async def notify(self, app: str, note: NotifyIn) -> NotifyResult:
        """Push ``note`` to every device of ``app`` concurrently, then record each outcome."""
        subs = await self.devices(app)
        payload: dict[str, Any] = {"title": note.title}
        for key in ("body", "url", "tag"):
            if (value := getattr(note, key)) is not None:
                payload[key] = value
        message = Message(
            payload=payload,
            ttl=self._default_ttl if note.ttl is None else note.ttl,
            urgency=note.urgency,
            topic=topic_from_tag(note.tag),
        )

        gate = asyncio.Semaphore(self._concurrency)

        async def one(sub: Subscription) -> Outcome:
            async with gate:
                return await self._sender.send(Target(sub.endpoint, sub.p256dh, sub.auth), message)

        outcomes = await asyncio.gather(*(one(s) for s in subs))
        await self._record(subs, outcomes)

        result = NotifyResult(
            sent=sum(o.status == "sent" for o in outcomes),
            failed=sum(o.status == "failed" for o in outcomes),
            removed=sum(o.status == "gone" for o in outcomes),
        )
        logger.info("notify.sent", app=app, tag=note.tag, devices=len(subs), **result.model_dump())
        return result

    async def _record(self, subs: list[Subscription], outcomes: list[Outcome]) -> None:
        if not subs:
            return
        now = utcnow()
        async with self._sessions() as session, session.begin():
            for sub, outcome in zip(subs, outcomes):
                row = await session.get(Subscription, sub.id)
                if row is None:  # unsubscribed while the push was in flight
                    continue
                if outcome.status == "sent":
                    row.last_success_at = now
                    row.failures = 0
                elif outcome.status == "gone":
                    await session.delete(row)
                    logger.info("subscription.removed", app=row.app, reason="gone", http_status=outcome.http_status)
                else:
                    row.failures += 1
                    logger.warning(
                        "notify.failed",
                        app=row.app,
                        subscription=row.id,
                        http_status=outcome.http_status,
                        reason=outcome.reason,
                        failures=row.failures,
                    )


__all__ = ["EndpointTaken", "NotifyService"]
