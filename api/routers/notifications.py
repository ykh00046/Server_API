"""HTTP endpoints for webhook notifications (webhook-notifications-v1).

Thin layer over api/notifications/*.  All business logic (validation,
DB access, dispatch) lives in the notifications package — this module
only translates between HTTP and those primitives.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from shared import get_logger

from ..notifications import KNOWN_EVENT_TYPES, emit_event, store
from ..notifications.schemas import (
    DeliveryPublic,
    EventTypeInfo,
    TestPing,
    WebhookCreate,
    WebhookCreated,
    WebhookPublic,
    WebhookUpdate,
)


class QueueStats(BaseModel):
    """Queue health snapshot returned by /notifications/queue/stats."""

    queued: int
    in_flight: int
    retrying: int
    success_24h: int
    failure_24h: int
    dead: int


class BulkRetryRequest(BaseModel):
    """Filter for POST /notifications/deliveries/bulk-retry."""

    statuses: list[str] = Field(default_factory=lambda: ["dead"])
    webhook_id: int | None = None
    limit: int = Field(default=500, ge=1, le=5000)
    dry_run: bool = False


class BulkRetryResult(BaseModel):
    """Outcome of a bulk dead-letter retry request."""

    requeued: int
    ids: list[int]
    dry_run: bool
    statuses: list[str]
    webhook_id: int | None = None


logger = get_logger(__name__)
router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ==========================================================
# Webhook CRUD
# ==========================================================
@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
def create_webhook(req: WebhookCreate):
    try:
        created, _ = store.create_webhook(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return created


@router.get("/webhooks", response_model=list[WebhookPublic])
def list_webhooks(active: bool | None = Query(default=None)):
    return store.list_public(active=active)


@router.get("/webhooks/{webhook_id}", response_model=WebhookPublic)
def get_webhook(webhook_id: int):
    wh = store.get_public(webhook_id)
    if wh is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    return wh


@router.patch("/webhooks/{webhook_id}", response_model=WebhookPublic | WebhookCreated)
def update_webhook(webhook_id: int, req: WebhookUpdate):
    try:
        result, _ = store.update_webhook(
            webhook_id,
            event_types=req.event_types,
            description=req.description,
            active=req.active,
            rotate_secret=req.rotate_secret,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if result is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    return result


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int):
    if not store.delete_webhook(webhook_id):
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    return {"deleted": True, "id": webhook_id}


# ==========================================================
# Test ping + deliveries
# ==========================================================
@router.post("/webhooks/{webhook_id}/test", response_model=DeliveryPublic)
def test_webhook(webhook_id: int, body: TestPing | None = None):
    if store.get_record(webhook_id) is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    payload: dict[str, Any] = (body.payload if body and body.payload else {"ok": True})
    # Force-emit ignoring subscription list: the user is explicitly testing
    # this single webhook regardless of its event_types. We replicate the
    # emit_event flow (pending → dispatch → finalize) inline so the active
    # flag and subscription filter don't gate the test.
    rec = store.get_record(webhook_id)
    if rec is None:  # pragma: no cover (re-check after the prior None guard)
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    from ..notifications import dispatcher  # local import keeps router import graph shallow
    delivery_id = store.create_pending_delivery(rec.id, "webhook.test", payload)
    outcome = dispatcher.send(
        url=rec.url,
        secret=rec.secret,
        event_type="webhook.test",
        delivery_id=delivery_id,
        payload=payload,
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
    if d is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="delivery record missing after dispatch")
    return d


@router.get(
    "/webhooks/{webhook_id}/deliveries",
    response_model=list[DeliveryPublic],
)
def list_deliveries(
    webhook_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    before_id: int | None = Query(
        default=None, ge=1,
        description="keyset 커서 — 이전 페이지 마지막 id (그보다 오래된 행 조회)",
    ),
):
    if store.get_record(webhook_id) is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    return store.list_deliveries(
        webhook_id, limit=limit, status=status, before_id=before_id
    )


# ==========================================================
# Event catalog
# ==========================================================
@router.get("/events", response_model=list[EventTypeInfo])
def list_events():
    return [
        EventTypeInfo(name=name, description=desc)
        for name, desc in sorted(KNOWN_EVENT_TYPES.items())
    ]


# ==========================================================
# Async dispatch queue (webhook-async-dispatch-v2)
# ==========================================================
@router.get("/queue/stats", response_model=QueueStats)
def queue_stats():
    return QueueStats(**store.queue_stats())


_ALLOWED_BULK_STATUSES = set(store.RETRYABLE_TERMINAL_STATUSES)  # {"dead", "failure"}


@router.post("/deliveries/bulk-retry", response_model=BulkRetryResult)
def bulk_retry_deliveries(req: BulkRetryRequest):
    """Re-queue every terminal-failure delivery (dead/failure) matching the
    filter. Built for post-outage recovery when many deliveries pile up in
    the dead-letter state. ``dry_run`` reports what would be re-queued
    without mutating anything."""
    requested = [str(s).strip().lower() for s in req.statuses if str(s).strip()]
    if not requested:
        raise HTTPException(
            status_code=400,
            detail="statuses must contain at least one of: "
            + ", ".join(sorted(_ALLOWED_BULK_STATUSES)),
        )
    invalid = [s for s in requested if s not in _ALLOWED_BULK_STATUSES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported statuses {invalid}; allowed: "
            + ", ".join(sorted(_ALLOWED_BULK_STATUSES)),
        )
    if req.dry_run:
        ids = store.list_retryable_delivery_ids(
            statuses=requested, webhook_id=req.webhook_id, limit=req.limit
        )
    else:
        ids = store.requeue_deliveries(
            statuses=requested, webhook_id=req.webhook_id, limit=req.limit
        )
    return BulkRetryResult(
        requeued=len(ids),
        ids=ids,
        dry_run=req.dry_run,
        statuses=requested,
        webhook_id=req.webhook_id,
    )


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryPublic)
def retry_delivery(delivery_id: int):
    if not store.requeue_delivery(delivery_id):
        raise HTTPException(status_code=404, detail=f"delivery {delivery_id} not found")
    d = store.get_delivery(delivery_id)
    if d is None:  # pragma: no cover (requeue just succeeded)
        raise HTTPException(status_code=500, detail="delivery vanished after requeue")
    return d


# Re-export for callers that prefer `from api.routers.notifications import emit_event`.
__all__ = ["router", "emit_event"]
