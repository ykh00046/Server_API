"""Unit tests for the dashboard webhook admin UI primitives.

Targets the testable layers (api_client + formatters) without importing
Streamlit. The api_client is exercised via `httpx.MockTransport` so all
10 endpoints can be verified end-to-end (path/method/body/response)
without a live server.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

# Load webhook_admin's pure modules directly from disk so the tests do not
# pull in dashboard/components/__init__.py (which eagerly imports streamlit
# via sibling modules). api_client and formatters are streamlit-free by
# design; loading them by file path keeps that boundary honest.
_ROOT = Path(__file__).resolve().parent.parent
_PKG_DIR = _ROOT / "dashboard" / "components" / "webhook_admin"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_api_client = _load_module("webhook_admin_api_client_under_test", _PKG_DIR / "api_client.py")
formatters = _load_module("webhook_admin_formatters_under_test", _PKG_DIR / "formatters.py")
WebhookAdminClient = _api_client.WebhookAdminClient
WebhookAdminError = _api_client.WebhookAdminError


# =====================================================================
# Helpers
# =====================================================================
class _Recorder:
    """Capture every request and dispatch to scripted responses."""

    def __init__(self, responses: list[httpx.Response] | None = None):
        self.calls: list[httpx.Request] = []
        self._responses = list(responses or [])
        self._default: httpx.Response | None = None

    def default(self, resp: httpx.Response) -> _Recorder:
        self._default = resp
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self._responses:
            return self._responses.pop(0)
        if self._default is not None:
            return self._default
        raise AssertionError(f"No scripted response for {request.method} {request.url}")


def _json_resp(status: int, body) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body), headers={"content-type": "application/json"})


def _client_with(handler) -> WebhookAdminClient:
    return WebhookAdminClient(
        "http://test",
        transport=httpx.MockTransport(handler),
    )


# =====================================================================
# api_client — endpoint coverage
# =====================================================================
def test_list_webhooks_active_filter_passes_query_param():
    rec = _Recorder([_json_resp(200, [{"id": 1, "url": "https://x", "event_types": [], "description": "", "active": True, "created_at": "2026-05-25T00:00:00", "updated_at": "2026-05-25T00:00:00"}])])
    with _client_with(rec.handler) as c:
        out = c.list_webhooks(active=True)
    assert out and out[0]["id"] == 1
    req = rec.calls[0]
    assert req.method == "GET"
    assert req.url.path == "/notifications/webhooks"
    assert dict(req.url.params) == {"active": "true"}


def test_list_webhooks_no_filter_omits_active():
    rec = _Recorder([_json_resp(200, [])])
    with _client_with(rec.handler) as c:
        c.list_webhooks()
    assert dict(rec.calls[0].url.params) == {}


def test_get_webhook_404_raises_webhook_admin_error():
    rec = _Recorder([_json_resp(404, {"detail": "webhook 99 not found"})])
    with _client_with(rec.handler) as c, pytest.raises(WebhookAdminError) as ei:
        c.get_webhook(99)
    assert ei.value.status == 404
    assert "not found" in str(ei.value)


def test_create_webhook_returns_secret_and_posts_body():
    body_out = {"id": 5, "url": "https://x", "event_types": ["a"], "description": "d", "active": True,
                "created_at": "2026-05-25T00:00:00", "updated_at": "2026-05-25T00:00:00", "secret": "S3CR3T"}
    rec = _Recorder([_json_resp(201, body_out)])
    with _client_with(rec.handler) as c:
        out = c.create_webhook(url="https://x", event_types=["a"], description="d", active=True)
    assert out["secret"] == "S3CR3T"
    req = rec.calls[0]
    assert req.method == "POST"
    assert json.loads(req.content) == {"url": "https://x", "event_types": ["a"], "description": "d", "active": True}


def test_update_webhook_partial_patch_only_sends_provided_fields():
    rec = _Recorder([_json_resp(200, {"id": 5, "url": "https://x", "event_types": ["a"], "description": "", "active": False, "created_at": "2026-05-25T00:00:00", "updated_at": "2026-05-25T00:00:00"})])
    with _client_with(rec.handler) as c:
        c.update_webhook(5, active=False)
    body = json.loads(rec.calls[0].content)
    assert body == {"rotate_secret": False, "active": False}
    assert rec.calls[0].method == "PATCH"
    assert rec.calls[0].url.path == "/notifications/webhooks/5"


def test_update_webhook_rotate_secret_flag_propagates():
    rec = _Recorder([_json_resp(200, {"id": 5, "url": "https://x", "event_types": [], "description": "", "active": True, "created_at": "x", "updated_at": "y", "secret": "NEW"})])
    with _client_with(rec.handler) as c:
        out = c.update_webhook(5, rotate_secret=True)
    body = json.loads(rec.calls[0].content)
    assert body["rotate_secret"] is True
    assert out["secret"] == "NEW"


def test_delete_webhook_returns_none_and_does_not_require_body():
    # FastAPI returns 200 with `{"deleted": True, ...}` but client must not raise on missing body either.
    rec = _Recorder([httpx.Response(204)])
    with _client_with(rec.handler) as c:
        result = c.delete_webhook(7)
    assert result is None
    assert rec.calls[0].method == "DELETE"
    assert rec.calls[0].url.path == "/notifications/webhooks/7"


def test_test_webhook_with_payload_posts_payload_wrapper():
    rec = _Recorder([_json_resp(200, {"id": 1, "webhook_id": 7, "event_type": "webhook.test", "status": "success", "response_status": 200, "response_body": None, "error": None, "attempted_at": "t", "duration_ms": 12})])
    with _client_with(rec.handler) as c:
        out = c.test_webhook(7, payload={"hello": "world"})
    assert out["status"] == "success"
    assert json.loads(rec.calls[0].content) == {"payload": {"hello": "world"}}
    assert rec.calls[0].url.path == "/notifications/webhooks/7/test"


def test_test_webhook_without_payload_sends_null_body():
    rec = _Recorder([_json_resp(200, {"id": 1, "webhook_id": 7, "event_type": "webhook.test", "status": "success", "response_status": 200, "response_body": None, "error": None, "attempted_at": "t", "duration_ms": 12})])
    with _client_with(rec.handler) as c:
        c.test_webhook(7)
    # `json=None` produces a body of literal "null" — verify the client did NOT send a payload key.
    raw = rec.calls[0].content
    assert raw in (b"", b"null")


def test_list_deliveries_status_filter():
    rec = _Recorder([_json_resp(200, [])])
    with _client_with(rec.handler) as c:
        c.list_deliveries(7, limit=10, status="failed")
    params = dict(rec.calls[0].url.params)
    assert params == {"limit": "10", "status": "failed"}


def test_list_event_types():
    rec = _Recorder([_json_resp(200, [{"name": "production.batch.created", "description": "..."}])])
    with _client_with(rec.handler) as c:
        out = c.list_event_types()
    assert out[0]["name"] == "production.batch.created"
    assert rec.calls[0].url.path == "/notifications/events"


def test_queue_stats_returns_dict_with_counters():
    payload = {"queued": 1, "in_flight": 2, "retrying": 3, "success_24h": 4, "failure_24h": 5, "dead": 6}
    rec = _Recorder([_json_resp(200, payload)])
    with _client_with(rec.handler) as c:
        out = c.queue_stats()
    assert out == payload


def test_retry_delivery_posts_to_correct_path():
    rec = _Recorder([_json_resp(200, {"id": 42, "webhook_id": 7, "event_type": "x", "status": "queued", "response_status": None, "response_body": None, "error": None, "attempted_at": "t", "duration_ms": 0})])
    with _client_with(rec.handler) as c:
        out = c.retry_delivery(42)
    assert out["status"] == "queued"
    assert rec.calls[0].method == "POST"
    assert rec.calls[0].url.path == "/notifications/deliveries/42/retry"


def test_bulk_retry_dead_defaults_to_dead_status():
    rec = _Recorder([_json_resp(200, {"requeued": 3, "ids": [1, 2, 3], "dry_run": False, "statuses": ["dead"], "webhook_id": None})])
    with _client_with(rec.handler) as c:
        out = c.bulk_retry_dead()
    assert out["requeued"] == 3
    req = rec.calls[0]
    assert req.method == "POST"
    assert req.url.path == "/notifications/deliveries/bulk-retry"
    body = json.loads(req.content)
    assert body == {"statuses": ["dead"], "limit": 500, "dry_run": False}


def test_bulk_retry_dead_passes_webhook_id_and_dry_run():
    rec = _Recorder([_json_resp(200, {"requeued": 0, "ids": [], "dry_run": True, "statuses": ["dead", "failure"], "webhook_id": 7})])
    with _client_with(rec.handler) as c:
        c.bulk_retry_dead(statuses=["dead", "failure"], webhook_id=7, limit=100, dry_run=True)
    body = json.loads(rec.calls[0].content)
    assert body == {"statuses": ["dead", "failure"], "limit": 100, "dry_run": True, "webhook_id": 7}


def test_bulk_retry_dead_surfaces_400():
    rec = _Recorder([_json_resp(400, {"detail": "unsupported statuses ['success']; allowed: dead, failure"})])
    with _client_with(rec.handler) as c, pytest.raises(WebhookAdminError) as ei:
        c.bulk_retry_dead(statuses=["success"])
    assert ei.value.status == 400
    assert "unsupported statuses" in str(ei.value)


# =====================================================================
# api_client — error normalization
# =====================================================================
def test_4xx_with_json_detail_surfaces_detail_message():
    rec = _Recorder([_json_resp(400, {"detail": "url scheme must be http or https"})])
    with _client_with(rec.handler) as c, pytest.raises(WebhookAdminError) as ei:
        c.create_webhook(url="ftp://x", event_types=[], description="", active=True)
    assert ei.value.status == 400
    assert "url scheme" in str(ei.value)


def test_5xx_without_json_falls_back_to_text():
    rec = _Recorder([httpx.Response(500, text="boom")])
    with _client_with(rec.handler) as c, pytest.raises(WebhookAdminError) as ei:
        c.queue_stats()
    assert ei.value.status == 500
    assert "boom" in str(ei.value)


def test_timeout_raises_with_status_none():
    def _raise(_request):
        raise httpx.ConnectTimeout("nope")
    with _client_with(_raise) as c, pytest.raises(WebhookAdminError) as ei:
        c.list_webhooks()
    assert ei.value.status is None
    assert "timed out" in str(ei.value)


def test_transport_error_raises_with_status_none():
    def _raise(_request):
        raise httpx.ConnectError("refused")
    with _client_with(_raise) as c, pytest.raises(WebhookAdminError) as ei:
        c.list_webhooks()
    assert ei.value.status is None
    assert "refused" in str(ei.value)


# =====================================================================
# api_client — auth header injection (auth-enable-v2)
# =====================================================================
def test_default_client_attaches_api_key_when_env_set(monkeypatch):
    """T6: DASHBOARD_API_KEY set + default construction → X-API-Key on request."""
    monkeypatch.setenv("DASHBOARD_API_KEY", "dash-key-123")
    rec = _Recorder([_json_resp(200, [])])
    with WebhookAdminClient(
        "http://test", transport=httpx.MockTransport(rec.handler)
    ) as c:
        c.list_webhooks()
    assert rec.calls[0].headers.get("x-api-key") == "dash-key-123"


def test_default_client_omits_api_key_when_env_absent(monkeypatch):
    """T7: no key configured → no X-API-Key header (existing no-key behavior)."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.delenv("MATERIALS_API_KEY", raising=False)
    rec = _Recorder([_json_resp(200, [])])
    with WebhookAdminClient(
        "http://test", transport=httpx.MockTransport(rec.handler)
    ) as c:
        c.list_webhooks()
    assert "x-api-key" not in rec.calls[0].headers


def test_explicit_headers_override_auth_headers(monkeypatch):
    """T8: explicit headers= takes precedence over auth_headers()."""
    monkeypatch.setenv("DASHBOARD_API_KEY", "dash-key-123")
    rec = _Recorder([_json_resp(200, [])])
    custom = {"X-API-Key": "injected", "X-Custom": "yes"}
    with WebhookAdminClient(
        "http://test",
        transport=httpx.MockTransport(rec.handler),
        headers=custom,
    ) as c:
        c.list_webhooks()
    headers = rec.calls[0].headers
    assert headers.get("x-api-key") == "injected"
    assert headers.get("x-custom") == "yes"



# =====================================================================
# formatters — pure functions
# =====================================================================
def test_format_queue_stats_cards_returns_six_in_fixed_order():
    stats = {"queued": 1, "in_flight": 2, "retrying": 3, "success_24h": 4, "failure_24h": 5, "dead": 6}
    cards = formatters.format_queue_stats_cards(stats)
    assert len(cards) == 6
    values = [v for _, v, _ in cards]
    assert values == [1, 2, 3, 4, 5, 6]
    labels = [lbl for lbl, _, _ in cards]
    assert "대기 중" in labels[0] and "포기됨" in labels[5]


def test_format_queue_stats_cards_handles_missing_or_invalid_keys():
    cards = formatters.format_queue_stats_cards({"queued": "not-a-number"})
    # All cards default to 0; the bad value is coerced safely.
    assert [v for _, v, _ in cards] == [0, 0, 0, 0, 0, 0]
    # None input should not crash.
    assert len(formatters.format_queue_stats_cards(None)) == 6


def test_format_webhook_row_truncates_long_url_and_renders_events():
    wh = {
        "id": 1,
        "url": "https://example.com/" + "x" * 200,
        "event_types": ["a", "b"],
        "active": True,
        "description": "d",
        "created_at": "2026-05-25T12:34:56.123",
    }
    row = formatters.format_webhook_row(wh)
    assert row["id"] == 1
    assert row["url"].endswith("…")
    assert len(row["url"]) == 60
    assert row["events"] == "a, b"
    assert row["active"] == "✅"
    assert row["created_at"] == "2026-05-25T12:34:56"


def test_format_webhook_row_empty_events_means_subscribe_all():
    row = formatters.format_webhook_row({"id": 2, "url": "https://x", "event_types": [], "active": False, "description": "", "created_at": ""})
    assert row["events"] == "(전체)"
    assert row["active"] == "⛔"


def test_format_delivery_row_status_emoji_and_duration():
    d = {"id": 7, "webhook_id": 1, "event_type": "production.batch.created",
         "status": "success", "response_status": 200, "response_body": "ok",
         "error": None, "attempted_at": "2026-05-25T01:02:03", "duration_ms": 87}
    row = formatters.format_delivery_row(d)
    assert row["status"].startswith("✅")
    assert row["duration"] == "87 ms"
    assert row["response_status"] == "200"


def test_format_delivery_row_unknown_status_uses_question_mark():
    row = formatters.format_delivery_row({"id": 1, "status": "weird", "duration_ms": None})
    assert row["status"].startswith("❔")
    assert row["duration"] == "-"
    assert row["response_status"] == "-"


def test_truncate_short_input_unchanged_and_long_input_gets_ellipsis():
    assert formatters.truncate("abc", 10) == "abc"
    assert formatters.truncate("abcdef", 4) == "abc…"
    assert formatters.truncate("", 10) == ""
    assert formatters.truncate(None, 10) == ""
    assert formatters.truncate("x", 0) == ""
    assert formatters.truncate("xyz", 1) == "…"


def test_parse_event_types_input_dedupes_strips_and_handles_mixed_separators():
    raw = "a, b\nc,, a , d"
    assert formatters.parse_event_types_input(raw) == ["a", "b", "c", "d"]
    assert formatters.parse_event_types_input("") == []
    assert formatters.parse_event_types_input(None) == []


def test_is_retryable_status_only_failed_dead():
    assert formatters.is_retryable_status("failed")
    assert formatters.is_retryable_status("dead")
    assert formatters.is_retryable_status("permanent_failure")
    assert not formatters.is_retryable_status("success")
    assert not formatters.is_retryable_status("queued")
    assert not formatters.is_retryable_status(None)


# =====================================================================
# Static page wiring (AC1) — verified by source inspection, not Streamlit runtime.
# =====================================================================
def test_app_py_registers_webhook_page_under_operations_section():
    """AC1: dashboard/app.py must declare a `views/webhooks.py` entry.

    We can't run the Streamlit page directly (no st.runtime in pytest), so
    we inspect the source to confirm the nav wiring is in place.
    (nav-routing-fix-v1: the directory is views/, NOT pages/ — a pages/ dir
    would re-enable Streamlit's legacy v1 routing on cold deep links.)
    """
    src = (_ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert '"운영"' in src
    assert 'views/webhooks.py' in src
    assert 'Webhook 관리' in src


def test_no_legacy_pages_directory():
    """nav-routing-fix-v1 regression guard: dashboard/pages/ must not exist.

    Even an EMPTY pages/ directory flips PagesManager.uses_pages_directory
    (Streamlit 1.58, pages_manager.py:58) and cold-session deep links bypass
    st.navigation entirely.
    """
    assert not (_ROOT / "dashboard" / "pages").exists()


def test_webhooks_page_file_exists_and_uses_api_base_url():
    page = (_ROOT / "dashboard" / "views" / "webhooks.py").read_text(encoding="utf-8")
    assert "WebhookAdminClient" in page
    assert "API_BASE_URL" in page
    # AC9: page-level try/except for catalog failure must be present.
    assert "except Exception" in page


def test_views_module_does_not_call_api_client_at_import_time():
    """Sanity: importing views.py should not perform any HTTP request.

    Cheap import-time smoke that protects future contributors from adding
    eager API calls that would break Streamlit's lazy-render contract.
    """
    # We can't import views.py (it requires streamlit at module top-level),
    # but we can verify the source has no module-level api_client.* invocation.
    src = (_PKG_DIR / "views.py").read_text(encoding="utf-8")
    # All client calls must be inside functions (heuristic: '    client.' indent).
    module_level_calls = [
        ln for ln in src.splitlines()
        if ln.startswith("client.") or ln.startswith("WebhookAdminClient(")
    ]
    assert module_level_calls == [], f"unexpected module-level api calls: {module_level_calls}"


def test_views_wires_bulk_retry_button_in_queue_stats():
    """webhook-bulk-retry-v1: the dead-letter bulk retry button must be wired
    into the queue-stats section, calling bulk_retry_dead via a helper, and
    still perform no module-level api calls."""
    src = (_PKG_DIR / "views.py").read_text(encoding="utf-8")
    assert "bulk_retry_dead" in src
    assert "_do_bulk_retry_dead" in src
    assert "webhook_bulk_retry_dead" in src  # button key
    # the helper call must be inside a function, never at module level
    module_level_calls = [
        ln for ln in src.splitlines()
        if ln.startswith("client.") or ln.startswith("WebhookAdminClient(")
    ]
    assert module_level_calls == []
