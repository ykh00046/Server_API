# api/_chat_stream.py
"""
SSE streaming endpoint helper for /chat/stream.

Emits events in order: meta → [tool_call]* → token+ → done
On error mid-stream: event: error (then generator returns).

Features (v2 — sse-streaming-optimization):
- Heartbeat: SSE comment (`: heartbeat`) every STREAM_HEARTBEAT_SEC idle
- Timeout: total stream capped at STREAM_TIMEOUT_SEC
- Token buffering: sub-50ms tokens merged (first token always immediate)
- Structured error codes: ai_disabled, timeout, model_error, internal
- tool_call: duplicate function names allowed (list-based tracking)

Reuses:
- api/_gemini_client.get_client  (singleton, shared with /chat/)
- api/_tool_dispatch.PRODUCTION_TOOLS
- api/_session_store              (get/save session history)
- shared/config.GEMINI_MODEL
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi.responses import StreamingResponse
from google.genai import types
from google.genai.errors import ClientError, ServerError

from shared import get_logger
from shared.config import (
    GEMINI_FALLBACK_ENABLED,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    STREAM_BUFFER_FLUSH_MS,
    STREAM_HEARTBEAT_SEC,
    STREAM_TIMEOUT_SEC,
)

from . import _session_store as _sstore
from ._gemini_client import extract_http_code, get_client, is_fallbackable
from ._tool_dispatch import PRODUCTION_TOOLS

# Structured error codes for SSE error events
ERR_AI_DISABLED = "ai_disabled"
ERR_TIMEOUT = "timeout"
ERR_MODEL_ERROR = "model_error"
ERR_RATE_LIMITED = "rate_limited"
ERR_INTERNAL = "internal"

logger = get_logger(__name__)


@dataclass
class _StreamOpenResult:
    stream: object | None  # provider stream — the aclose() target
    model: str
    aiter: object | None = None  # its iterator, already primed by one __anext__
    first_chunk: object | None = None  # primed chunk, replayed by _consume_stream
    fallback_used: bool = False
    error_frame: str | None = None


@dataclass
class _StreamState:
    full_text_parts: list[str] = field(default_factory=list)
    tools_emitted: list[tuple[str, dict]] = field(default_factory=list)
    token_buffer: list[str] = field(default_factory=list)
    last_token_time: float = 0.0
    first_token_sent: bool = False
    failed: bool = False

    def flush_buffer(self) -> str | None:
        """Flush accumulated token text as one SSE frame."""
        if not self.token_buffer:
            return None
        merged = "".join(self.token_buffer)
        self.full_text_parts.append(merged)
        self.token_buffer.clear()
        return _sse("token", {"text": merged})


def _sse(event: str, data: dict) -> str:
    """Format one SSE frame. ensure_ascii=False so Korean text stays readable."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _iter_with_heartbeat(
    aiter, heartbeat_sec: float
) -> AsyncIterator[object | None]:
    """Wrap an async iterator, yielding None as heartbeat on idle.

    Takes an already-obtained iterator (not the stream) because the caller has
    primed it with one __anext__ — re-iterating the stream would replay from
    the start or fail.

    Uses asyncio.wait (not wait_for) to avoid cancelling the pending __anext__
    coroutine on timeout — the chunk task stays alive across heartbeat intervals.

    Yields:
        chunk object from the iterator, or None if heartbeat_sec elapsed idle.
    """
    next_task = asyncio.ensure_future(aiter.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({next_task}, timeout=heartbeat_sec)
            if done:
                try:
                    chunk = next_task.result()
                except StopAsyncIteration:
                    return
                yield chunk
                next_task = asyncio.ensure_future(aiter.__anext__())
            else:
                yield None  # heartbeat signal
    finally:
        # Timeout/disconnect closes this generator with the prefetched
        # __anext__ still pending — without cancel it dangles ("Task was
        # destroyed but it is pending!") holding the provider HTTP response.
        if not next_task.done():
            next_task.cancel()


async def _safe_aclose(stream) -> None:
    """Close a provider stream if it supports aclose(), swallowing close errors."""
    stream_aclose = getattr(stream, "aclose", None)
    if stream_aclose is not None:
        with contextlib.suppress(Exception):
            await stream_aclose()


async def _open_and_prime(client_obj, model, contents, config):
    """Open a model stream and pull its first chunk.

    With tools=Python callables the SDK takes the automatic-function-calling
    path, where generate_content_stream() only builds a lazy async generator —
    no HTTP request is sent until the first __anext__. Quota (429) and overload
    (503) therefore surface here, not at open time, and priming is what brings
    them inside the caller's fallback decision. (google-genai 2.8.0)

    Returns (stream, aiter, first_chunk); first_chunk is None for an empty stream.
    """
    stream = await client_obj.aio.models.generate_content_stream(
        model=model, contents=contents, config=config,
    )
    aiter = stream.__aiter__()
    try:
        first_chunk = await aiter.__anext__()
    except StopAsyncIteration:
        first_chunk = None  # empty stream is valid — completes with done
    except BaseException:
        await _safe_aclose(stream)  # a failed prime leaves nobody else to close it
        raise
    return stream, aiter, first_chunk


async def _open_model_stream(client_obj, contents, config, request_id, start) -> _StreamOpenResult:
    """Open (and prime) the primary model stream, falling back when eligible."""
    try:
        stream, aiter, first = await _open_and_prime(
            client_obj, GEMINI_MODEL, contents, config
        )
        return _StreamOpenResult(
            stream=stream, model=GEMINI_MODEL, aiter=aiter, first_chunk=first
        )
    except (ClientError, ServerError) as error:
        if not (GEMINI_FALLBACK_ENABLED and is_fallbackable(error)):
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                f"[ChatStream Error] request_id={request_id} | "
                f"error={type(error).__name__}: {error} | duration_ms={duration_ms:.1f}"
            )
            code, message = _classify_stream_error(error)
            return _StreamOpenResult(
                stream=None,
                model=GEMINI_MODEL,
                error_frame=_sse("error", {"code": code, "message": message}),
            )

        logger.warning(
            f"[ChatStream Fallback] request_id={request_id} | "
            f"{GEMINI_MODEL} → {GEMINI_FALLBACK_MODEL} | trigger={error}"
        )
        try:
            stream, aiter, first = await _open_and_prime(
                client_obj, GEMINI_FALLBACK_MODEL, contents, config
            )
            return _StreamOpenResult(
                stream=stream,
                model=GEMINI_FALLBACK_MODEL,
                aiter=aiter,
                first_chunk=first,
                fallback_used=True,
            )
        except Exception as fallback_error:  # noqa: BLE001 — provider SDK boundary
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                f"[ChatStream Fallback Failed] request_id={request_id} | "
                f"error={fallback_error} | duration_ms={duration_ms:.1f}"
            )
            code, message = _classify_stream_error(fallback_error)
            return _StreamOpenResult(
                stream=None,
                model=GEMINI_FALLBACK_MODEL,
                fallback_used=True,
                error_frame=_sse("error", {"code": code, "message": message}),
            )
    except Exception as error:  # noqa: BLE001 — provider SDK boundary
        # Priming pulled consumption-time failures forward, so non-API errors can
        # now land here too. They are not fallbackable; report as before.
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            f"[ChatStream Error] request_id={request_id} | "
            f"error={type(error).__name__}: {error} | duration_ms={duration_ms:.1f}"
        )
        code, message = _classify_stream_error(error)
        return _StreamOpenResult(
            stream=None,
            model=GEMINI_MODEL,
            error_frame=_sse("error", {"code": code, "message": message}),
        )


def _tool_calls_from_chunk(chunk) -> list[tuple[str, dict]]:
    """Extract function calls from a provider chunk, tolerating malformed args."""
    tool_calls: list[tuple[str, dict]] = []
    for candidate in getattr(chunk, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            function_call = getattr(part, "function_call", None)
            if not function_call or not getattr(function_call, "name", None):
                continue
            try:
                args = dict(function_call.args) if getattr(function_call, "args", None) else {}
            except (TypeError, ValueError):
                args = {}
            tool_calls.append((function_call.name, args))
    return tool_calls


def _frames_from_chunk(chunk, state: _StreamState, buffer_flush_sec: float) -> list[str]:
    """Convert one provider chunk into ordered tool-call and token SSE frames."""
    frames: list[str] = []
    for name, args in _tool_calls_from_chunk(chunk):
        state.tools_emitted.append((name, args))
        frames.append(_sse("tool_call", {"name": name, "args": args}))

    text = getattr(chunk, "text", None)
    if not text:
        return frames
    now = time.perf_counter()
    if not state.first_token_sent:
        state.full_text_parts.append(text)
        frames.append(_sse("token", {"text": text}))
        state.first_token_sent = True
        state.last_token_time = now
        return frames

    state.token_buffer.append(text)
    if now - state.last_token_time >= buffer_flush_sec:
        flushed = state.flush_buffer()
        if flushed:
            frames.append(flushed)
        state.last_token_time = now
    return frames


def _classify_stream_error(error: Exception) -> tuple[str, str]:
    """Map a mid-stream error to (SSE code, user-facing message).

    Provider errors get a fixed Korean message keyed by HTTP code — the raw
    str(error) carries provider internals (quota details, request echoes) that
    have no business reaching the browser.
    """
    if isinstance(error, (ClientError, ServerError)):
        http = extract_http_code(error)
        if http == 429:
            return ERR_RATE_LIMITED, "AI 사용량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."
        return ERR_MODEL_ERROR, f"AI 모델 오류가 발생했습니다. (HTTP {http or 'unknown'})"
    return ERR_INTERNAL, str(error)[:500]


async def _consume_stream(
    opened: _StreamOpenResult, state, request_id, start
) -> AsyncIterator[str]:
    """Consume the primed provider stream and translate it to SSE frames.

    The provider stream is explicitly aclose()d on every exit path (timeout,
    error, completion) so its underlying HTTP response is not left to GC.
    """
    buffer_flush_sec = STREAM_BUFFER_FLUSH_MS / 1000.0
    # Priming already spent part of the budget; the rest is what consumption gets.
    remaining_sec = max(STREAM_TIMEOUT_SEC - (time.perf_counter() - start), 0.0)
    try:
        if opened.first_chunk is not None:  # replay the chunk priming pulled
            for frame in _frames_from_chunk(opened.first_chunk, state, buffer_flush_sec):
                yield frame

        async with asyncio.timeout(remaining_sec), contextlib.aclosing(
            _iter_with_heartbeat(opened.aiter, STREAM_HEARTBEAT_SEC)
        ) as heartbeat_iter:
            async for chunk in heartbeat_iter:
                if chunk is None:
                    flushed = state.flush_buffer()
                    if flushed:
                        yield flushed
                    yield ": heartbeat\n\n"
                    continue
                for frame in _frames_from_chunk(chunk, state, buffer_flush_sec):
                    yield frame
    except TimeoutError:
        state.failed = True
        duration_ms = (time.perf_counter() - start) * 1000
        partial_chars = sum(len(part) for part in state.full_text_parts)
        logger.warning(
            f"[ChatStream Timeout] request_id={request_id} | "
            f"partial_chars={partial_chars} | duration_ms={duration_ms:.1f}"
        )
        yield _sse(
            "error",
            {"code": ERR_TIMEOUT, "message": f"스트리밍 시간 초과 ({int(STREAM_TIMEOUT_SEC)}초)"},
        )
    except Exception as error:  # noqa: BLE001 — SSE provider boundary
        state.failed = True
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            f"[ChatStream Error] request_id={request_id} | "
            f"error={type(error).__name__}: {error} | duration_ms={duration_ms:.1f}"
        )
        code, message = _classify_stream_error(error)
        yield _sse("error", {"code": code, "message": message})
    finally:
        await _safe_aclose(opened.stream)


async def run_stream(
    query: str,
    session_id: str | None,
    client_ip: str,
    request_id: str,
    system_instruction: str,
) -> AsyncIterator[str]:
    """Async generator yielding SSE frames for a chat query.

    Rate limiting and session cleanup are expected to be performed by the caller
    (route handler) before invoking this function.
    """
    client_obj = get_client()
    if client_obj is None:
        logger.error(f"[ChatStream] request_id={request_id} | AI disabled")
        yield _sse(
            "error", {"code": ERR_AI_DISABLED, "message": "Gemini API Key is not configured."}
        )
        return

    history = _sstore.get_session_history(session_id, client_ip)
    user_content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
    contents = history + [user_content]

    start = time.perf_counter()
    query_preview = query[:100] + ("..." if len(query) > 100 else "")
    logger.info(f"[ChatStream Start] request_id={request_id} | query='{query_preview}'")

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=PRODUCTION_TOOLS,
    )
    # Priming (see _open_and_prime) runs the first provider round-trip, tool calls
    # included, so it can take seconds — heartbeat through it or the client's read
    # timeout fires before meta ever lands.
    open_task = asyncio.ensure_future(
        _open_model_stream(client_obj, contents, config, request_id, start)
    )
    try:
        while True:
            done, _ = await asyncio.wait({open_task}, timeout=STREAM_HEARTBEAT_SEC)
            if done:
                opened = open_task.result()
                break
            if time.perf_counter() - start > STREAM_TIMEOUT_SEC:
                logger.warning(
                    f"[ChatStream Timeout] request_id={request_id} | phase=open"
                )
                yield _sse("error", {
                    "code": ERR_TIMEOUT,
                    "message": f"스트리밍 시간 초과 ({int(STREAM_TIMEOUT_SEC)}초)",
                })
                return
            yield ": heartbeat\n\n"  # SSE comment — safe before meta
    finally:
        if not open_task.done():
            open_task.cancel()  # client disconnected mid-prime — reclaim the task

    if opened.error_frame:
        yield opened.error_frame
        return

    yield _sse("meta", {
        "request_id": request_id,
        "session_id": session_id,
        "model": opened.model,
        "fallback": opened.fallback_used,
    })

    state = _StreamState()
    async for frame in _consume_stream(opened, state, request_id, start):
        yield frame
    if state.failed:
        return

    # Flush remaining buffer after stream ends
    flushed = state.flush_buffer()
    if flushed:
        yield flushed

    duration_ms = (time.perf_counter() - start) * 1000
    full_text = "".join(state.full_text_parts)

    # Persist session only on successful completion
    if session_id and full_text:
        model_content = types.Content(role="model", parts=[types.Part.from_text(text=full_text)])
        _sstore.save_session_history(session_id, history + [user_content, model_content], client_ip)

    tool_names = [name for name, _ in state.tools_emitted]
    logger.info(
        f"[ChatStream Done] request_id={request_id} | tools={tool_names} | "
        f"chars={len(full_text)} | duration_ms={duration_ms:.1f}"
    )

    yield _sse("done", {
        "tools_used": tool_names,
        "duration_ms": round(duration_ms, 1),
        "chars": len(full_text),
    })


def streaming_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
