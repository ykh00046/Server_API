# api/_tool_dispatch.py
"""Gemini tool registry used by the chat orchestrator.

Extracted from api/chat.py (Act-1 of security-and-test-improvement).
Keeps `chat_with_data()` focused on orchestration only.
"""

from __future__ import annotations

from .tools import (
    compare_periods,
    execute_custom_query,
    get_item_history,
    get_monthly_trend,
    get_production_summary,
    get_top_items,
    search_production_items,
)

PRODUCTION_TOOLS = [
    search_production_items,
    get_production_summary,
    get_monthly_trend,
    get_top_items,
    compare_periods,
    get_item_history,
    execute_custom_query,
]
