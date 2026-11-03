"""WebPushSender maps the push service's answers to outcomes. pywebpush is patched: no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests
from pywebpush import WebPushException

from notify_hub import push
from notify_hub.push import Message, Target, WebPushSender, load_vapid

from .conftest import PEM

TARGET = Target("https://web.push.apple.com/QL1", "p", "a")
MESSAGE = Message(payload={"title": "Ciao", "url": "/budget"}, ttl=60, urgency="high", topic="t")


def _response(status: int, text: str = "") -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = text.encode()
    return r


@pytest.fixture
def sender() -> WebPushSender:
    return WebPushSender(load_vapid(PEM), "mailto:test@example.com")


async def test_sent_with_headers(sender: WebPushSender, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(push, "webpush", lambda **kw: calls.append(kw))
    outcome = await sender.send(TARGET, MESSAGE)
    assert outcome.status == "sent"
    (kw,) = calls
    assert kw["headers"] == {"Urgency": "high", "Topic": "t"}
    assert kw["ttl"] == 60
    assert kw["data"] == '{"title": "Ciao", "url": "/budget"}'
    assert kw["vapid_claims"] == {"sub": "mailto:test@example.com"}
    assert kw["subscription_info"] == {"endpoint": TARGET.endpoint, "keys": {"p256dh": "p", "auth": "a"}}


@pytest.mark.parametrize("status", [404, 410])
async def test_gone(sender: WebPushSender, monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    def fail(**_: Any) -> None:
        raise WebPushException("gone", response=_response(status))

    monkeypatch.setattr(push, "webpush", fail)
    assert (await sender.send(TARGET, MESSAGE)).status == "gone"


async def test_failed_keeps_reason(sender: WebPushSender, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(**_: Any) -> None:
        raise WebPushException("bad", response=_response(403, '{"reason":"BadJwtToken"}'))

    monkeypatch.setattr(push, "webpush", fail)
    outcome = await sender.send(TARGET, MESSAGE)
    assert (outcome.status, outcome.http_status) == ("failed", 403)
    assert outcome.reason is not None and "BadJwtToken" in outcome.reason


async def test_network_error(sender: WebPushSender, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(**_: Any) -> None:
        raise requests.ConnectionError("dns")

    monkeypatch.setattr(push, "webpush", fail)
    outcome = await sender.send(TARGET, MESSAGE)
    assert outcome.status == "failed" and outcome.http_status is None


def test_real_pywebpush_signs_with_our_key(
    sender: WebPushSender, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pywebpush accepts our Vapid object and produces a request (curl mode: nothing is sent).

    Curl mode always writes the payload to ``./encrypted.data``: run it in a temp dir.
    """
    monkeypatch.chdir(tmp_path)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from py_vapid import b64urlencode

    browser = ec.generate_private_key(ec.SECP256R1()).public_key()
    p256dh = b64urlencode(
        browser.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    curl = push.webpush(
        subscription_info={"endpoint": TARGET.endpoint, "keys": {"p256dh": p256dh, "auth": b64urlencode(b"0" * 16)}},
        data="{}",
        vapid_private_key=sender._vapid,
        vapid_claims={"sub": "mailto:test@example.com"},
        curl=True,
    )
    assert "vapid t=" in str(curl)
