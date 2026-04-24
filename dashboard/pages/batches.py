"""
배치 내역 (Batches) — Detailed production records table.

Shows:
- KPI cards (총 레코드 / 생산일 수 / 일 평균 배치)
- Filterable/sortable data table
- Excel/CSV export

Refactored 2026-04-24 (dashboard-pages-refactor cycle): page body decomposed into
three `_render_*` helpers. `_render_detail_table` returns the renamed DataFrame so
`_render_export_buttons` can reuse it for CSV export without re-running the prep.
"""

import pandas as pd
import streamlit as st

from data import get_filter_state, load_records, _cached_excel_bytes
from components.layout import render_page_header, get_page_columns, render_ai_column


# ==========================================================
# Section 1: KPI summary cards
# ==========================================================
def _render_kpi_cards(df: pd.DataFrame) -> None:
    """Render 3-column KPI row (총 레코드 / 생산일 수 / 일 평균 배치) + spacer."""
    kpi1, kpi2, kpi3 = st.columns(3)
    unique_days = df["production_dt"].dt.date.nunique() if not df.empty else 0
    avg_daily = len(df) / max(unique_days, 1) if not df.empty else 0
    with kpi1:
        st.metric("총 레코드", f"{len(df):,}건")
    with kpi2:
        st.metric("생산일 수", f"{unique_days}일")
    with kpi3:
        st.metric("일 평균 배치", f"{avg_daily:.1f}건")
    st.markdown('<div class="bkit-spacer-8"></div>', unsafe_allow_html=True)


# ==========================================================
# Section 2: Detail table
# ==========================================================
def _render_detail_table(df: pd.DataFrame) -> pd.DataFrame:
    """Render the production records dataframe and return the renamed copy for reuse."""
    display_detail = df[
        ["production_date", "item_code", "item_name", "good_quantity", "lot_number"]
    ].copy()
    display_detail["production_date"] = df["production_dt"].dt.strftime("%Y-%m-%d")
    display_detail = display_detail.rename(
        columns={
            "production_date": "생산일",
            "item_code": "제품코드",
            "item_name": "제품명",
            "good_quantity": "양품수량",
            "lot_number": "LOT 번호",
        }
    )
    st.dataframe(display_detail, width="stretch", hide_index=True)
    return display_detail


# ==========================================================
# Section 3: Export buttons
# ==========================================================
def _render_export_buttons(df: pd.DataFrame, display_detail: pd.DataFrame) -> None:
    """Render Excel + CSV download buttons. display_detail reuses the renamed frame."""
    export_col1, export_col2, _ = st.columns([1, 1, 4])
    with export_col1:
        st.download_button(
            "📥 Excel 다운로드",
            _cached_excel_bytes(df),
            "production_records.xlsx",
            width="stretch",
        )
    with export_col2:
        csv_data = display_detail.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📋 CSV 다운로드",
            csv_data,
            "production_records.csv",
            mime="text/csv",
            width="stretch",
        )


# ==========================================================
# Page entry
# ==========================================================
render_page_header("배치 내역", "생산 관리 > 배치 내역")

fs = get_filter_state()
item_codes = fs["item_codes"]
keyword = fs["keyword"]
date_from = fs["date_from"]
date_to = fs["date_to"]
limit = fs["limit"]
db_ver = fs["db_ver"]

col_main, col_ai = get_page_columns()

with col_main:
    df, bad_dt = load_records(item_codes, keyword, date_from, date_to, limit, db_ver=db_ver)

    if bad_dt > 0:
        st.warning(f"⚠️ {bad_dt:,}개 레코드의 날짜 파싱에 문제가 있습니다.")

    _render_kpi_cards(df)
    display_detail = _render_detail_table(df)
    _render_export_buttons(df, display_detail)

render_ai_column(col_ai)
