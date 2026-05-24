"""Re-exports for backward-compatible imports.

External callers MUST use `from api.tools import X` (works in both the legacy
single-module and the new package layout). Internal callers within the
api.tools package may import siblings directly.

Layout (api-router-split, 2026-05-22):
    items.py   — search_production_items, get_item_history
    summary.py — get_production_summary, get_monthly_trend,
                 get_top_items, compare_periods
    custom.py  — execute_custom_query (+ helpers)
    _common.py — internal _validate_date_range wrapper
"""
from .items import search_production_items, get_item_history
from .summary import (
    get_production_summary,
    get_monthly_trend,
    get_top_items,
    compare_periods,
)
from .custom import (
    execute_custom_query,
    _strip_sql_comments,
    _validate_custom_query_params,
)

__all__ = [
    "search_production_items",
    "get_item_history",
    "get_production_summary",
    "get_monthly_trend",
    "get_top_items",
    "compare_periods",
    "execute_custom_query",
    # Private helpers re-exported for tests (tests/test_sql_validation.py)
    "_strip_sql_comments",
    "_validate_custom_query_params",
]
