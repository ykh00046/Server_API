# tests/test_chat_stream.py
"""SSE /chat/stream endpoint tests with mocked Gemini streaming client.

Covers event contract: meta → [tool_call]* → token+ → done,
error path, rate limiting, and session persistence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from api.main import app
from api import chat as chat_mod
from api import _chat_stream as stream_mod


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_state():
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
    chat_mod._sessions.clear()
    yield


# ------------------------------------------------------------------
# Fake Gemini streaming client
# ------------------------------------------------------------------
class _FakePart:
    def __init__(self, function_call=None):
        self.function_call = function_call


class _FakeFunctionCall:
    def __init__(self, name, args=None):
        self.name = name
        self.args = args or {}


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


class _FakeAioModels:
    def __init__(self, chunks, raise_exc=None):
        self._chunks = chunks
        self._raise_exc = raise_exc

    async def generate_content_stream(self, **kwargs):
        if self._raise_exc:
            raise self._raise_exc
        return _async_iter(self._chunks)


class _FakeAio:
    def __init__(self, chunks, raise_exc=None):
        self.models = _FakeAioModels(chunks, raise_exc)


class _FakeClient:
    def __init__(self, chunks=None, raise_exc=None):
        self.aio = _FakeAio(chunks or [], raise_exc)


def _patch_client(monkeypatch, chunks=None, raise_exc=None, none_client=False):
    if none_client:
        fake = None
    else:
        fake = _FakeClient(chunks=chunks, raise_exc=raise_exc)
    monkeypatch.setattr(stream_mod, "get_client", lambda: fake)


# ------------------------------------------------------------------
# SSE parse helper
# ------------------------------------------------------------------
def _parse_sse(body: str) -> list[tuple[str, str]]:
    """Return list of (event, raw_data_json_str) in order."""
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
# Tests
# ------------------------------------------------------------------
def test_stream_meta_first(client, monkeypatch):
    _patch_client(monkeypatch, chunks=[_FakeChunk(text="hi")])
    r = client.post("/chat/stream", json={"query": "ping"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    assert events, "no SSE events parsed"
    assert events[0][0] == "meta"


def test_stream_emits_tokens_and_done(client, monkeypatch):
    _patch_client(monkeypatch, chunks=[
        _FakeChunk(text="Hello "),
        _FakeChunk(text="world"),
    ])
    r = client.post("/chat/stream", json={"query": "ping"})
    events = _parse_sse(r.text)
    names = [e[0] for e in events]
    assert names.count("token") == 2
    assert names[-1] == "done"


def test_stream_tool_call_event(client, monkeypatch):
    tool_call_part = _FakePart(
        function_call=_FakeFunctionCall("get_production_summary", {"date_from": "2026-01-01"})
    )
    _patch_client(monkeypatch, chunks=[
        _FakeChunk(parts=[tool_call_part]),
        _FakeChunk(text="Result "),
        _FakeChunk(text="summary."),
    ])
    r = client.post("/chat/stream", json={"query": "summary?"})
    events = _parse_sse(r.text)
    names = [e[0] for e in events]
    assert "tool_call" in names
    # Order: meta, tool_call before tokens, done last
    assert names.index("tool_call") < names.index("token")
    assert names[-1] == "done"


def test_stream_rate_limited(client, monkeypatch):
    _patch_client(monkeypatch, chunks=[_FakeChunk(text="ok")])
    # Exhaust the chat rate limiter
    from api.chat import chat_rate_limiter
    chat_rate_limiter._requests.clear()
    # RATE_LIMIT_CHAT = 20; do 20 successes then 1 that should 429
    for _ in range(20):
        rr = client.post("/chat/stream", json={"query": "q"})
        assert rr.status_code == 200
    r = client.post("/chat/stream", json={"query": "q"})
    assert r.status_code == 429


def test_stream_session_persisted(client, monkeypatch):
    _patch_client(monkeypatch, chunks=[
        _FakeChunk(text="first "),
        _FakeChunk(text="reply"),
    ])
    r = client.post("/chat/stream", json={"query": "hello", "session_id": "s-stream-1"})
    assert r.status_code == 200
    # Session should now contain 1 user + 1 model turn
    assert "s-stream-1" in chat_mod._sessions
    history = chat_mod._sessions["s-stream-1"]["history"]
    assert len(history) == 2  # user + model


def test_stream_error_event_when_client_missing(client, monkeypatch):
    _patch_client(monkeypatch, none_client=True)
    r = client.post("/chat/stream", json={"query": "hi"})
    assert r.status_code == 200  # stream started, error conveyed inline
    events = _parse_sse(r.text)
    # meta is emitted before we check client in _chat_stream? No — we check client first.
    # Our implementation yields error directly without meta. Verify that.
    names = [e[0] for e in events]
    assert "error" in names
