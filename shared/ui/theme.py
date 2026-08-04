"""
Theme helpers — industrial blue/slate palette (ui-design-overhaul-v1, 2026-06-11).

The theme itself lives in `.streamlit/config.toml` ([theme.light]/[theme.dark]);
light/dark switching is native via the app settings menu. This module only
keeps what Streamlit cannot theme for us: plotly chart palettes
(Streamlit's chartCategoricalColors does not reach manually-built plotly
figures).

History: the previous Pink/Sky CSS-token system (3 modes, ~165 lines of
injected CSS) was replaced by native theming — see the design doc
ui-design-overhaul-v1.design.md. The last CSS remnant (_STARTER_CARD_CSS
for AI starter cards) was removed 2026-08: DOM inspection showed its
selector never matched on Streamlit 1.58 ([data-testid="column"] no longer
exists and stBaseButton-secondary IS the button element), and the starter
cards themselves were unreachable code. This module injects no HTML.
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

ThemeMode = Literal["light", "dark"]

# --------------------------------------------------------------
# Chart color palettes (plotly figures built in pages/components)
# The categorical palette is the single source of truth and mirrors
# `chartCategoricalColors` in .streamlit/config.toml — do NOT edit these
# hex values in isolation; change config.toml and keep them aligned.
# --------------------------------------------------------------
# chartCategoricalColors from config.toml (light theme). Streamlit exposes
# these to its native chart elements (st.bar_chart etc.) but NOT to plotly
# figures built by hand, so charts.py / views import this list directly.
CHART_CATEGORICAL_COLORS = [
    "#2563eb", "#0d9488", "#f59e0b", "#7c3aed",
    "#dc2626", "#0891b2", "#64748b",
]

CHART_COLORS: dict[str, dict[str, str]] = {
    "light": {
        "chart_template": "plotly_white",
        "primary": CHART_CATEGORICAL_COLORS[0],
        "secondary": CHART_CATEGORICAL_COLORS[1],
        "accent": CHART_CATEGORICAL_COLORS[2],
    },
    "dark": {
        "chart_template": "plotly_dark",
        "primary": "#60a5fa",
        "secondary": "#2dd4bf",
        "accent": "#fbbf24",
    },
}

# Series palette for multi-series charts. The first 7 mirror
# CHART_CATEGORICAL_COLORS (config.toml); the last 3 are lighter companions
# used only when a chart exceeds 7 series, so the categorical identity is
# preserved for the common case.
CHART_SERIES_COLORS = CHART_CATEGORICAL_COLORS + ["#60a5fa", "#2dd4bf", "#94a3b8"]

def get_theme() -> ThemeMode:
    """Return the active base theme ("light" | "dark") from Streamlit."""
    try:
        if st.context.theme.base == "dark":
            return "dark"
    except AttributeError:
        pass
    return "light"


def get_colors() -> dict[str, str]:
    """Return the plotly-friendly color palette for the active theme."""
    return CHART_COLORS[get_theme()]


def get_chart_palette(n: int = len(CHART_CATEGORICAL_COLORS)) -> list[str]:
    """Return n categorical chart colors suited to the active theme.

    Light mode returns the leading entries of CHART_CATEGORICAL_COLORS (mirrors
    config.toml's chartCategoricalColors). Dark mode lifts them toward the dark
    theme accents so categorical fills stay readable on a dark plot background.
    Use for pie/bar markers that must read in BOTH themes (hardcoded light hex
    would wash out on dark).
    """
    if get_theme() == "dark":
        dark_pool = ["#60a5fa", "#2dd4bf", "#fbbf24", "#a78bfa", "#f87171", "#22d3ee", "#94a3b8"]
        pool = dark_pool + CHART_SERIES_COLORS
    else:
        pool = CHART_CATEGORICAL_COLORS + CHART_SERIES_COLORS
    return [pool[i % len(pool)] for i in range(max(n, 1))]


def init_theme() -> None:
    """Legacy hook — native theming needs no session-state setup."""


def render_theme_toggle() -> bool:
    """Legacy sidebar hook.

    The custom mode radio was removed: with [theme.light] and [theme.dark]
    both defined in config.toml, Streamlit's settings menu provides the
    toggle natively. Returns True when dark mode is active (legacy shape).
    """
    st.sidebar.caption("표시 모드는 우측 상단 설정(⋮) 메뉴에서 변경")
    return get_theme() == "dark"


def apply_dark_mode_css() -> None:
    """Legacy hook — superseded by native theming."""
