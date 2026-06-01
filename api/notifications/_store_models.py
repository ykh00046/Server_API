"""Internal dataclasses and row-mapping helpers for the notifications repos.

Extracted from api/notifications/store.py (structure-cleanup, 2026-05-27).
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any

from .schemas import DeliveryPublic, WebhookPublic


@dataclass
class WebhookRecord:
    """Internal full record including secret (for dispatcher use)."""

    id: int
    url: str
    secret: str
    event_types: list[str]
    description: str
    active: bool
    created_at: str
    updated_at: str


@dataclass
class ClaimedDelivery:
    """Row claimed by the worker — joins delivery + webhook for dispatch."""

    id: int
    webhook_id: int
    event_type: str
    payload: dict[str, Any]
    attempt: int
    url: str
    secret: str


def _row_to_record(row: sqlite3.Row) -> WebhookRecord:
    return WebhookRecord(
        id=row["id"],
        url=row["url"],
        secret=row["secret"],
        event_types=json.loads(row["event_types"]),
        description=row["description"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _record_to_public(rec: WebhookRecord) -> WebhookPublic:
    return WebhookPublic(
        id=rec.id,
        url=rec.url,
        event_types=rec.event_types,
        description=rec.description,
        active=rec.active,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _row_to_delivery(row: sqlite3.Row) -> DeliveryPublic:
    return DeliveryPublic(
        id=row["id"],
        webhook_id=row["webhook_id"],
        event_type=row["event_type"],
        status=row["status"],
        response_status=row["response_status"],
        response_body=row["response_body"],
        error=row["error"],
        attempted_at=row["attempted_at"],
        duration_ms=row["duration_ms"],
    )


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)
