"""The HTTP contract: auth, subscriptions, fan-out and cleanup."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from notify_hub.push import Outcome

from .conftest import FakeSender, auth, subscription


class TestAuth:
    def test_health_is_open(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok"}

    def test_missing_token(self, client: TestClient) -> None:
        assert client.get("/v1/subscriptions").status_code == 401

    def test_wrong_token(self, client: TestClient) -> None:
        r = client.get("/v1/subscriptions", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_apps_are_isolated(self, client: TestClient) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth("alfred"))
        assert client.get("/v1/subscriptions", headers=auth("jarvis")).json() == []
        # Jarvis can neither steal nor delete Alfred's endpoint.
        assert client.put("/v1/subscriptions", json=subscription(1), headers=auth("jarvis")).status_code == 409
        client.request(
            "DELETE", "/v1/subscriptions", json={"endpoint": subscription(1)["endpoint"]}, headers=auth("jarvis")
        )
        assert len(client.get("/v1/subscriptions", headers=auth("alfred")).json()) == 1


class TestPublicKey:
    def test_uncompressed_p256_point(self, client: TestClient) -> None:
        key = client.get("/v1/vapid-public-key", headers=auth()).json()["key"]
        raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
        assert len(raw) == 65 and raw[0] == 4
        assert "=" not in key


class TestSubscriptions:
    def test_upsert_is_idempotent(self, client: TestClient) -> None:
        first = client.put("/v1/subscriptions", json=subscription(1, "iPhone"), headers=auth()).json()
        again = subscription(1, "iPhone di casa")
        again["keys"]["auth"] = "rotated"
        second = client.put("/v1/subscriptions", json=again, headers=auth()).json()
        assert first["id"] == second["id"]
        assert second["label"] == "iPhone di casa"
        assert len(client.get("/v1/subscriptions", headers=auth()).json()) == 1

    def test_delete(self, client: TestClient) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth())
        ref = {"endpoint": subscription(1)["endpoint"]}
        assert client.request("DELETE", "/v1/subscriptions", json=ref, headers=auth()).status_code == 204
        assert client.request("DELETE", "/v1/subscriptions", json=ref, headers=auth()).status_code == 204
        assert client.get("/v1/subscriptions", headers=auth()).json() == []

    def test_rejects_non_url_endpoint(self, client: TestClient) -> None:
        bad = subscription(1)
        bad["endpoint"] = "not a url"
        assert client.put("/v1/subscriptions", json=bad, headers=auth()).status_code == 422


class TestNotify:
    def test_no_devices_is_not_an_error(self, client: TestClient) -> None:
        r = client.post("/v1/notify", json={"title": "Ciao"}, headers=auth())
        assert r.json() == {"sent": 0, "failed": 0, "removed": 0}

    def test_payload_and_headers(self, client: TestClient, sender: FakeSender) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth())
        note = {"title": "Budget", "body": "Ristoranti all'80%", "url": "/budget", "tag": "budget:2026-11/ristoranti"}
        assert client.post("/v1/notify", json=note, headers=auth()).json()["sent"] == 1

        target, message = sender.sent[0]
        assert target.p256dh == "p256dh-1" and target.auth == "auth-1"
        assert message.payload == note  # exactly what sw.js reads
        assert message.topic == "budget_2026-11_ristoranti"
        assert message.ttl == 86_400 and message.urgency == "normal"

    def test_only_the_calling_apps_devices(self, client: TestClient, sender: FakeSender) -> None:
        client.put("/v1/subscriptions", json=subscription(1), headers=auth("alfred"))
        client.put("/v1/subscriptions", json=subscription(2), headers=auth("jarvis"))
        client.post("/v1/notify", json={"title": "x"}, headers=auth("jarvis"))
        assert [t.endpoint for t, _ in sender.sent] == [subscription(2)["endpoint"]]

    def test_mixed_outcomes(self, client: TestClient, sender: FakeSender) -> None:
        for n in (1, 2, 3):
            client.put("/v1/subscriptions", json=subscription(n), headers=auth())
        sender.outcomes[subscription(2)["endpoint"]] = Outcome("gone", 410)
        sender.outcomes[subscription(3)["endpoint"]] = Outcome("failed", 500, "boom")

        r = client.post("/v1/notify", json={"title": "x"}, headers=auth())
        assert r.json() == {"sent": 1, "failed": 1, "removed": 1}

        rows = {row["endpoint"]: row for row in client.get("/v1/subscriptions", headers=auth()).json()}
        assert subscription(2)["endpoint"] not in rows  # 410 → deleted
        assert rows[subscription(1)["endpoint"]]["last_success_at"] is not None
        assert rows[subscription(3)["endpoint"]]["failures"] == 1

        # A success resets the counter.
        del sender.outcomes[subscription(3)["endpoint"]]
        client.post("/v1/notify", json={"title": "x"}, headers=auth())
        rows = {row["endpoint"]: row for row in client.get("/v1/subscriptions", headers=auth()).json()}
        assert rows[subscription(3)["endpoint"]]["failures"] == 0

    def test_validation(self, client: TestClient) -> None:
        assert client.post("/v1/notify", json={"title": ""}, headers=auth()).status_code == 422
        assert client.post("/v1/notify", json={"title": "x", "url": "https://evil"}, headers=auth()).status_code == 422
        assert client.post("/v1/notify", json={"title": "x", "urgency": "max"}, headers=auth()).status_code == 422
