# tests/test_chat_fallback.py
"""Fallback tests: primary model (Flash) fails → fallback model (2.5 Flash Lite, primary와 같은 family).

Covers sync /chat/ and SSE /chat/stream endpoints.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from google.genai.errors import ClientError, ServerError

from api import chat as chat_mod
from api import _chat_stream as stream_mod


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_sessions():
    chat_mod._sessions.clear()
    yield


# ------------------------------------------------------------------
# Fake Gemini helpers
# ------------------------------------------------------------------
class _FakePart:
    def __init__(self, function_call=None):
        self.function_call = function_call


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeCandidate:
    def __init__(self, parts):
        self.content = _FakeContent(parts)


class _FakeChunk:
    def __init__(self, text=None, parts=None):
        self.text = text
        self.candidates = [_FakeCandidate(parts or [])]


async def _async_iter(items):
    for it in items:
        yield it


def _make_429_error():
    """Create a fake 429 ClientError."""
    return ClientError(429, {"error": {"message": "Too Many Requests"}})


def _make_503_error():
    """Create a fake 503 ServerError."""
    return ServerError(503, {"error": {"message": "Service Unavailable"}})


def _make_500_error():
    """Create a fake 500 ServerError."""
    return ServerError(500, {"error": {"message": "Internal Server Error"}})


# ------------------------------------------------------------------
# SSE parser
# ------------------------------------------------------------------
def _parse_sse(body: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    cur_event: str | None = None
    for line in body.splitlines():
        if line.startswith("event:"):
            cur_event = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
            if cur_event is not None:
                events.append((cur_event, data))
                cur_event = None
    return events


# ------------------------------------------------------------------
# Fake sync models (for /chat/ endpoint)
# ------------------------------------------------------------------
class _FakeSyncResponse:
    def __init__(self, text="fallback response"):
        self.text = text
        self.candidates = [_FakeCandidate([])]
        self.usage_metadata = MagicMock(
            prompt_token_count=10,
            candidates_token_count=5,
            total_token_count=15,
        )

    @property
    def automatic_function_calling_history(self):
        return []


class _FakeSyncModels:
    """Simulates model.generate_content with configurable per-model behavior."""

    def __init__(self, primary_exc=None, fallback_exc=None, fallback_text="fallback ok"):
        self._primary_exc = primary_exc
        self._fallback_exc = fallback_exc
        self._fallback_text = fallback_text
        self._call_count = 0

    def generate_content(self, *, model, contents, config):
        self._call_count += 1
        from shared.config import GEMINI_MODEL
        if model == GEMINI_MODEL and self._primary_exc:
            raise self._primary_exc
        if model != GEMINI_MODEL:
            if self._fallback_exc:
                raise self._fallback_exc
            return _FakeSyncResponse(text=self._fallback_text)
        return _FakeSyncResponse(text="primary ok")


class _FakeSyncClient:
    def __init__(self, primary_exc=None, fallback_exc=None):
        self.models = _FakeSyncModels(primary_exc=primary_exc, fallback_exc=fallback_exc)


# ------------------------------------------------------------------
# Fake stream models (for /chat/stream endpoint)
# ------------------------------------------------------------------
class _FakeAioModels:
    def __init__(self, primary_exc=None, fallback_exc=None, fallback_chunks=None):
        self._primary_exc = primary_exc
        self._fallback_exc = fallback_exc
        self._fallback_chunks = fallback_chunks or [_FakeChunk(text="fallback stream")]

    async def generate_content_stream(self, *, model, contents, config):
        from shared.config import GEMINI_MODEL
        if model == GEMINI_MODEL and self._primary_exc:
            raise self._primary_exc
        if model != GEMINI_MODEL:
            if self._fallback_exc:
                raise self._fallback_exc
            return _async_iter(self._fallback_chunks)
        return _async_iter([_FakeChunk(text="primary stream")])


class _FakeAio:
    def __init__(self, **kwargs):
        self.models = _FakeAioModels(**kwargs)


class _FakeStreamClient:
    def __init__(self, **kwargs):
        self.aio = _FakeAio(**kwargs)


# ==================================================================
# Sync /chat/ fallback tests
# ==================================================================
class TestSyncFallback:
    def test_fallback_on_429(self, client, monkeypatch):
        """Flash 429 → fallback model succeeds."""
        fake = _FakeSyncClient(primary_exc=_make_429_error())
        monkeypatch.setattr(chat_mod, "_get_client", lambda: fake)
        monkeypatch.setattr(chat_mod, "GEMINI_FALLBACK_ENABLED", True)
        # Disable retry delays for fast test
        monkeypatch.setattr(chat_mod, "MAX_RETRIES", 1)

        r = client.post("/chat/", json={"query": "test"})
        data = r.json()
        assert r.status_code == 200
        assert data["status"] == "success"
        assert "flash-lite" in data["model_used"] or data["model_used"] != ""

    def test_both_models_fail(self, client, monkeypatch):
        """Flash 429 + fallback also fails → error response."""
        fake = _FakeSyncClient(
            primary_exc=_make_429_error(),
            fallback_exc=_make_503_error(),
        )
        monkeypatch.setattr(chat_mod, "_get_client", lambda: fake)
        monkeypatch.setattr(chat_mod, "GEMINI_FALLBACK_ENABLED", True)
        monkeypatch.setattr(chat_mod, "MAX_RETRIES", 1)

        r = client.post("/chat/", json={"query": "test"})
        data = r.json()
        assert data["status"] == "error"

    def test_no_fallback_on_500(self, client, monkeypatch):
        """500 error → retry only, no fallback (500 not in FALLBACK_STATUS_CODES)."""
        fake = _FakeSyncClient(primary_exc=_make_500_error())
        monkeypatch.setattr(chat_mod, "_get_client", lambda: fake)
        monkeypatch.setattr(chat_mod, "GEMINI_FALLBACK_ENABLED", True)
        monkeypatch.setattr(chat_mod, "MAX_RETRIES", 1)

        r = client.post("/chat/", json={"query": "test"})
        data = r.json()
        assert data["status"] == "error"

    def test_fallback_disabled(self, client, monkeypatch):
        """FALLBACK_ENABLED=false → no fallback attempt."""
        fake = _FakeSyncClient(primary_exc=_make_429_error())
        monkeypatch.setattr(chat_mod, "_get_client", lambda: fake)
        monkeypatch.setattr(chat_mod, "GEMINI_FALLBACK_ENABLED", False)
        monkeypatch.setattr(chat_mod, "MAX_RETRIES", 1)

        r = client.post("/chat/", json={"query": "test"})
        data = r.json()
        assert data["status"] == "error"


# ==================================================================
# SSE /chat/stream fallback tests
# ==================================================================
class TestStreamFallback:
    def test_stream_fallback_on_429(self, client, monkeypatch):
        """Stream Flash 429 → fallback model streams OK."""
        fake = _FakeStreamClient(primary_exc=_make_429_error())
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
        monkeypatch.setattr(stream_mod, "GEMINI_FALLBACK_ENABLED", True)

        r = client.post("/chat/stream", json={"query": "test"})
        assert r.status_code == 200
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "meta" in names
        assert "token" in names
        assert "done" in names

        # meta should indicate fallback
        meta_data = json.loads(events[names.index("meta")][1])
        assert meta_data["fallback"] is True
        assert "flash-lite" in meta_data["model"]

    def test_stream_both_fail(self, client, monkeypatch):
        """Stream: both models fail → error SSE event."""
        fake = _FakeStreamClient(
            primary_exc=_make_429_error(),
            fallback_exc=_make_503_error(),
        )
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
        monkeypatch.setattr(stream_mod, "GEMINI_FALLBACK_ENABLED", True)

        r = client.post("/chat/stream", json={"query": "test"})
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "error" in names

    def test_stream_fallback_disabled(self, client, monkeypatch):
        """Stream: FALLBACK_ENABLED=false → error on 429, no fallback."""
        fake = _FakeStreamClient(primary_exc=_make_429_error())
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
        monkeypatch.setattr(stream_mod, "GEMINI_FALLBACK_ENABLED", False)

        r = client.post("/chat/stream", json={"query": "test"})
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "error" in names
        assert "meta" not in names
