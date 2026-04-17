"""
KPI Dashboard Cards — B3 sidebar style.

Custom HTML cards with:
- Gradient top bar (pink/sky)
- Icon box
- MoM change rate
- CSS bar sparkline
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
        "active_products": active_products,
        "avg_batch_size": avg_batch_size,
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

    top_df = df[df["item_code"] == top_item]
    return get_sparkline_data(top_df, days)


def _format_number(n: int) -> str:
    """Format number with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n:,}"
    return str(n)


def _render_sparkline_bars(data: List[int], color_light: str, color_dark: str) -> str:
    """Generate CSS bar sparkline HTML."""
    if not data or max(data) == 0:
        return ""
    max_val = max(data)
    bars = ""
    for i, v in enumerate(data):
        h = max(int(v / max_val * 100), 3) if max_val > 0 else 3
        c = color_dark if i == len(data) - 1 else color_light
        bars += f'<div style="flex:1;border-radius:2px;min-height:3px;height:{h}%;background:{c};"></div>'
    return f'<div style="display:flex;align-items:end;gap:2px;height:28px;margin-top:10px;">{bars}</div>'


def render_kpi_cards(
    kpis: Dict[str, Any],
    colors: Dict[str, str],
    sparkline_data: Optional[List[int]] = None,
    batch_sparkline: Optional[List[int]] = None,
    top_product_sparkline: Optional[List[int]] = None
) -> None:
    """
    Render 4 KPI cards in B3 style with gradient bars, icons, and sparklines.

    Args:
        kpis: KPI values dict from calculate_kpis()
        colors: Theme color palette
        sparkline_data: Daily production trend for last 7 days
        batch_sparkline: Daily batch count trend for last 7 days
        top_product_sparkline: Daily trend for top product
    """
    if sparkline_data is None:
        sparkline_data = [0] * 7
    if batch_sparkline is None:
        batch_sparkline = [0] * 7
    if top_product_sparkline is None:
        top_product_sparkline = [0] * 7

    cards = [
        {
            "label": "총 생산량",
            "value": _format_number(kpis["total_qty"]),
            "icon": "📦",
            "gradient": "linear-gradient(90deg, #f472b6, #f9a8d4)",
            "icon_bg": "#fdf2f8",
            "icon_color": "#ec4899",
            "spark": _render_sparkline_bars(sparkline_data, "#fce7f3", "#f472b6"),
        },
        {
            "label": "배치 수",
            "value": f"{kpis['batch_count']:,}",
            "icon": "🧪",
            "gradient": "linear-gradient(90deg, #38bdf8, #7dd3fc)",
            "icon_bg": "#f0f9ff",
            "icon_color": "#0ea5e9",
            "spark": _render_sparkline_bars(batch_sparkline, "#e0f2fe", "#38bdf8"),
        },
        {
            "label": "활성 제품",
            "value": str(kpis.get("active_products", 0)),
            "icon": "🏷️",
            "gradient": "linear-gradient(90deg, #f9a8d4, #7dd3fc)",
            "icon_bg": "#fdf2f8",
            "icon_color": "#f472b6",
            "spark": "",  # No sparkline for count
        },
        {
            "label": "평균 배치 크기",
            "value": f"{kpis.get('avg_batch_size', 0):,}",
            "icon": "📏",
            "gradient": "linear-gradient(90deg, #0ea5e9, #f472b6)",
            "icon_bg": "#f0f9ff",
            "icon_color": "#0284c7",
            "spark": _render_sparkline_bars(top_product_sparkline, "#e0f2fe", "#0ea5e9"),
        },
    ]

    # Render as 4 columns
    cols = st.columns(4)
    for i, card in enumerate(cards):
        with cols[i]:
            st.markdown(f"""
            <div style="
                background: var(--color-bg-card, #fff);
                border-radius: var(--radius-card, 12px);
                padding: 18px;
                box-shadow: var(--shadow-card, 0 1px 3px rgba(0,0,0,0.06));
                border: 1px solid var(--color-border, rgba(236,72,153,0.1));
                position: relative;
                overflow: hidden;
            ">
                <div style="position:absolute;top:0;left:0;right:0;height:3px;background:{card['gradient']};"></div>
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <span style="font-size:0.75rem;color:var(--color-text-muted, #64748b);font-weight:500;">{card['label']}</span>
                    <span style="
                        width:36px;height:36px;border-radius:10px;
                        display:flex;align-items:center;justify-content:center;
                        font-size:16px;background:{card['icon_bg']};
                    ">{card['icon']}</span>
                </div>
                <div style="font-size:1.75rem;font-weight:700;color:var(--color-text, #1e293b);margin:6px 0 4px;">{card['value']}</div>
                {card['spark']}
            </div>
            """, unsafe_allow_html=True)
