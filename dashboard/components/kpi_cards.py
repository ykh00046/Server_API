"""
KPI Dashboard Cards — native st.metric (ui-design-overhaul-v1).

Pure KPI/sparkline computation + a thin render layer using
st.metric(border=True, chart_data=...) inside a horizontal container
(wraps responsively, unlike st.columns). Colors come from the native
theme — no custom HTML/CSS.
"""

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st


def calculate_kpis(
    df: pd.DataFrame,
    date_from: date | None,
    date_to: date | None
) -> dict[str, Any]:
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
            - active_products: Number of distinct products
            - avg_batch_size: Average quantity per batch
    """
    if df.empty:
        return {
            "total_qty": 0,
            "batch_count": 0,
            "daily_avg": 0.0,
            "top_item": "-",
            "top_item_name": "-",
            "active_products": 0,
            "avg_batch_size": 0,
        }

    # Calculate total quantity (handle NaN values)
    total_qty = int(df["good_quantity"].fillna(0).sum())
    batch_count = len(df)
    active_products = df["item_code"].nunique()
    avg_batch_size = int(total_qty / max(batch_count, 1))

    # Calculate daily average
    if date_from and date_to:
        days = (date_to - date_from).days + 1
        daily_avg = total_qty / max(days, 1)
    else:
        daily_avg = total_qty / 30

    # Find top product
    item_totals = df.groupby("item_code")["good_quantity"].sum()
    if not item_totals.empty:
        top_item = str(item_totals.idxmax())
        top_item_rows = df[df["item_code"] == top_item]["item_name"]
        top_item_name = str(top_item_rows.iloc[0]) if not top_item_rows.empty else "-"
    else:
        top_item = "-"
        top_item_name = "-"

    return {
        "total_qty": total_qty,
        "batch_count": batch_count,
        "daily_avg": daily_avg,
        "top_item": top_item,
        "top_item_name": top_item_name,
        "active_products": active_products,
        "avg_batch_size": avg_batch_size,
    }


def get_sparkline_data(
    df: pd.DataFrame,
    days: int = 7
) -> list[int]:
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

    daily = df.groupby("production_day")["good_quantity"].sum()
    recent_days = daily.tail(days)
    result = recent_days.tolist()

    while len(result) < days:
        result.insert(0, 0)

    return result


def get_sparkline_for_top_product(
    df: pd.DataFrame,
    top_item: str,
    days: int = 7
) -> list[int]:
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

    top_df = df[df["item_code"] == top_item]
    return get_sparkline_data(top_df, days)


def _format_number(n: int) -> str:
    """Format number with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n:,}"
    return str(n)


def _has_signal(data: list[int] | None) -> bool:
    """True if sparkline data exists and is not all zeros."""
    return bool(data) and max(data) > 0


def render_kpi_cards(
    kpis: dict[str, Any],
    colors: dict[str, str] | None = None,
    sparkline_data: list[int] | None = None,
    batch_sparkline: list[int] | None = None,
    top_product_sparkline: list[int] | None = None
) -> None:
    """
    Render 4 KPI cards as native bordered metrics with sparklines.

    Args:
        kpis: KPI values dict from calculate_kpis()
        colors: Unused (legacy param kept for call-site compatibility;
                colors now come from the native theme)
        sparkline_data: Daily production trend for last 7 days
        batch_sparkline: Daily batch count trend for last 7 days
        top_product_sparkline: Daily trend for top product
    """
    with st.container(horizontal=True):
        st.metric(
            "총 생산량",
            _format_number(kpis["total_qty"]),
            border=True,
            chart_data=sparkline_data if _has_signal(sparkline_data) else None,
            chart_type="line",
        )
        st.metric(
            "배치 수",
            f"{kpis['batch_count']:,}",
            border=True,
            chart_data=batch_sparkline if _has_signal(batch_sparkline) else None,
            chart_type="bar",
        )
        st.metric(
            "활성 제품",
            str(kpis.get("active_products", 0)),
            border=True,
        )
        st.metric(
            "평균 배치 크기",
            f"{kpis.get('avg_batch_size', 0):,}",
            border=True,
            chart_data=(
                top_product_sparkline if _has_signal(top_product_sparkline) else None
            ),
            chart_type="line",
        )
