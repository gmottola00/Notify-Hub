"""Alertmanager webhook: routing, auth and the notification it becomes."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from notify_hub.alerts import tag_for

from .conftest import FakeSender, auth, subscription


def webhook(status: str = "firing", severity: str = "critical", n: int = 1) -> dict[str, Any]:
    """A trimmed version of what Alertmanager really posts (extra fields included)."""
    return {
        "version": "4",
        "receiver": "notify",
        "status": status,
        "groupKey": '{}:{alertname="PgSharedDown"}',
        "groupLabels": {"alertname": "PgSharedDown"},
        "commonLabels": {"alertname": "PgSharedDown"},
        "externalURL": "http://alertmanager:9093",
        "truncatedAlerts": 0,
        "alerts": [
            {
                "status": status,
                "labels": {"alertname": "PgSharedDown", "severity": severity, "pod": f"pg-shared-{i}"},
                "annotations": {"summary": "Postgres pg-shared è giù", "description": "Le app sono senza DB."},
                "startsAt": "2026-11-17T10:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://prometheus/graph",
                "fingerprint": f"f{i}",
            }
            for i in range(n)
        ],
    }


class TestAlertmanager:
    def test_routes_to_target_app_devices(self, client: TestClient, sender: FakeSender) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth("alfred"))
        client.put("/v1/subscriptions", json=subscription(2), headers=auth("jarvis"))

        r = client.post("/v1/alertmanager", json=webhook(), headers=auth("alertmanager"))

        assert r.status_code == 200 and r.json()["sent"] == 1
        target, message = sender.sent[0]
        assert target.endpoint == subscription(1)["endpoint"]
        assert message.payload["title"] == "🔴 Postgres pg-shared è giù"
        assert message.payload["tag"] == tag_for('{}:{alertname="PgSharedDown"}')
        assert message.urgency == "high"

    def test_resolved_replaces_firing(self, client: TestClient, sender: FakeSender) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth("alfred"))
        client.post("/v1/alertmanager", json=webhook("firing"), headers=auth("alertmanager"))
        client.post("/v1/alertmanager", json=webhook("resolved"), headers=auth("alertmanager"))

        (_, firing), (_, resolved) = sender.sent
        assert resolved.payload["title"].startswith("✅ Risolto")
        assert resolved.topic == firing.topic and resolved.urgency == "normal"

    def test_warning_is_normal_urgency_and_counts_others(self, client: TestClient, sender: FakeSender) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth("alfred"))
        client.post("/v1/alertmanager", json=webhook(severity="warning", n=3), headers=auth("alertmanager"))

        _, message = sender.sent[0]
        assert message.urgency == "normal"
        assert message.payload["title"].startswith("🟠")
        assert message.payload["body"].endswith("(+2 altre allerte)")

    def test_caller_without_route_is_forbidden(self, client: TestClient, sender: FakeSender) -> None:
        r = client.post("/v1/alertmanager", json=webhook(), headers=auth("jarvis"))
        assert r.status_code == 403 and sender.sent == []

    def test_needs_token(self, client: TestClient) -> None:
        assert client.post("/v1/alertmanager", json=webhook()).status_code == 401
