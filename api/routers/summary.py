"""Aggregated /summary/* endpoints.

Moved from api/main.py during api-router-split (2026-05-22).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from shared import (
    DBRouter,
    DBTargets,
    api_cache,
    get_logger,
)
from shared.logging_config import QueryLogger

from .._http_helpers import _normalize_date, _validate_date_range

logger = get_logger(__name__)
router = APIRouter()


@api_cache("monthly_total")
def _monthly_total_cached(date_from_n: str | None, date_to_n: str | None) -> list[dict]:
    """Cached internal function for monthly_total."""
    targets = DBRouter.pick_targets(date_from_n, date_to_n)

    where = []
    params: list[Any] = []

    if date_from_n:
        where.append("production_date >= ?")
        params.append(date_from_n)
    if date_to_n:
        where.append("production_date < ?")
        params.append(date_to_n)

    where_clause = " AND ".join(where) if where else "1=1"

    with QueryLogger("monthly_total", targets, logger) as ql:
        sql, params_doubled = DBRouter.build_aggregation_sql(
            inner_select="substr(production_date, 1, 7) AS year_month, SUM(good_quantity) AS total, COUNT(*) AS cnt, AVG(good_quantity) AS avg_val",
            inner_where=where_clause,
            outer_select="year_month, SUM(total) AS total_production, SUM(cnt) AS batch_count, AVG(avg_val) AS avg_batch_size",
            outer_group_by="year_month",
            targets=targets,
            outer_order_by="year_month"
        )

        query_params = DBRouter.build_query_params(params, targets)
        results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        ql.set_row_count(len(results))

    return results


@router.get("/summary/monthly_total")
def monthly_total(
    date_from: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
):
    """
    Monthly production totals with optimized aggregation (Section B.1).
    Pre-aggregates in each DB before merging for better performance.
    v7: Cached with db_mtime invalidation.
    v8: Added date range validation.
    """
    date_from_n = _normalize_date(date_from)
    date_to_n = _normalize_date(date_to, add_days=1)

    _validate_date_range(date_from_n, date_to_n if not date_to_n else date_to)

    return _monthly_total_cached(date_from_n, date_to_n)


@api_cache("summary_by_item")
def _summary_by_item_cached(
    date_from_n: str, date_to_n: str,
    item_code: str | None, limit: int
) -> dict:
    """Cached internal function for summary_by_item."""
    targets = DBRouter.pick_targets(date_from_n, date_to_n)

    where = ["production_date >= ?", "production_date < ?"]
    params: list[Any] = [date_from_n, date_to_n]

    if item_code:
        where.append("item_code = ?")
        params.append(item_code)

    where_clause = " AND ".join(where)

    with QueryLogger("summary_by_item", targets, logger) as ql:
        sql, _ = DBRouter.build_aggregation_sql(
            inner_select="item_code, MAX(item_name) AS item_name, SUM(good_quantity) AS total, COUNT(*) AS cnt",
            inner_where=where_clause,
            outer_select="item_code, MAX(item_name) AS item_name, SUM(total) AS total_production, SUM(cnt) AS batch_count",
            outer_group_by="item_code",
            targets=targets,
            outer_order_by="total_production DESC",
            limit=limit
        )

        query_params = DBRouter.build_query_params(params, targets)
        results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        ql.set_row_count(len(results))

    return {
        "data": results,
        "count": len(results),
        "date_range": {"from": date_from_n, "to": date_to_n}
    }


@router.get("/summary/by_item")
def summary_by_item(
    date_from: str = Query(..., description="YYYY-MM-DD (inclusive, required)"),
    date_to: str = Query(..., description="YYYY-MM-DD (inclusive, required)"),
    item_code: str | None = Query(default=None, max_length=50, description="Filter by specific item"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """
    Production summary by item for arbitrary date range.
    Returns aggregated totals per item (no monthly breakdown).
    v8: Cached with db_mtime invalidation.
    v9: Added date range validation and input length constraints.
    """
    date_from_n = _normalize_date(date_from)
    date_to_n = _normalize_date(date_to, add_days=1)

    _validate_date_range(date_from_n, date_to_n if not date_to_n else date_to)

    return _summary_by_item_cached(date_from_n, date_to_n, item_code, limit)


@api_cache("monthly_by_item")
def _monthly_by_item_cached(
    year_month: str | None, item_code: str | None, limit: int
) -> list[dict]:
    """Cached internal function for monthly_by_item."""
    if year_month:
        year, month = map(int, year_month.split("-"))
        if month == 12:
            next_month_first = f"{year + 1}-01-01"
        else:
            next_month_first = f"{year}-{month + 1:02d}-01"
        targets = DBRouter.pick_targets(f"{year_month}-01", next_month_first)
    else:
        targets = DBTargets(use_archive=True, use_live=True)

    where = []
    params: list[Any] = []

    if year_month:
        where.append("substr(production_date, 1, 7) = ?")
        params.append(year_month)

    if item_code:
        where.append("item_code = ?")
        params.append(item_code)

    where_clause = " AND ".join(where) if where else "1=1"

    with QueryLogger("monthly_by_item", targets, logger) as ql:
        sql, _ = DBRouter.build_aggregation_sql(
            inner_select="substr(production_date, 1, 7) AS year_month, item_code, MAX(item_name) AS item_name, SUM(good_quantity) AS total, COUNT(*) AS cnt, AVG(good_quantity) AS avg_val",
            inner_where=where_clause,
            outer_select="year_month, item_code, MAX(item_name) AS item_name, SUM(total) AS total_production, SUM(cnt) AS batch_count, AVG(avg_val) AS avg_batch_size",
            outer_group_by="year_month, item_code",
            targets=targets,
            outer_order_by="year_month DESC, total_production DESC",
            limit=limit
        )

        query_params = DBRouter.build_query_params(params, targets)
        results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        ql.set_row_count(len(results))

    return results


@router.get("/summary/monthly_by_item")
def monthly_by_item(
    year_month: str | None = Query(default=None, max_length=7, pattern=r"^\d{4}-\d{2}$", description="e.g., 2026-01"),
    item_code: str | None = Query(default=None, max_length=50, description="Filter by item code"),
    limit: int = Query(default=5000, ge=1, le=50000),
):
    """
    Monthly production summary by item.
    v8: Cached with db_mtime invalidation.
    v9: Added input length constraints.
    """
    return _monthly_by_item_cached(year_month, item_code, limit)
