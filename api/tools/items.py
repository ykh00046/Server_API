"""AI tools — item search and history.

Note: Do NOT use 'from __future__ import annotations' here.
Gemini SDK requires actual type hints, not stringified ones.
"""

import sqlite3
from typing import Any

from shared import (
    ARCHIVE_DB_FILE,
    DBRouter,
    DBTargets,
    get_logger,
)
from shared.cache import api_cache
from shared.logging_config import QueryLogger
from shared.validators import escape_like_wildcards

logger = get_logger(__name__)


@api_cache("search_items")
def search_production_items(
    keyword: str,
    include_archive: bool = True  # Section 6.5: Default True for accurate answers
) -> dict[str, Any]:
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
            targets = DBTargets(use_archive=True, use_live=True)

            sql = """
                SELECT item_code, item_name, SUM(record_count) as record_count
                FROM (
                    SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
                    FROM archive.production_records
                    WHERE (item_code LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\')
                    GROUP BY item_code

                    UNION ALL

                    SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
                    FROM production_records
                    WHERE (item_code LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\')
                    GROUP BY item_code
                )
                GROUP BY item_code
                ORDER BY record_count DESC
                LIMIT 10
            """
            params = [like_keyword, like_keyword, like_keyword, like_keyword]
        else:
            targets = DBTargets(use_archive=False, use_live=True)

            sql = """
                SELECT item_code, MAX(item_name) as item_name, COUNT(*) as record_count
                FROM production_records
                WHERE item_code LIKE ? ESCAPE '\\' OR item_name LIKE ? ESCAPE '\\'
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

    except (sqlite3.Error, KeyError) as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(f"[Tool Error] search_production_items failed: keyword='{keyword}'")
        return {"status": "error", "message": str(e)}


@api_cache("item_history")
def get_item_history(
    item_code: str,
    limit: int = 10
) -> dict[str, Any]:
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

    except sqlite3.Error as e:  # noqa: BLE001 — Gemini tool boundary: 모든 예외를 error dict로 변환 (LLM 계약)
        logger.exception(f"[Tool Error] get_item_history failed: item_code={item_code}")
        return {"status": "error", "message": str(e)}
