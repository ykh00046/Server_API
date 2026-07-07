"""Anomaly detection subsystem (anomaly-detection-v1).

Scans production data on a schedule, applies rule-based detectors
(volume drop/spike, stale items), and emits findings as webhook events
via the existing notifications subsystem.

Public surface:
    collect_findings(today=None) -> list[Finding]   # read-only, no emit
    run_detection(emit=True, today=None) -> dict     # scan (+ optional emit)
"""
from __future__ import annotations

from .detector import collect_findings, run_detection
from .schemas import (
    EVENT_TYPE_DESCRIPTIONS,
    KIND_EVENT_TYPES,
    Finding,
    RuleOverrides,
)
from .store_findings import list_findings

__all__ = [
    "Finding",
    "KIND_EVENT_TYPES",
    "RuleOverrides",
    "collect_findings",
    "list_findings",
    "run_detection",
]


def _register_event_types() -> None:
    """Pre-register anomaly event types so they appear in the webhook admin
    UI / KNOWN_EVENT_TYPES even before the first anomaly fires."""
    try:
        from api.notifications.events import register_event_type

        for event_type, desc in EVENT_TYPE_DESCRIPTIONS.items():
            register_event_type(event_type, desc)
    except Exception:  # noqa: BLE001 — registration is best-effort, never fatal at import
        pass


_register_event_types()
