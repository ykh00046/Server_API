"""Integration tests for webhook-async-dispatch-v2.

Exercises:
- async emit_event (enqueue-only, returns immediately as queued)
- WebhookDispatchWorker.tick_once() processing one batch
- 5xx → retry path with exponential backoff
- 4xx → permanent failure (no retry)
- max_attempts → dead
- Retry-After header honored
- sync mode still works (regression for v1 AC)
- /test endpoint still works without an active worker
- /queue/stats and /deliveries/{id}/retry routes
- worker stop semantics (timeout + daemon GC fallback)

All external HTTP is routed through httpx.MockTransport — zero real network.
"""
from __future__ import annotations

import datetime as dt
import time

import httpx
import pytest

import shared.config as cfg
from api.notifications import dispatcher, events, store
from api.notifications.backoff import MAX_BACKOFF_SEC, next_delay
from api.notifications.worker import WebhookDispatchWorker


# ----------------------------------------------------------
# Fixtures (mirror tests/test_notifications.py for v1 parity)
# ----------------------------------------------------------
@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "notifications.db"
    monkeypatch.setattr(cfg, "NOTIFICATIONS_DB_FILE", db_path)
    store.reset_for_tests()
    yield db_path
    store.reset_for_tests()


@pytest.fixture
def captured():
    return {"requests": []}


def _make_ok_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(200, content=b'{"ack":true}')
    return httpx.MockTransport(handler)


def _make_5xx_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(503, content=b'{"err":"unavailable"}')
    return httpx.MockTransport(handler)


def _make_4xx_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(401, content=b'{"err":"unauthorized"}')
    return httpx.MockTransport(handler)


def _make_retry_after_transport(captured, seconds: int):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        return httpx.Response(
            503, content=b'{"err":"slow down"}', headers={"Retry-After": str(seconds)}
        )
    return httpx.MockTransport(handler)


def _make_slow_handler_transport(captured, delay_sec: float):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        time.sleep(delay_sec)
        return httpx.Response(200, content=b'{"ack":true}')
    return httpx.MockTransport(handler)


def _create_wh(client, *, event_types=("evt.async",), active=True):
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


# ==========================================================
# AC1 — async emit: enqueue only, no immediate dispatch
# ==========================================================
def test_async_emit_enqueues_without_dispatching(client, isolated_db, monkeypatch):
    """AC1: emit_event in async mode does NOT call dispatcher.send."""
    _create_wh(client)
    calls = {"n": 0}

    def fake_send(**kwargs):
        calls["n"] += 1
        return dispatcher.DispatchResult(
            status="success", response_status=200, response_body="",
            error=None, duration_ms=0,
        )
    monkeypatch.setattr(dispatcher, "send", fake_send)
    results = events.emit_event("evt.async", {"x": 1})  # async by default
    assert calls["n"] == 0, "async emit must not call dispatcher synchronously"
    assert len(results) == 1
    assert results[0].status == "queued"
    assert results[0].response_status is None


def test_worker_tick_processes_queued_delivery(client, isolated_db, captured):
    """AC1: a worker tick consumes a queued row, dispatcher gets called once."""
    wh = _create_wh(client)
    events.emit_event("evt.async", {"hello": "world"})
    transport = _make_ok_transport(captured)
    worker = WebhookDispatchWorker(transport=transport, random_fn=lambda: 0.5)
    n = worker.tick_once()
    assert n == 1
    assert len(captured["requests"]) == 1
    deliveries = store.list_deliveries(wh["id"])
    assert deliveries[0].status == "success"
    assert deliveries[0].response_status == 200


# ==========================================================
# AC2 — 5xx triggers retry, attempt increments
# ==========================================================
def test_5xx_response_schedules_retry_with_increased_attempt(client, isolated_db, captured):
    """AC2: 5xx → status='retrying', attempt=2, next_attempt_at in the future."""
    wh = _create_wh(client)
    events.emit_event("evt.async", {"x": 1})
    transport = _make_5xx_transport(captured)
    worker = WebhookDispatchWorker(
        transport=transport, max_attempts=5, random_fn=lambda: 0.5
    )
    worker.tick_once()
    rows = store.list_deliveries(wh["id"])
    assert len(rows) == 1
    # use raw row via the store's conn for attempt / next_attempt_at
    conn = store._get_conn()
    raw = conn.execute(
        "SELECT status, attempt, next_attempt_at FROM webhook_deliveries WHERE id=?",
        (rows[0].id,),
    ).fetchone()
    assert raw["status"] == "retrying"
    assert int(raw["attempt"]) == 2
    assert raw["next_attempt_at"] is not None
    # next_attempt_at must be in the future
    now = dt.datetime.now(dt.timezone.utc)
    nxt = dt.datetime.fromisoformat(raw["next_attempt_at"])
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=dt.timezone.utc)
    assert nxt > now


# ==========================================================
# AC3 — max_attempts caps retries; final status is 'dead'
# ==========================================================
def test_max_attempts_caps_at_dead(client, isolated_db, captured):
    """AC3: with MAX=2, after enough ticks we go queued→retrying→dead with ≤2 dispatcher calls."""
    wh = _create_wh(client)
    events.emit_event("evt.async", {"x": 1})
    transport = _make_5xx_transport(captured)
    worker = WebhookDispatchWorker(
        transport=transport, max_attempts=2, random_fn=lambda: 0.5
    )
    # Tick 1 — first attempt, fails, attempt becomes 2, scheduled retry
    worker.tick_once()
    # Force the retry to be due immediately by setting next_attempt_at into the past
    conn = store._get_conn()
    conn.execute(
        "UPDATE webhook_deliveries SET next_attempt_at = '1970-01-01T00:00:00+00:00'"
    )
    conn.commit()
    # Tick 2 — attempt=2 == max, fails → dead
    worker.tick_once()
    rows = store.list_deliveries(wh["id"])
    raw = conn.execute(
        "SELECT status, attempt FROM webhook_deliveries WHERE id=?", (rows[0].id,)
    ).fetchone()
    assert raw["status"] == "dead"
    # Dispatcher called exactly max_attempts (2) times
    assert len(captured["requests"]) == 2
    # Tick 3 — should not call dispatcher again
    worker.tick_once()
    assert len(captured["requests"]) == 2


# ==========================================================
# AC4 — backoff schedule is exponential with ±20% jitter
# ==========================================================
def test_next_delay_schedule_with_zero_jitter():
    """AC4: with jitter=0, delays follow [1, 5, 25, 125, None] for attempts 1..5."""
    zero_jitter = lambda: 0.5  # noqa: E731
    assert next_delay(1, max_attempts=5, random_fn=zero_jitter) == 1.0
    assert next_delay(2, max_attempts=5, random_fn=zero_jitter) == 5.0
    assert next_delay(3, max_attempts=5, random_fn=zero_jitter) == 25.0
    assert next_delay(4, max_attempts=5, random_fn=zero_jitter) == 125.0
    assert next_delay(5, max_attempts=5, random_fn=zero_jitter) is None
    # attempt 6 = also None
    assert next_delay(6, max_attempts=5, random_fn=zero_jitter) is None


def test_next_delay_jitter_within_bounds():
    """AC4: jitter keeps delays inside base * [0.8, 1.2)."""
    base = 25.0  # attempt=3
    for r in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 0.999):
        d = next_delay(3, max_attempts=10, random_fn=lambda r=r: r)
        assert 0.8 * base <= d <= 1.2 * base, f"delay {d} out of bounds at r={r}"


def test_next_delay_caps_at_max_backoff():
    """AC4 corner: Retry-After absurdly large → capped at MAX_BACKOFF_SEC."""
    d = next_delay(1, max_attempts=5, retry_after_sec=10_000_000.0, random_fn=lambda: 0.5)
    assert d is not None and d <= MAX_BACKOFF_SEC


# ==========================================================
# AC5 — Retry-After header overrides default schedule
# ==========================================================
def test_retry_after_header_drives_next_delay(client, isolated_db, captured):
    """AC5: response with Retry-After: 7 → next_attempt_at ≈ now + 7s±20%."""
    wh = _create_wh(client)
    events.emit_event("evt.async", {"x": 1})
    transport = _make_retry_after_transport(captured, seconds=7)
    worker = WebhookDispatchWorker(transport=transport, random_fn=lambda: 0.5)
    before = dt.datetime.now(dt.timezone.utc)
    worker.tick_once()
    after = dt.datetime.now(dt.timezone.utc)
    rows = store.list_deliveries(wh["id"])
    conn = store._get_conn()
    raw = conn.execute(
        "SELECT next_attempt_at FROM webhook_deliveries WHERE id=?", (rows[0].id,)
    ).fetchone()
    nxt = dt.datetime.fromisoformat(raw["next_attempt_at"])
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=dt.timezone.utc)
    delta = (nxt - before).total_seconds()
    # jitter is 0 at random_fn=0.5, so delay should be ~7s. Allow generous bound for clock skew.
    assert 5.5 <= delta <= 8.5, f"unexpected delta={delta}; nxt={nxt} before={before} after={after}"


# ==========================================================
# AC6 — sync mode still dispatches in-process (v1 regression)
# ==========================================================
def test_sync_mode_dispatches_inline(client, isolated_db, captured):
    """AC6: sync=True calls dispatcher.send immediately and returns final rows."""
    _create_wh(client)
    transport = _make_ok_transport(captured)
    results = events.emit_event("evt.async", {"x": 1}, sync=True, transport=transport)
    assert len(results) == 1
    assert results[0].status == "success"
    assert len(captured["requests"]) == 1


# ==========================================================
# AC7 — /test endpoint works without an active worker
# ==========================================================
def test_test_endpoint_works_without_worker(client, isolated_db, monkeypatch, captured):
    """AC7: /test uses the v1 sync path; no worker required."""
    transport = _make_ok_transport(captured)
    real_send = dispatcher.send

    def wrapped(**kwargs):
        kwargs.setdefault("transport", transport)
        return real_send(**kwargs)

    monkeypatch.setattr(dispatcher, "send", wrapped)
    wh = _create_wh(client, event_types=())
    r = client.post(f"/notifications/webhooks/{wh['id']}/test")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "success"
    assert d["response_status"] == 200


# ==========================================================
# AC8 — /queue/stats counts by status
# ==========================================================
def test_queue_stats_endpoint_counts_by_status(client, isolated_db):
    """AC8: /queue/stats returns 6 counters reflecting current rows."""
    wh = _create_wh(client)
    conn = store._get_conn()
    now = store._now_iso()
    # Seed one row per status
    seeds = [
        ("queued", None),
        ("in_flight", None),
        ("retrying", "1970-01-01T00:00:00+00:00"),
        ("success", None),
        ("failure", None),
        ("dead", None),
    ]
    for status_v, naa in seeds:
        conn.execute(
            "INSERT INTO webhook_deliveries (webhook_id, event_type, payload, status, "
            "attempted_at, duration_ms, attempt, next_attempt_at) "
            "VALUES (?, ?, ?, ?, ?, 0, 1, ?)",
            (wh["id"], "evt.x", "{}", status_v, now, naa),
        )
    conn.commit()
    r = client.get("/notifications/queue/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["queued"] >= 1
    assert s["in_flight"] >= 1
    assert s["retrying"] >= 1
    assert s["dead"] >= 1
    assert s["success_24h"] >= 1
    assert s["failure_24h"] >= 1


# ==========================================================
# AC9 — POST /deliveries/{id}/retry resets dead → queued
# ==========================================================
def test_retry_dead_delivery_returns_to_queue(client, isolated_db):
    """AC9: requeue endpoint resets status='queued', attempt=1."""
    wh = _create_wh(client)
    conn = store._get_conn()
    now = store._now_iso()
    cur = conn.execute(
        "INSERT INTO webhook_deliveries (webhook_id, event_type, payload, status, "
        "attempted_at, duration_ms, attempt, next_attempt_at) "
        "VALUES (?, ?, ?, 'dead', ?, 100, 5, NULL)",
        (wh["id"], "evt.x", '{"a":1}', now),
    )
    conn.commit()
    delivery_id = cur.lastrowid
    r = client.post(f"/notifications/deliveries/{delivery_id}/retry")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "queued"
    # attempt is not in DeliveryPublic but raw row should show 1
    raw = conn.execute(
        "SELECT attempt, response_status FROM webhook_deliveries WHERE id=?",
        (delivery_id,),
    ).fetchone()
    assert int(raw["attempt"]) == 1
    assert raw["response_status"] is None


def test_retry_missing_delivery_returns_404(client, isolated_db):
    r = client.post("/notifications/deliveries/99999/retry")
    assert r.status_code == 404


# ==========================================================
# AC10 — worker.stop respects timeout and never raises
# ==========================================================
def test_worker_stop_timeout_does_not_raise(client, isolated_db, captured):
    """AC10: when the worker thread is busy past `timeout`, stop() still returns cleanly."""
    _create_wh(client)
    events.emit_event("evt.async", {"x": 1})
    transport = _make_slow_handler_transport(captured, delay_sec=1.5)
    worker = WebhookDispatchWorker(
        transport=transport, tick_sec=0.05, random_fn=lambda: 0.5
    )
    worker.start()
    # Let the tick fire and the slow handler grab the request
    time.sleep(0.3)
    # Stop with a short timeout — handler hasn't returned yet
    worker.stop(timeout=0.2)
    # Should not raise; thread may still be alive but daemon GC takes over.
    assert worker._thread is None or worker._thread.daemon


# ==========================================================
# Extra — 4xx is a permanent failure, never retried
# ==========================================================
def test_4xx_response_marks_failure_no_retry(client, isolated_db, captured):
    """4xx → status='failure' immediately, dispatcher not called again."""
    wh = _create_wh(client)
    events.emit_event("evt.async", {"x": 1})
    transport = _make_4xx_transport(captured)
    worker = WebhookDispatchWorker(
        transport=transport, max_attempts=5, random_fn=lambda: 0.5
    )
    worker.tick_once()
    rows = store.list_deliveries(wh["id"])
    assert rows[0].status == "failure"
    assert rows[0].response_status == 401
    # Even if we tick again, the row is not due (status='failure') so no second call
    worker.tick_once()
    assert len(captured["requests"]) == 1


# ==========================================================
# Extra — OpenAPI exposes the 2 new v2 paths
# ==========================================================
def test_openapi_includes_v2_paths(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    assert "/notifications/queue/stats" in paths
    assert "/notifications/deliveries/{delivery_id}/retry" in paths
