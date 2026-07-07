"""
U6: Loading State Display - status display helpers.

2026-07 정리: 스켈레톤 3종·LoadingContext·render_cache_status는 호출처가
없어 제거 (unsafe_allow_html 예산 3곳도 함께 회수). 실사용은
render_last_update 하나뿐이다.
"""

from datetime import datetime

import streamlit as st


def render_last_update() -> None:
    """
    Render last update timestamp.

    Displays the current timestamp indicating when data was last refreshed.
    """
    st.caption(f"마지막 업데이트: {datetime.now():%Y-%m-%d %H:%M:%S}")
