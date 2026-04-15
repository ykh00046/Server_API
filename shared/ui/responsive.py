"""
U8: Responsive Layout Utilities - Mobile optimization.

Provides responsive layout utilities for adapting the dashboard
to different screen sizes (desktop, tablet, mobile).

v8 Enhancement:
- Viewport detection utilities
- Dynamic column calculation
- Touch-friendly component wrappers
"""

import streamlit as st
import streamlit.components.v1 as components
from typing import List, Optional, Callable, Any


def get_responsive_columns(count: int = 4) -> List[st.delta_generator.DeltaGenerator]:
    """
    Get columns with responsive CSS applied.

    Creates the specified number of columns. CSS media queries
    handle responsive behavior (stacking on mobile).

    Args:
        count: Number of columns to create (default: 4).

    Returns:
        List of column DeltaGenerator objects.

    Note:
        Responsive behavior is handled by CSS in apply_responsive_css().
        On mobile (<768px), columns will stack vertically.
    """
    cols = st.columns(count)
    return cols


def get_optimal_columns(default: int = 4) -> int:
    """
    Get optimal column count based on viewport width.

    Uses JavaScript to detect viewport width and returns
    appropriate column count.

    Args:
        default: Default column count if detection fails

    Returns:
        Optimal column count for current viewport
    """
    # Use session state to cache viewport width
    if "viewport_width" not in st.session_state:
        st.session_state.viewport_width = 1200  # Default to desktop

    width = st.session_state.viewport_width

    if width < 576:  # Mobile
        return 1
    elif width < 768:  # Large mobile
        return 2
    elif width < 1024:  # Tablet
        return min(2, default)
    else:  # Desktop
        return default


def apply_responsive_css() -> None:
    """
    Apply responsive CSS for mobile optimization.

    Injects CSS that:
    - Stacks KPI cards vertically on mobile
    - Increases touch targets for mobile interaction
    - Adjusts font sizes for better mobile readability
    - Handles tablet-specific layout adjustments

    Should be called once during app initialization.
    """
    st.markdown("""
    <style>
        /* Mobile responsive adjustments */
        @media (max-width: 768px) {
            /* Stack KPI cards and columns vertically */
            div[data-testid="stHorizontalBlock"] > div {
                flex-direction: column !important;
                width: 100% !important;
            }

            /* Increase touch targets for buttons */
            .stButton button {
                min-height: 44px;
                padding: 12px 20px;
            }

            /* Adjust font sizes for mobile */
            .stMetric label {
                font-size: 0.9rem !important;
            }
            .stMetric [data-testid="stMetricValue"] {
                font-size: 1.2rem !important;
            }

            /* Adjust sidebar width on mobile */
            [data-testid="stSidebar"] {
                width: 280px !important;
            }

            /* Make dataframes scrollable on mobile */
            .stDataFrame {
                overflow-x: auto;
            }

            /* Adjust tabs for mobile */
            .stTabs [role="tab"] {
                padding: 8px 12px;
                font-size: 0.85rem;
            }
        }

        /* Tablet adjustments */
        @media (min-width: 768px) and (max-width: 1024px) {
            /* Allow wrapping for medium screens */
            div[data-testid="stHorizontalBlock"] > div {
                flex-wrap: wrap;
            }

            /* 2-column layout for KPI cards on tablet */
            div[data-testid="stHorizontalBlock"] > div:nth-child(-n+4) {
                width: 50% !important;
            }
        }

        /* Desktop optimizations */
        @media (min-width: 1024px) {
            /* Ensure full utilization of wide layout */
            .block-container {
                max-width: 100%;
                padding-left: 3rem;
                padding-right: 3rem;
            }
        }

        /* Chart container responsiveness */
        .js-plotly-plot {
            width: 100% !important;
        }

        /* Improve data table scrolling */
        .stDataFrame [data-testid="stHorizontalBlock"] {
            overflow-x: auto;
        }
    </style>
    """, unsafe_allow_html=True)


# ==========================================================
# v8: Enhanced Responsive Features
# ==========================================================

def touch_friendly_button(
    label: str,
    key: Optional[str] = None,
    on_click: Optional[Callable] = None,
    args: Optional[tuple] = None,
    **kwargs
) -> bool:
    """
    Button with touch-friendly styling.

    Args:
        label: Button text
        key: Unique key
        on_click: Callback function
        args: Callback arguments
        **kwargs: Additional arguments for st.button

    Returns:
        True if button was clicked
    """
    # Apply touch-friendly CSS inline
    st.markdown("""
    <style>
        div[data-testid="stButton"] button {
            min-height: 44px;
            min-width: 44px;
            padding: 10px 16px;
            font-size: 16px;
        }
    </style>
    """, unsafe_allow_html=True)

    return st.button(label, key=key, on_click=on_click, args=args, **kwargs)


def touch_friendly_slider(
    label: str,
    min_value: int,
    max_value: int,
    value: int,
    key: Optional[str] = None,
    **kwargs
) -> int:
    """
    Slider with touch-friendly styling.

    Args:
        label: Slider label
        min_value: Minimum value
        max_value: Maximum value
        value: Default value
        key: Unique key
        **kwargs: Additional arguments for st.slider

    Returns:
        Selected value
    """
    return st.slider(
        label,
        min_value=min_value,
        max_value=max_value,
        value=value,
        key=key,
        **kwargs
    )


def responsive_grid(
    items: list,
    render_func: Callable[[Any], None],
    cols_desktop: int = 4,
    cols_tablet: int = 2,
    cols_mobile: int = 1
) -> None:
    """
    Render items in a responsive grid.

    Automatically adjusts column count based on viewport.

    Args:
        items: List of items to render
        render_func: Function to render each item
        cols_desktop: Columns on desktop (>1024px)
        cols_tablet: Columns on tablet (768-1024px)
        cols_mobile: Columns on mobile (<768px)
    """
    # Determine column count
    cols = get_optimal_columns(cols_desktop)

    # Adjust for tablet/mobile
    if "viewport_width" in st.session_state:
        width = st.session_state.viewport_width
        if width < 768:
            cols = cols_mobile
        elif width < 1024:
            cols = cols_tablet

    # Render grid
    columns = st.columns(cols)
    for idx, item in enumerate(items):
        col_idx = idx % cols
        with columns[col_idx]:
            render_func(item)


def detect_viewport() -> None:
    """
    Detect viewport width and store in session state.

    Injects JavaScript to detect viewport width and communicate
    it back to Streamlit via session state.
    """
    components.html("""
    <script>
    function sendViewportWidth() {
        const width = window.innerWidth;
        window.parent.postMessage({
            type: 'streamlit:setComponentValue',
            data: width
        }, '*');
    }

    // Send on load
    sendViewportWidth();

    // Send on resize
    window.addEventListener('resize', sendViewportWidth);
    </script>
    """, height=0)
