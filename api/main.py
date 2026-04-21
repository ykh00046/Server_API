from __future__ import annotations

import datetime as dt
import itertools
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse

# Add parent directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    DB_FILE,
    ARCHIVE_DB_FILE,
    ARCHIVE_CUTOFF_DATE,
    DATABASE_DIR,
    DBRouter,
    DBTargets,
    setup_logging,
    get_logger,
    api_cache,
    get_cache_stats,
    api_rate_limiter,
)
from shared.validators import (
    validate_date_range as _validate_date_range_pure,
    validate_length as _validate_length_pure,
    escape_like_wildcards,
)
from shared.logging_config import QueryLogger, set_request_id
from shared.config import CORS_ORIGINS
from shared.metrics import performance_monitor
from shared.rate_limiter import RateLimiter

from . import chat  # Import chat module
from . import _session_store as _sstore


# ==========================================================
# AI Health Check Cache (Section 6.4) - Thread-safe
# ==========================================================
_ai_health_cache = {
    "status": "unknown",
    "last_check": 0,
    "message": "Not checked yet"
}
_ai_health_cache_lock = threading.Lock()
AI_HEALTH_CACHE_TTL = 600  # 10 minutes

# ==========================================================
# Logging Setup
# ==========================================================
setup_logging()
logger = get_logger(__name__)

# ==========================================================
# FastAPI App (v7: ORJSONResponse + GZip + CORS)
# ==========================================================
app = FastAPI(
    title="Production Data API",
    default_response_class=ORJSONResponse,  # Faster JSON serialization
)
app.add_middleware(GZipMiddleware, minimum_size=500)  # Compress responses > 500 bytes

# CORS — allows future web frontend (React/Next.js) to call this API
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)


# ==========================================================
# Middleware for Request ID and Rate Limiting
# ==========================================================
# 요청 카운터 for 주기적 cleanup (GIL-safe itertools.count — no lock needed)
_request_counter = itertools.count()
_CLEANUP_INTERVAL = 100


@app.middleware("http")
async def add_request_id_and_rate_limit(request, call_next):
    """Add request ID and apply rate limiting to API endpoints."""
    request_id = set_request_id()

    # Skip rate limiting for health checks
    if request.url.path in ["/", "/healthz", "/healthz/ai", "/docs", "/openapi.json"]:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Apply rate limiting to API endpoints (except /chat which has its own limiter)
    if request.url.path.startswith("/chat"):
        # Chat has its own rate limiter in the endpoint
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # General API rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not api_rate_limiter.is_allowed(client_ip):
        retry_after = api_rate_limiter.retry_after(client_ip)
        logger.warning(
            f"[Rate Limited] ip={client_ip} | path={request.url.path} | "
            f"retry_after={retry_after}s"
        )
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded. Try again in {retry_after} seconds."},
            headers={
                "Retry-After": str(retry_after),
                "X-Request-ID": request_id,
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
            }
        )

    # Add rate limit headers to response
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-RateLimit-Limit"] = "60"
    response.headers["X-RateLimit-Remaining"] = str(api_rate_limiter.remaining(client_ip))

    # Periodic cleanup (every 100 requests — no lock needed with itertools.count)
    should_cleanup = next(_request_counter) % _CLEANUP_INTERVAL == 0

    if should_cleanup:
        removed = api_rate_limiter.cleanup()
        if removed > 0:
            logger.debug(f"[Rate Limiter Cleanup] Removed {removed} expired IPs")

    return response


# ==========================================================
# Helpers
# ==========================================================
def _normalize_date(date_str: str | None, add_days: int = 0) -> str | None:
    """
    Normalize date string to 'YYYY-MM-DD' format.
    Optionally add days (for inclusive end date handling).

    Raises:
        HTTPException: If date_str is not in valid YYYY-MM-DD format.
    """
    if not date_str:
        return None
    try:
        d = dt.date.fromisoformat(date_str)
        if add_days:
            d = d + dt.timedelta(days=add_days)
        return d.isoformat()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD (e.g., 2026-01-15)."
        )


def _validate_date_range(date_from: str | None, date_to: str | None) -> None:
    """Validate date_from <= date_to. Wraps shared validator with HTTPException."""
    if not date_from or not date_to:
        return
    try:
        _validate_date_range_pure(date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _validate_length(value: str | None, max_length: int, field_name: str) -> str | None:
    """Validate string length. Wraps shared validator with HTTPException."""
    try:
        return _validate_length_pure(value, max_length, field_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================
# v7: Cursor Pagination Helpers
# ==========================================================
import base64
import json


def _encode_cursor(production_date: str, record_id: int, source: str) -> str:
    """Encode cursor as base64 JSON."""
    cursor_data = {"d": production_date, "id": record_id, "src": source}
    return base64.urlsafe_b64encode(json.dumps(cursor_data).encode()).decode()


def _decode_cursor(cursor: str) -> dict | None:
    """Decode base64 JSON cursor. Returns None if invalid."""
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(decoded)
    except Exception:
        return None


# ==========================================================
# Routes
# ==========================================================
@app.get("/")
def read_root():
    return {"status": "active", "system": "Production Data Hub API"}


@app.get("/metrics/performance")
def metrics_performance():
    """Rolling-window query performance metrics (count / avg / p50 / p95 / p99 / cache_hit_rate)."""
    return performance_monitor.get_all_stats()


@app.get("/metrics/cache")
def metrics_cache():
    """Combined cache + performance snapshot for monitoring."""
    return {
        "api_cache": get_cache_stats(),
        "performance": performance_monitor.get_all_stats(),
    }


@app.get("/healthz")
def health_check():
    """
    API health check endpoint (lightweight).
    AI check uses cached status - call /healthz/ai for fresh check.
    """
    status = {
        "status": "ok",
        "timestamp": dt.datetime.now().isoformat(),
    }

    # Database check
    try:
        with DBRouter.get_connection(use_archive=False) as conn:
            conn.execute("SELECT 1").fetchone()
        status["database"] = "connected"

        # Add DB file info
        if DB_FILE.exists():
            status["db_size_mb"] = round(DB_FILE.stat().st_size / (1024 * 1024), 2)
    except Exception as e:
        status["status"] = "degraded"
        status["database"] = f"error: {e}"

    # Archive DB check
    if ARCHIVE_DB_FILE.exists():
        status["archive_db"] = "available"
        status["archive_size_mb"] = round(ARCHIVE_DB_FILE.stat().st_size / (1024 * 1024), 2)
    else:
        status["archive_db"] = "not_found"

    # AI API check (cached, lightweight)
    api_key_exists = bool(os.getenv("GEMINI_API_KEY"))
    status["ai_api"] = {
        "key_configured": api_key_exists,
        "cached_status": _ai_health_cache["status"],
        "last_check_age_sec": int(time.time() - _ai_health_cache["last_check"]) if _ai_health_cache["last_check"] > 0 else None
    }

    # v7: API Cache stats
    status["cache"] = get_cache_stats()

    # Disk space check
    try:
        disk_stat = os.statvfs(str(DATABASE_DIR)) if hasattr(os, 'statvfs') else None
        if disk_stat:
            free_gb = (disk_stat.f_frsize * disk_stat.f_bavail) / (1024**3)
            status["disk_free_gb"] = round(free_gb, 2)
    except Exception:
        # Windows doesn't have statvfs, use shutil
        try:
            import shutil
            total, used, free = shutil.disk_usage(str(DATABASE_DIR))
            status["disk_free_gb"] = round(free / (1024**3), 2)
        except Exception:
            pass

    return status


@app.get("/healthz/ai")
async def ai_health_check():
    """
    AI API health check with actual ping (cached for 10 minutes).
    Use this sparingly to avoid quota consumption.
    """
    # Check cache validity (thread-safe read)
    with _ai_health_cache_lock:
        cache_age = time.time() - _ai_health_cache["last_check"]
        if cache_age < AI_HEALTH_CACHE_TTL and _ai_health_cache["status"] != "unknown":
            return {
                "status": _ai_health_cache["status"],
                "message": _ai_health_cache["message"],
                "cached": True,
                "cache_age_sec": int(cache_age),
                "cache_ttl_sec": AI_HEALTH_CACHE_TTL,
                "sessions": _sstore.stats(),
            }

    # Perform actual check
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "error",
                "last_check": time.time(),
                "message": "API key not configured"
            })
        return {
            "status": "error",
            "message": "GEMINI_API_KEY not configured",
            "cached": False,
            "sessions": _sstore.stats(),
        }

    try:
        from google import genai
        from google.genai.errors import ClientError, ServerError

        client = genai.Client(api_key=api_key)

        # Lightweight ping - just list models (doesn't consume quota)
        models = client.models.list()
        model_count = sum(1 for _ in models)

        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "ok",
                "last_check": time.time(),
                "message": f"Connected, {model_count} models available"
            })

        return {
            "status": "ok",
            "message": _ai_health_cache["message"],
            "cached": False,
            "sessions": _sstore.stats(),
        }

    except ClientError as e:
        error_msg = f"Client error: {e}"
        status = "error"
        if "429" in str(e):
            error_msg = "Rate limited (quota may be exhausted)"
            status = "rate_limited"

        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": status,
                "last_check": time.time(),
                "message": error_msg
            })

        return {
            "status": status,
            "message": error_msg,
            "cached": False,
            "sessions": _sstore.stats(),
        }

    except ServerError as e:
        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "degraded",
                "last_check": time.time(),
                "message": f"Server error: {e}"
            })
        return {
            "status": "degraded",
            "message": str(e),
            "cached": False,
            "sessions": _sstore.stats(),
        }

    except Exception as e:
        with _ai_health_cache_lock:
            _ai_health_cache.update({
                "status": "error",
                "last_check": time.time(),
                "message": str(e)
            })
        return {
            "status": "error",
            "message": str(e),
            "cached": False,
            "sessions": _sstore.stats(),
        }


@app.get("/records")
def get_records(
    item_code: str | None = Query(default=None, max_length=50, description="Item code filter"),
    q: str | None = Query(default=None, max_length=100, description="Search query"),
    lot_number: str | None = Query(default=None, max_length=50, description="Lot number prefix filter (e.g., LT2026)"),
    date_from: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    min_quantity: int | None = Query(default=None, ge=0, description="Minimum good_quantity"),
    max_quantity: int | None = Query(default=None, ge=0, description="Maximum good_quantity"),
    limit: int = Query(default=1000, ge=1, le=5000),  # v7: 상한 조정 (20000→5000)
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
    # Normalize dates
    date_from_n = _normalize_date(date_from)
    date_to_n = _normalize_date(date_to, add_days=1)  # inclusive -> exclusive

    # Validate date range (date_from_n is the original, date_to_n has +1 day)
    _validate_date_range(date_from_n, date_to_n if not date_to_n else date_to)

    # Determine target DBs (Section 6.1)
    targets = DBRouter.pick_targets(date_from_n, date_to_n)

    # Build WHERE conditions
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
        params.append(f"{escape_like_wildcards(lot_number)}%")  # prefix match for index usage

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

    # v7: Cursor-based pagination
    cursor_data = None
    if cursor:
        cursor_data = _decode_cursor(cursor)
        if cursor_data:
            # Keyset pagination: (production_date, source, id) < (cursor_d, cursor_src, cursor_id)
            # Using string comparison for composite sort
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

    # Build UNION query with source column (Section 6.2)
    select_columns = "id, production_date, lot_number, item_code, item_name, good_quantity"

    with QueryLogger("records", targets, logger) as ql:
        # v7: Fixed sort order for cursor pagination
        sort_order = "production_date DESC, source DESC, id DESC"

        if cursor_data:
            # Cursor mode: no offset needed
            sql, params_doubled = DBRouter.build_union_sql(
                select_columns=select_columns,
                where_clause=where_clause,
                targets=targets,
                order_by=sort_order,
                limit=limit + 1,  # Fetch one extra to check if there's more
                include_source=True
            )
            query_params = DBRouter.build_query_params(params, targets)
            all_results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)

            has_more = len(all_results) > limit
            results = all_results[:limit]
        else:
            # Legacy offset mode (backward compatibility)
            # P0-3: Push OFFSET into SQL instead of Python-side slicing
            sql, params_doubled = DBRouter.build_union_sql(
                select_columns=select_columns,
                where_clause=where_clause,
                targets=targets,
                order_by=sort_order,
                limit=limit + 1,  # Fetch one extra to check if there's more
                include_source=True
            )
            if offset > 0:
                sql += f" OFFSET {int(offset)}"
            query_params = DBRouter.build_query_params(params, targets)
            all_results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)

            has_more = len(all_results) > limit
            results = all_results[:limit]

        ql.set_row_count(len(results))

    # v7: Build next_cursor
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


@app.get("/records/{item_code}")
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


@app.get("/items")
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


@app.get("/summary/monthly_total")
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

    # Validate date range
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


@app.get("/summary/by_item")
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

    # Validate date range
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


@app.get("/summary/monthly_by_item")
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
