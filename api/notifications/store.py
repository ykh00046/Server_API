"""SQLite repository for webhooks and delivery history.

A separate DB file (notifications.db) keeps webhook metadata out of the
production_analysis.db that the ERP intake pipeline rewrites periodically.

Connection strategy mirrors shared/database.py (thread-local cache + WAL
PRAGMAs) but scoped to a single DB so no DBRouter complexity is needed.
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import shared.config as _cfg
from shared import get_logger

from .schemas import (
    DeliveryPublic,
    WebhookCreate,
    WebhookCreated,
    WebhookPublic,
    validate_event_types,
    validate_webhook_url,
)

logger = get_logger(__name__)

_local = threading.local()
_schema_lock = threading.Lock()
_schema_initialized: set[str] = set()  # keyed by str(db_path)


# ==========================================================
# Connection management
# ==========================================================
def _db_path() -> Path:
    """Resolve the notifications DB path at call time so tests can monkeypatch
    shared.config.NOTIFICATIONS_DB_FILE between cases."""
    return Path(_cfg.NOTIFICATIONS_DB_FILE)


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    cache_key = f"conn::{path}"
    cached = getattr(_local, cache_key, None)
    if cached is not None:
        try:
            cached.execute("SELECT 1")
            return cached
        except sqlite3.Error:
            try:
                cached.close()
            except Exception:
                pass
            setattr(_local, cache_key, None)

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
    except sqlite3.Error as e:  # pragma: no cover (PRAGMAs almost never fail)
        logger.warning(f"[notifications.store] PRAGMA setup failed: {e}")

    _ensure_schema(conn, path)
    setattr(_local, cache_key, conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection, path: Path) -> None:
    key = str(path)
    with _schema_lock:
        if key in _schema_initialized:
            return
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT NOT NULL,
                secret          TEXT NOT NULL,
                event_types     TEXT NOT NULL,
                description     TEXT NOT NULL DEFAULT '',
                active          INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_webhooks_active ON webhooks(active);

            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id      INTEGER NOT NULL,
                event_type      TEXT NOT NULL,
                payload         TEXT NOT NULL,
                status          TEXT NOT NULL,
                response_status INTEGER,
                response_body   TEXT,
                error           TEXT,
                attempted_at    TEXT NOT NULL,
                duration_ms     INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_deliveries_webhook
                ON webhook_deliveries(webhook_id, attempted_at DESC);
            """
        )
        conn.commit()
        _schema_initialized.add(key)


def reset_for_tests() -> None:
    """Drop thread-local cache + schema-init cache. Test-only."""
    # Best-effort close of cached connections for this thread.
    for attr in list(vars(_local)):
        if attr.startswith("conn::"):
            try:
                getattr(_local, attr).close()
            except Exception:
                pass
            setattr(_local, attr, None)
    with _schema_lock:
        _schema_initialized.clear()


# ==========================================================
# Internal row mapping
# ==========================================================
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
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


# ==========================================================
# Webhook CRUD
# ==========================================================
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
        INSERT INTO webhooks (url, secret, event_types, description, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (url, secret, json.dumps(event_types), description, 1 if req.active else 0, now, now),
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
    conn.execute("DELETE FROM webhook_deliveries WHERE webhook_id = ?", (webhook_id,))
    conn.commit()
    return cur.rowcount > 0


# ==========================================================
# Deliveries
# ==========================================================
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
