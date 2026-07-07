"""Data model for anomaly detection findings.

A `Finding` is the unit produced by the pure rule functions in `rules.py`
and consumed by `detector.py` (for cooldown dedup + emit). It is plain data
— no I/O, no behavior beyond serialization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# kind -> webhook event_type. Keeping the mapping here (single source of truth)
# lets detector emit and __init__ pre-register without duplicating strings.
KIND_EVENT_TYPES: dict[str, str] = {
    "volume_drop": "production.anomaly.volume_drop",
    "volume_spike": "production.anomaly.volume_spike",
    "stale_item": "production.anomaly.stale_item",
}

EVENT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "production.anomaly.volume_drop": (
        "Daily good-quantity dropped sharply below the trailing average."
    ),
    "production.anomaly.volume_spike": (
        "Daily good-quantity spiked sharply above the trailing average."
    ),
    "production.anomaly.stale_item": (
        "A previously-active item has not been produced for an extended period."
    ),
}

# Severity ordering (low -> high) for optional downstream sorting/filtering.
SEVERITY_ORDER: dict[str, int] = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class RuleOverrides:
    """What-if threshold overrides (anomaly-dashboard-v2 F5).

    None = use the config value. Only the GET (preview) path may carry
    overrides — run_detection rejects emit=True + overrides as defense in
    depth, so what-if can never distort a real emission decision."""

    drop_pct: float | None = None
    spike_pct: float | None = None
    stale_days: int | None = None
    min_baseline_qty: float | None = None
    baseline_days: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Non-None overrides only — echoed in the scan response."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Finding:
    """A single detected anomaly."""

    kind: str
    severity: str
    key: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        """Webhook event type this finding maps to."""
        return KIND_EVENT_TYPES.get(self.kind, f"production.anomaly.{self.kind}")

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form, with event_type included."""
        out = asdict(self)
        out["event_type"] = self.event_type
        return out
