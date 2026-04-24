"""
Toast Notification Components

Provides toast notification system for user feedback.
Uses Streamlit's built-in toast functionality where available,
with CSS fallback for custom styling.

v8 Enhancement: Initial implementation
"""

from __future__ import annotations

import streamlit as st
from enum import Enum
from typing import Optional
from datetime import datetime


class ToastType(Enum):
    """Toast notification types."""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


def show_toast(
    message: str,
    type: ToastType = ToastType.INFO,
    icon: Optional[str] = None
) -> None:
    """
    Show a toast notification.

    Args:
        message: Message to display
        type: Type of notification (success, error, warning, info)
        icon: Optional icon override

    Note:
        Uses Streamlit's native toast when available (st.toast in Streamlit 1.34+),
        falls back to styled alert for older versions.
    """
    # Default icons by type
    default_icons = {
        ToastType.SUCCESS: "✅",
        ToastType.ERROR: "❌",
        ToastType.WARNING: "⚠️",
        ToastType.INFO: "ℹ️",
    }

    icon = icon or default_icons.get(type, "ℹ️")

    # Use Streamlit's native toast if available
    if hasattr(st, 'toast'):
        if type == ToastType.SUCCESS:
            st.toast(message, icon="✅")
        elif type == ToastType.ERROR:
            st.toast(message, icon="❌")
        elif type == ToastType.WARNING:
            st.toast(message, icon="⚠️")
        else:
            st.toast(message, icon="ℹ️")
    else:
        # Fallback to styled message
        _show_fallback_toast(message, type)


def _show_fallback_toast(message: str, type: ToastType) -> None:
    """Fallback toast using styled message."""
    if type == ToastType.SUCCESS:
        st.success(message)
    elif type == ToastType.ERROR:
        st.error(message)
    elif type == ToastType.WARNING:
        st.warning(message)
    else:
        st.info(message)


# Convenience functions
def toast_success(message: str) -> None:
    """Show success toast notification."""
    show_toast(message, ToastType.SUCCESS)


def toast_error(message: str) -> None:
    """Show error toast notification."""
    show_toast(message, ToastType.ERROR)


def toast_warning(message: str) -> None:
    """Show warning toast notification."""
    show_toast(message, ToastType.WARNING)


def toast_info(message: str) -> None:
    """Show info toast notification."""
    show_toast(message, ToastType.INFO)


class NotificationManager:
    """
    Manages multiple notifications with queue support.

    Usage:
        notifier = NotificationManager()
        notifier.add("Data saved", ToastType.SUCCESS)
        notifier.add("Warning: Low disk space", ToastType.WARNING)
        notifier.render()  # Display all notifications
    """

    def __init__(self):
        self._notifications: list[tuple[str, ToastType, datetime]] = []

    def add(
        self,
        message: str,
        type: ToastType = ToastType.INFO
    ) -> "NotificationManager":
        """
        Add a notification to the queue.

        Args:
            message: Notification message
            type: Notification type

        Returns:
            Self for chaining
        """
        self._notifications.append((message, type, datetime.now()))
        return self

    def success(self, message: str) -> "NotificationManager":
        """Add success notification."""
        return self.add(message, ToastType.SUCCESS)

    def error(self, message: str) -> "NotificationManager":
        """Add error notification."""
        return self.add(message, ToastType.ERROR)

    def warning(self, message: str) -> "NotificationManager":
        """Add warning notification."""
        return self.add(message, ToastType.WARNING)

    def info(self, message: str) -> "NotificationManager":
        """Add info notification."""
        return self.add(message, ToastType.INFO)

    def render(self) -> None:
        """Render all queued notifications."""
        for message, type, _ in self._notifications:
            show_toast(message, type)
        self._notifications.clear()

    def clear(self) -> None:
        """Clear all notifications without rendering."""
        self._notifications.clear()

    @property
    def count(self) -> int:
        """Get number of pending notifications."""
        return len(self._notifications)


# Global notification manager instance
_notification_manager: Optional[NotificationManager] = None


def get_notifier() -> NotificationManager:
    """
    Get global notification manager instance.

    Returns:
        NotificationManager instance
    """
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
