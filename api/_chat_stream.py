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
import json
import time
from typing import AsyncIterator

from fastapi.responses import StreamingResponse
from google.genai import types

from google.genai.errors import ClientError, ServerError

from shared import get_logger
from shared.config import (
    GEMINI_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_FALLBACK_ENABLED,
    STREAM_HEARTBEAT_SEC,
    STREAM_TIMEOUT_SEC,
    STREAM_BUFFER_FLUSH_MS,
)

from ._gemini_client import get_client
from ._tool_dispatch import PRODUCTION_TOOLS
from . import _session_store as _sstore

FALLBACK_STATUS_CODES = {429, 503}

# Structured error codes for SSE error events
ERR_AI_DISABLED = "ai_disabled"
ERR_TIMEOUT = "timeout"
ERR_MODEL_ERROR = "model_error"
ERR_RATE_LIMITED = "rate_limited"
ERR_INTERNAL = "internal"


def _is_fallbackable(e: Exception) -> bool:
    """Check if the error warrants a model fallback (429/503 only)."""
    if isinstance(e, (ClientError, ServerError)):
        status = getattr(e, "status", 0) or 0
        if status == 0:
            for code in FALLBACK_STATUS_CODES:
                if str(code) in str(e):
                    return True
        return status in FALLBACK_STATUS_CODES
    return False


logger = get_logger(__name__)


def _sse(event: str, data: dict) -> str:
    """Format one SSE frame. ensure_ascii=False so Korean text stays readable."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _iter_with_heartbeat(
    stream, heartbeat_sec: float
) -> AsyncIterator[object | None]:
    """Wrap async stream iterator, yielding None as heartbeat on idle.

    Uses asyncio.wait (not wait_for) to avoid cancelling the pending __anext__
    coroutine on timeout — the chunk task stays alive across heartbeat intervals.

    Yields:
        chunk object from stream, or None if heartbeat_sec elapsed without a chunk.
    """
    aiter = stream.__aiter__()
    next_task = asyncio.ensure_future(aiter.__anext__())
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
        yield _sse("error", {"code": ERR_AI_DISABLED, "message": "Gemini API Key is not configured."})
        return

    history = _sstore.get_session_history(session_id, client_ip)
    user_content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
    contents = history + [user_content]

    start = time.perf_counter()
    query_preview = query[:100] + ("..." if len(query) > 100 else "")
    logger.info(f"[ChatStream Start] request_id={request_id} | query='{query_preview}'")

    # Attempt primary model, fallback on 429/503
    model_to_use = GEMINI_MODEL
    fallback_used = False
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=PRODUCTION_TOOLS,
    )

    try:
        stream = await client_obj.aio.models.generate_content_stream(
            model=model_to_use, contents=contents, config=config,
        )
    except (ClientError, ServerError) as e:
        if GEMINI_FALLBACK_ENABLED and _is_fallbackable(e):
            model_to_use = GEMINI_FALLBACK_MODEL
            fallback_used = True
            logger.warning(
                f"[ChatStream Fallback] request_id={request_id} | "
                f"{GEMINI_MODEL} → {GEMINI_FALLBACK_MODEL} | trigger={e}"
            )
            try:
                stream = await client_obj.aio.models.generate_content_stream(
                    model=model_to_use, contents=contents, config=config,
                )
            except Exception as fb_err:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    f"[ChatStream Fallback Failed] request_id={request_id} | error={fb_err} | "
                    f"duration_ms={duration_ms:.1f}"
                )
                yield _sse("error", {"code": ERR_MODEL_ERROR, "message": str(fb_err)[:500]})
                return
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                f"[ChatStream Error] request_id={request_id} | "
                f"error={type(e).__name__}: {e} | duration_ms={duration_ms:.1f}"
            )
            yield _sse("error", {"code": ERR_MODEL_ERROR, "message": str(e)[:500]})
            return

    yield _sse("meta", {
        "request_id": request_id,
        "session_id": session_id,
        "model": model_to_use,
        "fallback": fallback_used,
    })

    full_text_parts: list[str] = []
    tools_emitted: list[tuple[str, dict]] = []

    # Token buffering state
    token_buffer: list[str] = []
    last_token_time: float = 0.0
    first_token_sent = False
    buffer_flush_sec = STREAM_BUFFER_FLUSH_MS / 1000.0

    def _flush_buffer():
        """Flush accumulated token buffer as a single SSE event."""
        if not token_buffer:
            return None
        merged = "".join(token_buffer)
        full_text_parts.append(merged)
        token_buffer.clear()
        return _sse("token", {"text": merged})

    try:
        async with asyncio.timeout(STREAM_TIMEOUT_SEC):
            async for chunk in _iter_with_heartbeat(stream, STREAM_HEARTBEAT_SEC):
                if chunk is None:
                    # Flush buffer before heartbeat
                    flushed = _flush_buffer()
                    if flushed:
                        yield flushed
                    yield ": heartbeat\n\n"
                    continue

                # 1) tool_call emission (duplicates allowed)
                candidates = getattr(chunk, "candidates", None) or []
                for cand in candidates:
                    content = getattr(cand, "content", None)
                    parts = getattr(content, "parts", None) or []
                    for p in parts:
                        fc = getattr(p, "function_call", None)
                        if fc and getattr(fc, "name", None):
                            try:
                                args = dict(fc.args) if getattr(fc, "args", None) else {}
                            except (TypeError, ValueError):
                                args = {}
                            tools_emitted.append((fc.name, args))
                            yield _sse("tool_call", {"name": fc.name, "args": args})

                # 2) token emission with buffering
                text = getattr(chunk, "text", None)
                if text:
                    now = time.perf_counter()
                    if not first_token_sent:
                        # First token: emit immediately for TTFT
                        full_text_parts.append(text)
                        yield _sse("token", {"text": text})
                        first_token_sent = True
                        last_token_time = now
                    else:
                        token_buffer.append(text)
                        elapsed = now - last_token_time
                        if elapsed >= buffer_flush_sec:
                            flushed = _flush_buffer()
                            if flushed:
                                yield flushed
                            last_token_time = now

    except TimeoutError:
        duration_ms = (time.perf_counter() - start) * 1000
        partial_chars = sum(len(p) for p in full_text_parts)
        logger.warning(
            f"[ChatStream Timeout] request_id={request_id} | "
            f"partial_chars={partial_chars} | duration_ms={duration_ms:.1f}"
        )
        yield _sse("error", {"code": ERR_TIMEOUT, "message": f"스트리밍 시간 초과 ({int(STREAM_TIMEOUT_SEC)}초)"})
        return
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            f"[ChatStream Error] request_id={request_id} | "
            f"error={type(e).__name__}: {e} | duration_ms={duration_ms:.1f}"
        )
        yield _sse("error", {"code": ERR_INTERNAL, "message": str(e)[:500]})
        return

    # Flush remaining buffer after stream ends
    flushed = _flush_buffer()
    if flushed:
        yield flushed

    duration_ms = (time.perf_counter() - start) * 1000
    full_text = "".join(full_text_parts)

    # Persist session only on successful completion
    if session_id and full_text:
        model_content = types.Content(role="model", parts=[types.Part.from_text(text=full_text)])
        _sstore.save_session_history(session_id, history + [user_content, model_content], client_ip)

    tool_names = [name for name, _ in tools_emitted]
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
