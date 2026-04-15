# api/tools.py
"""
Production Data Hub - AI Tool Functions

These functions are called by Gemini AI to query production data.
Uses shared DBRouter for consistent Archive/Live handling.

Note: Do NOT use 'from __future__ import annotations' here.
Gemini SDK requires actual type hints, not stringified ones.
"""

import re
import sys
import concurrent.futures
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Add parent directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    ARCHIVE_DB_FILE,
    ARCHIVE_CUTOFF_DATE,
    DBRouter,
    DBTargets,
    get_logger,
)
from shared.cache import api_cache
from shared.logging_config import QueryLogger
from shared.validators import (
    validate_date_range_exclusive,
    validate_db_path,
    resolve_archive_db,
    escape_like_wildcards,
)

logger = get_logger(__name__)


# ==========================================================
# Helpers
# ==========================================================
def _validate_date_range(date_from: str, date_to: str) -> tuple[str, str]:
    """Validate date range and return (date_from, next_day). Delegates to shared.validators."""
    return validate_date_range_exclusive(date_from, date_to)


# ==========================================================
# AI Tools
# ==========================================================

@api_cache("search_items")
def search_production_items(
    keyword: str,
    include_archive: bool = True  # Section 6.5: Default True for accurate answers
) -> Dict[str, Any]:
    """
    Search for product codes (item_code) matching the given keyword.
    AI should use this tool first when the user mentions a product by name.

    Args:
        keyword: Search keyword (product name or code fragment)
        include_archive: If True, also search discontinued products in Archive DB
                        (Default: True - for accurate historical queries)

    Returns:
        Dict with found items and their record counts
    """
    try:
        like_keyword = f"%{escape_like_wildcards(keyword)}%"

        if include_archive and ARCHIVE_DB_FILE.exists():
            # Search both Archive and Live, then merge results
            targets = DBTargets(use_archive=True, use_live=True)

            sql = """
                SELECT item_code, item_name, SUM(record_count) as record_count
                FROM (
                    SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
                    FROM archive.production_records
                    WHERE (item_code LIKE ? OR item_name LIKE ?)
                    GROUP BY item_code

                    UNION ALL

                    SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
                    FROM production_records
                    WHERE (item_code LIKE ? OR item_name LIKE ?)
                    GROUP BY item_code
                )
                GROUP BY item_code
                ORDER BY record_count DESC
                LIMIT 10
            """
            params = [like_keyword, like_keyword, like_keyword, like_keyword]
        else:
            # Live DB only
            targets = DBTargets(use_archive=False, use_live=True)

            sql = """
                SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
                FROM production_records
                WHERE item_code LIKE ? OR item_name LIKE ?
                GROUP BY item_code
                ORDER BY record_count DESC
                LIMIT 10
            """
            params = [like_keyword, like_keyword]

        with QueryLogger("search_items", targets, logger) as ql:
            ql.add_info("keyword", keyword)
            ql.add_info("include_archive", include_archive)

            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:

                rows = conn.execute(sql, params).fetchall()
                items = [dict(r) for r in rows]

            ql.set_row_count(len(items))

        result = {
            "status": "success",
            "search_keyword": keyword,
            "include_archive": include_archive,
            "found_items": items,
            "message": f"'{keyword}'와 유사한 제품 {len(items)}개를 찾았습니다." +
                       (" (단종 제품 포함)" if include_archive else " (현재 제품만)")
        }

        logger.info(f"[Tool] search_production_items: keyword='{keyword}' include_archive={include_archive} found={len(items)}")
        return result

    except Exception as e:
        logger.exception(f"[Tool Error] search_production_items failed: keyword='{keyword}'")
        return {"status": "error", "message": str(e)}


@api_cache("summary")
def get_production_summary(
    date_from: str,
    date_to: str,
    item_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get production statistics for a specified period.

    Args:
        date_from: Start date (YYYY-MM-DD), inclusive
        date_to: End date (YYYY-MM-DD), inclusive
        item_code: Exact product code (e.g., 'BW0021'). Use search_production_items first to find this.

    Returns:
        Dict with total_quantity, average_quantity, production_count
    """
    try:
        # Validate and convert date range
        date_from, next_day = _validate_date_range(date_from, date_to)

        # Determine target DBs
        targets = DBRouter.pick_targets(date_from, next_day)

        # Build WHERE clause
        where_parts = ["production_date >= ?", "production_date < ?"]
        params = [date_from, next_day]

        if item_code:
            where_parts.append("item_code = ?")
            params.append(item_code)

        where_clause = " AND ".join(where_parts)

        with QueryLogger("production_summary", targets, logger) as ql:
            ql.add_info("date_from", date_from)
            ql.add_info("date_to", date_to)
            if item_code:
                ql.add_info("item_code", item_code)

            # Build pre-aggregation query (Section B.1)
            sql, params_doubled = DBRouter.build_aggregation_sql(
                inner_select="SUM(good_quantity) AS total, COUNT(*) AS cnt, AVG(good_quantity) AS avg_val",
                inner_where=where_clause,
                outer_select="SUM(total) AS total, SUM(cnt) AS count, AVG(avg_val) AS average",
                outer_group_by="",  # No grouping needed for single row aggregation
                targets=targets
            )

            query_params = DBRouter.build_query_params(params, targets)

            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:

                row = conn.execute(sql, query_params).fetchone()
                res = dict(row) if row else {"total": 0, "count": 0, "average": 0}

            ql.set_row_count(res.get("count", 0))

        result = {
            "status": "success",
            "query_period": f"{date_from} ~ {date_to}",
            "item_code": item_code if item_code else "all",
            "db_targets": f"archive={targets.use_archive}, live={targets.use_live}",
            "data": {
                "total_quantity": res["total"] or 0,
                "average_quantity": round(res["average"], 2) if res["average"] else 0,
                "production_count": res["count"]
            }
        }

        logger.info(
            f"[Tool] get_production_summary: period={date_from}~{date_to} "
            f"item={item_code or 'all'} targets={targets} count={res['count']}"
        )
        return result

    except Exception as e:
        logger.exception(f"[Tool Error] get_production_summary failed: {date_from}~{date_to} item={item_code}")
        return {"status": "error", "message": str(e)}


@api_cache("monthly_trend")
def get_monthly_trend(
    date_from: str,
    date_to: str,
    item_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get monthly production trend (totals per month) for a specified period.

    Args:
        date_from: Start date (YYYY-MM-DD), inclusive
        date_to: End date (YYYY-MM-DD), inclusive
        item_code: Optional product code to filter the trend.

    Returns:
        Dict with list of monthly data (year_month, total_production, etc.)
    """
    try:
        # Validate and convert date range
        date_from, next_day = _validate_date_range(date_from, date_to)
        targets = DBRouter.pick_targets(date_from, next_day)

        where_parts = ["production_date >= ?", "production_date < ?"]
        params = [date_from, next_day]

        if item_code:
            where_parts.append("item_code = ?")
            params.append(item_code)

        where_clause = " AND ".join(where_parts)

        with QueryLogger("monthly_trend", targets, logger) as ql:
            ql.add_info("date_from", date_from)
            ql.add_info("date_to", date_to)
            if item_code:
                ql.add_info("item_code", item_code)

            sql, _ = DBRouter.build_aggregation_sql(
                inner_select="substr(production_date, 1, 7) AS year_month, SUM(good_quantity) AS total, COUNT(*) AS cnt",
                inner_where=where_clause,
                outer_select="year_month, SUM(total) AS total_production, SUM(cnt) AS batch_count",
                outer_group_by="year_month",
                targets=targets,
                outer_order_by="year_month"
            )

            query_params = DBRouter.build_query_params(params, targets)

            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:

                rows = conn.execute(sql, query_params).fetchall()
                trend = [dict(r) for r in rows]

            ql.set_row_count(len(trend))

        result = {
            "status": "success",
            "period": f"{date_from} ~ {date_to}",
            "item_code": item_code or "all",
            "trend": trend
        }
        logger.info(f"[Tool] get_monthly_trend: period={date_from}~{date_to} item={item_code or 'all'} months={len(trend)}")
        return result

    except Exception as e:
        logger.exception(f"[Tool Error] get_monthly_trend failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@api_cache("top_items")
def get_top_items(
    date_from: str,
    date_to: str,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Get the top produced items (by total quantity) for a specified period.

    Args:
        date_from: Start date (YYYY-MM-DD), inclusive
        date_to: End date (YYYY-MM-DD), inclusive
        limit: Number of top items to return (default: 5)

    Returns:
        Dict with list of top items (item_code, item_name, total_production)
    """
    try:
        # Validate and convert date range
        date_from, next_day = _validate_date_range(date_from, date_to)
        targets = DBRouter.pick_targets(date_from, next_day)

        where_clause = "production_date >= ? AND production_date < ?"
        params = [date_from, next_day]

        with QueryLogger("top_items", targets, logger) as ql:
            ql.add_info("date_from", date_from)
            ql.add_info("date_to", date_to)
            ql.add_info("limit", limit)

            sql, _ = DBRouter.build_aggregation_sql(
                inner_select="item_code, MAX(item_name) AS item_name, SUM(good_quantity) AS total",
                inner_where=where_clause,
                outer_select="item_code, MAX(item_name) AS item_name, SUM(total) AS total_production",
                outer_group_by="item_code",
                targets=targets,
                outer_order_by="total_production DESC",
                limit=limit
            )

            query_params = DBRouter.build_query_params(params, targets)

            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:

                rows = conn.execute(sql, query_params).fetchall()
                items = [dict(r) for r in rows]

            ql.set_row_count(len(items))

        result = {
            "status": "success",
            "period": f"{date_from} ~ {date_to}",
            "top_items": items
        }
        logger.info(f"[Tool] get_top_items: period={date_from}~{date_to} limit={limit} found={len(items)}")
        return result

    except Exception as e:
        logger.exception(f"[Tool Error] get_top_items failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@api_cache("compare_periods")
def compare_periods(
    period1_from: str,
    period1_to: str,
    period2_from: str,
    period2_to: str,
    item_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare production statistics between two periods.
    Use for questions like "이번 달 vs 저번 달", "올해 vs 작년", "1분기 vs 2분기", "전월 대비".

    Args:
        period1_from: Period 1 start date (YYYY-MM-DD), inclusive (주로 비교 기준이 되는 최신 기간)
        period1_to: Period 1 end date (YYYY-MM-DD), inclusive
        period2_from: Period 2 start date (YYYY-MM-DD), inclusive (주로 이전/기준 기간)
        period2_to: Period 2 end date (YYYY-MM-DD), inclusive
        item_code: Exact product code to filter. Use search_production_items first to find this.

    Returns:
        Dict with total_quantity, production_count, average for each period,
        plus quantity_diff and change_rate_pct comparing period1 vs period2.
    """
    try:
        p1_from, p1_next = _validate_date_range(period1_from, period1_to)
        p2_from, p2_next = _validate_date_range(period2_from, period2_to)

        def _query_stats(date_from: str, next_day: str) -> dict:
            targets = DBRouter.pick_targets(date_from, next_day)
            where_parts = ["production_date >= ?", "production_date < ?"]
            params = [date_from, next_day]
            if item_code:
                where_parts.append("item_code = ?")
                params.append(item_code)
            where_clause = " AND ".join(where_parts)

            sql, _ = DBRouter.build_aggregation_sql(
                inner_select="SUM(good_quantity) AS total, COUNT(*) AS cnt, AVG(good_quantity) AS avg_val",
                inner_where=where_clause,
                outer_select="SUM(total) AS total, SUM(cnt) AS count, AVG(avg_val) AS average",
                outer_group_by="",
                targets=targets,
            )
            query_params = DBRouter.build_query_params(params, targets)
            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
                row = conn.execute(sql, query_params).fetchone()
            return dict(row) if row else {"total": 0, "count": 0, "average": 0}

        with QueryLogger("compare_periods", DBTargets(use_archive=True, use_live=True), logger) as ql:
            ql.add_info("period1", f"{p1_from}~{period1_to}")
            ql.add_info("period2", f"{p2_from}~{period2_to}")
            if item_code:
                ql.add_info("item_code", item_code)

            # P1-1: Run both period queries in parallel (each uses its own thread-local conn)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(_query_stats, p1_from, p1_next)
                f2 = executor.submit(_query_stats, p2_from, p2_next)
                r1 = f1.result()
                r2 = f2.result()
            ql.set_row_count(2)

        t1 = r1.get("total") or 0
        t2 = r2.get("total") or 0
        diff = t1 - t2
        change_rate = round(diff / t2 * 100, 1) if t2 else None

        result = {
            "status": "success",
            "item_code": item_code or "all",
            "period1": {
                "range": f"{period1_from} ~ {period1_to}",
                "total_quantity": t1,
                "production_count": r1.get("count") or 0,
                "average_quantity": round(r1.get("average") or 0, 2),
            },
            "period2": {
                "range": f"{period2_from} ~ {period2_to}",
                "total_quantity": t2,
                "production_count": r2.get("count") or 0,
                "average_quantity": round(r2.get("average") or 0, 2),
            },
            "comparison": {
                "quantity_diff": diff,
                "change_rate_pct": change_rate,
                "direction": "증가" if diff > 0 else ("감소" if diff < 0 else "동일"),
            },
        }

        logger.info(
            f"[Tool] compare_periods: p1={p1_from}~{period1_to} p2={p2_from}~{period2_to} "
            f"item={item_code or 'all'} t1={t1} t2={t2} diff={diff}"
        )
        return result

    except Exception as e:
        logger.exception(f"[Tool Error] compare_periods failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@api_cache("item_history")
def get_item_history(
    item_code: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get the most recent production records for a specific item.
    Use for questions like "BW0021 최근 생산 이력", "XXX 마지막 10건", "최근에 언제 만들었어".

    Args:
        item_code: Exact product code (e.g., 'BW0021'). Use search_production_items first to find this.
        limit: Number of records to return (default: 10, max: 50)

    Returns:
        Dict with list of records sorted by date (newest first),
        each containing production_date, lot_number, good_quantity, source.
    """
    try:
        limit = max(1, min(limit, 50))

        # Always include archive to allow full history retrieval
        targets = DBTargets(use_archive=ARCHIVE_DB_FILE.exists(), use_live=True)

        where_clause = "item_code = ?"
        params = [item_code]

        with QueryLogger("item_history", targets, logger) as ql:
            ql.add_info("item_code", item_code)
            ql.add_info("limit", limit)

            sql, _ = DBRouter.build_union_sql(
                select_columns="production_date, lot_number, good_quantity",
                where_clause=where_clause,
                targets=targets,
                order_by="production_date DESC, source DESC",
                limit=limit,
            )

            query_params = DBRouter.build_query_params(params, targets)

            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
                rows = conn.execute(sql, query_params).fetchall()
                records = [dict(r) for r in rows]

            ql.set_row_count(len(records))

        result = {
            "status": "success",
            "item_code": item_code,
            "record_count": len(records),
            "records": records,
            "message": (
                f"'{item_code}' 최근 생산 이력 {len(records)}건 조회 완료"
                if records else
                f"'{item_code}'의 생산 이력이 없습니다."
            ),
        }

        logger.info(f"[Tool] get_item_history: item_code={item_code} limit={limit} found={len(records)}")
        return result

    except Exception as e:
        logger.exception(f"[Tool Error] get_item_history failed: item_code={item_code}")
        return {"status": "error", "message": str(e)}


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comments (block and line) to prevent validation bypass."""
    sql = re.sub(r'/\*.*?\*/', ' ', sql, flags=re.DOTALL)  # block comments
    sql = re.sub(r'--[^\n]*', ' ', sql)                      # line comments
    return sql.strip()


def execute_custom_query(
    sql: str,
    description: str = ""
) -> Dict[str, Any]:
    """
    Execute a custom SQL query for flexible data analysis.
    Use this tool when other tools cannot handle complex filtering conditions
    (e.g., lot_number patterns, multiple conditions, custom aggregations).

    IMPORTANT RULES:
    - Only SELECT queries are allowed (database is read-only)
    - Only 'production_records' table is available
    - Available columns: production_date, item_code, item_name, good_quantity, lot_number
    - Always include LIMIT clause (max 1000 rows)
    - For date ranges spanning multiple years, use UNION ALL with archive.production_records

    Args:
        sql: The SELECT SQL query to execute
        description: Brief description of what this query does (for logging)

    Returns:
        Dict with query results or error message

    Example queries:
        - "SELECT SUM(good_quantity) as total FROM production_records WHERE item_code = 'BW0021' AND lot_number LIKE '2%' AND production_date >= '2026-01-20'"
        - "SELECT lot_number, SUM(good_quantity) as qty FROM production_records WHERE item_code = 'ABC001' GROUP BY lot_number ORDER BY qty DESC LIMIT 10"
    """
    import sqlite3
    import threading
    from shared.config import (
        DB_FILE,
        ARCHIVE_DB_FILE,
        DB_TIMEOUT,
        CUSTOM_QUERY_TIMEOUT_SEC,
        ARCHIVE_DB_WHITELIST,
    )
    from shared.database import _apply_pragma_settings

    try:
        # Strip SQL comments before any validation (prevent bypass via comments)
        sql_clean = _strip_sql_comments(sql.strip())
        sql_upper = sql_clean.upper()

        # Validation 1: No semicolons (prevent multi-statement execution)
        if ";" in sql_clean:
            return {
                "status": "error",
                "message": "Multiple statements are not allowed (semicolon detected)."
            }

        # Validation 2: SELECT only (checked after comment stripping)
        if not sql_upper.startswith("SELECT"):
            return {
                "status": "error",
                "message": "Only SELECT queries are allowed."
            }

        # Validation 3: No dangerous keywords (extra safety layer)
        forbidden = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
            "CREATE", "REPLACE", "PRAGMA", "ATTACH", "DETACH", "VACUUM", "REINDEX",
            "LOAD_EXTENSION", "SQLITE_", "EXEC(", "EXECUTE", "SYSTEM",
            "SCRIPT", "JAVASCRIPT", "EVAL",
        ]
        for word in forbidden:
            if word in sql_upper:
                return {
                    "status": "error",
                    "message": f"Forbidden keyword detected: {word}"
                }

        # Validation 4: Must reference production_records
        if "PRODUCTION_RECORDS" not in sql_upper:
            return {
                "status": "error",
                "message": "Query must reference 'production_records' table."
            }

        # Add LIMIT if not present
        if "LIMIT" not in sql_upper:
            sql_clean = sql_clean + " LIMIT 1000"

        # Determine if archive is needed
        use_archive = "ARCHIVE.PRODUCTION_RECORDS" in sql_upper

        with QueryLogger("custom_query", DBTargets(use_archive=use_archive, use_live=True), logger) as ql:
            ql.add_info("description", description or "custom query")

            # Execute with timeout (3 seconds)
            # Dedicated connection required for conn.interrupt() — cannot use thread-local cache.
            # Apply PRAGMA settings so custom queries get same perf as regular API queries.
            db_uri = f"file:{DB_FILE.absolute()}?mode=ro"
            conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT)
            conn.row_factory = sqlite3.Row
            _apply_pragma_settings(conn)

            if use_archive:
                # Whitelist-enforced archive resolution (security-and-test-improvement)
                try:
                    archive_resolved = resolve_archive_db(ARCHIVE_DB_FILE, ARCHIVE_DB_WHITELIST)
                except (ValueError, FileNotFoundError) as e:
                    conn.close()
                    return {
                        "status": "error",
                        "code": "INVALID_ARCHIVE_PATH",
                        "message": f"Invalid archive DB: {e}",
                    }
                archive_uri = f"file:{archive_resolved.as_posix()}?mode=ro"
                try:
                    conn.execute("ATTACH DATABASE ? AS archive", (archive_uri,))
                except sqlite3.OperationalError:
                    # Parameter binding unsupported on some sqlite builds;
                    # safe because archive_resolved came from whitelist.
                    conn.execute(f"ATTACH DATABASE '{archive_uri}' AS archive")

            result = {"rows": [], "error": None}

            def run_query(connection):
                try:
                    cursor = connection.execute(sql_clean)
                    rows = cursor.fetchall()
                    result["rows"] = [dict(r) for r in rows]
                    result["columns"] = [desc[0] for desc in cursor.description] if cursor.description else []
                except Exception as e:
                    result["error"] = str(e)

            thread = threading.Thread(target=run_query, args=(conn,))
            thread.start()
            thread.join(timeout=CUSTOM_QUERY_TIMEOUT_SEC)

            if thread.is_alive():
                conn.interrupt()  # Cancel the running SQLite query
                thread.join(timeout=1.0)
                conn.close()
                return {
                    "status": "error",
                    "code": "QUERY_TIMEOUT",
                    "message": f"Query timeout (exceeded {CUSTOM_QUERY_TIMEOUT_SEC:.0f} seconds). Please simplify your query."
                }

            conn.close()

            if result["error"]:
                ql.set_row_count(0)
                logger.error(f"[Tool Error] execute_custom_query failed: {result['error']}")
                return {
                    "status": "error",
                    "message": result["error"]
                }

            ql.set_row_count(len(result["rows"]))

        logger.info(f"[Tool] execute_custom_query: {description or 'custom'} rows={len(result['rows'])}")
        return {
            "status": "success",
            "description": description,
            "row_count": len(result["rows"]),
            "columns": result["columns"],
            "data": result["rows"]
        }

    except Exception as e:
        logger.exception(f"[Tool Error] execute_custom_query failed: {str(e)}")
        return {"status": "error", "message": str(e)}


# Tool list for Gemini AI
PRODUCTION_TOOLS = [
    search_production_items,
    get_production_summary,
    get_monthly_trend,
    get_top_items,
    compare_periods,
    get_item_history,
    execute_custom_query
]
