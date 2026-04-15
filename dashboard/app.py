import io
import os
import re
import sys
import requests
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    DB_FILE,
    ARCHIVE_DB_FILE,
    DBRouter,
)
from shared.validators import escape_like_wildcards

# Import UI enhancement components
from shared.ui.theme import (
    init_theme,
    render_theme_toggle,
    apply_custom_css,
    get_colors,
)
from shared.ui.responsive import apply_responsive_css

from components import (
    # Loading
    show_loading_status,
    render_last_update,
    # Charts
    create_top10_bar_chart,
    create_distribution_pie,
    create_trend_lines,
    get_chart_config,
    # Presets
    init_presets,
    render_preset_manager,
    # AI Section
    render_ai_section,
)

st.set_page_config(
    page_title="Production Data Hub",
    layout="wide",
    page_icon=":factory:",
    initial_sidebar_state="collapsed"
)

# ==========================================================
# Theme and UI Initialization
# ==========================================================
init_theme()
apply_responsive_css()
render_theme_toggle()
apply_custom_css()
init_presets()


# ==========================================================
# Helpers
# ==========================================================
def get_db_mtime():
    """Get DB modification time for cache invalidation."""
    try:
        mtime = os.path.getmtime(DB_FILE)
        if ARCHIVE_DB_FILE.exists():
            archive_mtime = os.path.getmtime(ARCHIVE_DB_FILE)
            mtime = max(mtime, archive_mtime)
        return mtime
    except Exception:
        return 0


def run_self_check():
    if not DB_FILE.exists():
        return False, f"Database file not found: {DB_FILE}"
    try:
        with DBRouter.get_connection(use_archive=False) as conn:
            tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='production_records'", conn)
            if tables.empty:
                return False, "production_records table does not exist."
            columns = pd.read_sql("PRAGMA table_info(production_records)", conn)["name"].tolist()
            required = ["production_date", "item_code", "item_name", "good_quantity", "lot_number"]
            if not all(c in columns for c in required):
                return False, "Required columns are missing."
        if not ARCHIVE_DB_FILE.exists():
            return True, "Warning: Archive DB (2025) not found."
    except Exception as e:
        return False, f"DB connection check error: {e}"
    return True, ""


@st.cache_data(ttl=300)  # 5 minutes - product list rarely changes
def load_item_list(db_ver):
    with DBRouter.get_connection(use_archive=False) as conn:
        df = pd.read_sql("""
            SELECT item_code, MAX(item_name) AS item_name
            FROM production_records
            GROUP BY item_code
            ORDER BY item_code
        """, conn)
    df["label"] = df["item_code"] + " | " + df["item_name"].fillna("")
    return df


def _parse_production_dt(series: pd.Series) -> pd.Series:
    """
    Parse Korean datetime format to pandas datetime.

    Handles formats like:
    - "2026-01-20 오전 10:30:00" -> 2026-01-20 10:30:00
    - "2026-01-20 오후 02:15:00" -> 2026-01-20 14:15:00
    - "2026-01-20 오전 12:30:00" -> 2026-01-20 00:30:00 (midnight)
    - "2026-01-20 오후 12:30:00" -> 2026-01-20 12:30:00 (noon)
    - "2026-01-20 14:30:00" -> 2026-01-20 14:30:00 (24h format passthrough)
    - Also handles English "AM"/"PM" format
    """
    # Match both Korean (오전/오후) and English (AM/PM) formats
    pattern = re.compile(r"(\d{4}-\d{2}-\d{2})\s+(오전|오후|AM|PM)\s+(\d{1,2}):(\d{2}):(\d{2})")

    def convert_korean_time(val) -> str:
        """Convert Korean AM/PM format to 24-hour format."""
        if pd.isna(val):
            return val
        val_str = str(val)
        match = pattern.match(val_str)
        if not match:
            return val_str  # Return as-is for other formats (e.g., 24h format)

        date_part, ampm, hour_str, minute, second = match.groups()
        hour = int(hour_str)

        # Handle both Korean and English AM/PM
        is_am = ampm in ("오전", "AM")

        if is_am:
            # AM 12 = 00 (midnight), AM 1-11 = 1-11
            if hour == 12:
                hour = 0
        else:  # PM/오후
            # PM 12 = 12 (noon), PM 1-11 = 13-23
            if hour != 12:
                hour += 12

        return f"{date_part} {hour:02d}:{minute}:{second}"

    s = series.apply(convert_korean_time)
    dt = pd.to_datetime(s, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    dt2 = pd.to_datetime(series, errors="coerce", format="mixed")
    return dt.fillna(dt2)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


@st.cache_data(ttl=60)  # 1 minute - real-time data needed
def load_records(item_codes, keyword, date_from, date_to, limit, db_ver):
    where = []
    params = []

    # v7: SELECT column optimization (remove SELECT *)
    # Include id for stable sorting (matches api/main.py sort order)
    columns = "id, production_date, item_code, item_name, good_quantity, lot_number"

    if item_codes:
        where.append(f"item_code IN ({','.join(['?']*len(item_codes))})")
        params.extend(item_codes)
    if keyword:
        like = f"%{escape_like_wildcards(keyword)}%"
        where.append("(item_code LIKE ? OR item_name LIKE ? OR lot_number LIKE ?)")
        params.extend([like, like, like])
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    # Use DBRouter for consistent archive/live routing
    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None  # exclusive
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"

    final_sql, params_doubled = DBRouter.build_union_sql(
        select_columns=columns,
        where_clause=where_clause,
        targets=targets,
        order_by="production_date DESC, source DESC, id DESC",
        limit=int(limit),
        include_source=True,
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)

    df["good_quantity"] = pd.to_numeric(df["good_quantity"], errors="coerce")
    df["production_dt"] = _parse_production_dt(df["production_date"])
    df["production_day"] = df["production_dt"].dt.date
    df["year_month"] = df["production_dt"].dt.to_period("M").astype(str)
    bad = int(df["production_dt"].isna().sum())
    return df, bad


@st.cache_data(ttl=180)  # 3 minutes - aggregated data
def load_monthly_summary(date_from, date_to, db_ver):
    where, params = [], []
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    # Use DBRouter for consistent archive/live routing
    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None  # exclusive
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"
    
    # v8 Optimization: Use build_aggregation_sql for pre-aggregation in each DB
    final_sql, _ = DBRouter.build_aggregation_sql(
        inner_select="substr(production_date, 1, 7) AS year_month, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where=where_clause,
        outer_select="year_month, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count, AVG(total_prod/cnt) AS avg_batch_size",
        outer_group_by="year_month",
        targets=targets,
        outer_order_by="year_month"
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)
    return df


@st.cache_data(ttl=180)  # 3 minutes - daily aggregated data
def load_daily_summary(date_from, date_to, db_ver):
    """Load daily aggregated production data."""
    where, params = [], []
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"
    
    # v8 Optimization: Use build_aggregation_sql
    final_sql, _ = DBRouter.build_aggregation_sql(
        inner_select="substr(production_date, 1, 10) AS production_day, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where=where_clause,
        outer_select="production_day, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count",
        outer_group_by="production_day",
        targets=targets,
        outer_order_by="production_day"
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)
    return df


@st.cache_data(ttl=180)  # 3 minutes - weekly aggregated data
def load_weekly_summary(date_from, date_to, db_ver):
    """Load weekly aggregated production data."""
    where, params = [], []
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"
    
    # v8 Optimization: Use build_aggregation_sql
    # Use strftime for week-based grouping
    week_expr = "substr(production_date, 1, 4) || '-W' || printf('%02d', (strftime('%j', production_date) - 1) / 7 + 1)"
    
    final_sql, _ = DBRouter.build_aggregation_sql(
        inner_select=f"{week_expr} AS year_week, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where=where_clause,
        outer_select="year_week, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count",
        outer_group_by="year_week",
        targets=targets,
        outer_order_by="year_week"
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)
    return df


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


@st.cache_data(show_spinner=False)
def _cached_excel_bytes(df: pd.DataFrame) -> bytes:
    """Generate Excel bytes once per unique DataFrame (lazy, cached)."""
    return to_excel_bytes(df)


# ==========================================================
# UI Main
# ==========================================================
st.title(":factory: 생산 데이터 허브")

check_ok, check_msg = run_self_check()
if not check_ok:
    st.error(f":rotating_light: 시스템 초기화 실패: {check_msg}")
    st.stop()
elif check_msg:
    st.warning(check_msg)

current_db_ver = get_db_mtime()

# Sidebar - Search Conditions
st.sidebar.header(":mag: 검색 필터")
limit = st.sidebar.slider("최대 레코드 수", 500, 50000, 5000, 500)
keyword = st.sidebar.text_input("키워드 (코드/명칭/LOT)", value="").strip() or None

today = date.today()
date_range = st.sidebar.date_input("날짜 범위 (생산일)", value=(today - timedelta(days=90), today))
date_from, date_to = None, None
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    date_from, date_to = date_range[0], date_range[1]

items_df = load_item_list(db_ver=current_db_ver)
labels = items_df["label"].tolist()
label_to_code = dict(zip(labels, items_df["item_code"].tolist()))
selected_labels = st.sidebar.multiselect("제품 선택", options=labels, default=[])
item_codes = [label_to_code[x] for x in selected_labels] if selected_labels else None

# Filter Preset Manager - can return loaded preset values
loaded_preset = render_preset_manager(
    current_item_codes=item_codes,
    current_date_from=date_from,
    current_date_to=date_to,
    current_keyword=keyword,
    current_limit=limit
)

# Apply loaded preset values if user clicked Apply
if loaded_preset:
    # Note: In Streamlit, we can't directly set widget values.
    # The preset values are returned for informational purposes.
    # A more sophisticated implementation would use session_state
    # to control default values.
    st.sidebar.info(f"프리셋 로드됨. 필터 조정 후 새로고침하세요.")

if st.sidebar.button(":arrows_counterclockwise: 새로고침"):
    st.cache_data.clear()
    st.rerun()

# Display last update time
render_last_update()

# Tabs - AI Analysis first
tab1, tab2, tab3, tab4 = st.tabs([":robot: AI 분석", ":chart_with_upwards_trend: 추세", ":memo: 상세내역", ":bar_chart: 제품비교"])

with tab1:
    # AI Analysis Section with animation
    render_ai_section()

with tab2:
    # Aggregation unit selector
    agg_unit = st.radio(
        "집계 단위",
        options=["일별", "주별", "월별"],
        index=2,  # Default: Monthly
        horizontal=True
    )

    # Load appropriate data based on aggregation unit
    if agg_unit == "일별":
        summary_df = load_daily_summary(date_from, date_to, db_ver=current_db_ver)
        x_col = "production_day"
    elif agg_unit == "주별":
        summary_df = load_weekly_summary(date_from, date_to, db_ver=current_db_ver)
        x_col = "year_week"
    else:  # Monthly
        summary_df = load_monthly_summary(date_from, date_to, db_ver=current_db_ver)
        x_col = "year_month"

    st.subheader(f"{agg_unit} 생산량 및 배치 수")

    if len(summary_df) == 0:
        st.info("선택한 기간에 데이터가 없습니다.")
    else:
        # Get theme colors for chart template
        colors = get_colors()
        chart_template = colors.get("chart_template", "plotly_white")

        # Plotly Mixed Chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=summary_df[x_col],
                y=summary_df['total_production'],
                name="총 생산량",
                marker_color='#1f77b4'
            ),
            secondary_y=False
        )
        fig.add_trace(
            go.Scatter(
                x=summary_df[x_col],
                y=summary_df['batch_count'],
                name="배치 수",
                mode='lines+markers',
                line=dict(color='#ff7f0e', width=3)
            ),
            secondary_y=True
        )

        fig.update_layout(
            title_text=f"{agg_unit} 생산 추세",
            hovermode="x unified",
            template=chart_template
        )
        fig.update_yaxes(title_text="생산량 (개)", secondary_y=False)
        fig.update_yaxes(title_text="배치 수", secondary_y=True)

        st.plotly_chart(fig, width="stretch", config=get_chart_config(f"production_trends_{agg_unit.lower()}"))
        col_rename = {
            "year_month": "연월", "production_day": "생산일", "year_week": "주차",
            "total_production": "총 생산량", "batch_count": "배치 수", "avg_batch_size": "평균 배치 크기"
        }
        display_summary = summary_df.rename(columns=col_rename)
        if "평균 배치 크기" in display_summary.columns:
            display_summary["평균 배치 크기"] = display_summary["평균 배치 크기"].round(1)
        st.dataframe(display_summary, width="stretch", hide_index=True)

with tab3:
    # P1-2: Lazy-load records only when this tab is active
    df, bad_dt = load_records(item_codes, keyword, date_from, date_to, limit, db_ver=current_db_ver)
    if bad_dt > 0:
        st.warning(f":warning: {bad_dt:,}개 레코드의 날짜 파싱에 문제가 있습니다.")
    st.subheader(f"총 {len(df):,}개 레코드")
    display_detail = df[["production_date", "item_code", "item_name", "good_quantity", "lot_number"]].copy()
    display_detail["production_date"] = df["production_dt"].dt.strftime("%Y-%m-%d")
    display_detail = display_detail.rename(columns={
        "production_date": "생산일",
        "item_code": "제품코드",
        "item_name": "제품명",
        "good_quantity": "양품수량",
        "lot_number": "LOT 번호"
    })
    st.dataframe(display_detail, width="stretch", hide_index=True)
    st.download_button(":inbox_tray: Excel 다운로드", _cached_excel_bytes(df), "production_records.xlsx")

with tab4:
    st.subheader(":bar_chart: 제품 비교")

    # P1-2: Lazy-load records (cache hit if tab3 already loaded, free second call)
    df, _ = load_records(item_codes, keyword, date_from, date_to, limit, db_ver=current_db_ver)

    # Get theme colors for chart template
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")

    # Two columns for charts
    col_left, col_right = st.columns(2)

    with col_left:
        st.write("**Top 10 제품**")
        fig_bar = create_top10_bar_chart(df, chart_template)
        st.plotly_chart(fig_bar, width="stretch", config=get_chart_config("top10_products"))

    with col_right:
        st.write("**생산 분포**")
        fig_pie = create_distribution_pie(df, chart_template)
        st.plotly_chart(fig_pie, width="stretch", config=get_chart_config("product_distribution"))

    # Product trend comparison
    st.divider()
    st.write("**제품 추세 비교**")

    # Multi-select for products to compare
    if not items_df.empty:
        compare_options = items_df["item_code"].tolist()
        selected_compare = st.multiselect(
            "비교할 제품 선택 (최대 5개)",
            options=compare_options,
            max_selections=5,
            help="2-5개 제품을 선택하여 생산 추세를 비교하세요"
        )

        if selected_compare:
            # Aggregation unit for trend comparison
            trend_agg = st.radio(
                "추세 집계 단위",
                options=["일별", "주별", "월별"],
                index=2,
                horizontal=True,
                key="trend_agg_unit"
            )

            fig_trend = create_trend_lines(df, selected_compare, trend_agg, chart_template)
            st.plotly_chart(fig_trend, width="stretch", config=get_chart_config("product_trends"))
        else:
            st.info("위에서 제품을 선택하면 추세 비교가 표시됩니다.")
    else:
        st.info("비교할 제품이 없습니다.")
