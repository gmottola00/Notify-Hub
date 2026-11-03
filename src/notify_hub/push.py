"""Delivery to a push service (Apple, Mozilla, Google), behind a protocol.

The service only ever talks to :class:`Sender`. In production that is
:class:`WebPushSender` (pywebpush, which is synchronous and runs in a thread);
tests pass a fake, so the suite never touches the network.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid, b64urlencode
from pywebpush import WebPushException, webpush

Urgency = Literal["very-low", "low", "normal", "high"]


@dataclass(frozen=True)
class Target:
    """Where one push goes: the browser's PushSubscription, as stored."""

    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class Message:
    """What goes out: the JSON payload ``sw.js`` reads, plus the delivery headers."""

    payload: dict[str, Any]
    ttl: int
    urgency: Urgency = "normal"
    topic: str | None = None


@dataclass(frozen=True)
class Outcome:
    """How one delivery went.

    ``gone`` means the push service said 404 or 410: the subscription is dead
    for good (app removed, permission revoked) and must be deleted.
    """

    status: Literal["sent", "gone", "failed"]
    http_status: int | None = None
    reason: str | None = None


class Sender(Protocol):
    async def send(self, target: Target, message: Message) -> Outcome: ...


_TOPIC_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def topic_from_tag(tag: str | None) -> str | None:
    """The ``Topic`` header for a tag: at most 32 URL-safe base64 characters, as RFC 8030 asks.

    A push with the same topic replaces one still waiting for an offline phone,
    so ten budget warnings while the phone is off arrive as one.

    Example:
        >>> topic_from_tag("budget:2026-11/ristoranti")
        'budget_2026-11_ristoranti'
        >>> topic_from_tag("x" * 40) == "x" * 32
        True
        >>> topic_from_tag(None) is None, topic_from_tag("::") is None
        (True, True)
    """
    if not tag:
        return None
    topic = _TOPIC_UNSAFE.sub("_", tag)[:32].strip("_")
    return topic or None


def load_vapid(pem: str) -> Vapid:
    """Parse the PEM private key once, at startup. A bad key fails the boot, not the first push.

    A PEM squeezed onto one line with literal ``\\n`` (an env file read by a
    shell, a ``--from-literal``) is accepted too.

    Example:
        >>> from notify_hub.keys import new_vapid_pem
        >>> pem = new_vapid_pem()
        >>> public_key(load_vapid(pem)) == public_key(load_vapid(pem.replace("\\n", "\\\\n")))
        True
    """
    return Vapid.from_pem(pem.strip().replace("\\n", "\n").encode())


def public_key(vapid: Vapid) -> str:
    """The uncompressed public point, base64url without padding: what ``applicationServerKey`` takes."""
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return str(b64urlencode(raw))


class WebPushSender:
    """pywebpush over a thread. Every call builds fresh claims: pywebpush mutates the dict it is given."""

    def __init__(self, vapid: Vapid, subject: str, timeout: float = 10.0) -> None:
        self._vapid = vapid
        self._subject = subject
        self._timeout = timeout

    async def send(self, target: Target, message: Message) -> Outcome:
        return await asyncio.to_thread(self._send, target, message)

    def _send(self, target: Target, message: Message) -> Outcome:
        headers: dict[str, str | int | float] = {"Urgency": message.urgency}
        if message.topic:
            headers["Topic"] = message.topic
        try:
            webpush(
                subscription_info={"endpoint": target.endpoint, "keys": {"p256dh": target.p256dh, "auth": target.auth}},
                data=json.dumps(message.payload, ensure_ascii=False),
                vapid_private_key=self._vapid,
                vapid_claims={"sub": self._subject},
                ttl=message.ttl,
                headers=headers,
                timeout=self._timeout,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                return Outcome("gone", status)
            reason = (exc.response.text[:200] if exc.response is not None else str(exc)) or None
            return Outcome("failed", status, reason)
        except Exception as exc:  # network: DNS, TLS, timeout
            return Outcome("failed", None, f"{type(exc).__name__}: {exc}"[:200])
        return Outcome("sent", 201)


__all__ = [
    "Message",
    "Outcome",
    "Sender",
    "Target",
    "Urgency",
    "WebPushSender",
    "load_vapid",
    "public_key",
    "topic_from_tag",
]
