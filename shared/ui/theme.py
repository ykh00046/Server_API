"""
Theme helpers — industrial blue/slate palette (ui-design-overhaul-v1, 2026-06-11).

The theme itself lives in `.streamlit/config.toml` ([theme.light]/[theme.dark]);
light/dark switching is native via the app settings menu. This module only
keeps what Streamlit cannot theme for us:

- plotly chart palettes (Streamlit's chartCategoricalColors does not reach
  manually-built plotly figures), and
- a minimal CSS block for the AI starter-card buttons (multi-line tall
  buttons have no native equivalent).

History: the previous Pink/Sky CSS-token system (3 modes, ~165 lines of
injected CSS) was replaced by native theming — see the design doc
ui-design-overhaul-v1.design.md.
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

ThemeMode = Literal["light", "dark"]

# --------------------------------------------------------------
# Chart color palettes (plotly figures built in pages/components)
# Keep in sync with chartCategoricalColors in .streamlit/config.toml.
# --------------------------------------------------------------
CHART_COLORS: dict[str, dict[str, str]] = {
    "light": {
        "chart_template": "plotly_white",
        "primary": "#2563eb",
        "secondary": "#0d9488",
        "accent": "#f59e0b",
    },
    "dark": {
        "chart_template": "plotly_dark",
        "primary": "#60a5fa",
        "secondary": "#2dd4bf",
        "accent": "#fbbf24",
    },
}

# Blue→teal→amber series for multi-series charts.
CHART_SERIES_COLORS = [
    "#2563eb", "#0d9488", "#f59e0b", "#7c3aed",
    "#dc2626", "#0891b2", "#64748b", "#60a5fa",
    "#2dd4bf", "#94a3b8",
]

# AI starter-card buttons: tall, left-aligned, multi-line. No native
# equivalent in Streamlit 1.58 — kept as the single CSS remnant.
_STARTER_CARD_CSS = """
[data-testid="stVerticalBlock"] [data-testid="column"] [data-testid="stBaseButton-secondary"] button {
    min-height: 120px;
    text-align: left;
    white-space: pre-wrap;
}
"""


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


def apply_custom_css() -> None:
    """Inject the minimal CSS remnant (starter-card buttons only)."""
    st.markdown(f"<style>{_STARTER_CARD_CSS}</style>", unsafe_allow_html=True)
