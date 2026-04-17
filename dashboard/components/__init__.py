"""
Dashboard UI Enhancement Components.

This package contains modular components for the Production Data Hub dashboard:
- kpi_cards: KPI dashboard cards (B3 style)
- charts: Chart components (pink/sky palette)
- presets: Filter preset manager
- loading: Loading state display
- ai_section: AI analysis section with compact panel
- layout: Page layout helpers (header, AI toggle, columns)
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
    render_ai_section_compact,
    render_ai_status_indicator,
    render_ai_header_with_animation,
)
from .layout import (
    init_ai_panel_state,
    render_page_header,
    get_page_columns,
    render_ai_column,
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
    "render_ai_section_compact",
    "render_ai_status_indicator",
    "render_ai_header_with_animation",
    # layout
    "init_ai_panel_state",
    "render_page_header",
    "get_page_columns",
    "render_ai_column",
]
