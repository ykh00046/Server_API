"""Connection, schema, and migration management for the notifications DB.

Extracted from api/notifications/store.py (structure-cleanup, 2026-05-27).
``store.py`` re-exports ``reset_for_tests`` from here for back-compat.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import shared.config as _cfg
from shared import get_logger

logger = get_logger(__name__)

_local = threading.local()
_schema_lock = threading.Lock()
_schema_initialized: set[str] = set()  # keyed by str(db_path)
_schema_v2_initialized: set[str] = set()  # webhook-async-dispatch-v2 migration


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
            except sqlite3.Error:
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
    _ensure_schema_v2(conn, path)


def _ensure_schema_v2(conn: sqlite3.Connection, path: Path) -> None:
    """Idempotent v2 migration: add attempt / next_attempt_at / enqueued_at
    columns and the due-row index. Safe to run repeatedly."""
    key = str(path)
    with _schema_lock:
        if key in _schema_v2_initialized:
            return
        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(webhook_deliveries)"
            ).fetchall()
        }
        if "attempt" not in existing:
            conn.execute(
                "ALTER TABLE webhook_deliveries ADD COLUMN attempt "
                "INTEGER NOT NULL DEFAULT 1"
            )
        if "next_attempt_at" not in existing:
            conn.execute(
                "ALTER TABLE webhook_deliveries ADD COLUMN next_attempt_at TEXT"
            )
        if "enqueued_at" not in existing:
            conn.execute(
                "ALTER TABLE webhook_deliveries ADD COLUMN enqueued_at TEXT"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_deliveries_due "
            "ON webhook_deliveries(status, next_attempt_at)"
        )
        conn.commit()
        _schema_v2_initialized.add(key)


def reset_for_tests() -> None:
    """Drop thread-local cache + schema-init cache. Test-only."""
    for attr in list(vars(_local)):
        if attr.startswith("conn::"):
            conn = getattr(_local, attr, None)
            if conn is not None:
                try:
                    conn.close()
                except (sqlite3.Error, OSError) as e:
                    logger.debug("reset_for_tests close failed: %s", e)
            setattr(_local, attr, None)
    with _schema_lock:
        _schema_initialized.clear()
        _schema_v2_initialized.clear()
