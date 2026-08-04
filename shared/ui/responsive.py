"""
Responsive Layout Utilities — global CSS for mobile/desktop adaptation.

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
- v3 (dashboard-ui-med, 2026-08): Removed the tablet (768–1024px) block. It
  forced **every** `stHorizontalBlock` column to `flex: 0 0 50%`, which threw
  away the deliberate column ratios the pages are built on (헤더 [8,2],
  AI 분할 [7,3], 4-up KPI 행, 액션 행 [3,1,1]) and reflowed them into an
  arbitrary 2-up grid. Mobile (<768px, full stacking) and desktop (>1024px,
  padding) remain — tablet widths now simply render the desktop ratios.
"""

import streamlit as st


def apply_responsive_css() -> None:
    """
    Apply responsive CSS for mobile / desktop layouts.

    Injects CSS that:
    - Stacks chart/content columns vertically on mobile (<768px)
    - Provides full-width breathing room on desktop (>1024px)
    - Leaves tablet widths (768-1024px) on the desktop column ratios — a
      blanket 2-up override destroyed the pages' intentional ratios
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
