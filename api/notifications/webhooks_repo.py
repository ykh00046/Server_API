"""CRUD operations for the webhooks table.

Extracted from api/notifications/store.py (structure-cleanup, 2026-05-27).
"""
from __future__ import annotations

import json
from typing import Any

from ._store_connection import _get_conn
from ._store_models import (
    WebhookRecord,
    _generate_secret,
    _now_iso,
    _record_to_public,
    _row_to_record,
)
from .schemas import (
    WebhookCreate,
    WebhookCreated,
    WebhookPublic,
    validate_event_types,
    validate_webhook_url,
)


def create_webhook(req: WebhookCreate) -> tuple[WebhookCreated, WebhookRecord]:
    """Validate, insert, and return (public-with-secret, internal-record)."""
    url = validate_webhook_url(req.url)
    event_types = validate_event_types(req.event_types)
    description = req.description or ""
    secret = _generate_secret()
    now = _now_iso()
    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO webhooks (url, secret, event_types, description, active,
                              created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            url,
            secret,
            json.dumps(event_types),
            description,
            1 if req.active else 0,
            now,
            now,
        ),
    )
    conn.commit()
    wh_id = cur.lastrowid
    rec = get_record(wh_id)
    assert rec is not None
    created = WebhookCreated(
        id=rec.id,
        url=rec.url,
        event_types=rec.event_types,
        description=rec.description,
        active=rec.active,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        secret=secret,
    )
    return created, rec


def get_record(webhook_id: int) -> WebhookRecord | None:
    row = _get_conn().execute(
        "SELECT * FROM webhooks WHERE id = ?", (webhook_id,)
    ).fetchone()
    return _row_to_record(row) if row else None


def get_public(webhook_id: int) -> WebhookPublic | None:
    rec = get_record(webhook_id)
    return _record_to_public(rec) if rec else None


def list_public(active: bool | None = None) -> list[WebhookPublic]:
    if active is None:
        rows = _get_conn().execute(
            "SELECT * FROM webhooks ORDER BY id ASC"
        ).fetchall()
    else:
        rows = _get_conn().execute(
            "SELECT * FROM webhooks WHERE active = ? ORDER BY id ASC",
            (1 if active else 0,),
        ).fetchall()
    return [_record_to_public(_row_to_record(r)) for r in rows]


def list_records(active_only: bool = False) -> list[WebhookRecord]:
    """Internal — includes secret. Used by events.emit_event."""
    if active_only:
        rows = _get_conn().execute(
            "SELECT * FROM webhooks WHERE active = 1 ORDER BY id ASC"
        ).fetchall()
    else:
        rows = _get_conn().execute(
            "SELECT * FROM webhooks ORDER BY id ASC"
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def update_webhook(
    webhook_id: int,
    *,
    event_types: list[str] | None = None,
    description: str | None = None,
    active: bool | None = None,
    rotate_secret: bool = False,
) -> tuple[WebhookPublic | WebhookCreated | None, WebhookRecord | None]:
    """Apply partial update. Returns (response_model, internal_record).

    response_model is WebhookCreated when rotate_secret=True (so the caller
    can return the new plaintext secret), else WebhookPublic.
    """
    rec = get_record(webhook_id)
    if rec is None:
        return None, None
    conn = _get_conn()
    sets: list[str] = []
    params: list[Any] = []
    if event_types is not None:
        sets.append("event_types = ?")
        params.append(json.dumps(validate_event_types(event_types)))
    if description is not None:
        sets.append("description = ?")
        params.append(description)
    if active is not None:
        sets.append("active = ?")
        params.append(1 if active else 0)
    new_secret: str | None = None
    if rotate_secret:
        new_secret = _generate_secret()
        sets.append("secret = ?")
        params.append(new_secret)
    if not sets:
        # No fields changed — return current state without bumping updated_at.
        return _record_to_public(rec), rec
    sets.append("updated_at = ?")
    params.append(_now_iso())
    params.append(webhook_id)
    conn.execute(f"UPDATE webhooks SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    updated = get_record(webhook_id)
    assert updated is not None
    if rotate_secret and new_secret is not None:
        return (
            WebhookCreated(
                id=updated.id,
                url=updated.url,
                event_types=updated.event_types,
                description=updated.description,
                active=updated.active,
                created_at=updated.created_at,
                updated_at=updated.updated_at,
                secret=new_secret,
            ),
            updated,
        )
    return _record_to_public(updated), updated


def delete_webhook(webhook_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    # Manual cascade — SQLite ON DELETE CASCADE requires foreign_keys=ON
    # at connection time; we set that PRAGMA, but belt-and-suspenders.
    conn.execute(
        "DELETE FROM webhook_deliveries WHERE webhook_id = ?", (webhook_id,)
    )
    conn.commit()
    return cur.rowcount > 0
