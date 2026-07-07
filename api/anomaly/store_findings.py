"""Append-only persistence for emitted anomaly findings (anomaly-dashboard-v2).

Records every successfully-emitted finding into a dedicated SQLite file
(``anomaly.db`` — same per-subsystem file-split convention as notifications/
materials) so the dashboard can show a history timeline. The cooldown state
file cannot serve this purpose: it holds only key→timestamp, is pruned at
7×cooldown, and carries no message/severity.

Contract with the emit path (design FR-6): **nothing in this module raises
to its callers** — a history-write failure must never break or delay webhook
emission. Failures are logged and reported as 0.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import shared.config as _cfg
from shared import get_logger

from .schemas import Finding

logger = get_logger(__name__)

_local = threading.local()
_schema_lock = threading.Lock()
_schema_initialized: set[str] = set()

_LIST_LIMIT_MAX = 500


def _db_path() -> Path:
    """Resolve at call time so tests can monkeypatch cfg.ANOMALY_DB_FILE."""
    return Path(_cfg.ANOMALY_DB_FILE)


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    cache_key = f"conn::{path}"
    cached = getattr(_local, cache_key, None)
    if cached is not None:
        try:
            cached.execute("SELECT 1")
            return cached
        except sqlite3.Error:
            with contextlib.suppress(sqlite3.Error):
                cached.close()
            setattr(_local, cache_key, None)

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except sqlite3.Error as e:  # pragma: no cover (PRAGMAs almost never fail)
        logger.warning("[anomaly.findings] PRAGMA setup failed: %s", e)

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
            CREATE TABLE IF NOT EXISTS anomaly_findings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kind        TEXT NOT NULL,
                severity    TEXT NOT NULL,
                key         TEXT NOT NULL,
                message     TEXT NOT NULL,
                details     TEXT NOT NULL DEFAULT '{}',
                event_type  TEXT NOT NULL,
                emitted_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_findings_emitted
                ON anomaly_findings(emitted_at);
            CREATE INDEX IF NOT EXISTS idx_findings_kind
                ON anomaly_findings(kind, emitted_at);
            """
        )
        conn.commit()
        _schema_initialized.add(key)


def record_findings(
    findings: list[Finding], *, now_iso: str | None = None
) -> int:
    """Append emitted findings to history. Returns # recorded.

    Never raises (FR-6): the emit path calls this fire-and-forget, so any
    disk/lock failure is logged and swallowed."""
    if not findings:
        return 0
    now = now_iso or _now_iso()
    try:
        conn = _get_conn()
        conn.executemany(
            "INSERT INTO anomaly_findings "
            "(kind, severity, key, message, details, event_type, emitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    f.kind, f.severity, f.key, f.message,
                    json.dumps(f.details, ensure_ascii=False),
                    f.event_type, now,
                )
                for f in findings
            ],
        )
        conn.commit()
        return len(findings)
    except Exception as e:  # noqa: BLE001 — fire-and-forget boundary: 이력 실패가 발행을 막으면 안 된다
        logger.warning("[anomaly.findings] record failed (이력만 유실): %s", e)
        return 0


def list_findings(
    *,
    days: int = 30,
    kind: str | None = None,
    severity: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Emitted findings within the last ``days``, newest first.

    details is deserialized back to a dict. On storage errors returns []
    (v1 convention: read paths never raise to the router)."""
    days = max(1, int(days))
    limit = max(1, min(int(limit), _LIST_LIMIT_MAX))
    cutoff = (
        dt.datetime.now() - dt.timedelta(days=days)
    ).isoformat(timespec="seconds")

    where = ["emitted_at >= ?"]
    params: list[Any] = [cutoff]
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if severity:
        where.append("severity = ?")
        params.append(severity)
    params.append(limit)

    try:
        rows = _get_conn().execute(
            f"""
            SELECT id, kind, severity, key, message, details, event_type,
                   emitted_at
              FROM anomaly_findings
             WHERE {" AND ".join(where)}
             ORDER BY emitted_at DESC, id DESC
             LIMIT ?
            """,
            params,
        ).fetchall()
    except sqlite3.Error as e:
        logger.warning("[anomaly.findings] list failed: %s", e)
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        try:
            item["details"] = json.loads(item["details"] or "{}")
        except (TypeError, json.JSONDecodeError):
            item["details"] = {}
        out.append(item)
    return out


def prune_findings(*, retention_days: int | None = None) -> int:
    """Delete history older than the retention window. Returns # deleted.

    Never raises — called lazily from the emit path (same FR-6 contract)."""
    retention = (
        retention_days
        if retention_days is not None
        else _cfg.ANOMALY_FINDINGS_RETENTION_DAYS
    )
    retention = max(1, int(retention))
    cutoff = (
        dt.datetime.now() - dt.timedelta(days=retention)
    ).isoformat(timespec="seconds")
    try:
        conn = _get_conn()
        cur = conn.execute(
            "DELETE FROM anomaly_findings WHERE emitted_at < ?", (cutoff,)
        )
        conn.commit()
        return int(cur.rowcount or 0)
    except Exception as e:  # noqa: BLE001 — fire-and-forget boundary (record_findings와 동일 계약)
        logger.warning("[anomaly.findings] prune failed: %s", e)
        return 0


def reset_for_tests() -> None:
    """Drop thread-local connections + schema-init cache. Test-only."""
    for attr in list(vars(_local)):
        if attr.startswith("conn::"):
            conn = getattr(_local, attr, None)
            if conn is not None:
                with contextlib.suppress(sqlite3.Error):
                    conn.close()
            setattr(_local, attr, None)
    with _schema_lock:
        _schema_initialized.clear()
