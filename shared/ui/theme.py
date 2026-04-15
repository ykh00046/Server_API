"""
Theme Manager - CSS token system + dark/high-contrast modes.

ui-modernization-streamlit-extras (2026-04-15):
- Introduces CSS custom properties (tokens) for color, radius, shadow.
- Adds high-contrast palette (MA-04 accessibility, WCAG AA).
- apply_custom_css() now injects :root tokens + base rules.

Dark mode is still driven by Streamlit's config.toml / Settings menu;
`_theme_mode` in session_state overrides for explicit user choice.
"""

from __future__ import annotations

import streamlit as st
from typing import Literal, Dict

ThemeMode = Literal["light", "dark", "high-contrast"]

# --------------------------------------------------------------
# Chart color palettes (legacy — still used by plotly templates)
# --------------------------------------------------------------
CHART_COLORS: Dict[str, Dict[str, str]] = {
    "light": {
        "chart_template": "plotly_white",
        "primary": "#667eea",
        "secondary": "#764ba2",
        "accent": "#FF4B4B",
    },
    "dark": {
        "chart_template": "plotly_dark",
        "primary": "#4da6ff",
        "secondary": "#ffaa00",
        "accent": "#FF6B6B",
    },
    "high-contrast": {
        "chart_template": "plotly_white",
        "primary": "#0000ee",
        "secondary": "#000000",
        "accent": "#cc0000",
    },
}

# --------------------------------------------------------------
# CSS Tokens (injected as :root custom properties)
# --------------------------------------------------------------
TOKENS_LIGHT: Dict[str, str] = {
    "--color-primary": "#667eea",
    "--color-primary-hover": "#5568d3",
    "--color-accent": "#764ba2",
    "--color-bg-card": "#ffffff",
    "--color-bg-card-alt": "rgba(102,126,234,0.03)",
    "--color-border": "rgba(102,126,234,0.15)",
    "--color-border-strong": "rgba(102,126,234,0.35)",
    "--color-text": "#1a1a1a",
    "--color-text-muted": "#666666",
    "--radius-card": "12px",
    "--radius-pill": "20px",
    "--shadow-card": "0 2px 8px rgba(0,0,0,0.05)",
    "--shadow-card-hover": "0 4px 12px rgba(102,126,234,0.15)",
    "--focus-ring": "0 0 0 3px rgba(102,126,234,0.35)",
}

TOKENS_DARK: Dict[str, str] = {
    "--color-primary": "#8ea3ff",
    "--color-primary-hover": "#a5b6ff",
    "--color-accent": "#b388ff",
    "--color-bg-card": "#1e1e2e",
    "--color-bg-card-alt": "rgba(142,163,255,0.05)",
    "--color-border": "rgba(142,163,255,0.25)",
    "--color-border-strong": "rgba(142,163,255,0.5)",
    "--color-text": "#e6e6e6",
    "--color-text-muted": "#a0a0b0",
    "--radius-card": "12px",
    "--radius-pill": "20px",
    "--shadow-card": "0 2px 8px rgba(0,0,0,0.35)",
    "--shadow-card-hover": "0 4px 14px rgba(142,163,255,0.25)",
    "--focus-ring": "0 0 0 3px rgba(142,163,255,0.55)",
}

# WCAG AA target: ≥ 4.5:1 for normal text, ≥ 7:1 preferred.
# Pure #000/#fff pair achieves 21:1.
TOKENS_HIGH_CONTRAST: Dict[str, str] = {
    "--color-primary": "#0000ee",
    "--color-primary-hover": "#0000aa",
    "--color-accent": "#000000",
    "--color-bg-card": "#ffffff",
    "--color-bg-card-alt": "#ffffff",
    "--color-border": "#000000",
    "--color-border-strong": "#000000",
    "--color-text": "#000000",
    "--color-text-muted": "#000000",
    "--radius-card": "4px",
    "--radius-pill": "4px",
    "--shadow-card": "none",
    "--shadow-card-hover": "none",
    "--focus-ring": "0 0 0 3px #0000ee",
}

_BASE_RULES = """
[data-testid="stChatMessage"] {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-card);
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow-card);
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
[data-testid="stChatMessage"]:hover {
    box-shadow: var(--shadow-card-hover);
    transform: translateY(-1px);
}
.stMarkdown table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 0.9rem;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: var(--shadow-card);
}
.stMarkdown th {
    background-color: var(--color-primary) !important;
    color: #ffffff !important;
    padding: 10px !important;
    text-align: left !important;
    font-weight: 600;
}
.stMarkdown td {
    padding: 8px 10px !important;
    border-bottom: 1px solid var(--color-border) !important;
}
.stDownloadButton button {
    border-color: var(--color-primary);
    color: var(--color-primary);
    border-radius: var(--radius-pill);
}
.stDownloadButton button:hover {
    background-color: var(--color-primary);
    color: #ffffff;
}
div[data-testid="column"] button:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
}
"""


def init_theme() -> None:
    """Initialize theme state in session_state."""
    if "_theme_mode" not in st.session_state:
        st.session_state["_theme_mode"] = "auto"
    if "dark_mode" not in st.session_state:
        try:
            st.session_state.dark_mode = st.context.theme.base == "dark"
        except AttributeError:
            st.session_state.dark_mode = False


def _resolve_mode() -> ThemeMode:
    """Resolve effective theme mode from user selection + Streamlit context."""
    explicit = st.session_state.get("_theme_mode", "auto")
    if explicit == "high-contrast":
        return "high-contrast"
    if explicit == "dark":
        return "dark"
    if explicit == "light":
        return "light"
    # auto: follow Streamlit
    try:
        if st.context.theme.base == "dark":
            return "dark"
    except AttributeError:
        pass
    if st.session_state.get("dark_mode", False):
        return "dark"
    return "light"


def get_theme() -> ThemeMode:
    """Return current effective theme."""
    return _resolve_mode()


def get_colors() -> Dict[str, str]:
    """Return plotly-friendly color palette for current theme."""
    return CHART_COLORS[_resolve_mode()]


def render_theme_toggle() -> bool:
    """Sidebar theme mode selector.

    Returns True if dark-family mode is active (dark or high-contrast),
    preserving the legacy return shape.
    """
    current = st.session_state.get("_theme_mode", "auto")
    options = ["auto", "light", "dark", "high-contrast"]
    labels = {
        "auto": "자동",
        "light": "라이트",
        "dark": "다크",
        "high-contrast": "고대비 (접근성)",
    }
    choice = st.sidebar.radio(
        "표시 모드",
        options=options,
        index=options.index(current) if current in options else 0,
        format_func=lambda k: labels[k],
        key="_theme_mode_radio",
    )
    st.session_state["_theme_mode"] = choice
    mode = _resolve_mode()
    st.sidebar.caption(f"현재: {labels.get(mode, mode)}")
    return mode in ("dark", "high-contrast")


def apply_dark_mode_css() -> None:
    """Legacy hook — superseded by apply_custom_css()."""
    pass


def apply_custom_css() -> None:
    """Inject :root CSS tokens + base rules for the current theme."""
    mode = _resolve_mode()
    tokens = {
        "light": TOKENS_LIGHT,
        "dark": TOKENS_DARK,
        "high-contrast": TOKENS_HIGH_CONTRAST,
    }[mode]
    css_vars = "\n".join(f"  {k}: {v};" for k, v in tokens.items())
    st.markdown(
        f"<style>\n:root {{\n{css_vars}\n}}\n{_BASE_RULES}\n</style>",
        unsafe_allow_html=True,
    )
