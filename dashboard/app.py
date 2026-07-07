"""
Production Data Hub — Main Entry Point.

B3 Sidebar UI: st.navigation multi-page with sidebar filters.
Pages are loaded from the dashboard/views/ directory.

NOTE(nav-routing-fix-v1): the directory is deliberately NOT named "pages/" —
a directory of that name (even empty) flips Streamlit's legacy v1 multipage
flag (PagesManager.uses_pages_directory) and cold-session deep links would
then bypass st.navigation and this script entirely (no sidebar/filters).
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from components import apply_pending_preset, init_presets, render_preset_manager
from components.layout import init_ai_panel_state
from data import get_db_mtime, load_item_list, run_self_check

from shared.ui.responsive import apply_responsive_css
from shared.ui.theme import (
    apply_custom_css,
    init_theme,
    render_theme_toggle,
)

# ==========================================================
# Page Configuration
# ==========================================================
st.set_page_config(
    page_title="생산 데이터 허브",
    layout="wide",
    page_icon=":material/factory:",
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
    st.error(f"시스템 초기화 실패: {check_msg}", icon=":material/error:")
    st.stop()
elif check_msg:
    st.warning(check_msg)

# ==========================================================
# Navigation (st.navigation + st.Page)
# ==========================================================
pages = {
    "대시보드": [
        st.Page("views/overview.py", title="종합 현황", icon=":material/dashboard:", default=True),
        st.Page("views/trends.py", title="생산 추세", icon=":material/trending_up:"),
    ],
    "생산 관리": [
        st.Page("views/batches.py", title="배치 내역", icon=":material/list_alt:"),
        st.Page("views/products.py", title="제품별 분석", icon=":material/inventory_2:"),
    ],
    "자재": [
        st.Page("views/materials.py", title="자재요청", icon=":material/receipt_long:"),
        st.Page("views/binder.py", title="액상바인더출고", icon=":material/water_drop:"),
    ],
    "운영": [
        st.Page("views/webhooks.py", title="Webhook 관리", icon=":material/notifications:"),
    ],
}

nav = st.navigation(pages)

# ==========================================================
# Sidebar: Logo + Filters (rendered BEFORE nav.run())
# ==========================================================
with st.sidebar:
    # Logo area
    st.markdown("### :material/factory: 생산 데이터 허브")
    st.caption("Production Data Hub")

    # Filters section
    st.markdown("#### :material/filter_list: 검색 필터")

    current_db_ver = get_db_mtime()

    items_df = load_item_list(db_ver=current_db_ver)
    labels = items_df["label"].tolist()
    label_to_code = dict(zip(labels, items_df["item_code"].tolist(), strict=True))

    # Preset 적용 값을 위젯 생성 전에 flt_* 세션 키로 주입 (생성 후엔 금지)
    apply_pending_preset({code: label for label, code in label_to_code.items()})

    today = date.today()
    st.session_state.setdefault("flt_limit", 5000)
    st.session_state.setdefault("flt_keyword", "")
    st.session_state.setdefault("flt_dates", (today - timedelta(days=90), today))
    st.session_state.setdefault("flt_products", [])
    # DB 교체로 사라진 제품 라벨이 남아 있으면 multiselect가 죽는다
    _label_set = set(labels)
    st.session_state["flt_products"] = [
        x for x in st.session_state["flt_products"] if x in _label_set
    ]

    limit = st.slider(
        "최대 레코드 수", min_value=500, max_value=50000, step=500, key="flt_limit"
    )
    keyword = st.text_input("키워드 (코드/명칭/LOT)", key="flt_keyword").strip() or None

    date_range = st.date_input("날짜 범위 (생산일)", key="flt_dates")
    date_from, date_to = None, None
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        date_from, date_to = date_range[0], date_range[1]

    selected_labels = st.multiselect("제품 선택", options=labels, key="flt_products")
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

    # Preset manager — 적용은 _pending_preset 큐잉 + rerun으로 위 flt_* 키에 반영
    render_preset_manager(
        current_item_codes=item_codes,
        current_date_from=date_from,
        current_date_to=date_to,
        current_keyword=keyword,
        current_limit=limit,
    )

    if st.button("새로고침", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    # Theme hint (native light/dark toggle lives in the settings menu)
    render_theme_toggle()

# ==========================================================
# Run Selected Page
# ==========================================================
nav.run()
