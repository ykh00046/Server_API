"""CRUD + async-queue operations for the webhook_deliveries table.

Extracted from api/notifications/store.py (structure-cleanup, 2026-05-27).
Covers both v1 sync path (create_pending / finalize) and the v2 async path
(enqueue / claim / record_attempt / queue_stats / requeue).
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Any, Mapping

from shared import get_logger

from .schemas import DeliveryPublic
from ._store_connection import _get_conn
from ._store_models import (
    ClaimedDelivery,
    _now_iso,
    _row_to_delivery,
)

logger = get_logger(__name__)


# ----- v1 sync path -------------------------------------------------------
def create_pending_delivery(
    webhook_id: int, event_type: str, payload: Mapping[str, Any]
) -> int:
    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO webhook_deliveries
            (webhook_id, event_type, payload, status, attempted_at, duration_ms)
        VALUES (?, ?, ?, 'pending', ?, 0)
        """,
        (webhook_id, event_type, json.dumps(dict(payload)), _now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def finalize_delivery(
    delivery_id: int,
    *,
    status: str,
    response_status: int | None,
    response_body: str | None,
    error: str | None,
    duration_ms: int,
) -> None:
    conn = _get_conn()
    conn.execute(
        """
        UPDATE webhook_deliveries
        SET status = ?, response_status = ?, response_body = ?, error = ?,
            duration_ms = ?, attempted_at = ?
        WHERE id = ?
        """,
        (
            status,
            response_status,
            response_body,
            error,
            duration_ms,
            _now_iso(),
            delivery_id,
        ),
    )
    conn.commit()


def get_delivery(delivery_id: int) -> DeliveryPublic | None:
    row = _get_conn().execute(
        "SELECT * FROM webhook_deliveries WHERE id = ?", (delivery_id,)
    ).fetchone()
    return _row_to_delivery(row) if row else None


# ----- v2 async path ------------------------------------------------------
def enqueue_delivery(
    webhook_id: int,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    now_iso: str | None = None,
) -> int:
    """Insert a queued delivery row. Returns delivery_id.

    Unlike ``create_pending_delivery`` (v1 sync path), this sets:
        status='queued', attempt=1, next_attempt_at=now (eligible immediately),
        enqueued_at=now.
    """
    now = now_iso or _now_iso()
    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO webhook_deliveries
            (webhook_id, event_type, payload, status, attempted_at,
             duration_ms, attempt, next_attempt_at, enqueued_at)
        VALUES (?, ?, ?, 'queued', ?, 0, 1, ?, ?)
        """,
        (webhook_id, event_type, json.dumps(dict(payload)), now, now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def claim_due_deliveries(*, now_iso: str, limit: int) -> list[ClaimedDelivery]:
    """Atomically transition up to ``limit`` due rows to 'in_flight' and
    return them joined with their webhook (url, secret).

    A row is due when:
      status IN ('queued', 'retrying')
      AND (next_attempt_at IS NULL OR next_attempt_at <= now_iso)
      AND webhook.active = 1
    """
    limit = max(1, int(limit))
    conn = _get_conn()
    claimed: list[ClaimedDelivery] = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT d.id, d.webhook_id, d.event_type, d.payload, d.attempt,
                   w.url, w.secret
              FROM webhook_deliveries d
              JOIN webhooks w ON w.id = d.webhook_id
             WHERE d.status IN ('queued','retrying')
               AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= ?)
               AND w.active = 1
             ORDER BY d.next_attempt_at ASC, d.id ASC
             LIMIT ?
            """,
            (now_iso, limit),
        ).fetchall()
        for r in rows:
            upd = conn.execute(
                "UPDATE webhook_deliveries SET status='in_flight' "
                "WHERE id = ? AND status IN ('queued','retrying')",
                (r["id"],),
            )
            if upd.rowcount == 0:
                continue
            claimed.append(
                ClaimedDelivery(
                    id=r["id"],
                    webhook_id=r["webhook_id"],
                    event_type=r["event_type"],
                    payload=json.loads(r["payload"]),
                    attempt=int(r["attempt"] or 1),
                    url=r["url"],
                    secret=r["secret"],
                )
            )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.warning("[notifications.store] claim failed: %s", e)
        return []
    return claimed


def record_attempt(
    delivery_id: int,
    *,
    outcome: Any,                # dispatcher.DispatchResult
    next_status: str,            # 'success' | 'failure' | 'retrying' | 'dead'
    next_attempt_at: str | None,
    attempt: int,
) -> None:
    """Finalize one attempt. Updates the row with the dispatch outcome
    plus the new status / attempt / next_attempt_at."""
    conn = _get_conn()
    conn.execute(
        """
        UPDATE webhook_deliveries
        SET status = ?, response_status = ?, response_body = ?, error = ?,
            duration_ms = ?, attempted_at = ?, attempt = ?, next_attempt_at = ?
        WHERE id = ?
        """,
        (
            next_status,
            outcome.response_status,
            outcome.response_body,
            outcome.error,
            outcome.duration_ms,
            _now_iso(),
            attempt,
            next_attempt_at,
            delivery_id,
        ),
    )
    conn.commit()


def queue_stats() -> dict[str, int]:
    """Counters for /notifications/queue/stats endpoint."""
    conn = _get_conn()
    out: dict[str, int] = {
        "queued": 0,
        "in_flight": 0,
        "retrying": 0,
        "success_24h": 0,
        "failure_24h": 0,
        "dead": 0,
    }
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM webhook_deliveries GROUP BY status"
    ).fetchall()
    for r in rows:
        s = r["status"]
        if s in ("queued", "in_flight", "retrying", "dead"):
            out[s] = int(r["n"])
    cutoff = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    ).isoformat()
    rows2 = conn.execute(
        """
        SELECT status, COUNT(*) AS n FROM webhook_deliveries
        WHERE attempted_at >= ? AND status IN ('success', 'failure')
        GROUP BY status
        """,
        (cutoff,),
    ).fetchall()
    for r in rows2:
        s = r["status"]
        if s == "success":
            out["success_24h"] = int(r["n"])
        elif s == "failure":
            out["failure_24h"] = int(r["n"])
    return out


def requeue_delivery(delivery_id: int) -> bool:
    """Reset a delivery (typically dead/failure) back to queued with
    attempt=1 and next_attempt_at=now. Returns False if id not found."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id FROM webhook_deliveries WHERE id = ?", (delivery_id,)
    ).fetchone()
    if row is None:
        return False
    now = _now_iso()
    conn.execute(
        """
        UPDATE webhook_deliveries
        SET status='queued', attempt=1, next_attempt_at=?,
            response_status=NULL, response_body=NULL, error=NULL,
            duration_ms=0
        WHERE id = ?
        """,
        (now, delivery_id),
    )
    conn.commit()
    return True


def list_deliveries(
    webhook_id: int, *, limit: int = 50, status: str | None = None
) -> list[DeliveryPublic]:
    limit = max(1, min(int(limit), 500))
    if status:
        rows = _get_conn().execute(
            """
            SELECT * FROM webhook_deliveries
            WHERE webhook_id = ? AND status = ?
            ORDER BY id DESC LIMIT ?
            """,
            (webhook_id, status, limit),
        ).fetchall()
    else:
        rows = _get_conn().execute(
            """
            SELECT * FROM webhook_deliveries
            WHERE webhook_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (webhook_id, limit),
        ).fetchall()
    return [_row_to_delivery(r) for r in rows]
