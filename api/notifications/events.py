"""Event registry + emit_event entrypoint.

`emit_event` is the only function other code in this project should call
when something interesting happens (e.g. a new production record was
inserted). It looks up active webhooks whose `event_types` includes the
event, sends to each via the dispatcher, and records each attempt.

The dispatcher never raises, and emit_event also never raises: callers can
fire-and-forget.
"""
from __future__ import annotations

from typing import Any, Mapping

import httpx

from shared import get_logger

from . import dispatcher, store
from .schemas import DeliveryPublic

logger = get_logger(__name__)


KNOWN_EVENT_TYPES: dict[str, str] = {
    "webhook.test": "Manual test ping (POST /notifications/webhooks/{id}/test).",
    "production.record.created": "A new production record was inserted into the live DB.",
    "production.threshold.exceeded": "A production volume crossed a configured threshold.",
}


def register_event_type(name: str, description: str = "") -> None:
    """Register a new event type if not already known. Idempotent."""
    if not name:
        return
    KNOWN_EVENT_TYPES.setdefault(name, description or "")


def emit_event(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[DeliveryPublic]:
    """Dispatch event to all active, subscribed webhooks.

    Args:
        event_type: namespaced event name, e.g. 'production.record.created'.
        payload: JSON-serializable mapping; sent as the request body.
        transport: optional httpx transport (test seam — injected by tests).

    Returns:
        List of DeliveryPublic, one per webhook that matched. Empty list if
        no matching webhooks (or all are inactive).
    """
    register_event_type(event_type)
    results: list[DeliveryPublic] = []
    for rec in store.list_records(active_only=True):
        if event_type not in rec.event_types:
            continue
        delivery_id = store.create_pending_delivery(rec.id, event_type, payload)
        outcome = dispatcher.send(
            url=rec.url,
            secret=rec.secret,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
            transport=transport,
        )
        store.finalize_delivery(
            delivery_id,
            status=outcome.status,
            response_status=outcome.response_status,
            response_body=outcome.response_body,
            error=outcome.error,
            duration_ms=outcome.duration_ms,
        )
        d = store.get_delivery(delivery_id)
        if d is not None:
            results.append(d)
    logger.info(
        "[webhook.emit] event=%s matched=%d", event_type, len(results)
    )
    return results
