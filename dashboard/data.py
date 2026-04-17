"""
Data Loading Layer — shared data functions for all dashboard pages.

Extracted from app.py to support multi-page architecture.
All data loading, parsing, and caching functions live here.
"""

import io
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

import pandas as pd
import streamlit as st

# Add parent directory for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    DB_FILE,
    ARCHIVE_DB_FILE,
    DBRouter,
)
from shared.validators import escape_like_wildcards


# ==========================================================
# Helpers
# ==========================================================
def get_db_mtime() -> float:
    """Get DB modification time for cache invalidation."""
    try:
        mtime = os.path.getmtime(DB_FILE)
        if ARCHIVE_DB_FILE.exists():
            archive_mtime = os.path.getmtime(ARCHIVE_DB_FILE)
            mtime = max(mtime, archive_mtime)
        return mtime
    except Exception:
        return 0


def run_self_check() -> Tuple[bool, str]:
    """Run database health check."""
    if not DB_FILE.exists():
        return False, f"Database file not found: {DB_FILE}"
    try:
        with DBRouter.get_connection(use_archive=False) as conn:
            tables = pd.read_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='production_records'",
                conn,
            )
            if tables.empty:
                return False, "production_records table does not exist."
            columns = pd.read_sql("PRAGMA table_info(production_records)", conn)[
                "name"
            ].tolist()
            required = [
                "production_date",
                "item_code",
                "item_name",
                "good_quantity",
                "lot_number",
            ]
            if not all(c in columns for c in required):
                return False, "Required columns are missing."
        if not ARCHIVE_DB_FILE.exists():
            return True, "Warning: Archive DB (2025) not found."
    except Exception as e:
        return False, f"DB connection check error: {e}"
    return True, ""


def _parse_production_dt(series: pd.Series) -> pd.Series:
    """
    Parse Korean datetime format to pandas datetime.

    Handles formats like:
    - "2026-01-20 오전 10:30:00" -> 2026-01-20 10:30:00
    - "2026-01-20 오후 02:15:00" -> 2026-01-20 14:15:00
    - "2026-01-20 오전 12:30:00" -> 2026-01-20 00:30:00 (midnight)
    - "2026-01-20 오후 12:30:00" -> 2026-01-20 12:30:00 (noon)
    - "2026-01-20 14:30:00" -> 2026-01-20 14:30:00 (24h format passthrough)
    - Also handles English "AM"/"PM" format
    """
    # Match both Korean (오전/오후) and English (AM/PM) formats
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2})\s+(오전|오후|AM|PM)\s+(\d{1,2}):(\d{2}):(\d{2})"
    )

    def convert_korean_time(val) -> str:
        """Convert Korean AM/PM format to 24-hour format."""
        if pd.isna(val):
            return val
        val_str = str(val)
        match = pattern.match(val_str)
        if not match:
            return val_str  # Return as-is for other formats (e.g., 24h format)

        date_part, ampm, hour_str, minute, second = match.groups()
        hour = int(hour_str)

        # Handle both Korean and English AM/PM
        is_am = ampm in ("오전", "AM")

        if is_am:
            # AM 12 = 00 (midnight), AM 1-11 = 1-11
            if hour == 12:
                hour = 0
        else:  # PM/오후
            # PM 12 = 12 (noon), PM 1-11 = 13-23
            if hour != 12:
                hour += 12

        return f"{date_part} {hour:02d}:{minute}:{second}"

    s = series.apply(convert_korean_time)
    dt = pd.to_datetime(s, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    dt2 = pd.to_datetime(series, errors="coerce", format="mixed")
    return dt.fillna(dt2)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


# ==========================================================
# Cached Data Loading
# ==========================================================
@st.cache_data(ttl=300)  # 5 minutes - product list rarely changes
def load_item_list(db_ver):
    with DBRouter.get_connection(use_archive=False) as conn:
        df = pd.read_sql(
            """
            SELECT item_code, MAX(item_name) AS item_name
            FROM production_records
            GROUP BY item_code
            ORDER BY item_code
        """,
            conn,
        )
    df["label"] = df["item_code"] + " | " + df["item_name"].fillna("")
    return df


@st.cache_data(ttl=60)  # 1 minute - real-time data needed
def load_records(
    item_codes: Optional[List[str]],
    keyword: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    limit: int,
    db_ver,
) -> Tuple[pd.DataFrame, int]:
    where = []
    params = []

    columns = "id, production_date, item_code, item_name, good_quantity, lot_number"

    if item_codes:
        where.append(f"item_code IN ({','.join(['?']*len(item_codes))})")
        params.extend(item_codes)
    if keyword:
        like = f"%{escape_like_wildcards(keyword)}%"
        where.append("(item_code LIKE ? OR item_name LIKE ? OR lot_number LIKE ?)")
        params.extend([like, like, like])
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    # Use DBRouter for consistent archive/live routing
    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None  # exclusive
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"

    final_sql, _unused_params = DBRouter.build_union_sql(
        select_columns=columns,
        where_clause=where_clause,
        targets=targets,
        order_by="production_date DESC, source DESC, id DESC",
        limit=int(limit),
        include_source=True,
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)

    df["good_quantity"] = pd.to_numeric(df["good_quantity"], errors="coerce")
    df["production_dt"] = _parse_production_dt(df["production_date"])
    df["production_day"] = df["production_dt"].dt.date
    df["year_month"] = df["production_dt"].dt.to_period("M").astype(str)
    bad = int(df["production_dt"].isna().sum())
    return df, bad


@st.cache_data(ttl=180)  # 3 minutes - aggregated data
def load_monthly_summary(date_from, date_to, db_ver):
    where, params = [], []
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"

    final_sql, _ = DBRouter.build_aggregation_sql(
        inner_select="substr(production_date, 1, 7) AS year_month, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where=where_clause,
        outer_select="year_month, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count, AVG(total_prod/cnt) AS avg_batch_size",
        outer_group_by="year_month",
        targets=targets,
        outer_order_by="year_month",
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)
    return df


@st.cache_data(ttl=180)
def load_daily_summary(date_from, date_to, db_ver):
    """Load daily aggregated production data."""
    where, params = [], []
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"

    final_sql, _ = DBRouter.build_aggregation_sql(
        inner_select="substr(production_date, 1, 10) AS production_day, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where=where_clause,
        outer_select="production_day, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count",
        outer_group_by="production_day",
        targets=targets,
        outer_order_by="production_day",
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)
    return df


@st.cache_data(ttl=180)
def load_weekly_summary(date_from, date_to, db_ver):
    """Load weekly aggregated production data."""
    where, params = [], []
    if date_from:
        where.append("production_date >= ?")
        params.append(_iso(date_from))
    if date_to:
        next_day = date_to + timedelta(days=1)
        where.append("production_date < ?")
        params.append(_iso(next_day))

    date_from_str = _iso(date_from) if date_from else None
    date_to_str = _iso(date_to + timedelta(days=1)) if date_to else None
    targets = DBRouter.pick_targets(date_from_str, date_to_str)

    where_clause = " AND ".join(where) if where else "1=1"

    week_expr = "substr(production_date, 1, 4) || '-W' || printf('%02d', (strftime('%j', production_date) - 1) / 7 + 1)"

    final_sql, _ = DBRouter.build_aggregation_sql(
        inner_select=f"{week_expr} AS year_week, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where=where_clause,
        outer_select="year_week, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count",
        outer_group_by="year_week",
        targets=targets,
        outer_order_by="year_week",
    )
    query_params = DBRouter.build_query_params(params, targets)

    with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
        df = pd.read_sql(final_sql, conn, params=query_params)
    return df


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()


@st.cache_data(show_spinner=False)
def _cached_excel_bytes(df: pd.DataFrame) -> bytes:
    """Generate Excel bytes once per unique DataFrame (lazy, cached)."""
    return to_excel_bytes(df)


# ==========================================================
# Filter State Helpers (session_state based)
# ==========================================================
def get_filter_state() -> dict:
    """Get current filter state from session_state['_filters'] dict."""
    filters = st.session_state.get("_filters", {})
    return {
        "item_codes": filters.get("item_codes"),
        "keyword": filters.get("keyword"),
        "date_from": filters.get("date_from"),
        "date_to": filters.get("date_to"),
        "limit": filters.get("limit", 5000),
        "db_ver": get_db_mtime(),
    }
