"""
Production Data Hub — Main Entry Point.

B3 Sidebar UI: st.navigation multi-page with sidebar filters.
Pages are loaded from dashboard/pages/ directory.
"""

import sys
from pathlib import Path
from datetime import date, timedelta

import streamlit as st

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data import get_db_mtime, load_item_list, run_self_check
from shared.ui.theme import (
    init_theme,
    render_theme_toggle,
    apply_custom_css,
)
from shared.ui.responsive import apply_responsive_css
from components import init_presets, render_preset_manager
from components.layout import init_ai_panel_state

# ==========================================================
# Page Configuration
# ==========================================================
st.set_page_config(
    page_title="생산 데이터 허브",
    layout="wide",
    page_icon="🏭",
    initial_sidebar_state="expanded",
)

# ==========================================================
# Theme and UI Initialization
# ==========================================================
init_theme()
apply_responsive_css()
apply_custom_css()
init_presets()
init_ai_panel_state()

# ==========================================================
# Self-Check
# ==========================================================
check_ok, check_msg = run_self_check()
if not check_ok:
    st.error(f"🚨 시스템 초기화 실패: {check_msg}")
    st.stop()
elif check_msg:
    st.warning(check_msg)

# ==========================================================
# Navigation (st.navigation + st.Page)
# ==========================================================
pages = {
    "대시보드": [
        st.Page("pages/overview.py", title="종합 현황", icon="📊", default=True),
        st.Page("pages/trends.py", title="생산 추세", icon="📈"),
    ],
    "생산 관리": [
        st.Page("pages/batches.py", title="배치 내역", icon="📋"),
        st.Page("pages/products.py", title="제품별 분석", icon="📦"),
    ],
}

nav = st.navigation(pages)

# ==========================================================
# Sidebar: Logo + Filters (rendered BEFORE nav.run())
# ==========================================================
with st.sidebar:
    # Logo area
    st.markdown(
        '<div class="bkit-sidebar-logo">'
        '<div class="bkit-title">🏭 생산 데이터 허브</div>'
        '<div class="bkit-subtitle">Production Data Hub</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Filters section
    st.markdown("#### 🔍 검색 필터")

    current_db_ver = get_db_mtime()

    limit = st.slider("최대 레코드 수", 500, 50000, 5000, 500)
    keyword = st.text_input("키워드 (코드/명칭/LOT)", value="").strip() or None

    today = date.today()
    date_range = st.date_input(
        "날짜 범위 (생산일)", value=(today - timedelta(days=90), today)
    )
    date_from, date_to = None, None
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        date_from, date_to = date_range[0], date_range[1]

    items_df = load_item_list(db_ver=current_db_ver)
    labels = items_df["label"].tolist()
    label_to_code = dict(zip(labels, items_df["item_code"].tolist()))
    selected_labels = st.multiselect("제품 선택", options=labels, default=[])
    item_codes = (
        [label_to_code[x] for x in selected_labels] if selected_labels else None
    )

    # Store filter state in session_state for pages to access
    st.session_state["_filters"] = {
        "item_codes": item_codes,
        "keyword": keyword,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
    }

    # Preset manager
    loaded_preset = render_preset_manager(
        current_item_codes=item_codes,
        current_date_from=date_from,
        current_date_to=date_to,
        current_keyword=keyword,
        current_limit=limit,
    )
    if loaded_preset:
        st.info("프리셋 로드됨. 필터 조정 후 새로고침하세요.")

    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # Theme toggle
    render_theme_toggle()

# ==========================================================
# Run Selected Page
# ==========================================================
nav.run()
