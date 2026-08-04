"""
AI Section Component - Enhanced AI Analysis interface.

Features:
- Status indicator
- Smart insights cards
- Enhanced chat UI with Zero-State layout
- Excel download from AI tables
"""

import io
import time
import uuid
from collections.abc import Iterator

import httpx
import pandas as pd
import streamlit as st

from shared.api_client import auth_headers
from shared.config import API_BASE_URL, GEMINI_MODEL

from ._parsing import parse_markdown_table, parse_sse_events

# Structured error code → user-facing Korean message mapping
_ERROR_MESSAGES = {
    "ai_disabled": "AI 엔진이 비활성화되어 있습니다.",
    "timeout": "AI 응답 시간이 초과되었습니다. 짧은 질문으로 다시 시도해 주세요.",
    "model_error": "AI 모델 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "rate_limited": "요청이 너무 많습니다. 1분 후 다시 시도해 주세요.",
    "internal": "내부 오류가 발생했습니다. 관리자에게 문의하세요.",
}

_MAX_RETRIES = 1
_RETRY_DELAY_SEC = 2.0


def _get_session_id() -> str:
    """Client-generated multi-turn session id. The server never mints one —
    it persists history only under the id the client sends, so sending None
    every turn (the pre-fix behavior) silently disabled multi-turn context."""
    if "chat_session_id" not in st.session_state:
        st.session_state["chat_session_id"] = str(uuid.uuid4())
    return st.session_state["chat_session_id"]


def _reset_chat() -> None:
    """Clear history AND rotate the server-side session id — keeping the old
    id would make the next question answer with the previous conversation."""
    st.session_state.messages = []
    st.session_state["chat_session_id"] = str(uuid.uuid4())

def _stream_chat_tokens_once(stream_url: str, payload: dict) -> Iterator[str]:
    """Single-attempt SSE stream consumer.

    Raises httpx.ConnectError or httpx.ReadTimeout on connection/timeout issues.
    Other errors are handled internally (st.error shown, no raise).

    Side effects:
    - st.toast on `tool_call` events
    - st.error on `error` events
    - st.session_state["_last_chat_meta"] populated on `done`
    """
    with httpx.stream(
        "POST", stream_url, json=payload, timeout=60.0, headers=auth_headers()
    ) as r:
        if r.status_code != 200:
            try:
                detail = r.read().decode("utf-8", "replace")
            except (httpx.HTTPError, UnicodeDecodeError, OSError):
                detail = ""
            st.error(f"스트리밍 요청 실패: HTTP {r.status_code} {detail[:200]}")
            return
        for event_name, data in parse_sse_events(r.iter_lines()):
            if event_name == "token":
                yield data.get("text", "")
            elif event_name == "tool_call":
                st.toast(data.get("name", ""), icon=":material/build:")
            elif event_name == "error":
                code = data.get("code", "internal")
                msg = _ERROR_MESSAGES.get(code, data.get("message", "AI 스트리밍 오류"))
                st.error(msg)
                return
            elif event_name == "done":
                st.session_state["_last_chat_meta"] = data
                return


def _stream_chat_tokens(stream_url: str, payload: dict) -> Iterator[str]:
    """Yield text tokens from SSE endpoint with auto-retry on connection errors.

    Retries up to _MAX_RETRIES times on ConnectError or ReadTimeout (only if
    no tokens have been yielded yet, to prevent duplicate text).
    """
    for attempt in range(_MAX_RETRIES + 1):
        tokens_yielded = False
        try:
            for token in _stream_chat_tokens_once(stream_url, payload):
                tokens_yielded = True
                yield token
            return  # Success or handled internally
        except httpx.ConnectError:
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            st.error("AI 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요.")
        except httpx.ReadTimeout:
            if attempt < _MAX_RETRIES and not tokens_yielded:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            st.error("AI 응답 시간이 초과되었습니다. 다시 시도해 주세요.")
        except Exception as e:  # noqa: BLE001 — UI safety: 어떤 SSE 파싱/네트워크 오류도 사용자에게 토스트로 전달
            st.error(f"스트리밍 오류: {e}")
            return  # Don't retry unknown errors


def _render_table_download(content: str, key_prefix: str, index: int) -> None:
    """Render Excel download button if content contains a markdown table."""
    df = parse_markdown_table(content)
    if df is None:
        return
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="AI_Data")
        st.download_button(
            label="엑셀 다운로드",
            icon=":material/download:",
            data=output.getvalue(),
            file_name=f"ai_analysis_{index}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_{index}",
        )
    except Exception:  # noqa: BLE001 — download button은 부수적 UX, 실패해도 메인 흐름 영향 없음
        pass


def _process_pending_user_message(chat_container, api_url: str) -> None:
    """Stream AI response for the last user message. Handles rerun safely."""
    if (
        len(st.session_state.messages) == 0
        or st.session_state.messages[-1]["role"] != "user"
    ):
        return

    latest_prompt = st.session_state.messages[-1]["content"]
    target = chat_container if chat_container is not None else st.container()
    with target, st.chat_message("assistant", avatar=":material/smart_toy:"):
        payload = {
            "query": latest_prompt,
            "session_id": _get_session_id(),
        }
        full_answer = st.write_stream(_stream_chat_tokens(api_url, payload))
        if isinstance(full_answer, list):
            full_answer = "".join(str(p) for p in full_answer)
        # Always append assistant message to prevent infinite rerun (H5)
        st.session_state.messages.append(
            {"role": "assistant", "content": full_answer or "응답을 받지 못했습니다."}
        )
        st.rerun()


# ==========================================================
# Compact AI Panel (for right-side column in 2-panel layout)
# ==========================================================
QUICK_CHIPS = [
    ("이번 주 요약", "이번 주 생산 현황을 요약해 줘."),
    ("이상 감지", "최근 생산 데이터에서 이상 패턴이 있는지 확인해 줘."),
    ("전월 비교", "이번 달과 지난 달의 총 생산량, 배치 수를 비교해 줘."),
    ("TOP 5 제품", "상위 5개 제품의 생산량과 점유율을 표로 보여줘."),
]


def render_ai_section_compact(api_url: str | None = None) -> None:
    """
    Render compact AI panel for the always-visible right column.

    The former full-page variant (render_ai_section + starter cards) was
    removed as unreachable code — no view ever routed to it; this compact
    panel (quick chips, 400px chat container) is the only AI surface.
    """
    api_url = api_url or f"{API_BASE_URL}/chat/stream"

    # Compact header
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**:material/smart_toy: AI 분석 비서**")
        st.badge(GEMINI_MODEL, color="blue")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_container = None  # Set when active chat is rendered

    # Quick prompt chips (shown when no messages)
    if len(st.session_state.messages) == 0:
        with st.container(horizontal_alignment="center"):
            st.markdown(":material/chat:")
            st.caption("무엇을 분석할까요?")

        # Quick chips as buttons
        chip_clicked = None
        cols = st.columns(2)
        for idx, (label, prompt) in enumerate(QUICK_CHIPS):
            with cols[idx % 2]:
                if st.button(label, key=f"qchip_{idx}", width="stretch"):
                    chip_clicked = prompt

        if chip_clicked:
            st.session_state.messages.append({"role": "user", "content": chip_clicked})
            st.rerun()

    # Active chat
    else:
        chat_container = st.container(height=400)
        with chat_container:
            for i, message in enumerate(st.session_state.messages):
                avatar = (
                    ":material/person:" if message["role"] == "user"
                    else ":material/smart_toy:"
                )
                with st.chat_message(message["role"], avatar=avatar):
                    content = message["content"]
                    st.markdown(content, unsafe_allow_html=False)
                    if message["role"] == "assistant":
                        _render_table_download(content, "dl_compact", i)

    # Chat input
    prompt = st.chat_input("질문하세요...", key="compact_chat_input")

    if prompt and (
        len(st.session_state.messages) == 0
        or st.session_state.messages[-1]["content"] != prompt
    ):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

    _process_pending_user_message(chat_container, api_url)

    # New chat button
    if len(st.session_state.messages) > 0 and st.button(
        "새 대화", icon=":material/add_comment:", key="compact_new_chat", width="stretch"
    ):
        _reset_chat()
        st.rerun()
