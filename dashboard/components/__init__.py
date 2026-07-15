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

from .ai_section import (
    render_ai_header_with_animation,
    render_ai_section,
    render_ai_section_compact,
    render_ai_status_indicator,
)
from .charts import (
    create_distribution_pie,
    create_top10_bar_chart,
    create_trend_lines,
    get_chart_config,
)
from .kpi_cards import (
    calculate_kpis,
    get_avg_batch_sparkline,
    get_batch_count_sparkline,
    get_sparkline_data,
    render_kpi_cards,
)
from .layout import (
    empty_state,
    get_page_columns,
    init_ai_panel_state,
    page_header,
    render_ai_column,
    render_page_header,
)
from .loading import render_last_update
from .presets import (
    apply_pending_preset,
    delete_preset,
    get_preset_names,
    init_presets,
    load_preset,
    render_preset_manager,
    save_preset,
)

__all__ = [
    # loading
    "render_last_update",
    # kpi_cards
    "calculate_kpis",
    "render_kpi_cards",
    "get_sparkline_data",
    "get_batch_count_sparkline",
    "get_avg_batch_sparkline",
    # charts
    "create_top10_bar_chart",
    "create_distribution_pie",
    "create_trend_lines",
    "get_chart_config",
    # presets
    "init_presets",
    "apply_pending_preset",
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
    "page_header",
    "empty_state",
    "render_page_header",
    "get_page_columns",
    "render_ai_column",
]
