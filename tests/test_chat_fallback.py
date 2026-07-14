# tests/test_chat_fallback.py
"""Fallback tests: primary model (Flash) fails → fallback model (2.5 Flash Lite, primary와 같은 family).

Covers sync /chat/ and SSE /chat/stream endpoints.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from google.genai.errors import ClientError, ServerError

from api import _chat_stream as stream_mod
from api import chat as chat_mod
from api._gemini_client import is_fallbackable


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
    """A 429 in the shape the live API actually returns (with error.status)."""
    return ClientError(429, {"error": {
        "code": 429,
        "message": "Resource has been exhausted (e.g. check quota).",
        "status": "RESOURCE_EXHAUSTED",
    }})


def _make_503_error():
    """A 503 in the shape the live API actually returns."""
    return ServerError(503, {"error": {
        "code": 503,
        "message": "The service is currently unavailable.",
        "status": "UNAVAILABLE",
    }})


def _make_500_error():
    """A 500 in the shape the live API actually returns."""
    return ServerError(500, {"error": {
        "code": 500,
        "message": "Internal error.",
        "status": "INTERNAL",
    }})


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


class _FakeLazyAioModels(_FakeAioModels):
    """Mirrors the real AFC path: generate_content_stream() returns a lazy async
    generator, so the provider error surfaces on the first __anext__ — not at
    open time like _FakeAioModels (which is the non-AFC shape)."""

    def __init__(self, *, chunks_before_error=0, primary_chunks=None, **kwargs):
        super().__init__(**kwargs)
        self._chunks_before_error = chunks_before_error
        self._primary_chunks = (
            [_FakeChunk(text="primary stream")] if primary_chunks is None
            else primary_chunks
        )

    async def generate_content_stream(self, *, model, contents, config):
        from shared.config import GEMINI_MODEL
        primary = model == GEMINI_MODEL
        exc = self._primary_exc if primary else self._fallback_exc
        chunks = self._primary_chunks if primary else self._fallback_chunks
        before_error = self._chunks_before_error

        async def _gen():
            if exc:
                for chunk in chunks[:before_error]:
                    yield chunk
                raise exc
            for chunk in chunks:
                yield chunk

        return _gen()


class _FakeAio:
    def __init__(self, lazy=False, **kwargs):
        self.models = (
            _FakeLazyAioModels(**kwargs) if lazy else _FakeAioModels(**kwargs)
        )


class _FakeStreamClient:
    def __init__(self, **kwargs):
        self.aio = _FakeAio(**kwargs)


# ==================================================================
# Error classification (F-01a)
# ==================================================================
class TestErrorClassification:
    def test_sdk_error_shape_contract(self):
        """Breaks first if google-genai ever changes the .code(int)/.status(str) contract."""
        e = _make_429_error()
        assert isinstance(e.code, int) and e.code == 429
        assert e.status == "RESOURCE_EXHAUSTED"
        assert "429" in str(e)

    @pytest.mark.parametrize("err,expected", [
        (_make_429_error(), True),
        (_make_503_error(), True),
        (_make_500_error(), False),
        (ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}}), False),
    ])
    def test_is_fallbackable_real_sdk_shape(self, err, expected):
        assert is_fallbackable(err) is expected

    def test_is_fallbackable_status_absent_shape(self):
        """Malformed responses (no error.status) still classify via message scan."""
        err = ClientError(429, {"error": {"message": "429 Too Many Requests"}})
        assert is_fallbackable(err) is True

    def test_is_fallbackable_ignores_non_api_errors(self):
        assert is_fallbackable(ValueError("429")) is False

    @pytest.mark.parametrize("err,expected", [
        (_make_429_error(), (True, 429)),
        (_make_503_error(), (True, 503)),
        (_make_500_error(), (True, 500)),
        (ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}}), (False, 400)),
    ])
    def test_is_retryable_real_sdk_shape(self, err, expected):
        assert chat_mod._is_retryable_error(err) == expected

    def test_is_retryable_non_api_error(self):
        assert chat_mod._is_retryable_error(ValueError("boom")) == (False, 0)


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

    def test_none_answer_returns_friendly_200(self, client, monkeypatch):
        """SAFETY 차단 등으로 response.text가 None이어도 raw 500이 아니라
        200 + 안내 메시지를 반환하고, 세션 이력은 오염시키지 않는다
        (full-review-202607 H)."""
        fake = _FakeSyncClient()
        fake.models.generate_content = (
            lambda **kwargs: _FakeSyncResponse(text=None)
        )
        monkeypatch.setattr(chat_mod, "_get_client", lambda: fake)

        r = client.post("/chat/", json={"query": "test", "session_id": "s-none"})
        assert r.status_code == 200
        data = r.json()
        assert "답변을 생성하지 못했습니다" in data["answer"]
        # 텍스트 없는 턴은 세션에 저장하지 않음 (스트리밍 경로와 동일 규칙)
        assert "s-none" not in chat_mod._sessions


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


# ==================================================================
# SSE fallback on the real AFC (lazy generator) path — F-01b
# ==================================================================
class TestStreamLazyFallback:
    def test_stream_fallback_on_lazy_429(self, client, monkeypatch):
        """With tools=callables the SDK raises on first __anext__, not at open.
        Priming pulls that error into the fallback decision."""
        fake = _FakeStreamClient(lazy=True, primary_exc=_make_429_error())
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
        monkeypatch.setattr(stream_mod, "GEMINI_FALLBACK_ENABLED", True)

        r = client.post("/chat/stream", json={"query": "test"})
        assert r.status_code == 200
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "meta" in names
        assert "token" in names
        assert "done" in names

        meta = json.loads(events[names.index("meta")][1])
        assert meta["fallback"] is True
        assert "flash-lite" in meta["model"]

    def test_stream_lazy_both_models_fail(self, client, monkeypatch):
        """Lazy 429 on primary, lazy 503 on fallback → error event, no meta."""
        fake = _FakeStreamClient(
            lazy=True,
            primary_exc=_make_429_error(),
            fallback_exc=_make_503_error(),
        )
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
        monkeypatch.setattr(stream_mod, "GEMINI_FALLBACK_ENABLED", True)

        r = client.post("/chat/stream", json={"query": "test"})
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "error" in names
        assert "meta" not in names

        err = json.loads(events[names.index("error")][1])
        assert err["code"] == "model_error"

    def test_stream_error_after_first_chunk_is_classified(self, client, monkeypatch):
        """A 429 *after* the first chunk cannot fall back (text already sent), but
        it must still surface as rate_limited — never as a raw provider dump."""
        fake = _FakeStreamClient(
            lazy=True,
            primary_exc=_make_429_error(),
            chunks_before_error=1,
        )
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)
        monkeypatch.setattr(stream_mod, "GEMINI_FALLBACK_ENABLED", True)

        r = client.post("/chat/stream", json={"query": "test"})
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "meta" in names  # primary opened fine — no fallback
        assert "error" in names

        meta = json.loads(events[names.index("meta")][1])
        assert meta["fallback"] is False

        err = json.loads(events[names.index("error")][1])
        assert err["code"] == "rate_limited"
        assert "RESOURCE_EXHAUSTED" not in err["message"]
        assert "잠시 후" in err["message"]

    def test_stream_empty_lazy_stream_completes(self, client, monkeypatch):
        """Zero-chunk stream: priming finds nothing, and that is not an error."""
        fake = _FakeStreamClient(lazy=True, primary_chunks=[])
        monkeypatch.setattr(stream_mod, "get_client", lambda: fake)

        r = client.post("/chat/stream", json={"query": "test"})
        events = _parse_sse(r.text)
        names = [e[0] for e in events]
        assert "meta" in names
        assert "done" in names
        assert "error" not in names

        done = json.loads(events[names.index("done")][1])
        assert done["chars"] == 0
