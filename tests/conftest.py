"""Shared fixtures: a real app on a per-test SQLite file, with a fake push sender."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

# Nothing from a developer's .env may leak in.
os.environ.pop("NOTIFY_APPS", None)
os.environ.pop("NOTIFY_VAPID_PRIVATE_KEY", None)

from notify_hub.api.app import create_app  # noqa: E402
from notify_hub.auth import digest  # noqa: E402
from notify_hub.keys import new_vapid_pem  # noqa: E402
from notify_hub.push import Message, Outcome, Target  # noqa: E402
from notify_hub.settings import get_settings  # noqa: E402

TOKENS = {"alfred": "alfred-token", "jarvis": "jarvis-token"}
PEM = new_vapid_pem()


@dataclass
class FakeSender:
    """Records every push; ``outcomes[endpoint]`` scripts the reply (default: sent)."""

    outcomes: dict[str, Outcome] = field(default_factory=dict)
    sent: list[tuple[Target, Message]] = field(default_factory=list)

    async def send(self, target: Target, message: Message) -> Outcome:
        self.sent.append((target, message))
        return self.outcomes.get(target.endpoint, Outcome("sent", 201))


@pytest.fixture(autouse=True)
def _env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("NOTIFY_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/notify.db")
    monkeypatch.setenv("NOTIFY_VAPID_PRIVATE_KEY", PEM)
    monkeypatch.setenv("NOTIFY_VAPID_SUBJECT", "mailto:test@example.com")
    monkeypatch.setenv("NOTIFY_APPS", json.dumps({app: digest(tok) for app, tok in TOKENS.items()}))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def client(sender: FakeSender) -> Iterator[TestClient]:
    with TestClient(create_app(sender=sender)) as c:
        yield c


def auth(app: str = "alfred") -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[app]}"}


def subscription(n: int = 1, label: str | None = None) -> dict[str, Any]:
    return {
        "endpoint": f"https://web.push.apple.com/QL{n}",
        "keys": {"p256dh": f"p256dh-{n}", "auth": f"auth-{n}"},
        "label": label,
    }
