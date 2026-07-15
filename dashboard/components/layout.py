"""
Layout Components — shared layout helpers for all pages.

Provides:
- page_header(): 통일 페이지 헤더 (제목 + 한 줄 캡션 + 구분선) — 모든 뷰 공용.
- empty_state(): 빈 결과/로딩 대체 안내 (메시지 + 다음 행동 힌트) — 전 뷰 공용.
- render_page_header(): page_header + AI 패널 토글 (AI 컬럼을 쓰는 뷰 전용).
- get_page_columns() / render_ai_column(): 2-Panel layout
"""

import streamlit as st


def init_ai_panel_state() -> None:
    """Initialize AI panel toggle state."""
    if "ai_panel_open" not in st.session_state:
        st.session_state["ai_panel_open"] = False  # 기본: 닫힘 (메인 콘텐츠 우선)


def page_header(title: str, caption: str = "", icon: str | None = None) -> None:
    """통일된 페이지 헤더: 제목(아이콘 옵션) + 한 줄 캡션 + 구분선.

    모든 뷰(overview/trends/batches/products/materials/binder/webhooks/anomaly)가
    동일한 헤더 패턴을 갖도록 한다. 색상·타이포는 config.toml 테마에 맡긴다
    (st.title/st.caption 은 네이티브 테이밍을 따르므로 라이트/다크 모두 깨지지 않는다).

    Args:
        title: 페이지 제목 텍스트 (아이콘은 별도 icon 인자로 전달).
        caption: 제목 아래 한 줄 설명. 빈 문자열이면 캡션 미출력.
        icon: ':material/...:' 토큰. 주면 제목 앞에 붙인다.
    """
    heading = f"{icon} {title}" if icon else title
    st.title(heading, anchor=False)
    if caption:
        st.caption(caption)
    st.divider()


def empty_state(message: str, hint: str | None = None, icon: str = ":material/inbox:") -> None:
    """데이터 없음/빈 결과의 통일 안내 상태.

    st.info 메시지 + (선택) 다음 행동 힌트 캡션을 함께 보여준다.
    단순 st.info("데이터가 없습니다.") 대신 "왜 비었는지 + 무엇을 해볼 수 있는지"를
    주기 위한 공용 헬퍼. unsafe_allow_html 없이 네이티브 위젯만 사용한다.

    Args:
        message: 빈 상태의 핵심 안내 문구.
        hint: 사용자가 시도해볼 다음 행동 제안. None 이면 힌트 줄 생략.
        icon: 안내에 쓸 material 아이콘 토큰 (기본: inbox).
    """
    st.info(message, icon=icon)
    if hint:
        st.caption(f"다음: {hint}")


def render_page_header(title: str, breadcrumb: str = "") -> None:
    """AI 토글이 포함된 페이지 헤더 (AI 컬럼을 사용하는 뷰 전용).

    page_header 의 시각적 패턴(제목+캡션+구분선)을 따르되, AI 패널 토글 버튼을
    제목 행의 별도 컬럼에 함께 렌더한 뒤 구분선으로 마무리한다.
    """
    col_title, col_toggle = st.columns([8, 2])
    with col_title:
        st.markdown(f"### {title}")
        if breadcrumb:
            st.caption(breadcrumb)
    with col_toggle:
        is_open = st.session_state.get("ai_panel_open", False)
        btn_label = "AI 닫기" if is_open else "AI 열기"
        if st.button(btn_label, icon=":material/smart_toy:", key=f"ai_toggle_{title}"):
            st.session_state["ai_panel_open"] = not is_open
            st.rerun()
    st.divider()


def get_page_columns():
    """Get main and AI columns based on AI panel state.

    Returns:
        (col_main, col_ai) or (container, None)
    """
    if st.session_state.get("ai_panel_open", False):
        col_main, col_ai = st.columns([7, 3])
        return col_main, col_ai
    else:
        return st.container(), None


def render_ai_column(col_ai) -> None:
    """Render AI panel in the provided column."""
    if col_ai is None:
        return
    with col_ai:
        from components.ai_section import render_ai_section_compact
        render_ai_section_compact()
