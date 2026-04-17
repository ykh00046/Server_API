"""
종합 현황 (Overview) — Main dashboard page.

Shows:
- KPI cards (4-column, B3 style)
- Chart grid (2-col: monthly trend + top 10)
- Chart grid (3-col: product trend + distribution + gauge)
- Always-visible AI panel (right column, toggleable)
"""

import streamlit as st
from plotly.subplots import make_subplots
import plotly.graph_objects as go

from data import get_filter_state, load_records, load_monthly_summary, load_item_list
from components import (
    render_kpi_cards,
    calculate_kpis,
    get_sparkline_data,
    get_sparkline_for_top_product,
    create_top10_bar_chart,
    create_distribution_pie,
    get_chart_config,
    render_last_update,
)
from components.layout import render_page_header, get_page_columns, render_ai_column
from shared.ui.theme import get_colors

# Page header
render_page_header("종합 현황", "대시보드 > 종합 현황")

# Get filter state from session
fs = get_filter_state()
item_codes = fs["item_codes"]
keyword = fs["keyword"]
date_from = fs["date_from"]
date_to = fs["date_to"]
limit = fs["limit"]
db_ver = fs["db_ver"]

# 2-Panel layout
col_main, col_ai = get_page_columns()

with col_main:
    # Load data
    df, bad_dt = load_records(item_codes, keyword, date_from, date_to, limit, db_ver=db_ver)

    # KPI Cards
    kpis = calculate_kpis(df, date_from, date_to)
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")
    sparkline = get_sparkline_data(df)
    top_spark = get_sparkline_for_top_product(df, kpis["top_item"])

    render_kpi_cards(
        kpis, colors,
        sparkline_data=sparkline,
        batch_sparkline=sparkline,
        top_product_sparkline=top_spark,
    )

    st.markdown('<div class="bkit-spacer-8"></div>', unsafe_allow_html=True)

    # Chart row 1: Monthly trend + Top 10
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("**📈 월별 생산 추세**")
        summary_df = load_monthly_summary(date_from, date_to, db_ver=db_ver)
        if len(summary_df) > 0:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Bar(
                    x=summary_df["year_month"],
                    y=summary_df["total_production"],
                    name="총 생산량",
                    marker_color="#ec4899",
                ),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=summary_df["year_month"],
                    y=summary_df["batch_count"],
                    name="배치 수",
                    mode="lines+markers",
                    line=dict(color="#0ea5e9", width=3),
                ),
                secondary_y=True,
            )
            fig.update_layout(
                hovermode="x unified",
                template=chart_template,
                height=280,
                margin=dict(l=40, r=40, t=30, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                xaxis_type="category",
            )
            fig.update_yaxes(title_text="생산량", secondary_y=False)
            fig.update_yaxes(title_text="배치 수", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True, config=get_chart_config("monthly_trend"))
        else:
            st.info("데이터가 없습니다.")

    with chart_col2:
        st.markdown("**🏆 Top 10 제품별 생산량**")
        fig_bar = create_top10_bar_chart(df, chart_template)
        fig_bar.update_layout(height=280, margin=dict(l=80, r=20, t=30, b=40))
        st.plotly_chart(fig_bar, use_container_width=True, config=get_chart_config("top10"))

    # Chart row 2: Distribution
    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        st.markdown("**🍩 생산 분포**")
        fig_pie = create_distribution_pie(df, chart_template)
        fig_pie.update_layout(height=260, margin=dict(l=20, r=20, t=30, b=40))
        st.plotly_chart(fig_pie, use_container_width=True, config=get_chart_config("distribution"))

    with chart_col4:
        # Quick stats table
        st.markdown("**📊 최근 현황 요약**")
        if not df.empty:
            recent = df.head(7)[["production_date", "item_code", "item_name", "good_quantity"]].copy()
            recent["production_date"] = df.head(7)["production_dt"].dt.strftime("%Y-%m-%d")
            recent = recent.rename(columns={
                "production_date": "생산일",
                "item_code": "코드",
                "item_name": "제품명",
                "good_quantity": "양품수량",
            })
            st.dataframe(recent, use_container_width=True, hide_index=True, height=260)
        else:
            st.info("데이터가 없습니다.")

    render_last_update()

# AI panel
render_ai_column(col_ai)
