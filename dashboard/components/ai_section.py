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

try:
    import streamlit_shadcn_ui as sui
    _HAS_SHADCN = True
except ImportError:
    sui = None  # type: ignore[assignment]
    _HAS_SHADCN = False


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

STARTER_PROMPTS = [
    {
        "icon": "📊",
        "title": "이번 달 제품별 생산 현황",
        "desc": "최근 30일간 제품별 생산량, 배치 수, 점유율을 표로 정리합니다.",
        "prompt": "최근 30일간 제품별 생산량, 배치 수, 점유율(%)을 표로 정리하고 분석 코멘트도 달아줘.",
    },
    {
        "icon": "🏆",
        "title": "생산량 TOP 10 리포트",
        "desc": "올해 상위 10개 제품의 생산량·점유율·증감을 분석합니다.",
        "prompt": "올해 상위 10개 제품의 생산량, 점유율(%), 전월 대비 증감률을 표로 보여주고 주요 트렌드를 분석해 줘.",
    },
    {
        "icon": "⚖️",
        "title": "전월 대비 증감 분석",
        "desc": "이번 달과 지난 달 제품별 성과를 비교합니다.",
        "prompt": "이번 달과 지난 달의 총 생산량, 배치 수를 비교하고, 주요 제품별 증감 현황도 표로 정리해 줘.",
    },
    {
        "icon": "🔍",
        "title": "BW0021 종합 분석",
        "desc": "BW0021 제품의 월별 추이와 최근 이력을 확인합니다.",
        "prompt": "BW0021 제품의 월별 생산 추이와 최근 10건 이력을 표로 보여주고, 평균 생산량과 추세를 분석해 줘.",
    },
]


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


def _render_starter_card(idx: int, item: dict) -> str | None:
    """Render one starter prompt card. Returns the selected prompt or None."""
    title = f"{item['icon']} {item['title']}"
    if _HAS_SHADCN:
        sui.card(
            title=title,
            content=item["desc"],
            description="클릭해서 AI에게 분석을 요청하세요.",
            key=f"starter_card_{idx}",
        )
        if sui.button(
            text="이 분석 시작",
            variant="outline",
            key=f"starter_btn_{idx}",
        ):
            return item["prompt"]
        return None
    # Fallback: plain Streamlit button
    if st.button(f"{title}\n\n{item['desc']}", key=f"starter_fallback_{idx}"):
        return item["prompt"]
    return None


def render_ai_status_indicator(is_online: bool = True) -> None:
    """
    Render AI status indicator.
    """
    if is_online:
        st.badge("AI 엔진: 온라인", icon=":material/check_circle:", color="green")
    else:
        st.badge("AI 엔진: 오프라인", icon=":material/cancel:", color="red")


def render_ai_header_with_animation() -> None:
    """Render AI section header (native title + caption)."""
    st.title("생산 데이터 분석 AI", anchor=False)
    st.caption(f"Core Engine: {GEMINI_MODEL} | 2025-2026 통합 데이터")


def render_ai_chat(api_url: str | None = None) -> None:
    """
    Render professional AI chat interface with Zero-State Conversational UI.
    """
    api_url = api_url or f"{API_BASE_URL}/chat/stream"

    # Initialize chat history (Empty for True Zero-State)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_container = None  # Set when active chat is rendered

    # ==========================================
    # 1. Zero-State UI (대화 시작 전 중앙 화면)
    # ==========================================
    if len(st.session_state.messages) == 0:
        st.space(60)
        with st.container(horizontal_alignment="center"):
            st.markdown(":material/waving_hand:")
            st.subheader("무엇을 분석해 드릴까요?", anchor=False)
            st.caption("자연어로 질문하면, 수십만 건의 데이터를 즉시 분석해 표와 차트로 답변합니다.")
        st.space(24)

        # Starter card button sizing CSS lives in theme.py (_STARTER_CARD_CSS)

        col1, col2 = st.columns(2)
        prompt_clicked: str | None = None
        for idx, item in enumerate(STARTER_PROMPTS):
            with (col1 if idx % 2 == 0 else col2):
                chosen = _render_starter_card(idx, item)
                if chosen:
                    prompt_clicked = chosen

        if prompt_clicked:
            st.session_state.messages.append({"role": "user", "content": prompt_clicked})
            st.rerun()

        # Fill remaining space so input stays at bottom
        st.space(150)

    # ==========================================
    # 2. Active Chat UI (대화 진행 중)
    # ==========================================
    else:
        # Context hint
        st.caption(
            ":material/lightbulb: 팁: '표로 정리해줘'라고 질문하면 데이터를 "
            "엑셀로 다운로드할 수 있습니다.",
            text_alignment="right",
        )

        # Chat container
        chat_container = st.container(height=500)

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
                        _render_table_download(content, "dl_ai_table", i)

    # ==========================================
    # 3. Input & Processing (공통)
    # ==========================================
    prompt = st.chat_input("데이터에 대해 무엇이든 질문하세요 (예: 올해 1분기 총 생산량은?)", key="full_chat_input")

    if prompt and (
        len(st.session_state.messages) == 0
        or st.session_state.messages[-1]["content"] != prompt
    ):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

    _process_pending_user_message(chat_container, api_url)

    # Clear chat button (Only in Active Chat UI)
    if len(st.session_state.messages) > 0:
        st.markdown("")  # spacer
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("새로운 대화 시작", icon=":material/add_comment:", help="대화 기록을 지우고 초기 화면으로 돌아갑니다."):
                _reset_chat()
                st.rerun()


def render_ai_section(api_url: str | None = None) -> None:
    """
    Render complete AI analysis section (full-width, for dedicated AI page).

    Base message/table/download styling is centralized in
    `shared/ui/theme.apply_custom_css()` via CSS tokens.
    Role-specific accents (user vs assistant) remain here since they
    depend on DOM attributes that the centralized rules do not target.
    """
    api_url = api_url or f"{API_BASE_URL}/chat/stream"

    # Chat role CSS is in theme.py _BASE_RULES

    # Header and Status
    col_h, col_s = st.columns([3, 1])
    with col_h:
        render_ai_header_with_animation()
    with col_s:
        st.write("") # Padding
        st.write("")
        render_ai_status_indicator(is_online=True)
    
    st.divider()
    render_ai_chat(api_url)


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

    Differences from full render_ai_section:
    - Smaller header (no large gradient text)
    - Quick prompt chips instead of starter cards
    - Height-constrained chat container (400px)
    - No full-page zero-state UI
    """
    api_url = api_url or f"{API_BASE_URL}/chat/stream"

    # Chat role CSS is in theme.py _BASE_RULES

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
