"""Records / items endpoints.

Moved from api/main.py during api-router-split (2026-05-22). Cursor encoding
helpers live with the routes that use them.
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from fastapi import APIRouter, Query

from shared import (
    ARCHIVE_DB_FILE,
    DBRouter,
    DBTargets,
    api_cache,
    get_logger,
)
from shared.logging_config import QueryLogger
from shared.validators import escape_like_wildcards

from .._http_helpers import _normalize_date, _validate_date_range

logger = get_logger(__name__)
router = APIRouter()


# ==========================================================
# v7: Cursor Pagination Helpers
# ==========================================================
def _encode_cursor(production_date: str, record_id: int, source: str) -> str:
    """Encode cursor as base64 JSON."""
    cursor_data = {"d": production_date, "id": record_id, "src": source}
    return base64.urlsafe_b64encode(json.dumps(cursor_data).encode()).decode()


def _decode_cursor(cursor: str) -> dict | None:
    """Decode base64 JSON cursor. Returns None if invalid."""
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


@router.get("/records")
def get_records(
    item_code: str | None = Query(default=None, max_length=50, description="Item code filter"),
    q: str | None = Query(default=None, max_length=100, description="Search query"),
    lot_number: str | None = Query(default=None, max_length=50, description="Lot number prefix filter (e.g., LT2026)"),
    date_from: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    min_quantity: int | None = Query(default=None, ge=0, description="Minimum good_quantity"),
    max_quantity: int | None = Query(default=None, ge=0, description="Maximum good_quantity"),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0, description="Deprecated: Use cursor instead"),
    cursor: str | None = Query(default=None, description="v7: Cursor for pagination (base64 JSON)"),
):
    """
    Query production records with filters.
    Automatically routes to Archive/Live DB based on date range.

    v7 Enhancement:
    - Cursor-based pagination (recommended for large datasets)
    - offset is deprecated but still supported for backward compatibility
    - Input validation for length constraints and date range
    """
    date_from_n = _normalize_date(date_from)
    date_to_n = _normalize_date(date_to, add_days=1)

    _validate_date_range(date_from_n, date_to_n if not date_to_n else date_to)

    targets = DBRouter.pick_targets(date_from_n, date_to_n)

    where = []
    params: list[Any] = []

    if item_code:
        where.append("item_code = ?")
        params.append(item_code)

    if q:
        like = f"%{escape_like_wildcards(q)}%"
        where.append("(item_code LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\' OR lot_number LIKE ? ESCAPE '\\')")
        params.extend([like, like, like])

    if lot_number:
        where.append("lot_number LIKE ? ESCAPE '\\'")
        params.append(f"{escape_like_wildcards(lot_number)}%")

    if date_from_n:
        where.append("production_date >= ?")
        params.append(date_from_n)

    if date_to_n:
        where.append("production_date < ?")
        params.append(date_to_n)

    if min_quantity is not None:
        where.append("good_quantity >= ?")
        params.append(min_quantity)

    if max_quantity is not None:
        where.append("good_quantity <= ?")
        params.append(max_quantity)

    cursor_data = None
    if cursor:
        cursor_data = _decode_cursor(cursor)
        if cursor_data:
            where.append(
                "(production_date < ? OR "
                "(production_date = ? AND source < ?) OR "
                "(production_date = ? AND source = ? AND id < ?))"
            )
            params.extend([
                cursor_data["d"],
                cursor_data["d"], cursor_data["src"],
                cursor_data["d"], cursor_data["src"], cursor_data["id"]
            ])

    where_clause = " AND ".join(where) if where else "1=1"

    select_columns = "id, production_date, lot_number, item_code, item_name, good_quantity"

    with QueryLogger("records", targets, logger) as ql:
        sort_order = "production_date DESC, source DESC, id DESC"

        if cursor_data:
            sql, params_doubled = DBRouter.build_union_sql(
                select_columns=select_columns,
                where_clause=where_clause,
                targets=targets,
                order_by=sort_order,
                limit=limit + 1,
                include_source=True
            )
            query_params = DBRouter.build_query_params(params, targets)
            all_results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)

            has_more = len(all_results) > limit
            results = all_results[:limit]
        else:
            if offset > 0:
                logger.warning(
                    f"[Deprecated] /records called with offset={int(offset)} — "
                    f"use cursor pagination instead (cursor=...)"
                )
            sql, params_doubled = DBRouter.build_union_sql(
                select_columns=select_columns,
                where_clause=where_clause,
                targets=targets,
                order_by=sort_order,
                limit=limit + 1,
                include_source=True
            )
            if offset > 0:
                sql += f" OFFSET {int(offset)}"
            query_params = DBRouter.build_query_params(params, targets)
            all_results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)

            has_more = len(all_results) > limit
            results = all_results[:limit]

        ql.set_row_count(len(results))

    next_cursor = None
    if has_more and results:
        last = results[-1]
        next_cursor = _encode_cursor(last["production_date"], last["id"], last["source"])

    return {
        "data": results,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "count": len(results)
    }


@api_cache("records_item")
def _get_item_records_cached(item_code: str, limit: int) -> list[dict]:
    """Cached internal function for get_item_records."""
    targets = DBTargets(use_archive=ARCHIVE_DB_FILE.exists(), use_live=True)

    select_columns = "id, production_date, lot_number, item_code, item_name, good_quantity"
    where_clause = "item_code = ?"
    params = [item_code]

    with QueryLogger("records_by_item", targets, logger) as ql:
        ql.add_info("item_code", item_code)

        sql, _ = DBRouter.build_union_sql(
            select_columns=select_columns,
            where_clause=where_clause,
            targets=targets,
            order_by="production_date DESC, source DESC, id DESC",
            limit=limit,
            include_source=True
        )

        query_params = DBRouter.build_query_params(params, targets)
        results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        ql.set_row_count(len(results))

    return results


@router.get("/records/{item_code}")
def get_item_records(item_code: str, limit: int = 5000):
    """Get production records for a specific item code (all time periods)."""
    return _get_item_records_cached(item_code, limit)


@api_cache("items")
def _list_items_cached(q: str | None, limit: int) -> list[dict]:
    """Cached internal function for list_items."""
    where = ""
    params: list[Any] = []

    if q:
        like = f"%{escape_like_wildcards(q)}%"
        where = "WHERE item_code LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\'"
        params.extend([like, like])

    sql = f"""
    SELECT
        item_code,
        MAX(item_name) AS item_name,
        COUNT(*) AS record_count
    FROM production_records
    {where}
    GROUP BY item_code
    ORDER BY record_count DESC, item_code
    LIMIT ?
    """
    params.append(int(limit))

    with QueryLogger("items", "live_only", logger) as ql:
        results = DBRouter.query(sql, params, use_archive=False)
        ql.set_row_count(len(results))

    return results


@router.get("/items")
def list_items(
    q: str | None = Query(default=None, max_length=100, description="Search query"),
    limit: int = Query(default=200, ge=1, le=2000)
):
    """
    List products/items with record counts.
    Queries Live DB only for performance (discontinued products may be excluded).
    v7: Cached with db_mtime invalidation.
    v9: Added input length constraints.
    """
    return _list_items_cached(q, limit)
