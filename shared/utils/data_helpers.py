#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Shared Data Processing and Formatting Utilities.

Provides unified logic for:
- Number formatting (K, M)
- Category mapping (English <-> Korean)
- Unit resolution (kg, L)
- Common Pandas aggregations
"""

import pandas as pd
from typing import List, Union, Dict, Tuple


# ==========================================================
# Formatting
# ==========================================================

def format_large_number(num: Union[int, float], suffix: str = '') -> str:
    """Formats a large number into human-readable format (K, M)."""
    if pd.isna(num):
        return f"0{suffix}"
    num = float(num)

    if abs(num) < 1000:
        return f"{num:,.0f}{suffix}"
    elif abs(num) < 1_000_000:
        return f"{num/1000:,.1f}K{suffix}"
    else:
        return f"{num/1_000_000:,.1f}M{suffix}"


# ==========================================================
# Category Mapping
# ==========================================================

CATEGORY_KR_MAP = {
    'Ink': '잉크',
    'Water': '용수',
    'Chemical': '약품',
    'Other': '기타',
}

CATEGORY_EN_MAP = {v: k for k, v in CATEGORY_KR_MAP.items()}

# Legacy label support
LEGACY_KR_TO_EN = {
    '수': 'Water',
    '화학': 'Chemical',
    '잉크': 'Ink',
    '기타': 'Other',
}


def to_korean_category(labels: Union[str, List[str]]) -> Union[str, List[str]]:
    """Map English category label(s) to Korean display label(s)."""
    if isinstance(labels, list):
        return [CATEGORY_KR_MAP.get(x, x) for x in labels]
    return CATEGORY_KR_MAP.get(labels, labels)


def to_english_category(labels: Union[str, List[str]]) -> Union[str, List[str]]:
    """Map Korean display category label(s) to English internal label(s)."""
    if isinstance(labels, list):
        return [CATEGORY_EN_MAP.get(x, LEGACY_KR_TO_EN.get(x, x)) for x in labels]
    return CATEGORY_EN_MAP.get(labels, LEGACY_KR_TO_EN.get(labels, labels))


# ==========================================================
# Data Aggregations (Pandas based)
# ==========================================================

def aggregate_daily_production(
    data: pd.DataFrame, 
    date_col: str = 'production_date', 
    val_col: str = 'good_quantity'
) -> pd.DataFrame:
    """Aggregate production data by date."""
    if data.empty:
        return pd.DataFrame(columns=['date', 'quantity'])

    # Ensure datetime
    if not pd.api.types.is_datetime64_any_dtype(data[date_col]):
        data = data.copy()
        data[date_col] = pd.to_datetime(data[date_col], errors='coerce')

    summary = data.groupby(data[date_col].dt.date)[val_col].sum().reset_index()
    summary.columns = ['date', 'quantity']
    return summary


def calculate_summary_stats(
    data: pd.DataFrame, 
    date_col: str = 'production_date', 
    val_col: str = 'good_quantity'
) -> Dict[str, float]:
    """Calculate daily avg, max, min stats."""
    if data.empty:
        return {'avg': 0.0, 'max': 0.0, 'min': 0.0}

    daily_totals = data.groupby(data[date_col].dt.date)[val_col].sum()
    return {
        'avg': daily_totals.mean(),
        'max': daily_totals.max(),
        'min': daily_totals.min()
    }


def aggregate_hourly_production(
    data: pd.DataFrame, 
    date_col: str = 'production_date', 
    val_col: str = 'good_quantity'
) -> pd.DataFrame:
    """Aggregate production data by hour (0-23)."""
    if data.empty:
        return pd.DataFrame(columns=['hour', 'quantity'])

    df = data.copy()
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

    hourly = (
        df.dropna(subset=[date_col])
        .assign(hour=df[date_col].dt.hour)
        .groupby('hour')[val_col]
        .sum()
        .reindex(range(24), fill_value=0)
        .reset_index()
    )
    hourly.columns = ['hour', 'quantity']
    return hourly


def resolve_display_unit(selected_categories: List[str], mode: str = 'auto') -> Tuple[str, bool]:
    """Determine unit label (kg/L) based on categories."""
    if mode != 'auto':
        return mode, False

    if not selected_categories:
        return 'kg', False

    unique = set(selected_categories)
    if 'Water' in unique and len(unique) > 1:
        return 'kg/L', True
    if unique == {'Water'}:
        return 'L', False

    return 'kg', False
