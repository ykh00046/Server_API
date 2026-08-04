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
from components.kpi_cards import kpi_row
from components.layout import (
    download_pair,
    empty_state,
    get_page_columns,
    render_ai_column,
    render_page_header,
)
from data import _cached_excel_bytes, get_filter_state, load_records


# ==========================================================
# Section 1: KPI summary cards
# ==========================================================
def _render_kpi_cards(df: pd.DataFrame) -> None:
    """Render 3-column KPI row (총 레코드 / 생산일 수 / 일 평균 배치) + spacer.

    overview 페이지와 동일한 시각 계층(bordered metric, help 툴팁)을 따른다.
    """
    unique_days = df["production_dt"].dt.date.nunique() if not df.empty else 0
    avg_daily = len(df) / max(unique_days, 1) if not df.empty else 0
    kpi_row([
        {
            "label": "총 레코드",
            "value": f"{len(df):,}건",
            "help": "선택 기간 내 생산 레코드(행) 총 건수",
        },
        {
            "label": "생산일 수",
            "value": f"{unique_days}일",
            "help": "선택 기간 중 실제 생산이 기록된 고유 일수",
        },
        {
            "label": "일 평균 배치",
            "value": f"{avg_daily:.1f}건",
            "help": "총 레코드 ÷ 생산일 수",
        },
    ])
    st.space(8)


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
    """Render Excel + CSV download buttons. display_detail reuses the renamed frame.

    Excel 은 원본 df(_cached_excel_bytes 캐시)를, CSV 는 화면과 같은 한글 헤더
    프레임을 내보낸다 — 기존 동작 그대로다.
    """
    download_pair(
        display_detail,
        _cached_excel_bytes(df),
        "production_records",
    )


# ==========================================================
# Page entry
# ==========================================================
render_page_header("배치 내역", "생산 데이터 > 배치 내역")

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
        st.warning(
            f"{bad_dt:,}개 레코드의 날짜 파싱에 문제가 있습니다.",
            icon=":material/warning:",
        )

    if df.empty:
        # 0행 상태에서 KPI·표·다운로드를 그대로 두면 빈 파일을 받게 된다.
        empty_state(
            "선택한 조건에 해당하는 생산 레코드가 없습니다.",
            hint="사이드바에서 기간을 넓히거나 제품·키워드 필터를 해제해 보세요.",
        )
    else:
        _render_kpi_cards(df)
        display_detail = _render_detail_table(df)
        _render_export_buttons(df, display_detail)

render_ai_column(col_ai)
