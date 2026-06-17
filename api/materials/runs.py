"""Run history for material backups + automation triggers (materials-run-v1).

Records every backup received (kind='backup') and every manual automation
trigger (kind='automation') in the material_runs table, so the dashboard can
show "실행했는지 / 이력" without a GUI on the headless ops PC. Reuses the
materials.db connection + schema from store.py.
"""
from __future__ import annotations

import sqlite3

from .schemas import MaterialRun
from .store import _get_conn, _now_iso


def _row_to_run(row: sqlite3.Row) -> MaterialRun:
    return MaterialRun(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        rows=row["rows"],
        inserted=row["inserted"],
        updated=row["updated"],
        exit_code=row["exit_code"],
        message=row["message"],
    )


def record_backup_run(rows: int, inserted: int, updated: int) -> int:
    """Record a completed backup (POST /materials/backup) as a success run."""
    now = _now_iso()
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO material_runs "
        "(kind, status, started_at, finished_at, rows, inserted, updated) "
        "VALUES ('backup', 'success', ?, ?, ?, ?, ?)",
        (now, now, rows, inserted, updated),
    )
    conn.commit()
    return cur.lastrowid


def start_run(kind: str) -> int:
    """Create a 'running' run and return its id."""
    now = _now_iso()
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO material_runs (kind, status, started_at) VALUES (?, 'running', ?)",
        (kind, now),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(
    run_id: int,
    status: str,
    *,
    exit_code: int | None = None,
    message: str | None = None,
) -> None:
    """Mark a run finished (status 'success' | 'failed')."""
    conn = _get_conn()
    conn.execute(
        "UPDATE material_runs SET status = ?, finished_at = ?, exit_code = ?, "
        "message = ? WHERE id = ?",
        (status, _now_iso(), exit_code, message, run_id),
    )
    conn.commit()


def has_active_automation() -> bool:
    """True if an automation run is currently 'running' (concurrency guard)."""
    row = _get_conn().execute(
        "SELECT 1 FROM material_runs WHERE kind = 'automation' AND status = 'running' "
        "LIMIT 1"
    ).fetchone()
    return row is not None


def get_run(run_id: int) -> MaterialRun | None:
    row = _get_conn().execute(
        "SELECT * FROM material_runs WHERE id = ?", (run_id,)
    ).fetchone()
    return _row_to_run(row) if row else None


def list_runs(*, kind: str | None = None, limit: int = 50) -> list[MaterialRun]:
    limit = max(1, min(limit, 500))
    if kind:
        rows = _get_conn().execute(
            "SELECT * FROM material_runs WHERE kind = ? ORDER BY id DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    else:
        rows = _get_conn().execute(
            "SELECT * FROM material_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_run(r) for r in rows]
