"""HTTP endpoints for webhook notifications (webhook-notifications-v1).

Thin layer over api/notifications/*.  All business logic (validation,
DB access, dispatch) lives in the notifications package — this module
only translates between HTTP and those primitives.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from shared import get_logger

from ..notifications import KNOWN_EVENT_TYPES, emit_event
from ..notifications import store
from ..notifications.schemas import (
    DeliveryPublic,
    EventTypeInfo,
    TestPing,
    WebhookCreate,
    WebhookCreated,
    WebhookPublic,
    WebhookUpdate,
)

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
        raise HTTPException(status_code=400, detail=str(e))
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
        raise HTTPException(status_code=400, detail=str(e))
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
):
    if store.get_record(webhook_id) is None:
        raise HTTPException(status_code=404, detail=f"webhook {webhook_id} not found")
    return store.list_deliveries(webhook_id, limit=limit, status=status)


# ==========================================================
# Event catalog
# ==========================================================
@router.get("/events", response_model=list[EventTypeInfo])
def list_events():
    return [
        EventTypeInfo(name=name, description=desc)
        for name, desc in sorted(KNOWN_EVENT_TYPES.items())
    ]


# Re-export for callers that prefer `from api.routers.notifications import emit_event`.
__all__ = ["router", "emit_event"]
