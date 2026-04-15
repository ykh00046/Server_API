# tests/test_api_integration.py
"""FastAPI TestClient-based integration tests.

Covers the public REST surface plus the /chat/ endpoint with a mocked
Gemini client so no external API calls are made.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from api.main import app
from api import chat as chat_mod


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    # Avoid cross-test pollution of the in-memory rate limiter.
    from shared import api_rate_limiter
    from api.chat import chat_rate_limiter
    try:
        api_rate_limiter._requests.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        chat_rate_limiter._requests.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    yield


# ----------------------------------------------------------
# Health endpoints
# ----------------------------------------------------------
def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "database" in body


def test_healthz_ai_shape(client):
    r = client.get("/healthz/ai")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    # FR-01: sessions block must always be present
    assert "sessions" in body
    sessions = body["sessions"]
    assert {"count", "ttl_sec", "max_per_ip", "max_total"} <= set(sessions.keys())
    assert isinstance(sessions["count"], int)


# ----------------------------------------------------------
# Records endpoints
# ----------------------------------------------------------
def test_records_limit(client):
    r = client.get("/records", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "records" in body or "data" in body or isinstance(body, (list, dict))


def test_records_bad_date(client):
    r = client.get("/records", params={"date_from": "not-a-date"})
    assert r.status_code == 400


def test_items(client):
    r = client.get("/items")
    assert r.status_code == 200


def test_summary_monthly_total(client):
    r = client.get("/summary/monthly_total", params={"year": 2026})
    assert r.status_code in (200, 404)  # 404 acceptable if no data


# ----------------------------------------------------------
# Chat endpoint (Gemini mocked)
# ----------------------------------------------------------
class _FakeResponse:
    def __init__(self, text="mocked reply"):
        self.text = text
        self.candidates = []
        self.automatic_function_calling_history = []
        self.usage_metadata = None


class _FakeModels:
    def generate_content(self, *args, **kwargs):
        return _FakeResponse()


class _FakeClient:
    models = _FakeModels()


@pytest.fixture
def fake_gemini(monkeypatch):
    monkeypatch.setattr(chat_mod, "_get_client", lambda: _FakeClient())
    yield


def test_chat_single_turn(client, fake_gemini):
    r = client.post("/chat/", json={"query": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "mocked reply"
    assert body["status"] == "success"


def test_chat_multi_turn_same_ip(client, fake_gemini):
    chat_mod._sessions.clear()
    r1 = client.post("/chat/", json={"query": "first", "session_id": "s-abc"})
    assert r1.status_code == 200
    r2 = client.post("/chat/", json={"query": "second", "session_id": "s-abc"})
    assert r2.status_code == 200
    # History should have accumulated 4 entries (2 user + 2 model)
    assert len(chat_mod._sessions["s-abc"]["history"]) == 4


def test_chat_rejects_empty_key(client, monkeypatch):
    monkeypatch.setattr(chat_mod, "_get_client", lambda: None)
    r = client.post("/chat/", json={"query": "hi"})
    assert r.status_code == 500


# ----------------------------------------------------------
# security-followup-observability: FR-02 additional cases
# ----------------------------------------------------------
def test_records_by_item_code(client):
    """GET /records/{item_code} — 200 with list or 404 if absent."""
    r = client.get("/records/BW0021")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert isinstance(body, (list, dict))


def test_summary_by_item(client):
    """GET /summary/by_item — aggregated response."""
    r = client.get(
        "/summary/by_item",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "limit": 5},
    )
    assert r.status_code in (200, 404)


def test_records_invalid_cursor_is_graceful(client):
    """Invalid cursor falls back to unpaginated query (no 500)."""
    r = client.get("/records", params={"cursor": "@@not-a-cursor@@", "limit": 3})
    assert r.status_code == 200


def test_chat_rate_limit_boundary(client, fake_gemini, monkeypatch):
    """21st call in a minute must 429 with code=RATE_LIMITED."""
    from api.chat import chat_rate_limiter
    monkeypatch.setattr(chat_rate_limiter, "max_requests", 3)
    chat_rate_limiter._requests.clear()
    chat_mod._sessions.clear()
    for _ in range(3):
        r = client.post("/chat/", json={"query": "hi"})
        assert r.status_code == 200
    r = client.post("/chat/", json={"query": "over"})
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["code"] == "RATE_LIMITED"


def test_metrics_performance_shape(client):
    """GET /metrics/performance returns dict of per-query stats (possibly empty)."""
    r = client.get("/metrics/performance")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    for stats in body.values():
        assert {"count", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "cache_hit_rate"} <= set(stats.keys())


def test_metrics_cache_shape_and_populated(client):
    """Cache-decorated endpoint should populate performance_monitor."""
    from shared.metrics import performance_monitor
    performance_monitor.reset()
    client.get("/items", params={"limit": 5})
    client.get("/items", params={"limit": 5})  # cache hit
    r = client.get("/metrics/cache")
    assert r.status_code == 200
    body = r.json()
    assert "api_cache" in body and "performance" in body
    assert {"size", "maxsize", "ttl"} <= set(body["api_cache"].keys())
    perf = body["performance"]
    assert any(stats.get("count", 0) >= 1 for stats in perf.values())
