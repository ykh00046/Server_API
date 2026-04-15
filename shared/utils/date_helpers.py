#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Shared Date and Range Utilities for Production Data Hub.

Provides unified logic for:
- Date range presets (Last 7/30 days, current/last month)
- Change percentage calculation
- Aggregate statistics over time
"""

from datetime import datetime, timedelta
from typing import Tuple, Optional
import pandas as pd


def get_current_week_range() -> Tuple[datetime.date, datetime.date]:
    """Last 7 days (today back to 6 days ago)."""
    today = datetime.today().date()
    start_date = today - timedelta(days=6)
    return start_date, today


def get_last_week_range() -> Tuple[datetime.date, datetime.date]:
    """The 7-day period before the current week."""
    today = datetime.today().date()
    last_week_end = today - timedelta(days=7)
    last_week_start = today - timedelta(days=13)
    return last_week_start, last_week_end


def get_current_month_range() -> Tuple[datetime.date, datetime.date]:
    """Start and end date of the current calendar month."""
    today = datetime.today().date()
    start_date = today.replace(day=1)
    # Next month's 1st day - 1 day
    if today.month == 12:
        end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return start_date, end_date


def get_last_month_range() -> Tuple[datetime.date, datetime.date]:
    """Start and end date of the previous calendar month."""
    today = datetime.today().date()
    first_day_current = today.replace(day=1)
    last_day_prev = first_day_current - timedelta(days=1)
    first_day_prev = last_day_prev.replace(day=1)
    return first_day_prev, last_day_prev


def get_relative_range(days: int = 30) -> Tuple[datetime.date, datetime.date]:
    """Range for the last N days ending today."""
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=days - 1)
    return start_date, end_date


def calculate_change_percentage(current_value: float, previous_value: float) -> float:
    """
    Calculate percentage change between two values.

    Args:
        current_value: New value
        previous_value: Old/Base value

    Returns:
        float: Percentage change (rounded to 1 decimal)
    """
    if previous_value == 0:
        return 0.0 if current_value == 0 else 100.0

    change = ((current_value - previous_value) / previous_value) * 100
    return round(change, 1)


def parse_production_date(series: pd.Series) -> pd.Series:
    """
    Unified production date parser for Pandas Series.
    Attempts to parse multiple formats consistently.
    """
    # Try standard YYYY-MM-DD first
    dt = pd.to_datetime(series, errors='coerce')
    return dt
