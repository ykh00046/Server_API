# api/_chat_stream.py
"""
SSE streaming endpoint helper for /chat/stream.

Emits events in order: meta → [tool_call]* → token+ → done
On error mid-stream: event: error (then generator returns).

Reuses:
- api/_gemini_client.get_client  (singleton, shared with /chat/)
- api/_tool_dispatch.PRODUCTION_TOOLS
- api/_session_store              (get/save session history)
- shared/config.GEMINI_MODEL
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

from fastapi.responses import StreamingResponse
from google.genai import types

from shared import get_logger
from shared.config import GEMINI_MODEL

from ._gemini_client import get_client
from ._tool_dispatch import PRODUCTION_TOOLS
from . import _session_store as _sstore

logger = get_logger(__name__)


def _sse(event: str, data: dict) -> str:
    """Format one SSE frame. ensure_ascii=False so Korean text stays readable."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
        yield _sse("error", {"code": "AI_DISABLED", "message": "Gemini API Key is not configured."})
        return

    history = _sstore.get_session_history(session_id, client_ip)
    user_content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
    contents = history + [user_content]

    yield _sse("meta", {
        "request_id": request_id,
        "session_id": session_id,
        "model": GEMINI_MODEL,
    })

    full_text_parts: list[str] = []
    tools_emitted: set[str] = set()
    start = time.perf_counter()
    query_preview = query[:100] + ("..." if len(query) > 100 else "")
    logger.info(f"[ChatStream Start] request_id={request_id} | query='{query_preview}'")

    try:
        stream = await client_obj.aio.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=PRODUCTION_TOOLS,
            ),
        )
        async for chunk in stream:
            # 1) tool_call emission
            candidates = getattr(chunk, "candidates", None) or []
            for cand in candidates:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) or []
                for p in parts:
                    fc = getattr(p, "function_call", None)
                    if fc and getattr(fc, "name", None) and fc.name not in tools_emitted:
                        tools_emitted.add(fc.name)
                        try:
                            args = dict(fc.args) if getattr(fc, "args", None) else {}
                        except (TypeError, ValueError):
                            args = {}
                        yield _sse("tool_call", {"name": fc.name, "args": args})

            # 2) token emission
            text = getattr(chunk, "text", None)
            if text:
                full_text_parts.append(text)
                yield _sse("token", {"text": text})
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            f"[ChatStream Error] request_id={request_id} | "
            f"error={type(e).__name__}: {e} | duration_ms={duration_ms:.1f}"
        )
        yield _sse("error", {"code": type(e).__name__, "message": str(e)[:300]})
        return

    duration_ms = (time.perf_counter() - start) * 1000
    full_text = "".join(full_text_parts)

    # Persist session only on successful completion
    if session_id and full_text:
        model_content = types.Content(role="model", parts=[types.Part.from_text(text=full_text)])
        _sstore.save_session_history(session_id, history + [user_content, model_content], client_ip)

    logger.info(
        f"[ChatStream Done] request_id={request_id} | tools={sorted(tools_emitted)} | "
        f"chars={len(full_text)} | duration_ms={duration_ms:.1f}"
    )

    yield _sse("done", {
        "tools_used": sorted(tools_emitted),
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
