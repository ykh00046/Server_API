"""
Responsive Layout Utilities — global CSS for mobile/tablet/desktop adaptation.

Currently the only public API is `apply_responsive_css()`, which is called
once during dashboard app initialization (`dashboard/app.py`).

History:
- v1 (ui-ux-enhancement, 2026-04): Added viewport detection wrappers
  (`get_optimal_columns`, `responsive_grid`, `detect_viewport`, etc.).
- v2 (products-refactor, 2026-04-23): Removed the entire viewport-detection
  chain after confirming `detect_viewport()`'s `postMessage` does not propagate
  to `st.session_state`, leaving the dependent helpers as dead code.
  Wrapper helpers (`get_responsive_columns`, `touch_friendly_button`,
  `touch_friendly_slider`) had no external callers and added no value beyond
  the global CSS, so they were also removed.
  If real viewport detection is needed in the future, consider integrating
  `streamlit-js-eval` (separate cycle).
"""

import streamlit as st


def apply_responsive_css() -> None:
    """
    Apply responsive CSS for mobile / tablet / desktop layouts.

    Injects CSS that:
    - Stacks chart/content columns vertically on mobile (<768px)
    - Switches to 2-column layout on tablet (768-1024px)
    - Provides full-width breathing room on desktop (>1024px)
    - Enforces touch-friendly button sizing (min 44x44 globally)
    - Allows tables and Plotly charts to scroll horizontally when needed

    Should be called once during app initialization.
    """
    st.markdown("""
    <style>
        /* ─── Touch-friendly buttons (global, injected once) ─── */
        div[data-testid="stButton"] button {
            min-height: 44px;
            min-width: 44px;
        }

        /* ─── Mobile responsive ─── */
        @media (max-width: 768px) {
            /* Stack only chart/content columns, not KPI rows or button groups */
            .block-container div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }
            .block-container div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                flex: 0 0 100% !important;
                max-width: 100% !important;
            }
            .stButton button {
                padding: 12px 20px;
            }
            [data-testid="stSidebar"] {
                width: 280px !important;
            }
            .stDataFrame {
                overflow-x: auto;
            }
            /* Keep metric columns side-by-side on mobile (2-up) */
            [data-testid="stMetric"] {
                min-width: 0;
            }
        }

        /* ─── Tablet ─── */
        @media (min-width: 768px) and (max-width: 1024px) {
            .block-container div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
            }
            .block-container div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                flex: 0 0 50% !important;
                max-width: 50% !important;
            }
        }

        /* ─── Desktop ─── */
        @media (min-width: 1024px) {
            .block-container {
                max-width: 100%;
                padding-left: 2rem;
                padding-right: 2rem;
            }
        }

        /* Chart responsiveness */
        .js-plotly-plot {
            width: 100% !important;
        }
        .stDataFrame [data-testid="stHorizontalBlock"] {
            overflow-x: auto;
        }
    </style>
    """, unsafe_allow_html=True)
