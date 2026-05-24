"""Webhook notifications subsystem (webhook-notifications-v1).

Public API:
    emit_event(event_type, payload, *, transport=None) -> list[DeliveryPublic]
    register_event_type(name, description)
    KNOWN_EVENT_TYPES: dict[str, str]

Other modules in this package (`store`, `dispatcher`, `schemas`) are also
importable, but external callers should prefer the events entrypoint above.
"""
from __future__ import annotations

from .events import (
    KNOWN_EVENT_TYPES,
    emit_event,
    register_event_type,
)

__all__ = [
    "KNOWN_EVENT_TYPES",
    "emit_event",
    "register_event_type",
]
