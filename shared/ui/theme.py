"""
Theme Manager - CSS token system + dark/high-contrast modes.

B3 Sidebar UI: Pink/Sky palette (2026-04-17).
- Pink (#ec4899) as primary
- Sky (#0ea5e9) as accent
- Gradient: linear-gradient(135deg, #ec4899, #0ea5e9)

Dark mode is still driven by Streamlit's config.toml / Settings menu;
`_theme_mode` in session_state overrides for explicit user choice.
"""

from __future__ import annotations

import streamlit as st
from typing import Literal, Dict

ThemeMode = Literal["light", "dark", "high-contrast"]

# --------------------------------------------------------------
# Chart color palettes (used by plotly templates)
# --------------------------------------------------------------
CHART_COLORS: Dict[str, Dict[str, str]] = {
    "light": {
        "chart_template": "plotly_white",
        "primary": "#ec4899",
        "secondary": "#0ea5e9",
        "accent": "#f43f5e",
    },
    "dark": {
        "chart_template": "plotly_dark",
        "primary": "#f472b6",
        "secondary": "#38bdf8",
        "accent": "#fb7185",
    },
    "high-contrast": {
        "chart_template": "plotly_white",
        "primary": "#be185d",
        "secondary": "#0369a1",
        "accent": "#cc0000",
    },
}

# Pink/Sky chart color series for multi-series charts
CHART_SERIES_COLORS = [
    "#ec4899", "#0ea5e9", "#f472b6", "#38bdf8",
    "#f9a8d4", "#7dd3fc", "#f43f5e", "#0284c7",
    "#fda4af", "#bae6fd",
]

# --------------------------------------------------------------
# CSS Tokens (injected as :root custom properties)
# --------------------------------------------------------------
TOKENS_LIGHT: Dict[str, str] = {
    "--color-primary": "#ec4899",
    "--color-primary-hover": "#db2777",
    "--color-accent": "#0ea5e9",
    "--color-accent-hover": "#0284c7",
    "--color-gradient": "linear-gradient(135deg, #ec4899, #0ea5e9)",
    "--color-bg": "#f8f9fc",
    "--color-bg-card": "#ffffff",
    "--color-bg-card-alt": "rgba(236,72,153,0.03)",
    "--color-border": "rgba(236,72,153,0.15)",
    "--color-border-strong": "rgba(236,72,153,0.35)",
    "--color-text": "#1e293b",
    "--color-text-muted": "#64748b",
    "--color-success": "#10b981",
    "--color-warning": "#f59e0b",
    "--color-danger": "#ef4444",
    "--radius-card": "12px",
    "--radius-sm": "8px",
    "--radius-pill": "20px",
    "--shadow-card": "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
    "--shadow-card-hover": "0 4px 12px rgba(236,72,153,0.12)",
    "--focus-ring": "0 0 0 3px rgba(236,72,153,0.35)",
}

TOKENS_DARK: Dict[str, str] = {
    "--color-primary": "#f472b6",
    "--color-primary-hover": "#f9a8d4",
    "--color-accent": "#38bdf8",
    "--color-accent-hover": "#7dd3fc",
    "--color-gradient": "linear-gradient(135deg, #f472b6, #38bdf8)",
    "--color-bg": "#0f172a",
    "--color-bg-card": "#1e293b",
    "--color-bg-card-alt": "rgba(244,114,182,0.05)",
    "--color-border": "rgba(244,114,182,0.25)",
    "--color-border-strong": "rgba(244,114,182,0.5)",
    "--color-text": "#e2e8f0",
    "--color-text-muted": "#94a3b8",
    "--color-success": "#34d399",
    "--color-warning": "#fbbf24",
    "--color-danger": "#f87171",
    "--radius-card": "12px",
    "--radius-sm": "8px",
    "--radius-pill": "20px",
    "--shadow-card": "0 2px 8px rgba(0,0,0,0.35)",
    "--shadow-card-hover": "0 4px 14px rgba(244,114,182,0.25)",
    "--focus-ring": "0 0 0 3px rgba(244,114,182,0.55)",
}

# WCAG AA target: ≥ 4.5:1 for normal text, ≥ 7:1 preferred.
TOKENS_HIGH_CONTRAST: Dict[str, str] = {
    "--color-primary": "#be185d",
    "--color-primary-hover": "#9d174d",
    "--color-accent": "#0369a1",
    "--color-accent-hover": "#075985",
    "--color-gradient": "linear-gradient(135deg, #be185d, #0369a1)",
    "--color-bg": "#ffffff",
    "--color-bg-card": "#ffffff",
    "--color-bg-card-alt": "#ffffff",
    "--color-border": "#000000",
    "--color-border-strong": "#000000",
    "--color-text": "#000000",
    "--color-text-muted": "#000000",
    "--color-success": "#065f46",
    "--color-warning": "#92400e",
    "--color-danger": "#991b1b",
    "--radius-card": "4px",
    "--radius-sm": "4px",
    "--radius-pill": "4px",
    "--shadow-card": "none",
    "--shadow-card-hover": "none",
    "--focus-ring": "0 0 0 3px #be185d",
}

_BASE_RULES = """
/* Utility classes — replace inline unsafe_allow_html */
.bkit-flex-center {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 15px;
}
.bkit-status-dot { font-size: 1.2rem; }
.bkit-hint-badge {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 10px;
}
.bkit-hint-badge span {
    background: var(--color-bg-card-alt);
    color: var(--color-primary);
    padding: 6px 16px;
    border-radius: var(--radius-pill);
    font-size: 0.85rem;
    font-weight: 500;
}
.bkit-spacer-8 { height: 8px; }
.bkit-gradient-header {
    padding: 10px 14px;
    background: var(--color-gradient, linear-gradient(135deg, #ec4899, #0ea5e9));
    border-radius: var(--radius-sm, 8px);
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.bkit-gradient-header span { color: #fff; }
.bkit-gradient-header .bkit-model-tag { font-size: 0.7rem; color: rgba(255,255,255,0.8); }
.bkit-zero-state {
    text-align: center;
    margin-top: 60px;
    margin-bottom: 40px;
}
.bkit-zero-state .bkit-icon { font-size: 3.5rem; margin-bottom: 15px; }
.bkit-zero-state h2 { font-weight: 700; color: var(--color-text); }
.bkit-zero-state p { color: #888; font-size: 1.1rem; }
.bkit-compact-zero-state {
    text-align: center;
    padding: 20px 0 10px;
}
.bkit-compact-zero-state .bkit-icon { font-size: 1.8rem; margin-bottom: 8px; }
.bkit-compact-zero-state p { color: var(--color-text-muted, #64748b); font-size: 0.85rem; }
.bkit-ai-header {
    padding: 5px 0;
}
.bkit-ai-header h1 {
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0px;
}
.bkit-ai-header p { color: #888; font-size: 0.95rem; }
/* Chat role accents */
[data-testid="stChatMessage"][data-testid*="assistant"] {
    background-color: var(--color-bg-card-alt);
    border-left: 3px solid var(--color-primary);
    padding: 0.6rem;
    margin-bottom: 0.5rem;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    background-color: var(--color-bg-card-alt);
    border-right: 3px solid var(--color-accent);
    padding: 0.6rem;
    margin-bottom: 0.5rem;
}
/* Sidebar logo */
.bkit-sidebar-logo {
    padding: 8px 0 16px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 12px;
}
.bkit-sidebar-logo .bkit-title { font-size:1.1rem;font-weight:700;color:var(--color-text, #1e293b); }
.bkit-sidebar-logo .bkit-subtitle { font-size:0.7rem;color:var(--color-text-muted, #64748b); }
/* KPI card styling */
.bkit-kpi-card {
    background: var(--color-bg-card, #fff);
    border-radius: var(--radius-card, 12px);
    padding: 18px;
    box-shadow: var(--shadow-card, 0 1px 3px rgba(0,0,0,0.06));
    border: 1px solid var(--color-border, rgba(236,72,153,0.1));
    position: relative;
    overflow: hidden;
}
.bkit-kpi-card .bkit-kpi-bar { position:absolute;top:0;left:0;right:0;height:3px; }
.bkit-kpi-card .bkit-kpi-header { display:flex;justify-content:space-between;align-items:flex-start; }
.bkit-kpi-card .bkit-kpi-label { font-size:0.75rem;color:var(--color-text-muted, #64748b);font-weight:500; }
.bkit-kpi-card .bkit-kpi-icon { width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px; }
.bkit-kpi-card .bkit-kpi-value { font-size:1.75rem;font-weight:700;color:var(--color-text, #1e293b);margin:6px 0 4px; }
/* Starter card button styling (zero-state AI prompt cards) */
[data-testid="stVerticalBlock"] [data-testid="column"] [data-testid="stBaseButton-secondary"] button {
    min-height: 120px;
    text-align: left;
    background-color: var(--color-bg-card);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-card);
    transition: all 0.2s ease;
    white-space: pre-wrap;
}
[data-testid="stVerticalBlock"] [data-testid="column"] [data-testid="stBaseButton-secondary"] button:hover {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-card-hover);
    transform: translateY(-2px);
}

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
    background: var(--color-gradient) !important;
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
