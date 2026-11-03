"""Tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from notify_hub.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subscription(Base):
    """One browser on one device, subscribed for one app.

    ``endpoint`` is globally unique: the push service mints it per subscription.
    A browser that re-subscribes for another app gets another endpoint.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    """Consecutive failed deliveries. Reset on success; a 404/410 deletes the row instead."""


__all__ = ["Subscription", "utcnow"]
