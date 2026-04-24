"""
Layout Components — shared layout helpers for all pages.

Provides:
- render_page_header(): Breadcrumb + AI toggle
- get_page_columns() / render_ai_column(): 2-Panel layout
- AI panel toggle state management
"""

import streamlit as st


def init_ai_panel_state() -> None:
    """Initialize AI panel toggle state."""
    if "ai_panel_open" not in st.session_state:
        st.session_state["ai_panel_open"] = False  # 기본: 닫힘 (메인 콘텐츠 우선)


def render_page_header(title: str, breadcrumb: str = "") -> None:
    """Render a page header with title and AI toggle."""
    col_title, col_toggle = st.columns([8, 2])
    with col_title:
        st.markdown(
            f"### {title}",
        )
        if breadcrumb:
            st.caption(breadcrumb)
    with col_toggle:
        is_open = st.session_state.get("ai_panel_open", False)
        btn_label = "🤖 닫기" if is_open else "🤖 열기"
        if st.button(btn_label, key=f"ai_toggle_{title}"):
            st.session_state["ai_panel_open"] = not is_open
            st.rerun()


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
