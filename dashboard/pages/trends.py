"""
생산 추세 (Trends) — Production trend analysis page.

Shows daily/weekly/monthly production trends with aggregation toggle.
Uses st.segmented_control for aggregation unit selection.
"""

import streamlit as st
from plotly.subplots import make_subplots
import plotly.graph_objects as go

from data import (
    get_filter_state,
    load_daily_summary,
    load_weekly_summary,
    load_monthly_summary,
)
from components import get_chart_config
from components.layout import render_page_header, get_page_columns, render_ai_column
from shared.ui.theme import get_colors

# Page header
render_page_header("생산 추세", "대시보드 > 생산 추세")

# Get filter state
fs = get_filter_state()
date_from = fs["date_from"]
date_to = fs["date_to"]
db_ver = fs["db_ver"]

# 2-Panel layout
col_main, col_ai = get_page_columns()

with col_main:
    # Aggregation unit selector (segmented control)
    agg_unit = st.segmented_control(
        "집계 단위",
        options=["일별", "주별", "월별"],
        default="월별",
        key="trend_agg_unit",
    )

    # Load appropriate data
    if agg_unit == "일별":
        summary_df = load_daily_summary(date_from, date_to, db_ver=db_ver)
        x_col = "production_day"
    elif agg_unit == "주별":
        summary_df = load_weekly_summary(date_from, date_to, db_ver=db_ver)
        x_col = "year_week"
    else:  # 월별
        summary_df = load_monthly_summary(date_from, date_to, db_ver=db_ver)
        x_col = "year_month"

    if len(summary_df) == 0:
        st.info("선택한 기간에 데이터가 없습니다.")
    else:
        colors = get_colors()
        chart_template = colors.get("chart_template", "plotly_white")

        # Main trend chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=summary_df[x_col],
                y=summary_df["total_production"],
                name="총 생산량",
                marker_color="#ec4899",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=summary_df[x_col],
                y=summary_df["batch_count"],
                name="배치 수",
                mode="lines+markers",
                line=dict(color="#0ea5e9", width=3),
            ),
            secondary_y=True,
        )

        fig.update_layout(
            title_text=f"{agg_unit} 생산 추세",
            hovermode="x unified",
            template=chart_template,
            height=400,
            margin=dict(l=50, r=50, t=50, b=50),
            xaxis_type="category",
        )
        fig.update_yaxes(title_text="생산량 (개)", secondary_y=False)
        fig.update_yaxes(title_text="배치 수", secondary_y=True)

        st.plotly_chart(
            fig, use_container_width=True,
            config=get_chart_config(f"trends_{agg_unit}"),
        )

        # Summary table
        col_rename = {
            "year_month": "연월",
            "production_day": "생산일",
            "year_week": "주차",
            "total_production": "총 생산량",
            "batch_count": "배치 수",
            "avg_batch_size": "평균 배치 크기",
        }
        display_summary = summary_df.rename(columns=col_rename)
        if "평균 배치 크기" in display_summary.columns:
            display_summary["평균 배치 크기"] = display_summary["평균 배치 크기"].round(1)
        st.dataframe(display_summary, use_container_width=True, hide_index=True)

# AI panel
render_ai_column(col_ai)
