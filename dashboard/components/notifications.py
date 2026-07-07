"""
Toast Notification Components — thin wrappers over st.toast.

2026-07 정리: ToastType/NotificationManager/get_notifier/toast_warning은
호출처가 없어 제거. 실사용은 webhook_admin이 쓰는 아래 3개 래퍼뿐이다.
(st.toast는 Streamlit 1.34+ 네이티브 — 구버전 fallback도 함께 제거)
"""

from __future__ import annotations

import streamlit as st


def toast_success(message: str) -> None:
    """Show success toast notification."""
    st.toast(message, icon=":material/check_circle:")


def toast_error(message: str) -> None:
    """Show error toast notification."""
    st.toast(message, icon=":material/error:")


def toast_info(message: str) -> None:
    """Show info toast notification."""
    st.toast(message, icon=":material/info:")
