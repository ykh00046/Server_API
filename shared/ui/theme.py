"""
U1: Theme Manager - Dark mode support for dashboard.

Dark mode is configured via .streamlit/config.toml and Streamlit's settings menu.
Users can switch themes via Menu > Settings > Theme.
"""

import streamlit as st
from typing import Literal, Dict

ThemeMode = Literal["light", "dark"]

# Color palettes for charts
CHART_COLORS: Dict[str, Dict[str, str]] = {
    "light": {
        "chart_template": "plotly_white",
        "primary": "#1f77b4",
        "secondary": "#ff7f0e",
        "accent": "#FF4B4B",
    },
    "dark": {
        "chart_template": "plotly_dark",
        "primary": "#4da6ff",
        "secondary": "#ffaa00",
        "accent": "#FF6B6B",
    }
}


def init_theme() -> None:
    """
    Initialize theme state in session_state.

    Call this once at the start of the app, after st.set_page_config().
    """
    if "dark_mode" not in st.session_state:
        # Try to detect from st.context.theme.base (Streamlit 1.40+)
        try:
            detected = st.context.theme.base == "dark"
            st.session_state.dark_mode = detected
        except AttributeError:
            st.session_state.dark_mode = False


def get_theme() -> ThemeMode:
    """
    Get current theme mode.

    Returns:
        "dark" if dark mode is enabled, "light" otherwise.
    """
    # Try to detect from Streamlit context
    try:
        if st.context.theme.base == "dark":
            return "dark"
    except AttributeError:
        pass

    # Check session_state
    if st.session_state.get("dark_mode", False):
        return "dark"

    return "light"


def get_colors() -> Dict[str, str]:
    """
    Get color palette for current theme.

    Returns:
        Dict with color values for current theme mode.
    """
    return CHART_COLORS[get_theme()]


def render_theme_toggle() -> bool:
    """
    Render theme toggle info in sidebar.

    Shows current theme status and instructions for changing theme.
    Streamlit's theme is controlled via config.toml and browser settings.

    Returns:
        Current dark mode state (True = dark, False = light).
    """
    is_dark = get_theme() == "dark"

    # Show current theme status
    theme_name = "Dark" if is_dark else "Light"
    st.sidebar.caption(f"Theme: {theme_name}")

    # Note about changing theme
    st.sidebar.caption(
        "Change theme: Menu (☰) → Settings → Theme"
    )

    return is_dark


def apply_dark_mode_css() -> None:
    """
    Apply dark mode CSS if needed.

    Streamlit handles dark mode automatically via config.toml.
    This function provides additional chart color adjustments.
    """
    pass  # Streamlit handles this via config.toml


def apply_custom_css() -> None:
    """
    Apply custom CSS based on current theme.

    This is the main entry point for theme CSS application.
    """
    apply_dark_mode_css()
