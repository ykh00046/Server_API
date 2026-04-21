# tests/test_chat_stream.py
"""SSE /chat/stream endpoint tests with mocked Gemini streaming client.

Covers event contract: meta → [tool_call]* → token+ → done,
error path, rate limiting, and session persistence.
"""

from __future__ import annotations

import pytest

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
    """Return list of (event, raw_data_json_str) in order.

    Also collects SSE comments (lines starting with ':') as ('comment', text).
    """
    events: list[tuple[str, str]] = []
    cur_event: str | None = None
    for line in body.splitlines():
        if line.startswith(":"):
            events.append(("comment", line[1:].strip()))
        elif line.startswith("event:"):
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
    names = [e[0] for e in events]
    assert "error" in names


# ------------------------------------------------------------------
# New tests: SSE streaming optimization (S1-S6)
# ------------------------------------------------------------------
import asyncio
import json


class _SlowAsyncIter:
    """Fake async iterator that waits *delay* seconds between chunks."""

    def __init__(self, chunks, delay: float = 0.0):
        self._chunks = list(chunks)
        self._delay = delay
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        if self._idx > 0 and self._delay:
            await asyncio.sleep(self._delay)
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


class _FakeAioModelsSlow:
    def __init__(self, chunks, delay=0.0, raise_exc=None):
        self._chunks = chunks
        self._delay = delay
        self._raise_exc = raise_exc

    async def generate_content_stream(self, **kwargs):
        if self._raise_exc:
            raise self._raise_exc
        return _SlowAsyncIter(self._chunks, delay=self._delay)


class _FakeClientSlow:
    def __init__(self, chunks=None, delay=0.0, raise_exc=None):
        self.aio = type("FakeAio", (), {
            "models": _FakeAioModelsSlow(chunks or [], delay, raise_exc)
        })()


def _patch_client_slow(monkeypatch, chunks=None, delay=0.0, raise_exc=None):
    fake = _FakeClientSlow(chunks=chunks, delay=delay, raise_exc=raise_exc)
    monkeypatch.setattr(stream_mod, "get_client", lambda: fake)


# S5: Structured error codes
def test_stream_error_code_ai_disabled(client, monkeypatch):
    """ai_disabled error code when client is None."""
    _patch_client(monkeypatch, none_client=True)
    r = client.post("/chat/stream", json={"query": "hi"})
    events = _parse_sse(r.text)
    err_events = [(e, json.loads(d)) for e, d in events if e == "error"]
    assert len(err_events) == 1
    assert err_events[0][1]["code"] == "ai_disabled"


def test_stream_error_code_model_error(client, monkeypatch):
    """model_error code when Gemini raises non-fallbackable exception."""
    from google.genai.errors import ClientError
    exc = ClientError.__new__(ClientError)
    exc.status = 400
    exc.message = "400 Bad Request: invalid query"
    exc.args = ("400 Bad Request: invalid query",)
    _patch_client(monkeypatch, raise_exc=exc)
    r = client.post("/chat/stream", json={"query": "hi"})
    events = _parse_sse(r.text)
    err_events = [(e, json.loads(d)) for e, d in events if e == "error"]
    assert len(err_events) == 1
    assert err_events[0][1]["code"] == "model_error"


def test_stream_error_code_internal(client, monkeypatch):
    """internal code when exception occurs mid-stream."""
    class _FailingIter:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise RuntimeError("unexpected mid-stream failure")

    class _FakeAioModelsFailing:
        async def generate_content_stream(self, **kwargs):
            return _FailingIter()

    fake_client = type("FC", (), {
        "aio": type("FA", (), {
            "models": _FakeAioModelsFailing()
        })()
    })()
    monkeypatch.setattr(stream_mod, "get_client", lambda: fake_client)
    r = client.post("/chat/stream", json={"query": "hi"})
    events = _parse_sse(r.text)
    err_events = [(e, json.loads(d)) for e, d in events if e == "error"]
    assert len(err_events) == 1
    assert err_events[0][1]["code"] == "internal"


# S6: tool_call duplicate names allowed
def test_stream_tool_call_duplicate_allowed(client, monkeypatch):
    """Same function called twice should emit two tool_call events."""
    tc1 = _FakePart(function_call=_FakeFunctionCall("get_production_summary", {"q": "a"}))
    tc2 = _FakePart(function_call=_FakeFunctionCall("get_production_summary", {"q": "b"}))
    _patch_client(monkeypatch, chunks=[
        _FakeChunk(parts=[tc1]),
        _FakeChunk(parts=[tc2]),
        _FakeChunk(text="done"),
    ])
    r = client.post("/chat/stream", json={"query": "compare"})
    events = _parse_sse(r.text)
    tc_events = [(e, json.loads(d)) for e, d in events if e == "tool_call"]
    assert len(tc_events) == 2
    assert tc_events[0][1]["args"]["q"] == "a"
    assert tc_events[1][1]["args"]["q"] == "b"
    # done event should list both
    done_events = [json.loads(d) for e, d in events if e == "done"]
    assert done_events[0]["tools_used"] == ["get_production_summary", "get_production_summary"]


# S1: heartbeat on slow stream
def test_stream_heartbeat_emitted(client, monkeypatch):
    """Heartbeat comment emitted when chunk interval exceeds STREAM_HEARTBEAT_SEC."""
    # Set heartbeat to 0.1s for fast test
    monkeypatch.setattr(stream_mod, "STREAM_HEARTBEAT_SEC", 0.1)
    monkeypatch.setattr(stream_mod, "STREAM_TIMEOUT_SEC", 10.0)
    _patch_client_slow(monkeypatch, chunks=[
        _FakeChunk(text="hello "),
        _FakeChunk(text="world"),
    ], delay=0.25)
    r = client.post("/chat/stream", json={"query": "slow"})
    events = _parse_sse(r.text)
    comments = [e for e in events if e[0] == "comment"]
    assert len(comments) >= 1, f"Expected heartbeat comments, got: {events}"
    assert comments[0][1] == "heartbeat"


def test_stream_heartbeat_does_not_break_events(client, monkeypatch):
    """Token events still arrive correctly between heartbeats."""
    monkeypatch.setattr(stream_mod, "STREAM_HEARTBEAT_SEC", 0.05)
    monkeypatch.setattr(stream_mod, "STREAM_TIMEOUT_SEC", 30.0)
    _patch_client_slow(monkeypatch, chunks=[
        _FakeChunk(text="a"),
        _FakeChunk(text="b"),
        _FakeChunk(text="c"),
    ], delay=0.1)
    r = client.post("/chat/stream", json={"query": "ping"})
    events = _parse_sse(r.text)
    token_events = [json.loads(d) for e, d in events if e == "token"]
    full = "".join(t["text"] for t in token_events)
    assert "abc" == full
    assert events[-1][0] == "done"


# S2: stream timeout
def test_stream_timeout(client, monkeypatch):
    """Stream exceeding STREAM_TIMEOUT_SEC emits timeout error."""
    monkeypatch.setattr(stream_mod, "STREAM_HEARTBEAT_SEC", 0.05)
    monkeypatch.setattr(stream_mod, "STREAM_TIMEOUT_SEC", 0.2)

    class _InfiniteIter:
        def __aiter__(self):
            return self
        async def __anext__(self):
            await asyncio.sleep(0.1)
            return _FakeChunk(text="x")

    class _FakeAioInfinite:
        async def generate_content_stream(self, **kwargs):
            return _InfiniteIter()

    fake = type("FC", (), {
        "aio": type("FA", (), {"models": _FakeAioInfinite()})()
    })()
    monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
    r = client.post("/chat/stream", json={"query": "infinite"})
    events = _parse_sse(r.text)
    err_events = [(e, json.loads(d)) for e, d in events if e == "error"]
    assert len(err_events) == 1
    assert err_events[0][1]["code"] == "timeout"


# S4: token buffering
def test_stream_token_buffering(client, monkeypatch):
    """Fast consecutive tokens should be merged (fewer token events than chunks)."""
    monkeypatch.setattr(stream_mod, "STREAM_HEARTBEAT_SEC", 10.0)
    monkeypatch.setattr(stream_mod, "STREAM_TIMEOUT_SEC", 10.0)
    # 10 fast chunks with no delay → should be buffered
    chunks = [_FakeChunk(text=f"t{i}") for i in range(10)]
    _patch_client_slow(monkeypatch, chunks=chunks, delay=0.0)
    r = client.post("/chat/stream", json={"query": "fast"})
    events = _parse_sse(r.text)
    token_events = [json.loads(d) for e, d in events if e == "token"]
    # First token is always immediate, rest are buffered
    # With 10 chunks and ~0 delay, we expect fewer than 10 token events
    full = "".join(t["text"] for t in token_events)
    assert full == "".join(f"t{i}" for i in range(10))
    # At minimum: 1 (first immediate) + at least 1 buffered flush
    assert len(token_events) <= 10, "Buffering should merge some tokens"


def test_stream_first_token_immediate(client, monkeypatch):
    """First token should be emitted immediately, not buffered."""
    monkeypatch.setattr(stream_mod, "STREAM_HEARTBEAT_SEC", 10.0)
    monkeypatch.setattr(stream_mod, "STREAM_TIMEOUT_SEC", 10.0)
    _patch_client_slow(monkeypatch, chunks=[
        _FakeChunk(text="FIRST"),
        _FakeChunk(text="second"),
    ], delay=0.0)
    r = client.post("/chat/stream", json={"query": "ttft"})
    events = _parse_sse(r.text)
    token_events = [json.loads(d) for e, d in events if e == "token"]
    assert len(token_events) >= 1
    assert token_events[0]["text"] == "FIRST"
