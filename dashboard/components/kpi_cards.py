"""
U2: KPI Dashboard Cards - Key Performance Indicators display.

Displays key metrics at the top of the dashboard:
- Total production quantity
- Production batch count
- Daily average production
- Top produced product

Features:
- Sparklines showing 7-day trend
- Responsive horizontal layout
- Card-style borders
- Dark mode support
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from typing import Dict, Any, Optional, List


def calculate_kpis(
    df: pd.DataFrame,
    date_from: Optional[date],
    date_to: Optional[date]
) -> Dict[str, Any]:
    """
    Calculate KPI metrics from dataframe.

    Args:
        df: Production records dataframe with columns:
            - good_quantity: Production quantity
            - item_code: Product code
            - item_name: Product name
        date_from: Start date of the period
        date_to: End date of the period

    Returns:
        Dict with keys:
            - total_qty: Total production quantity
            - batch_count: Number of production batches
            - daily_avg: Average daily production
            - top_item: Product code with highest production
            - top_item_name: Product name of top item
    """
    if df.empty:
        return {
            "total_qty": 0,
            "batch_count": 0,
            "daily_avg": 0.0,
            "top_item": "-",
            "top_item_name": "-",
        }

    # Calculate total quantity (handle NaN values)
    total_qty = int(df["good_quantity"].fillna(0).sum())
    batch_count = len(df)

    # Calculate daily average
    if date_from and date_to:
        days = (date_to - date_from).days + 1
        daily_avg = total_qty / max(days, 1)
    else:
        # Default: assume 30 days if no date range specified
        daily_avg = total_qty / 30

    # Find top product
    item_totals = df.groupby("item_code")["good_quantity"].sum()
    if not item_totals.empty:
        top_item = str(item_totals.idxmax())
        # Get the name for the top item
        top_item_rows = df[df["item_code"] == top_item]["item_name"]
        if not top_item_rows.empty:
            top_item_name = str(top_item_rows.iloc[0])
        else:
            top_item_name = "-"
    else:
        top_item = "-"
        top_item_name = "-"

    return {
        "total_qty": total_qty,
        "batch_count": batch_count,
        "daily_avg": daily_avg,
        "top_item": top_item,
        "top_item_name": top_item_name,
    }


def get_sparkline_data(
    df: pd.DataFrame,
    days: int = 7
) -> List[int]:
    """
    Get daily production trend for sparkline display.

    Args:
        df: Production records dataframe with 'production_day' column
        days: Number of recent days to include

    Returns:
        List of daily totals for the last N days (oldest to newest)
    """
    if df.empty or "production_day" not in df.columns:
        return [0] * days

    # Group by day and sum
    daily = df.groupby("production_day")["good_quantity"].sum()

    # Get last N days with data
    recent_days = daily.tail(days)

    # Convert to list, fill missing with 0
    result = recent_days.tolist()

    # Pad with zeros if less than requested days
    while len(result) < days:
        result.insert(0, 0)

    return result


def get_sparkline_for_top_product(
    df: pd.DataFrame,
    top_item: str,
    days: int = 7
) -> List[int]:
    """
    Get daily production trend for the top product.

    Args:
        df: Production records dataframe
        top_item: Item code of the top product
        days: Number of recent days to include

    Returns:
        List of daily totals for the top product
    """
    if df.empty or top_item == "-":
        return [0] * days

    # Filter for top product
    top_df = df[df["item_code"] == top_item]

    return get_sparkline_data(top_df, days)


def render_kpi_cards(
    kpis: Dict[str, Any],
    colors: Dict[str, str],
    sparkline_data: Optional[List[int]] = None,
    batch_sparkline: Optional[List[int]] = None,
    top_product_sparkline: Optional[List[int]] = None
) -> None:
    """
    Render 4 KPI metric cards in a responsive row with sparklines.

    Uses st.container(horizontal=True) for responsive layout that
    wraps on smaller screens. CSS ensures equal width cards.
    Each metric has border=True for card-style appearance.

    Args:
        kpis: KPI values dict from calculate_kpis()
        colors: Theme color palette (for future use)
        sparkline_data: Daily production trend for last 7 days
        batch_sparkline: Daily batch count trend for last 7 days
        top_product_sparkline: Daily trend for top product
    """
    # Default sparklines if not provided
    if sparkline_data is None:
        sparkline_data = [0] * 7
    if batch_sparkline is None:
        batch_sparkline = [0] * 7
    if top_product_sparkline is None:
        top_product_sparkline = [0] * 7

    # Sparkline color sourced from the theme palette (shared/ui/theme.CHART_COLORS).
    sparkline_color = colors.get("accent", "#FF4B4B")

    # CSS for equal-width cards and visible sparklines
    st.markdown(f"""
    <style>
        /* Equal width for KPI cards in horizontal container */
        .stHorizontalBlock .stElementContainer {{
            flex: 1 1 0 !important;
            min-width: 150px;
        }}
        /* Consistent card height */
        .stMetric {{
            height: 100%;
        }}
        /* Align content consistently */
        .stMetric > div {{
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        /* Make sparklines more visible with theme-aware colors */
        .stMetric svg path {{
            stroke: {sparkline_color} !important;
        }}
        .stMetric svg path[fill="#a3a8b8"] {{
            fill: {sparkline_color} !important;
        }}
        .stMetric svg path[fill="#6a6d77"] {{
            fill: {sparkline_color} !important;
        }}
        /* Also target circles (data points) */
        .stMetric svg circle {{
            stroke: {sparkline_color} !important;
            fill: {sparkline_color} !important;
        }}
    </style>
    """, unsafe_allow_html=True)

    # Use horizontal container for responsive layout
    with st.container(horizontal=True):
        # KPI 1: Total Production with trend
        st.metric(
            label="총 생산량",
            value=f"{kpis['total_qty']:,} 개",
            border=True,
            chart_data=sparkline_data,
            chart_type="line"
        )

        # KPI 2: Batch Count with trend
        st.metric(
            label="배치 수",
            value=f"{kpis['batch_count']:,} 건",
            border=True,
            chart_data=batch_sparkline,
            chart_type="bar"
        )

        # KPI 3: Daily Average (with empty sparkline for height consistency)
        st.metric(
            label="일 평균 생산",
            value=f"{kpis['daily_avg']:,.0f} 개",
            border=True,
            chart_data=[0] * 7,  # Empty sparkline for consistent height
            chart_type="line"
        )

        # KPI 4: Top Product with trend
        top_name = kpis['top_item_name']
        if len(top_name) > 20:
            top_name = top_name[:20] + "..."

        st.metric(
            label=f"최다 제품 ({kpis['top_item']})",
            value=top_name if top_name != "-" else "-",
            border=True,
            chart_data=top_product_sparkline,
            chart_type="line"
        )

    st.divider()
