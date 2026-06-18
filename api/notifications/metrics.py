"""Prometheus-compatible read model for webhook operational metrics.

All values are SQLite snapshots, so every exported family is a gauge. Only
fixed labels are used; URLs, IDs, secrets, event types, and payloads never
enter the metrics surface.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from ._store_connection import _get_conn

# Design Ref: §3 — fixed cardinality with explicit zero-valued states.
WEBHOOK_STATES: tuple[str, ...] = ("active", "inactive")
DELIVERY_STATUSES: tuple[str, ...] = (
    "pending", "queued", "in_flight", "retrying",
    "success", "failure", "dead", "skipped",
)
OUTCOMES_24H: tuple[str, ...] = ("success", "failure")


@dataclass(frozen=True)
class WebhookMetricsSnapshot:
    webhooks: dict[str, int]
    deliveries: dict[str, int]
    deliveries_24h: dict[str, int]
    duration_avg_ms_24h: float
    duration_max_ms_24h: int
    oldest_queue_age_seconds: float


def _as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def _age_seconds(timestamp: str | None, now: dt.datetime) -> float:
    if not timestamp:
        return 0.0
    try:
        parsed = _as_utc(dt.datetime.fromisoformat(timestamp))
    except ValueError:
        return 0.0
    return max(0.0, (_as_utc(now) - parsed).total_seconds())


def collect_snapshot(*, now: dt.datetime | None = None) -> WebhookMetricsSnapshot:
    """Collect one read-only metrics snapshot from the notifications DB."""
    current = _as_utc(now or dt.datetime.now(dt.UTC))
    cutoff = (current - dt.timedelta(hours=24)).isoformat()
    conn = _get_conn()

    webhooks = {state: 0 for state in WEBHOOK_STATES}
    for row in conn.execute(
        "SELECT active, COUNT(*) AS n FROM webhooks GROUP BY active"
    ).fetchall():
        webhooks["active" if bool(row["active"]) else "inactive"] = int(row["n"])

    deliveries = {status: 0 for status in DELIVERY_STATUSES}
    for row in conn.execute(
        "SELECT status, COUNT(*) AS n FROM webhook_deliveries GROUP BY status"
    ).fetchall():
        status = str(row["status"])
        if status in deliveries:
            deliveries[status] = int(row["n"])

    deliveries_24h = {outcome: 0 for outcome in OUTCOMES_24H}
    for row in conn.execute(
        """
        SELECT status, COUNT(*) AS n
          FROM webhook_deliveries
         WHERE attempted_at >= ? AND status IN ('success', 'failure')
         GROUP BY status
        """,
        (cutoff,),
    ).fetchall():
        deliveries_24h[str(row["status"])] = int(row["n"])

    duration = conn.execute(
        """
        SELECT COALESCE(AVG(duration_ms), 0.0) AS avg_ms,
               COALESCE(MAX(duration_ms), 0) AS max_ms
          FROM webhook_deliveries
         WHERE attempted_at >= ? AND status IN ('success', 'failure')
        """,
        (cutoff,),
    ).fetchone()
    oldest = conn.execute(
        """
        SELECT MIN(COALESCE(enqueued_at, attempted_at)) AS oldest_at
          FROM webhook_deliveries
         WHERE status IN ('queued', 'retrying')
        """
    ).fetchone()

    return WebhookMetricsSnapshot(
        webhooks=webhooks,
        deliveries=deliveries,
        deliveries_24h=deliveries_24h,
        duration_avg_ms_24h=float(duration["avg_ms"]),
        duration_max_ms_24h=int(duration["max_ms"]),
        oldest_queue_age_seconds=_age_seconds(oldest["oldest_at"], current),
    )


def _number(value: int | float) -> str:
    """Render a finite Prometheus number without locale-dependent formatting."""
    if isinstance(value, int):
        return str(value)
    number = float(value)
    if not math.isfinite(number):
        return "0"
    if number.is_integer():
        return str(int(number))
    return format(number, ".6g")


def _family(name: str, help_text: str, samples: list[str]) -> list[str]:
    return [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", *samples]


def render_prometheus(snapshot: WebhookMetricsSnapshot | None = None) -> str:
    """Render a snapshot using Prometheus text exposition format 0.0.4."""
    data = snapshot or collect_snapshot()
    lines: list[str] = []

    name = "production_data_hub_webhooks"
    lines.extend(_family(name, "Configured webhooks by activation state.", [
        f'{name}{{state="{state}"}} {_number(data.webhooks[state])}'
        for state in WEBHOOK_STATES
    ]))
    name = "production_data_hub_webhook_deliveries"
    lines.extend(_family(name, "Stored webhook deliveries by current status.", [
        f'{name}{{status="{status}"}} {_number(data.deliveries[status])}'
        for status in DELIVERY_STATUSES
    ]))
    name = "production_data_hub_webhook_deliveries_24h"
    lines.extend(_family(
        name,
        "Completed webhook deliveries in the trailing 24 hours by outcome.",
        [
            f'{name}{{outcome="{outcome}"}} {_number(data.deliveries_24h[outcome])}'
            for outcome in OUTCOMES_24H
        ],
    ))

    scalar_families = (
        (
            "production_data_hub_webhook_delivery_duration_avg_ms_24h",
            "Average completed webhook delivery duration in milliseconds over 24 hours.",
            data.duration_avg_ms_24h,
        ),
        (
            "production_data_hub_webhook_delivery_duration_max_ms_24h",
            "Maximum completed webhook delivery duration in milliseconds over 24 hours.",
            data.duration_max_ms_24h,
        ),
        (
            "production_data_hub_webhook_oldest_queue_age_seconds",
            "Age in seconds of the oldest queued or retrying webhook delivery.",
            data.oldest_queue_age_seconds,
        ),
    )
    for metric_name, help_text, value in scalar_families:
        lines.extend(_family(metric_name, help_text, [f"{metric_name} {_number(value)}"]))

    # Plan SC-1: Prometheus exposition requires a trailing newline.
    return "\n".join(lines) + "\n"


__all__ = [
    "DELIVERY_STATUSES", "OUTCOMES_24H", "WEBHOOK_STATES",
    "WebhookMetricsSnapshot", "collect_snapshot", "render_prometheus",
]
