"""AI tools — period summaries, monthly trend, top items, period comparison.

Note: Do NOT use 'from __future__ import annotations' here.
Gemini SDK requires actual type hints, not stringified ones.
"""

import concurrent.futures
import sqlite3
from typing import Any

from shared import (
    DBRouter,
    DBTargets,
    get_logger,
)
from shared.cache import api_cache
from shared.logging_config import QueryLogger

from ._common import _validate_date_range

logger = get_logger(__name__)


@api_cache("summary")
def get_production_summary(
    date_from: str,
    date_to: str,
    item_code: str | None = None
) -> dict[str, Any]:
    """
    Get production statistics for a specified period.

    Args:
        date_from: Start date (YYYY-MM-DD), inclusive
        date_to: End date (YYYY-MM-DD), inclusive
        item_code: Exact product code (e.g., 'BW0021'). Use
            search_production_items first to find this.

    Returns:
        Dict with total_quantity, average_quantity, production_count
    """
    try:
        date_from, next_day = _validate_date_range(date_from, date_to)

        targets = DBRouter.pick_targets(date_from, next_day)

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

            sql, params_doubled = DBRouter.build_aggregation_sql(
                inner_select=(
                    "SUM(good_quantity) AS total, COUNT(*) AS cnt, "
                    "AVG(good_quantity) AS avg_val"
                ),
                inner_where=where_clause,
                outer_select="SUM(total) AS total, SUM(cnt) AS count, AVG(avg_val) AS average",
                outer_group_by="",
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

    except Exception as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(
            f"[Tool Error] get_production_summary failed: {date_from}~{date_to} item={item_code}"
        )
        return {"status": "error", "message": str(e)}


@api_cache("monthly_trend")
def get_monthly_trend(
    date_from: str,
    date_to: str,
    item_code: str | None = None
) -> dict[str, Any]:
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
                inner_select=(
                    "substr(production_date, 1, 7) AS year_month, "
                    "SUM(good_quantity) AS total, COUNT(*) AS cnt"
                ),
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
        logger.info(
            f"[Tool] get_monthly_trend: period={date_from}~{date_to} "
            f"item={item_code or 'all'} months={len(trend)}"
        )
        return result

    except sqlite3.Error as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(f"[Tool Error] get_monthly_trend failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@api_cache("top_items")
def get_top_items(
    date_from: str,
    date_to: str,
    limit: int = 5
) -> dict[str, Any]:
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
                outer_select=(
                    "item_code, MAX(item_name) AS item_name, "
                    "SUM(total) AS total_production"
                ),
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
        logger.info(
            f"[Tool] get_top_items: period={date_from}~{date_to} limit={limit} found={len(items)}"
        )
        return result

    except sqlite3.Error as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(f"[Tool Error] get_top_items failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@api_cache("compare_periods")
def compare_periods(
    period1_from: str,
    period1_to: str,
    period2_from: str,
    period2_to: str,
    item_code: str | None = None
) -> dict[str, Any]:
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
                inner_select=(
                    "SUM(good_quantity) AS total, COUNT(*) AS cnt, "
                    "AVG(good_quantity) AS avg_val"
                ),
                inner_where=where_clause,
                outer_select="SUM(total) AS total, SUM(cnt) AS count, AVG(avg_val) AS average",
                outer_group_by="",
                targets=targets,
            )
            query_params = DBRouter.build_query_params(params, targets)
            with DBRouter.get_connection(use_archive=targets.use_archive) as conn:
                row = conn.execute(sql, query_params).fetchone()
            return dict(row) if row else {"total": 0, "count": 0, "average": 0}

        with QueryLogger(
            "compare_periods", DBTargets(use_archive=True, use_live=True), logger
        ) as ql:
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

    except Exception as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(f"[Tool Error] compare_periods failed: {str(e)}")
        return {"status": "error", "message": str(e)}
