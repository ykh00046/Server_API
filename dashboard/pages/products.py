"""
제품별 분석 (Products) — Product category drill-down analysis page.

Replaces the previous duplicate chart layout with:
- Product category overview (AS/AC/AW/기타 classification)
- Category-level KPI metrics
- Per-product drill-down with monthly trend and recent batches
- Cross-product trend comparison

Refactored 2026-04-23 (products-refactor cycle): page body decomposed into
five `_render_*` helpers. The module top-level remains the Streamlit entry
script (executed top-to-bottom on each rerun) and only orchestrates load +
classification + section calls.
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from data import get_filter_state, load_records, load_item_list
from components import (
    create_trend_lines,
    get_chart_config,
)
from components.layout import render_page_header, get_page_columns, render_ai_column
from shared.ui.theme import get_colors

# ==========================================================
# Product Category Classification
# ==========================================================
PRODUCT_CATEGORIES = {
    "AS": {"label": "AS (어셈블리)", "icon": "🔩", "color": "#ec4899"},
    "AC": {"label": "AC (악세사리)", "icon": "💎", "color": "#0ea5e9"},
    "AW": {"label": "AW (조립완성)", "icon": "📦", "color": "#f43f5e"},
}


def _classify_item_code(code: str) -> str:
    """Classify item_code by its prefix (AS, AC, AW, or 기타)."""
    prefix = str(code)[:2].upper()
    if prefix in PRODUCT_CATEGORIES:
        return prefix
    return "기타"


def _get_category_info(cat: str) -> dict:
    """Get display info for a category."""
    return PRODUCT_CATEGORIES.get(cat, {"label": f"기타 ({cat})", "icon": "📋", "color": "#94a3b8"})


# ==========================================================
# Section 1: Category Overview KPIs
# ==========================================================
def _render_category_kpis(cat_summary: pd.DataFrame, num_cats: int) -> None:
    """Render category-level KPI cards (one per detected category)."""
    kpi_cols = st.columns(max(num_cats, 1))
    for i, row in cat_summary.iterrows():
        cat_info = _get_category_info(row["category"])
        with kpi_cols[i % num_cats]:
            st.markdown(
                f'<div class="bkit-kpi-card">'
                f'<div class="bkit-kpi-bar" style="background:{cat_info["color"]}"></div>'
                f'<div class="bkit-kpi-header">'
                f'<span class="bkit-kpi-label">{cat_info["label"]}</span>'
                f'<span class="bkit-kpi-icon" style="background:rgba(0,0,0,0.03)">{cat_info["icon"]}</span>'
                f'</div>'
                f'<div class="bkit-kpi-value">{row["total_qty"]:,.0f}</div>'
                f'<div style="display:flex;justify-content:space-between;font-size:0.8rem;color:var(--color-text-muted, #64748b);margin-top:4px;">'
                f'<span>{row["batch_count"]:,}배치</span>'
                f'<span>{row["product_count"]}품목</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ==========================================================
# Section 2: Category Distribution Charts
# ==========================================================
def _render_distribution_charts(
    df: pd.DataFrame,
    cat_summary: pd.DataFrame,
    categories_present: list,
    chart_template: str,
) -> None:
    """Render category distribution (pie) + per-category Top 5 (grouped bar)."""
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("**🍩 카테고리별 생산 비중**")
        cat_colors = [_get_category_info(c)["color"] for c in cat_summary["category"]]
        cat_labels = [_get_category_info(c)["label"] for c in cat_summary["category"]]
        fig_cat = go.Figure(go.Pie(
            labels=cat_labels,
            values=cat_summary["total_qty"],
            hole=0.45,
            marker=dict(colors=cat_colors),
            textinfo="percent+label",
            textposition="outside",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "생산량: %{value:,} 개<br>"
                "점유율: %{percent}<extra></extra>"
            ),
        ))
        fig_cat.update_layout(
            template=chart_template,
            height=360,
            showlegend=False,
            margin=dict(l=20, r=20, t=10, b=20),
        )
        st.plotly_chart(fig_cat, width="stretch", config=get_chart_config("category_dist"))

    with chart_col2:
        st.markdown("**📊 카테고리별 Top 5 제품**")
        item_totals = (
            df.groupby(["category", "item_code"])["good_quantity"]
            .sum()
            .reset_index()
        )
        fig_stack = go.Figure()
        for cat in categories_present:
            cat_data = item_totals[item_totals["category"] == cat].nlargest(5, "good_quantity")
            cat_info = _get_category_info(cat)
            fig_stack.add_trace(go.Bar(
                x=cat_data["item_code"],
                y=cat_data["good_quantity"],
                name=cat_info["label"],
                marker_color=cat_info["color"],
                text=cat_data["good_quantity"].apply(lambda x: f"{x:,.0f}"),
                textposition="outside",
                hovertemplate=(
                    f"<b>{cat_info['label']}</b><br>"
                    "제품: %{x}<br>"
                    "생산량: %{y:,}<extra></extra>"
                ),
            ))
        fig_stack.update_layout(
            template=chart_template,
            height=360,
            barmode="group",
            xaxis_title="제품코드",
            yaxis_title="생산량",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=50, r=20, t=40, b=60),
        )
        st.plotly_chart(fig_stack, width="stretch", config=get_chart_config("cat_top5"))


# ==========================================================
# Section 3: Product Drill-Down
# ==========================================================
def _render_drilldown_item_detail(
    item_df: pd.DataFrame,
    selected_code: str,
    colors: dict,
    chart_template: str,
) -> None:
    """Render KPIs + monthly trend + recent batches for a single selected product."""
    d_col1, d_col2, d_col3, d_col4 = st.columns(4)
    with d_col1:
        st.metric("총 생산량", f"{item_df['good_quantity'].sum():,.0f}")
    with d_col2:
        st.metric("배치 수", f"{len(item_df):,}")
    with d_col3:
        avg_batch = item_df["good_quantity"].mean() if not item_df.empty else 0
        st.metric("평균 배치 크기", f"{avg_batch:,.0f}")
    with d_col4:
        days_active = item_df["production_dt"].dt.date.nunique() if not item_df.empty else 0
        st.metric("생산일 수", f"{days_active}")

    detail_col1, detail_col2 = st.columns([3, 2])

    with detail_col1:
        st.markdown(f"**📈 {selected_code} 월별 추이**")
        if not item_df.empty:
            monthly = (
                item_df.groupby("year_month")["good_quantity"]
                .agg(["sum", "count"])
                .reset_index()
            )
            monthly.columns = ["year_month", "total_qty", "batch_count"]

            fig_monthly = go.Figure()
            fig_monthly.add_trace(go.Bar(
                x=monthly["year_month"],
                y=monthly["total_qty"],
                name="생산량",
                marker_color=colors["primary"],
                text=monthly["total_qty"].apply(lambda x: f"{x:,.0f}"),
                textposition="outside",
            ))
            fig_monthly.update_layout(
                template=chart_template,
                height=340,
                hovermode="x unified",
                xaxis_type="category",
                xaxis_title="연월",
                yaxis_title="생산량",
                margin=dict(l=50, r=20, t=20, b=40),
            )
            st.plotly_chart(
                fig_monthly, width="stretch",
                config=get_chart_config(f"product_{selected_code}_trend"),
            )
        else:
            st.info("데이터가 없습니다.")

    with detail_col2:
        st.markdown("**📋 최근 배치 이력**")
        if not item_df.empty:
            recent = (
                item_df.sort_values("production_dt", ascending=False)
                .head(10)[["production_dt", "good_quantity", "lot_number"]]
                .copy()
            )
            recent["production_dt"] = recent["production_dt"].dt.strftime("%Y-%m-%d")
            recent = recent.rename(columns={
                "production_dt": "생산일",
                "good_quantity": "양품수량",
                "lot_number": "LOT",
            })
            st.dataframe(recent, width="stretch", hide_index=True, height=340)
        else:
            st.info("데이터가 없습니다.")


def _render_drilldown(
    df: pd.DataFrame,
    categories_present: list,
    colors: dict,
    chart_template: str,
) -> None:
    """Render category-tabbed drill-down with selectbox + per-product detail."""
    tab_labels = [_get_category_info(c)["label"] for c in categories_present] + ["전체"]
    tabs = st.tabs(tab_labels)

    for tab_idx, tab in enumerate(tabs):
        with tab:
            if tab_idx < len(categories_present):
                selected_cat = categories_present[tab_idx]
                cat_df = df[df["category"] == selected_cat]
            else:
                selected_cat = "all"
                cat_df = df

            available_items = (
                cat_df.groupby(["item_code", "item_name"])["good_quantity"]
                .sum()
                .reset_index()
                .sort_values("good_quantity", ascending=False)
            )
            item_options = [
                f"{row['item_code']} | {row['item_name']} ({row['good_quantity']:,.0f})"
                for _, row in available_items.iterrows()
            ]
            item_code_map = dict(zip(item_options, available_items["item_code"]))

            selected_item_label = st.selectbox(
                "제품 선택",
                options=item_options,
                key=f"drill_select_{selected_cat}",
                help="제품을 선택하면 월별 추이와 최근 배치 이력을 확인합니다",
            )

            if selected_item_label:
                selected_code = item_code_map[selected_item_label]
                item_df = cat_df[cat_df["item_code"] == selected_code].copy()
                _render_drilldown_item_detail(item_df, selected_code, colors, chart_template)


# ==========================================================
# Section 4: Cross-Product Trend Comparison
# ==========================================================
def _render_trend_comparison(df: pd.DataFrame, db_ver: str, chart_template: str) -> None:
    """Render multi-product trend comparison with aggregation toggle."""
    items_df = load_item_list(db_ver=db_ver)
    if items_df.empty:
        st.info("비교할 제품이 없습니다.")
        return

    compare_options = items_df["item_code"].tolist()
    selected_compare = st.multiselect(
        "비교할 제품 선택 (최대 5개)",
        options=compare_options,
        max_selections=5,
        help="2-5개 제품을 선택하여 생산 추세를 비교하세요",
    )

    if not selected_compare:
        st.info("위에서 제품을 선택하면 추세 비교가 표시됩니다.")
        return

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
        width="stretch",
        config=get_chart_config("product_trends"),
    )


# ==========================================================
# Page entry
# ==========================================================
render_page_header("제품별 분석", "생산 관리 > 제품별 분석")

fs = get_filter_state()
item_codes = fs["item_codes"]
keyword = fs["keyword"]
date_from = fs["date_from"]
date_to = fs["date_to"]
limit = fs["limit"]
db_ver = fs["db_ver"]

col_main, col_ai = get_page_columns()

with col_main:
    df, _ = load_records(item_codes, keyword, date_from, date_to, limit, db_ver=db_ver)
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")

    if df.empty:
        st.info("조회된 데이터가 없습니다. 사이드바 필터를 조정해 주세요.")
    else:
        df["category"] = df["item_code"].apply(_classify_item_code)
        cat_summary = (
            df.groupby("category")
            .agg(
                total_qty=("good_quantity", "sum"),
                batch_count=("good_quantity", "count"),
                product_count=("item_code", "nunique"),
            )
            .reset_index()
        )
        categories_present = cat_summary["category"].tolist()

        st.markdown("#### 📊 카테고리별 현황")
        _render_category_kpis(cat_summary, len(categories_present))
        st.markdown('<div class="bkit-spacer-8"></div>', unsafe_allow_html=True)

        _render_distribution_charts(df, cat_summary, categories_present, chart_template)

        st.divider()
        st.markdown("#### 🔍 제품 상세 드릴다운")
        _render_drilldown(df, categories_present, colors, chart_template)

        st.divider()
        st.markdown("#### 📈 제품 추세 비교")
        _render_trend_comparison(df, db_ver, chart_template)

render_ai_column(col_ai)
