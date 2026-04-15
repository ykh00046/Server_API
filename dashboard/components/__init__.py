"""
Dashboard UI Enhancement Components.

This package contains modular components for the Production Data Hub dashboard:
- kpi_cards: KPI dashboard cards (U2)
- charts: Chart components (U3-U5)
- presets: Filter preset manager (U7)
- loading: Loading state display (U6)
- ai_section: AI analysis section with animations (U9)
"""

from .loading import (
    show_loading_status,
    render_last_update,
    render_cache_status,
)
from .kpi_cards import (
    calculate_kpis,
    render_kpi_cards,
    get_sparkline_data,
    get_sparkline_for_top_product,
)
from .charts import (
    create_top10_bar_chart,
    create_distribution_pie,
    create_trend_lines,
    add_range_selector,
    add_download_button,
    get_chart_config,
)
from .presets import (
    init_presets,
    get_preset_names,
    save_preset,
    load_preset,
    delete_preset,
    render_preset_manager,
)
from .ai_section import (
    render_ai_section,
    render_ai_status_indicator,
    render_ai_header_with_animation,
)

__all__ = [
    # loading
    "show_loading_status",
    "render_last_update",
    "render_cache_status",
    # kpi_cards
    "calculate_kpis",
    "render_kpi_cards",
    "get_sparkline_data",
    "get_sparkline_for_top_product",
    # charts
    "create_top10_bar_chart",
    "create_distribution_pie",
    "create_trend_lines",
    "add_range_selector",
    "add_download_button",
    "get_chart_config",
    # presets
    "init_presets",
    "get_preset_names",
    "save_preset",
    "load_preset",
    "delete_preset",
    "render_preset_manager",
    # ai_section
    "render_ai_section",
    "render_ai_status_indicator",
    "render_ai_header_with_animation",
]
