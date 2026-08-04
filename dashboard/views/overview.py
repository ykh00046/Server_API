"""
종합 현황 (Overview) — Main dashboard page.

Shows:
- KPI cards (4-column, B3 style)
- Chart row 1 (2-col: monthly trend + top 10)
- Chart row 2 (2-col: distribution + recent records)
- Always-visible AI panel (right column, toggleable)

Refactored 2026-04-24 (dashboard-pages-refactor cycle): page body decomposed into
three `_render_*` helpers. Module top-level remains the Streamlit entry script
(executed top-to-bottom on each rerun) and only orchestrates load + setup + section calls.
"""

import plotly.graph_objects as go
import streamlit as st
from components import (
    calculate_kpis,
    create_distribution_pie,
    get_avg_batch_sparkline,
    get_batch_count_sparkline,
    get_chart_config,
    get_sparkline_data,
    render_kpi_cards,
    render_last_update,
)
from components.charts import LEGEND_TOP, create_top10_bar_chart
from components.layout import (
    empty_state,
    get_page_columns,
    render_ai_column,
    render_page_header,
    section_header,
)
from data import get_filter_state, load_monthly_summary, load_records
from plotly.subplots import make_subplots

from shared.ui.theme import get_colors


# ==========================================================
# Section 1: KPI cards
# ==========================================================
def _render_kpi_section(df, date_from, date_to, colors) -> None:
    """Render 4-column KPI cards (총 생산량 / 배치 수 / 평균 / Top 제품) + spacer."""
    kpis = calculate_kpis(df, date_from, date_to)
    render_kpi_cards(
        kpis, colors,
        sparkline_data=get_sparkline_data(df),
        batch_sparkline=get_batch_count_sparkline(df),
        avg_batch_sparkline=get_avg_batch_sparkline(df),
    )
    st.space(8)


# ==========================================================
# Section 2: Chart row 1 — Monthly trend + Top 10
# ==========================================================
def _render_chart_row_1(df, date_from, date_to, db_ver, chart_template, colors) -> None:
    """Render dual-axis monthly trend (left col) + Top 10 bar (right col)."""
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        section_header("월별 생산 추세", ":material/trending_up:")
        summary_df = load_monthly_summary(date_from, date_to, db_ver=db_ver)
        if len(summary_df) > 0:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Bar(
                    x=summary_df["year_month"],
                    y=summary_df["total_production"],
                    name="총 생산량",
                    marker_color=colors["primary"],
                ),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=summary_df["year_month"],
                    y=summary_df["batch_count"],
                    name="배치 수",
                    mode="lines+markers",
                    line=dict(color=colors["secondary"], width=3),
                ),
                secondary_y=True,
            )
            fig.update_layout(
                hovermode="x unified",
                template=chart_template,
                height=360,
                margin=dict(l=40, r=40, t=30, b=40),
                legend=LEGEND_TOP,
                xaxis_type="category",
            )
            fig.update_yaxes(title_text="생산량", secondary_y=False)
            fig.update_yaxes(title_text="배치 수", secondary_y=True)
            st.plotly_chart(fig, width="stretch", config=get_chart_config("monthly_trend"))
        else:
            empty_state(
                "해당 기간의 월별 추세 데이터가 없습니다.",
                hint="사이드바에서 기간/제품 필터를 조정해 보세요.",
            )

    with chart_col2:
        section_header("Top 10 제품별 생산량", ":material/leaderboard:")
        fig_bar = create_top10_bar_chart(df, chart_template, marker_color=colors["primary"])
        fig_bar.update_layout(height=360, margin=dict(l=80, r=20, t=30, b=40))
        st.plotly_chart(fig_bar, width="stretch", config=get_chart_config("top10"))


# ==========================================================
# Section 3: Chart row 2 — Distribution + Recent summary
# ==========================================================
def _render_chart_row_2(df, chart_template) -> None:
    """Render production distribution donut (left) + recent summary table (right)."""
    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        section_header("생산 분포", ":material/donut_small:")
        fig_pie = create_distribution_pie(df, chart_template)
        fig_pie.update_layout(height=340, margin=dict(l=20, r=20, t=30, b=40))
        st.plotly_chart(fig_pie, width="stretch", config=get_chart_config("distribution"))

    with chart_col4:
        section_header("최근 현황 요약", ":material/table_chart:")
        if not df.empty:
            recent = df.head(7)[
                ["production_date", "item_code", "item_name", "good_quantity"]
            ].copy()
            recent["production_date"] = df.head(7)["production_dt"].dt.strftime("%Y-%m-%d")
            recent = recent.rename(columns={
                "production_date": "생산일",
                "item_code": "코드",
                "item_name": "제품명",
                "good_quantity": "양품수량",
            })
            st.dataframe(recent, width="stretch", hide_index=True, height=340)
        else:
            empty_state(
                "최근 현황 요약 데이터가 없습니다.",
                hint="데이터가 수집되면 최근 7건이 여기 표시됩니다.",
            )


# ==========================================================
# Page entry
# ==========================================================
render_page_header("종합 현황", "대시보드 > 종합 현황")

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
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")

    _render_kpi_section(df, date_from, date_to, colors)
    _render_chart_row_1(df, date_from, date_to, db_ver, chart_template, colors)
    _render_chart_row_2(df, chart_template)

    render_last_update()

render_ai_column(col_ai)
