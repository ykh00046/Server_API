"""Integration tests for webhook-bulk-retry-v1.

Exercises the bulk dead-letter retry path:
- POST /notifications/deliveries/bulk-retry (default: all 'dead')
- statuses filter (dead + failure), webhook_id scoping
- dry_run (no mutation)
- input validation (forbidden/empty statuses -> 400, limit bounds -> 422)
- limit capping with id-ASC ordering
- end-to-end: re-queued rows are claimed + dispatched by the worker
- raw-row parity with the single-row requeue (attempt/next_attempt_at/response)

All external HTTP is routed through httpx.MockTransport — zero real network.
"""
from __future__ import annotations

import httpx
import pytest

import shared.config as cfg
from api.notifications import store
from api.notifications.worker import WebhookDispatchWorker


# ----------------------------------------------------------
# Fixtures (mirror tests/test_notifications_async.py)
# ----------------------------------------------------------
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "notifications.db"
    monkeypatch.setattr(cfg, "NOTIFICATIONS_DB_FILE", db_path)
    store.reset_for_tests()
    yield db_path
    store.reset_for_tests()


def _make_ok_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(200, content=b'{"ack":true}')
    return httpx.MockTransport(handler)


def _create_wh(client, *, event_types=("evt.bulk",), active=True):
    r = client.post(
        "/notifications/webhooks",
        json={
            "url": "https://example.com/hook",
            "event_types": list(event_types),
            "active": active,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _seed_delivery(webhook_id: int, status: str, *, attempt: int = 5) -> int:
    """Insert a webhook_deliveries row directly with the given status."""
    conn = store._get_conn()
    now = store._now_iso()
    cur = conn.execute(
        "INSERT INTO webhook_deliveries (webhook_id, event_type, payload, status, "
        "attempted_at, duration_ms, attempt, next_attempt_at, response_status, error) "
        "VALUES (?, 'evt.bulk', '{\"a\":1}', ?, ?, 123, ?, NULL, 500, 'boom')",
        (webhook_id, status, now, attempt),
    )
    conn.commit()
    return int(cur.lastrowid)


def _status_of(delivery_id: int) -> str:
    row = store._get_conn().execute(
        "SELECT status FROM webhook_deliveries WHERE id=?", (delivery_id,)
    ).fetchone()
    return row["status"]


# ==========================================================
# AC1 — default bulk-retry re-queues all 'dead'
# ==========================================================
def test_bulk_retry_default_requeues_all_dead(client, isolated_db):
    wh = _create_wh(client)
    ids = [_seed_delivery(wh["id"], "dead") for _ in range(3)]
    r = client.post("/notifications/deliveries/bulk-retry", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requeued"] == 3
    assert sorted(body["ids"]) == sorted(ids)
    assert body["dry_run"] is False
    assert body["statuses"] == ["dead"]
    for did in ids:
        assert _status_of(did) == "queued"


# ==========================================================
# AC2 — statuses=[dead,failure] hits both, leaves others alone
# ==========================================================
def test_bulk_retry_dead_and_failure_only(client, isolated_db):
    wh = _create_wh(client)
    dead_ids = [_seed_delivery(wh["id"], "dead") for _ in range(2)]
    fail_ids = [_seed_delivery(wh["id"], "failure") for _ in range(2)]
    ok_id = _seed_delivery(wh["id"], "success")
    queued_id = _seed_delivery(wh["id"], "queued")
    r = client.post(
        "/notifications/deliveries/bulk-retry",
        json={"statuses": ["dead", "failure"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["requeued"] == 4
    for did in dead_ids + fail_ids:
        assert _status_of(did) == "queued"
    # untouched
    assert _status_of(ok_id) == "success"
    assert _status_of(queued_id) == "queued"  # was already queued, unchanged set


# ==========================================================
# AC3 — dry_run reports ids without mutating
# ==========================================================
def test_bulk_retry_dry_run_does_not_mutate(client, isolated_db):
    wh = _create_wh(client)
    ids = [_seed_delivery(wh["id"], "dead") for _ in range(2)]
    r = client.post(
        "/notifications/deliveries/bulk-retry",
        json={"dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["requeued"] == 2
    assert sorted(body["ids"]) == sorted(ids)
    # still dead — nothing changed
    for did in ids:
        assert _status_of(did) == "dead"


# ==========================================================
# AC4 — webhook_id scopes the retry
# ==========================================================
def test_bulk_retry_webhook_id_scopes(client, isolated_db):
    wh1 = _create_wh(client)
    wh2 = _create_wh(client)
    wh1_dead = [_seed_delivery(wh1["id"], "dead") for _ in range(2)]
    wh2_dead = _seed_delivery(wh2["id"], "dead")
    r = client.post(
        "/notifications/deliveries/bulk-retry",
        json={"webhook_id": wh1["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["requeued"] == 2
    for did in wh1_dead:
        assert _status_of(did) == "queued"
    assert _status_of(wh2_dead) == "dead"  # other webhook untouched


# ==========================================================
# AC5 — forbidden status -> 400
# ==========================================================
@pytest.mark.parametrize("bad", [["success"], ["queued", "dead"], ["retrying"]])
def test_bulk_retry_forbidden_status_400(client, isolated_db, bad):
    r = client.post("/notifications/deliveries/bulk-retry", json={"statuses": bad})
    assert r.status_code == 400, r.text


# ==========================================================
# AC6 — empty statuses -> 400
# ==========================================================
def test_bulk_retry_empty_statuses_400(client, isolated_db):
    r = client.post("/notifications/deliveries/bulk-retry", json={"statuses": []})
    assert r.status_code == 400, r.text


# ==========================================================
# AC7 — nothing to retry -> 200, requeued=0
# ==========================================================
def test_bulk_retry_no_targets_returns_zero(client, isolated_db):
    _create_wh(client)
    r = client.post("/notifications/deliveries/bulk-retry", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requeued"] == 0
    assert body["ids"] == []


# ==========================================================
# AC8 — limit caps (id ASC) and out-of-range -> 422
# ==========================================================
def test_bulk_retry_limit_caps_oldest_first(client, isolated_db):
    wh = _create_wh(client)
    ids = [_seed_delivery(wh["id"], "dead") for _ in range(5)]
    r = client.post("/notifications/deliveries/bulk-retry", json={"limit": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requeued"] == 2
    # oldest two ids (smallest) selected
    assert sorted(body["ids"]) == sorted(ids[:2])
    assert _status_of(ids[0]) == "queued"
    assert _status_of(ids[2]) == "dead"


def test_bulk_retry_limit_over_max_422(client, isolated_db):
    r = client.post("/notifications/deliveries/bulk-retry", json={"limit": 6000})
    assert r.status_code == 422, r.text


# ==========================================================
# AC9 — re-queued rows are picked up + dispatched by the worker
# ==========================================================
def test_requeued_delivery_is_dispatched_by_worker(client, isolated_db):
    wh = _create_wh(client)
    did = _seed_delivery(wh["id"], "dead")
    r = client.post("/notifications/deliveries/bulk-retry", json={})
    assert r.status_code == 200, r.text
    assert _status_of(did) == "queued"

    captured = {"requests": []}
    worker = WebhookDispatchWorker(
        transport=_make_ok_transport(captured), random_fn=lambda: 0.5
    )
    n = worker.tick_once()
    assert n == 1
    assert len(captured["requests"]) == 1
    assert _status_of(did) == "success"


# ==========================================================
# AC10 — raw-row parity with single requeue
# ==========================================================
def test_bulk_requeue_resets_attempt_and_response_fields(client, isolated_db):
    wh = _create_wh(client)
    did = _seed_delivery(wh["id"], "dead", attempt=5)
    client.post("/notifications/deliveries/bulk-retry", json={})
    raw = store._get_conn().execute(
        "SELECT status, attempt, next_attempt_at, response_status, error, duration_ms "
        "FROM webhook_deliveries WHERE id=?",
        (did,),
    ).fetchone()
    assert raw["status"] == "queued"
    assert int(raw["attempt"]) == 1
    assert raw["next_attempt_at"] is not None
    assert raw["response_status"] is None
    assert raw["error"] is None
    assert int(raw["duration_ms"]) == 0


# ==========================================================
# AC11 — OpenAPI exposes the new path
# ==========================================================
def test_openapi_includes_bulk_retry_path(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    assert "/notifications/deliveries/bulk-retry" in paths
    # existing single-retry path still present
    assert "/notifications/deliveries/{delivery_id}/retry" in paths
