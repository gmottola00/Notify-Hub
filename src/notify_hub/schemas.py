"""Request and response bodies."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from notify_hub.push import Urgency


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class SubscriptionIn(BaseModel):
    """``PushSubscription.toJSON()`` as the browser produces it, plus an optional label."""

    endpoint: HttpUrl
    keys: SubscriptionKeys
    label: str | None = Field(default=None, max_length=255)
    """Free text to tell devices apart in the list, e.g. the user agent."""


class SubscriptionRef(BaseModel):
    endpoint: HttpUrl


class SubscriptionOut(BaseModel):
    id: int
    endpoint: str
    label: str | None
    created_at: datetime
    last_success_at: datetime | None
    failures: int


class NotifyIn(BaseModel):
    """One notification for every device subscribed to the calling app.

    ``url`` is a path inside the app (``/budget``), opened when the notification
    is tapped. ``tag`` replaces an earlier notification with the same tag on the
    phone, and becomes the ``Topic`` header for the push service.
    """

    title: str = Field(min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=500, pattern=r"^/")
    tag: str | None = Field(default=None, max_length=120)
    ttl: int | None = Field(default=None, ge=0, le=2_419_200)
    urgency: Urgency = "normal"


class NotifyResult(BaseModel):
    sent: int
    failed: int
    removed: int


class PublicKey(BaseModel):
    key: str


__all__ = ["NotifyIn", "NotifyResult", "PublicKey", "SubscriptionIn", "SubscriptionOut", "SubscriptionRef"]
