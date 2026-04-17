"""
AI Section Component - Enhanced AI Analysis interface.

Features:
- Status indicator
- Smart insights cards
- Enhanced chat UI with Zero-State layout
- Excel download from AI tables
"""

import io
import json
import re
from typing import Iterator, Optional

import httpx
import pandas as pd
import streamlit as st

from shared.config import API_BASE_URL, GEMINI_MODEL

try:
    import streamlit_shadcn_ui as sui
    _HAS_SHADCN = True
except Exception:
    sui = None  # type: ignore[assignment]
    _HAS_SHADCN = False


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


def _stream_chat_tokens(stream_url: str, payload: dict) -> Iterator[str]:
    """Yield text tokens from the /chat/stream SSE endpoint.

    Side effects:
    - st.toast on `tool_call` events
    - st.error on `error` events
    - st.session_state["_last_chat_meta"] populated on `done`
    """
    try:
        with httpx.stream("POST", stream_url, json=payload, timeout=60.0) as r:
            if r.status_code != 200:
                try:
                    detail = r.read().decode("utf-8", "replace")
                except Exception:
                    detail = ""
                st.error(f"스트리밍 요청 실패: HTTP {r.status_code} {detail[:200]}")
                return
            event_name: Optional[str] = None
            for line in r.iter_lines():
                if not line:
                    event_name = None
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if event_name == "token":
                        yield data.get("text", "")
                    elif event_name == "tool_call":
                        st.toast(f"🔧 {data.get('name', '')}", icon="⚙️")
                    elif event_name == "error":
                        st.error(data.get("message", "AI 스트리밍 오류"))
                        return
                    elif event_name == "done":
                        st.session_state["_last_chat_meta"] = data
                        return
    except httpx.ConnectError:
        st.error("AI 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요.")
    except httpx.ReadTimeout:
        st.error("AI 응답 시간이 초과되었습니다. 다시 시도해 주세요.")
    except Exception as e:
        st.error(f"스트리밍 오류: {e}")


_UNSAFE_HTML_RE = re.compile(
    r"<\s*script[^>]*>.*?<\s*/\s*script\s*>|"
    r"\bon\w+\s*=\s*[\"'][^\"']*[\"']|"
    r"<\s*iframe[^>]*>|<\s*object[^>]*>|<\s*embed[^>]*>|"
    r"javascript\s*:",
    re.IGNORECASE | re.DOTALL,
)


def _sanitize_ai_content(content: str) -> str:
    """Strip dangerous HTML from AI-generated content."""
    return _UNSAFE_HTML_RE.sub("", content)


def _render_table_download(content: str, key_prefix: str, index: int) -> None:
    """Render Excel download button if content contains a markdown table."""
    if "|" not in content or "\n|" not in content:
        return
    try:
        lines = content.split("\n")
        table_lines = [
            line for line in lines if "|" in line and line.strip().startswith("|")
        ]
        if len(table_lines) <= 2:
            return
        table_text = "\n".join(table_lines).replace("**", "")
        df = pd.read_csv(
            io.StringIO(table_text.replace(" ", "")), sep="|"
        ).dropna(how="all", axis=1)
        df = df[~df.iloc[:, 0].str.contains(r"^-+$", na=False)]
        df.columns = [col.strip() for col in df.columns]
        if df.empty:
            return
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="AI_Data")
        st.download_button(
            label="📊 엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"ai_analysis_{index}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_{index}",
        )
    except Exception:
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
    with target:
        with st.chat_message("assistant", avatar="🤖"):
            payload = {
                "query": latest_prompt,
                "session_id": st.session_state.get("chat_session_id"),
            }
            full_answer = st.write_stream(_stream_chat_tokens(api_url, payload))
            if isinstance(full_answer, list):
                full_answer = "".join(str(p) for p in full_answer)
            # Always append assistant message to prevent infinite rerun (H5)
            st.session_state.messages.append(
                {"role": "assistant", "content": full_answer or "⚠️ 응답을 받지 못했습니다."}
            )
            st.rerun()


def _render_starter_card(idx: int, item: dict) -> Optional[str]:
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
    status_color = "#00aa66" if is_online else "#cc4444"
    status_text = "온라인" if is_online else "오프라인"
    status_icon = "●" if is_online else "○"

    st.markdown(
        f'<div class="bkit-flex-center">'
        f'<span class="bkit-status-dot" style="color:{status_color}">{status_icon}</span>'
        f'<span style="color:{status_color};font-weight:600">AI 엔진: {status_text}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_ai_header_with_animation() -> None:
    """Render AI section header with styling."""
    st.markdown(
        f'<div class="bkit-ai-header">'
        f'<h1>생산 데이터 분석 AI</h1>'
        f'<p>Core Engine: {GEMINI_MODEL} | 2025-2026 통합 데이터</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


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
        st.markdown(
            '<div class="bkit-zero-state">'
            '<div class="bkit-icon">👋</div>'
            '<h2>무엇을 분석해 드릴까요?</h2>'
            '<p>자연어로 질문하면, 수십만 건의 데이터를 즉시 분석해 표와 차트로 답변합니다.</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Starter card styling is in theme.py _BASE_RULES (.bkit-starter-cards)

        col1, col2 = st.columns(2)
        prompt_clicked: Optional[str] = None
        for idx, item in enumerate(STARTER_PROMPTS):
            with (col1 if idx % 2 == 0 else col2):
                chosen = _render_starter_card(idx, item)
                if chosen:
                    prompt_clicked = chosen

        if prompt_clicked:
            st.session_state.messages.append({"role": "user", "content": prompt_clicked})
            st.rerun()

        # Fill remaining space so input stays at bottom
        st.markdown("<div style='height:150px'></div>", unsafe_allow_html=True)

    # ==========================================
    # 2. Active Chat UI (대화 진행 중)
    # ==========================================
    else:
        # Context Hint Badge
        st.markdown(
            '<div class="bkit-hint-badge">'
            '<span>💡 팁: \'표로 정리해줘\'라고 질문하면 데이터를 엑셀로 다운로드할 수 있습니다.</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Chat container
        chat_container = st.container(height=500)

        with chat_container:
            for i, message in enumerate(st.session_state.messages):
                avatar = "👤" if message["role"] == "user" else "🤖"
                with st.chat_message(message["role"], avatar=avatar):
                    content = _sanitize_ai_content(message["content"])
                    st.markdown(content)
                    if message["role"] == "assistant":
                        _render_table_download(content, "dl_ai_table", i)

    # ==========================================
    # 3. Input & Processing (공통)
    # ==========================================
    prompt = st.chat_input("데이터에 대해 무엇이든 질문하세요 (예: 올해 1분기 총 생산량은?)")

    if prompt:
        if len(st.session_state.messages) == 0 or st.session_state.messages[-1]["content"] != prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.rerun()

    _process_pending_user_message(chat_container, api_url)

    # Clear chat button (Only in Active Chat UI)
    if len(st.session_state.messages) > 0:
        st.markdown("")  # spacer
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("새로운 대화 시작", icon="✨", help="대화 기록을 지우고 초기 화면으로 돌아갑니다."):
                st.session_state.messages = []
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
    st.markdown(
        f'<div class="bkit-gradient-header">'
        f'<span style="font-size:0.9rem;font-weight:700">🤖 AI 분석 비서</span>'
        f'<span class="bkit-model-tag">{GEMINI_MODEL}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_container = None  # Set when active chat is rendered

    # Quick prompt chips (shown when no messages)
    if len(st.session_state.messages) == 0:
        st.markdown(
            '<div class="bkit-compact-zero-state">'
            '<div class="bkit-icon">💬</div>'
            '<p>무엇을 분석할까요?</p>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Quick chips as buttons
        chip_clicked = None
        cols = st.columns(2)
        for idx, (label, prompt) in enumerate(QUICK_CHIPS):
            with cols[idx % 2]:
                if st.button(label, key=f"qchip_{idx}", use_container_width=True):
                    chip_clicked = prompt

        if chip_clicked:
            st.session_state.messages.append({"role": "user", "content": chip_clicked})
            st.rerun()

    # Active chat
    else:
        chat_container = st.container(height=400)
        with chat_container:
            for i, message in enumerate(st.session_state.messages):
                avatar = "👤" if message["role"] == "user" else "🤖"
                with st.chat_message(message["role"], avatar=avatar):
                    content = _sanitize_ai_content(message["content"])
                    st.markdown(content)
                    if message["role"] == "assistant":
                        _render_table_download(content, "dl_compact", i)

    # Chat input
    prompt = st.chat_input("질문하세요...", key="compact_chat_input")

    if prompt:
        if len(st.session_state.messages) == 0 or st.session_state.messages[-1]["content"] != prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.rerun()

    _process_pending_user_message(chat_container, api_url)

    # New chat button
    if len(st.session_state.messages) > 0:
        if st.button("✨ 새 대화", key="compact_new_chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
