"""Integration tests for the webhook notifications subsystem.

All HTTP calls to user-registered webhook URLs are routed through
httpx.MockTransport so no real network requests escape the test process.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib

import httpx
import orjson
import pytest

import shared.config as cfg
from api.notifications import dispatcher, events, store
from api.notifications.dispatcher import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
)
from api.routers import notifications as router_mod


# ----------------------------------------------------------
# Fixtures
# ----------------------------------------------------------
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the notifications store at a fresh tmp DB for each test."""
    db_path = tmp_path / "notifications.db"
    monkeypatch.setattr(cfg, "NOTIFICATIONS_DB_FILE", db_path)
    store.reset_for_tests()
    yield db_path
    store.reset_for_tests()


@pytest.fixture
def captured():
    """Container the mock transport writes incoming requests into."""
    return {"requests": []}


@pytest.fixture
def ok_transport(captured):
    """httpx MockTransport that records requests and returns 200 OK."""
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(200, content=b'{"ack":true}')
    return httpx.MockTransport(handler)


@pytest.fixture
def fail_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(500, content=b'{"err":"boom"}')
    return httpx.MockTransport(handler)


@pytest.fixture
def network_error_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        raise httpx.ConnectError("simulated connection failure", request=request)
    return httpx.MockTransport(handler)


@pytest.fixture
def patched_router(monkeypatch, ok_transport):
    """Patch dispatcher.send used by the router so /test goes through MockTransport."""
    real_send = dispatcher.send

    def wrapped(**kwargs):
        kwargs.setdefault("transport", ok_transport)
        return real_send(**kwargs)

    monkeypatch.setattr(dispatcher, "send", wrapped)
    yield
    monkeypatch.setattr(dispatcher, "send", real_send)


# ----------------------------------------------------------
# Webhook CRUD
# ----------------------------------------------------------
def test_create_get_list_delete_returns_secret_once(client, isolated_db):
    payload = {
        "url": "https://example.com/hook",
        "event_types": ["webhook.test"],
        "description": "primary",
    }
    r = client.post("/notifications/webhooks", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] >= 1
    assert body["url"] == payload["url"]
    assert body["secret"]  # one-time disclosure
    wh_id = body["id"]

    # GET single — no secret
    r2 = client.get(f"/notifications/webhooks/{wh_id}")
    assert r2.status_code == 200
    assert "secret" not in r2.json()

    # LIST — no secret in any entry
    r3 = client.get("/notifications/webhooks")
    assert r3.status_code == 200
    rows = r3.json()
    assert any(w["id"] == wh_id for w in rows)
    assert all("secret" not in w for w in rows)

    # DELETE
    r4 = client.delete(f"/notifications/webhooks/{wh_id}")
    assert r4.status_code == 200
    assert r4.json()["deleted"] is True

    # GET after delete — 404
    r5 = client.get(f"/notifications/webhooks/{wh_id}")
    assert r5.status_code == 404


def test_url_validation_rejects_bad_scheme(client, isolated_db):
    r = client.post(
        "/notifications/webhooks",
        json={"url": "ftp://example.com/x", "event_types": []},
    )
    assert r.status_code == 400
    assert "scheme" in r.json()["detail"].lower()


def test_url_validation_rejects_missing_host(client, isolated_db):
    r = client.post(
        "/notifications/webhooks",
        json={"url": "https://", "event_types": []},
    )
    assert r.status_code == 400


def test_blocked_host(client, isolated_db, monkeypatch):
    monkeypatch.setenv("WEBHOOK_BLOCKED_HOSTS", "blocked.example.com")
    r = client.post(
        "/notifications/webhooks",
        json={"url": "https://blocked.example.com/x", "event_types": []},
    )
    assert r.status_code == 400


# ----------------------------------------------------------
# /test endpoint: signature + history
# ----------------------------------------------------------
def test_test_endpoint_signs_payload_and_records_delivery(
    client, isolated_db, patched_router, captured
):
    create = client.post(
        "/notifications/webhooks",
        json={"url": "https://example.com/hook", "event_types": []},
    )
    assert create.status_code == 201
    wh = create.json()
    wh_id = wh["id"]
    secret = wh["secret"]

    # Custom payload
    ping = client.post(
        f"/notifications/webhooks/{wh_id}/test",
        json={"payload": {"hello": "world"}},
    )
    assert ping.status_code == 200, ping.text
    d = ping.json()
    assert d["webhook_id"] == wh_id
    assert d["event_type"] == "webhook.test"
    assert d["status"] == "success"
    assert d["response_status"] == 200

    # Verify exactly one HTTP request fired with valid signature.
    assert len(captured["requests"]) == 1
    req = captured["requests"][0]
    body = bytes(req.content)
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    assert req.headers[SIGNATURE_HEADER] == expected
    assert req.headers[EVENT_HEADER] == "webhook.test"
    assert req.headers[DELIVERY_HEADER] == str(d["id"])
    assert TIMESTAMP_HEADER in req.headers
    # Body actually contains our payload
    assert orjson.loads(body) == {"hello": "world"}

    # Delivery shows up in history
    hist = client.get(f"/notifications/webhooks/{wh_id}/deliveries")
    assert hist.status_code == 200
    rows = hist.json()
    assert len(rows) == 1
    assert rows[0]["id"] == d["id"]


def test_test_endpoint_records_failure_when_remote_returns_500(
    client, isolated_db, monkeypatch, fail_transport, captured
):
    real_send = dispatcher.send

    def wrapped(**kwargs):
        kwargs.setdefault("transport", fail_transport)
        return real_send(**kwargs)

    monkeypatch.setattr(dispatcher, "send", wrapped)
    create = client.post(
        "/notifications/webhooks",
        json={"url": "https://example.com/hook", "event_types": []},
    )
    wh_id = create.json()["id"]

    ping = client.post(f"/notifications/webhooks/{wh_id}/test")
    assert ping.status_code == 200
    d = ping.json()
    assert d["status"] == "failure"
    assert d["response_status"] == 500


def test_test_endpoint_records_failure_on_network_error(
    client, isolated_db, monkeypatch, network_error_transport
):
    real_send = dispatcher.send

    def wrapped(**kwargs):
        kwargs.setdefault("transport", network_error_transport)
        return real_send(**kwargs)

    monkeypatch.setattr(dispatcher, "send", wrapped)
    create = client.post(
        "/notifications/webhooks",
        json={"url": "https://example.com/hook", "event_types": []},
    )
    wh_id = create.json()["id"]

    ping = client.post(f"/notifications/webhooks/{wh_id}/test")
    assert ping.status_code == 200
    d = ping.json()
    assert d["status"] == "failure"
    assert d["response_status"] is None
    assert "ConnectError" in (d["error"] or "")


# ----------------------------------------------------------
# emit_event filtering
# ----------------------------------------------------------
def test_emit_event_skips_unsubscribed_webhooks(client, isolated_db, ok_transport, captured):
    # webhook subscribed to a *different* event
    client.post(
        "/notifications/webhooks",
        json={"url": "https://example.com/hook", "event_types": ["other.event"]},
    )
    results = events.emit_event(
        "production.record.created", {"x": 1}, transport=ok_transport
    )
    assert results == []
    assert captured["requests"] == []


def test_emit_event_skips_inactive_webhooks(client, isolated_db, ok_transport, captured):
    create = client.post(
        "/notifications/webhooks",
        json={
            "url": "https://example.com/hook",
            "event_types": ["production.record.created"],
            "active": False,
        },
    )
    assert create.status_code == 201
    results = events.emit_event(
        "production.record.created", {"x": 1}, transport=ok_transport
    )
    assert results == []
    assert captured["requests"] == []


def test_emit_event_dispatches_to_matching_active_webhook(
    client, isolated_db, ok_transport, captured
):
    client.post(
        "/notifications/webhooks",
        json={
            "url": "https://example.com/hook",
            "event_types": ["production.record.created"],
        },
    )
    # webhook-async-dispatch-v2: emit_event now async-by-default. This case
    # asserts the synchronous in-process dispatch path explicitly.
    results = events.emit_event(
        "production.record.created", {"id": 42},
        sync=True, transport=ok_transport,
    )
    assert len(results) == 1
    assert results[0].status == "success"
    assert len(captured["requests"]) == 1


# ----------------------------------------------------------
# Secret rotation
# ----------------------------------------------------------
def test_rotate_secret_returns_new_secret_and_invalidates_old_signature(
    client, isolated_db, patched_router, captured
):
    create = client.post(
        "/notifications/webhooks",
        json={"url": "https://example.com/hook", "event_types": []},
    )
    wh = create.json()
    wh_id = wh["id"]
    old_secret = wh["secret"]

    patch = client.patch(
        f"/notifications/webhooks/{wh_id}",
        json={"rotate_secret": True},
    )
    assert patch.status_code == 200
    rotated = patch.json()
    assert "secret" in rotated
    new_secret = rotated["secret"]
    assert new_secret != old_secret

    # Trigger a delivery and verify it uses the NEW secret, not the old.
    ping = client.post(f"/notifications/webhooks/{wh_id}/test")
    assert ping.status_code == 200
    req = captured["requests"][-1]
    body = bytes(req.content)
    old_sig = "sha256=" + hmac.new(old_secret.encode(), body, hashlib.sha256).hexdigest()
    new_sig = "sha256=" + hmac.new(new_secret.encode(), body, hashlib.sha256).hexdigest()
    assert req.headers[SIGNATURE_HEADER] == new_sig
    assert req.headers[SIGNATURE_HEADER] != old_sig


def test_patch_without_rotate_does_not_expose_secret(client, isolated_db):
    create = client.post(
        "/notifications/webhooks",
        json={"url": "https://example.com/hook", "event_types": []},
    )
    wh_id = create.json()["id"]
    patch = client.patch(
        f"/notifications/webhooks/{wh_id}",
        json={"description": "renamed"},
    )
    assert patch.status_code == 200
    assert "secret" not in patch.json()
    assert patch.json()["description"] == "renamed"


# ----------------------------------------------------------
# Event catalog
# ----------------------------------------------------------
def test_events_catalog_contains_core_types(client, isolated_db):
    r = client.get("/notifications/events")
    assert r.status_code == 200
    names = {e["name"] for e in r.json()}
    assert {
        "webhook.test",
        "production.record.created",
        "production.threshold.exceeded",
    } <= names


# ----------------------------------------------------------
# 404 paths
# ----------------------------------------------------------
def test_get_missing_returns_404(client, isolated_db):
    assert client.get("/notifications/webhooks/9999").status_code == 404


def test_patch_missing_returns_404(client, isolated_db):
    r = client.patch("/notifications/webhooks/9999", json={"active": False})
    assert r.status_code == 404


def test_delete_missing_returns_404(client, isolated_db):
    assert client.delete("/notifications/webhooks/9999").status_code == 404


def test_test_missing_returns_404(client, isolated_db):
    assert client.post("/notifications/webhooks/9999/test").status_code == 404


def test_list_deliveries_missing_returns_404(client, isolated_db):
    r = client.get("/notifications/webhooks/9999/deliveries")
    assert r.status_code == 404


# ----------------------------------------------------------
# AC9: pre-existing OpenAPI paths must remain present
# ----------------------------------------------------------
def test_openapi_preserves_existing_paths_and_adds_notifications(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    # All historically published paths must still exist (sample of the API surface).
    expected_existing = {
        "/",
        "/healthz",
        "/healthz/ai",
        "/metrics/performance",
        "/metrics/cache",
        "/records",
        "/records/{item_code}",
        "/items",
        "/summary/monthly_total",
        "/summary/by_item",
        "/chat/",
    }
    missing = expected_existing - paths
    assert not missing, f"pre-existing paths disappeared: {missing}"

    # All new notifications paths must now exist.
    expected_new = {
        "/notifications/webhooks",
        "/notifications/webhooks/{webhook_id}",
        "/notifications/webhooks/{webhook_id}/test",
        "/notifications/webhooks/{webhook_id}/deliveries",
        "/notifications/events",
    }
    missing_new = expected_new - paths
    assert not missing_new, f"missing new notifications paths: {missing_new}"
