"""
제품 비교 (Products) — Product comparison analysis page.

Shows:
- Top 10 bar chart + Distribution pie (2-col)
- Product trend comparison (multi-select, multi-line)
"""

import streamlit as st

from data import get_filter_state, load_records, load_item_list
from components import (
    create_top10_bar_chart,
    create_distribution_pie,
    create_trend_lines,
    get_chart_config,
)
from components.layout import render_page_header, get_page_columns, render_ai_column
from shared.ui.theme import get_colors

# Page header
render_page_header("제품별 분석", "생산 관리 > 제품별 분석")

# Get filter state
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
    df, _ = load_records(item_codes, keyword, date_from, date_to, limit, db_ver=db_ver)
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")

    # Chart row: Top 10 + Distribution
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("**🏆 Top 10 제품**")
        fig_bar = create_top10_bar_chart(df, chart_template)
        fig_bar.update_layout(height=350, margin=dict(l=80, r=20, t=30, b=40))
        st.plotly_chart(
            fig_bar, use_container_width=True, config=get_chart_config("top10_products")
        )

    with chart_col2:
        st.markdown("**🍩 생산 분포**")
        fig_pie = create_distribution_pie(df, chart_template)
        fig_pie.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=40))
        st.plotly_chart(
            fig_pie,
            use_container_width=True,
            config=get_chart_config("product_distribution"),
        )

    # Product trend comparison
    st.divider()
    st.markdown("**📈 제품 추세 비교**")

    items_df = load_item_list(db_ver=db_ver)
    if not items_df.empty:
        compare_options = items_df["item_code"].tolist()
        selected_compare = st.multiselect(
            "비교할 제품 선택 (최대 5개)",
            options=compare_options,
            max_selections=5,
            help="2-5개 제품을 선택하여 생산 추세를 비교하세요",
        )

        if selected_compare:
            trend_agg = st.segmented_control(
                "추세 집계 단위",
                options=["일별", "주별", "월별"],
                default="월별",
                key="product_trend_agg",
            )

            fig_trend = create_trend_lines(df, selected_compare, trend_agg, chart_template)
            fig_trend.update_layout(height=400)
            st.plotly_chart(
                fig_trend,
                use_container_width=True,
                config=get_chart_config("product_trends"),
            )
        else:
            st.info("위에서 제품을 선택하면 추세 비교가 표시됩니다.")
    else:
        st.info("비교할 제품이 없습니다.")

# AI panel
render_ai_column(col_ai)
