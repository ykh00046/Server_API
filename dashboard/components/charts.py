"""
U3-U5: Chart Components - Data visualization for dashboard.

Provides interactive charts:
- Top 10 products bar chart (U3)
- Product distribution pie/donut chart (U3)
- Product trend comparison lines (U3)
- Range selector enhancement (U5)
- Download button enhancement (U5)
"""


import pandas as pd
import plotly.graph_objects as go

from shared.ui.theme import CHART_SERIES_COLORS, get_chart_palette

# ==========================================================
# Layout constants — 차트 높이·범례 배치의 SSOT
# ==========================================================
# 빌더가 반환하는 차트의 기본 높이. 뷰가 좁은 2단 컬럼에 넣을 때만
# update_layout(height=...) 로 낮춘다 (360/340 등은 그 자리의 의도적 예외).
CHART_HEIGHT = 400

# 제목은 호출 측(view)의 section_header가 담당하므로 plotly 내부 title 을 두지
# 않는다 — 상단 여백은 "제목 없음" 기준값으로 통일한다.
CHART_MARGIN_TOP = 30

# 가로 범례를 플롯 영역 위(왼쪽 정렬)에 붙이는 표준 배치.
# x/xanchor 는 plotly 의 가로 범례 기본값을 명시한 것이라 기존 렌더와 동일하다.
LEGEND_TOP = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)

# 파이/도넛처럼 플롯 위쪽에 라벨이 놓여 상단 범례가 겹치는 차트 전용 배치.
LEGEND_BOTTOM = dict(orientation="h", yanchor="bottom", y=-0.2)


def create_top10_bar_chart(
    df: pd.DataFrame, template: str, marker_color: str | None = None
) -> go.Figure:
    """
    Create horizontal bar chart for top 10 products.

    Args:
        df: Production records dataframe with columns:
            - item_code: Product code
            - item_name: Product name
            - good_quantity: Production quantity
        template: Plotly template name (e.g., "plotly_white", "plotly_dark")

    Returns:
        Plotly Figure object with horizontal bar chart.
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14)
        )
        return fig

    # Aggregate by item
    item_totals = df.groupby(["item_code", "item_name"])["good_quantity"].sum().reset_index()
    item_totals = item_totals.nlargest(10, "good_quantity")

    fig = go.Figure(go.Bar(
        x=item_totals["good_quantity"],
        y=item_totals["item_code"],
        orientation='h',
        text=item_totals["good_quantity"].apply(lambda x: f"{x:,.0f}"),
        textposition='outside',
        marker_color=marker_color if marker_color is not None else get_chart_palette(1)[0],
        hovertemplate=(
            "<b>%{y}</b><br>"
            "생산량: %{x:,} 개<br>"
            "<extra></extra>"
        )
    ))

    # 제목은 호출 측(view)의 섹션 헤더가 담당한다 — plotly 내부 title 을 두면
    # 같은 문구가 두 번 렌더된다. t 여백은 제목 없는 기준(CHART_MARGIN_TOP)으로 통일.
    fig.update_layout(
        xaxis_title="생산량 (개)",
        yaxis_title="제품코드",
        template=template,
        height=CHART_HEIGHT,
        yaxis=dict(autorange="reversed"),  # Top product at top
        margin=dict(l=100, r=50, t=CHART_MARGIN_TOP, b=50)
    )

    return fig


def create_distribution_pie(df: pd.DataFrame, template: str) -> go.Figure:
    """
    Create donut chart for product distribution.

    Shows top 10 products individually, with remaining products
    grouped as "Others".

    Args:
        df: Production records dataframe with columns:
            - item_code: Product code
            - good_quantity: Production quantity
        template: Plotly template name

    Returns:
        Plotly Figure object with donut chart.
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14)
        )
        return fig

    # Aggregate by item
    item_totals = df.groupby("item_code")["good_quantity"].sum().reset_index()

    # Top 10 + Others
    top10 = item_totals.nlargest(10, "good_quantity")
    if len(item_totals) > 10:
        others_sum = item_totals[
            ~item_totals["item_code"].isin(top10["item_code"])
        ]["good_quantity"].sum()
        others_row = pd.DataFrame([{"item_code": "Others", "good_quantity": others_sum}])
        top10 = pd.concat([top10, others_row], ignore_index=True)

    fig = go.Figure(go.Pie(
        labels=top10["item_code"],
        values=top10["good_quantity"],
        hole=0.4,
        marker=dict(colors=get_chart_palette(len(top10))),
        textinfo='percent+label',
        textposition='outside',
        hovertemplate=(
            "<b>%{label}</b><br>"
            "생산량: %{value:,} 개<br>"
            "점유율: %{percent}<extra></extra>"
        )
    ))

    # 제목은 호출 측 섹션 헤더가 담당 (중복 렌더 방지).
    fig.update_layout(
        template=template,
        height=CHART_HEIGHT,
        showlegend=True,
        legend=LEGEND_BOTTOM,
        margin=dict(l=20, r=20, t=CHART_MARGIN_TOP, b=40)
    )

    return fig


def create_trend_lines(
    df: pd.DataFrame,
    item_codes: list[str],
    agg_unit: str,
    template: str
) -> go.Figure:
    """
    Create multi-line trend chart for selected products.

    Shows production trends over time for multiple products,
    with aggregation by day, week, or month.

    Args:
        df: Production records dataframe with columns:
            - item_code: Product code
            - good_quantity: Production quantity
            - production_date: Date string
            - production_dt: Parsed datetime
            - year_month: Year-month string
        item_codes: List of product codes to display
        agg_unit: Aggregation unit - "Daily", "Weekly", or "Monthly"
        template: Plotly template name

    Returns:
        Plotly Figure object with multi-line trend chart.
    """
    if df.empty or not item_codes:
        fig = go.Figure()
        fig.add_annotation(
            text="Select products to view trends",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14)
        )
        return fig

    # Filter by selected items
    filtered = df[df["item_code"].isin(item_codes)].copy()

    if filtered.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No data for selected products",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14)
        )
        return fig

    # Determine period column based on aggregation unit
    if agg_unit == "일별":
        filtered["period"] = filtered["production_date"].str[:10]  # YYYY-MM-DD
    elif agg_unit == "주별":
        # %W(월요일 시작): data.py load_weekly_summary의 SQL week_expr와 동일 규칙
        filtered["period"] = filtered["production_dt"].dt.strftime("%Y-W%W")
    else:  # 월별 (default)
        filtered["period"] = filtered["year_month"]

    # Aggregate by period and item
    agg_df = filtered.groupby(["period", "item_code"])["good_quantity"].sum().reset_index()

    fig = go.Figure()

    # Color palette for lines (from theme)
    colors = CHART_SERIES_COLORS

    for idx, item_code in enumerate(item_codes):
        item_data = agg_df[agg_df["item_code"] == item_code].sort_values("period")
        color = colors[idx % len(colors)]

        fig.add_trace(go.Scatter(
            x=item_data["period"],
            y=item_data["good_quantity"],
            mode='lines+markers',
            name=item_code,
            line=dict(color=color, width=2),
            marker=dict(color=color, size=6),
            hovertemplate=(
                f"<b>{item_code}</b><br>"
                "기간: %{x}<br>"
                "생산량: %{y:,} 개<extra></extra>"
            )
        ))

    # 제목은 호출 측 섹션 헤더가 담당 (중복 렌더 방지).
    fig.update_layout(
        xaxis_title="기간",
        yaxis_title="생산량 (개)",
        template=template,
        height=CHART_HEIGHT,
        hovermode="x unified",
        xaxis_type="category",
        legend=LEGEND_TOP,
        margin=dict(l=60, r=30, t=CHART_MARGIN_TOP, b=40)
    )

    return fig


def get_chart_config(filename: str) -> dict:
    """
    Get Plotly chart configuration dict for st.plotly_chart.

    Args:
        filename: Base filename for downloaded images

    Returns:
        Configuration dict for use with st.plotly_chart(config=...)
    """
    return {
        'displayModeBar': True,
        'scrollZoom': True,
        'displaylogo': False,
        'toImageButtonOptions': {
            'format': 'png',
            'filename': filename,
            'height': 800,
            'width': 1200,
            'scale': 2
        }
    }
