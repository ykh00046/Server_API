"""
U6: Loading State Display - Progress indicators and status display.

Provides loading state management with progress bars and
status indicators for data operations.

v8 Enhancement:
- Skeleton loading components for better perceived performance
- Multiple skeleton types (table, kpi, chart)
"""

import streamlit as st
from datetime import datetime
from typing import Optional


# ==========================================================
# Skeleton Loading Components (v8)
# ==========================================================

_SKELETON_CSS = """
<style>
.skeleton-table {
    width: 100%;
    border-collapse: collapse;
}
.skeleton-table td {
    padding: 12px;
    border-bottom: 1px solid var(--color-border, rgba(0,0,0,0.1));
}
.skeleton-cell {
    background: linear-gradient(90deg,
        var(--color-bg-card-alt, #e2e8f0) 25%,
        var(--color-border, #cbd5e1) 50%,
        var(--color-bg-card-alt, #e2e8f0) 75%);
    background-size: 200% 100%;
    animation: skeleton-pulse 1.5s ease-in-out infinite;
    height: 20px;
    border-radius: 4px;
}
.skeleton-kpi-container {
    display: flex;
    gap: 20px;
    margin-bottom: 20px;
}
.skeleton-kpi-card {
    flex: 1;
    background: linear-gradient(90deg,
        var(--color-bg-card-alt, #e2e8f0) 25%,
        var(--color-border, #cbd5e1) 50%,
        var(--color-bg-card-alt, #e2e8f0) 75%);
    background-size: 200% 100%;
    animation: skeleton-pulse 1.5s ease-in-out infinite;
    border-radius: var(--radius-card, 12px);
    padding: 20px;
    height: 100px;
}
.skeleton-chart {
    background: linear-gradient(90deg,
        var(--color-bg-card-alt, #e2e8f0) 25%,
        var(--color-border, #cbd5e1) 50%,
        var(--color-bg-card-alt, #e2e8f0) 75%);
    background-size: 200% 100%;
    animation: skeleton-pulse 1.5s ease-in-out infinite;
    border-radius: var(--radius-card, 12px);
    width: 100%;
}
@keyframes skeleton-pulse {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}
</style>
"""


def show_skeleton_table(rows: int = 5, cols: int = 4) -> None:
    """
    Display skeleton table while loading.

    Args:
        rows: Number of skeleton rows
        cols: Number of columns
    """
    html = _SKELETON_CSS + '<table class="skeleton-table">'
    for _ in range(rows):
        html += '<tr>'
        for c in range(cols):
            width = "100%" if c == 0 else f"{60 + (c * 10)}%"
            html += f'<td><div class="skeleton-cell" style="width: {width}"></div></td>'
        html += '</tr>'
    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)


def show_skeleton_kpi(count: int = 4) -> None:
    """
    Display skeleton KPI cards while loading.

    Args:
        count: Number of skeleton cards
    """
    html = _SKELETON_CSS + '<div class="skeleton-kpi-container">'
    for _ in range(count):
        html += '<div class="skeleton-kpi-card"></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def show_skeleton_chart(height: int = 400) -> None:
    """
    Display skeleton chart while loading.

    Args:
        height: Height of skeleton in pixels
    """
    html = f'{_SKELETON_CSS}<div class="skeleton-chart" style="height: {height}px"></div>'
    st.markdown(html, unsafe_allow_html=True)


# ==========================================================
# Progress Bar Loading
# ==========================================================

class LoadingContext:
    """
    Context manager for loading state with progress bar.

    Usage:
        with show_loading_status("Loading data...") as loader:
            loader.update(0.5, "Halfway there...")
            # do work
            loader.update(1.0, "Complete!")
    """

    def __init__(self, message: str = "Loading..."):
        """
        Initialize loading context.

        Args:
            message: Initial loading message to display.
        """
        self.msg = message
        self.placeholder: Optional[st.empty] = None
        self.progress_bar = None

    def __enter__(self) -> "LoadingContext":
        """Enter context and create progress bar."""
        self.placeholder = st.empty()
        self.progress_bar = self.placeholder.progress(0, text=self.msg)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and clean up progress bar."""
        if self.progress_bar is not None:
            self.progress_bar.empty()

    def update(self, progress: float, message: Optional[str] = None) -> None:
        """
        Update progress bar.

        Args:
            progress: Progress value from 0.0 to 1.0.
            message: Optional new message to display.
        """
        if self.progress_bar is not None:
            msg = message or self.msg
            self.progress_bar.progress(int(progress * 100), text=msg)


def show_loading_status(message: str = "Loading data...") -> LoadingContext:
    """
    Create a loading state context manager.

    Args:
        message: Loading message to display.

    Returns:
        LoadingContext instance for use with 'with' statement.

    Example:
        with show_loading_status("Fetching records...") as loader:
            # Load data
            df = load_data()
            loader.update(0.5, "Processing...")
            # Process data
            process(df)
    """
    return LoadingContext(message)


# ==========================================================
# Status Display
# ==========================================================

def render_last_update() -> None:
    """
    Render last update timestamp.

    Displays the current timestamp indicating when data was last refreshed.
    """
    st.caption(f"마지막 업데이트: {datetime.now():%Y-%m-%d %H:%M:%S}")


def render_cache_status(cache_hit: bool) -> None:
    """
    Render cache hit/miss indicator.

    Args:
        cache_hit: True if data came from cache, False if from database.

    Displays a small status indicator showing whether data was loaded
    from cache or fetched from the database.
    """
    if cache_hit:
        st.success("캐시에서 로드됨", icon="✅")
    else:
        st.info("데이터베이스에서 로드됨", icon="ℹ️")
