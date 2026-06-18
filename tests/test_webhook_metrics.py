"""L1/L2/L5 verification for webhook-metrics-v1."""
from __future__ import annotations

import datetime as dt
import time

import pytest

import shared.config as cfg
from api.notifications import store
from api.notifications.metrics import (
    DELIVERY_STATUSES,
    WebhookMetricsSnapshot,
    collect_snapshot,
    render_prometheus,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "notifications.db"
    monkeypatch.setattr(cfg, "NOTIFICATIONS_DB_FILE", db_path)
    store.reset_for_tests()
    yield db_path
    store.reset_for_tests()


def _create_webhook(client, *, active=True, url="https://example.com/metrics-secret"):
    response = client.post(
        "/notifications/webhooks",
        json={"url": url, "event_types": ["metrics.test"], "active": active},
    )
    assert response.status_code == 201
    return response.json()


def _insert_delivery(
    webhook_id: int,
    status: str,
    attempted_at: str,
    *,
    duration_ms: int = 0,
    enqueued_at: str | None = None,
) -> None:
    conn = store._get_conn()
    conn.execute(
        """
        INSERT INTO webhook_deliveries
            (webhook_id, event_type, payload, status, attempted_at,
             duration_ms, attempt, next_attempt_at, enqueued_at)
        VALUES (?, 'metrics.test', ?, ?, ?, ?, 1, NULL, ?)
        """,
        (webhook_id, '{"token":"payload-secret"}', status, attempted_at, duration_ms, enqueued_at),
    )
    conn.commit()


def test_empty_snapshot_and_renderer_include_fixed_zero_states(isolated_db):
    snapshot = collect_snapshot(now=dt.datetime(2026, 6, 19, tzinfo=dt.UTC))
    assert snapshot.webhooks == {"active": 0, "inactive": 0}
    assert snapshot.deliveries == dict.fromkeys(DELIVERY_STATUSES, 0)
    text = render_prometheus(snapshot)
    assert "# TYPE production_data_hub_webhook_deliveries gauge" in text
    assert 'production_data_hub_webhook_deliveries{status="dead"} 0' in text
    assert text.endswith("\n")


def test_snapshot_counts_window_duration_and_queue_age(client, isolated_db):
    now = dt.datetime(2026, 6, 19, 12, 0, tzinfo=dt.UTC)
    active = _create_webhook(client, active=True)
    _create_webhook(client, active=False, url="https://example.org/inactive")
    _insert_delivery(active["id"], "success", (now - dt.timedelta(hours=1)).isoformat(), duration_ms=100)
    _insert_delivery(active["id"], "failure", (now - dt.timedelta(hours=2)).isoformat(), duration_ms=300)
    _insert_delivery(active["id"], "success", (now - dt.timedelta(hours=25)).isoformat(), duration_ms=900)
    _insert_delivery(active["id"], "queued", (now - dt.timedelta(seconds=60)).isoformat(), enqueued_at=(now - dt.timedelta(seconds=90)).isoformat())
    _insert_delivery(active["id"], "retrying", now.isoformat(), enqueued_at=(now + dt.timedelta(seconds=10)).isoformat())

    snapshot = collect_snapshot(now=now)
    assert snapshot.webhooks == {"active": 1, "inactive": 1}
    assert snapshot.deliveries["success"] == 2
    assert snapshot.deliveries["failure"] == 1
    assert snapshot.deliveries["queued"] == 1
    assert snapshot.deliveries_24h == {"success": 1, "failure": 1}
    assert snapshot.duration_avg_ms_24h == 200.0
    assert snapshot.duration_max_ms_24h == 300
    assert snapshot.oldest_queue_age_seconds == 90.0


def test_renderer_uses_only_fixed_labels_and_never_leaks_sensitive_data(client, isolated_db):
    created = _create_webhook(client, url="https://secret.example/private-hook")
    _insert_delivery(created["id"], "dead", store._now_iso())
    text = render_prometheus()
    assert 'status="dead"' in text
    for forbidden in ("secret.example", "private-hook", created["secret"], "payload-secret", 'webhook_id="'):
        assert forbidden not in text


def test_metrics_endpoint_contract_and_openapi(client, isolated_db):
    started = time.perf_counter()
    response = client.get("/metrics")
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "# HELP production_data_hub_webhooks" in response.text
    assert elapsed < 0.2
    paths = client.get("/openapi.json").json()["paths"]
    assert "/metrics" in paths
    assert "/metrics/performance" in paths
    assert "/metrics/cache" in paths


def test_metrics_endpoint_uses_existing_auth_policy(client, isolated_db, monkeypatch):
    monkeypatch.setattr(cfg, "API_AUTH_ENABLED", True)
    monkeypatch.setattr(cfg, "API_KEYS", ("metrics-key",))
    monkeypatch.setattr(cfg, "API_BEARER_TOKENS", ())
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "metrics-key"}).status_code == 200


def test_renderer_formats_supplied_snapshot_without_database():
    snapshot = WebhookMetricsSnapshot(
        webhooks={"active": 2, "inactive": 1},
        deliveries=dict.fromkeys(DELIVERY_STATUSES, 0),
        deliveries_24h={"success": 3, "failure": 1},
        duration_avg_ms_24h=12.5,
        duration_max_ms_24h=20,
        oldest_queue_age_seconds=4.25,
    )
    text = render_prometheus(snapshot)
    assert "production_data_hub_webhook_delivery_duration_avg_ms_24h 12.5" in text
    assert "production_data_hub_webhook_oldest_queue_age_seconds 4.25" in text
