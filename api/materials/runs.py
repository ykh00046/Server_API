"""Run history for material backups + automation triggers (materials-run-v1).

Records every backup received (kind='backup') and every manual automation
trigger (kind='automation') in the material_runs table, so the dashboard can
show "실행했는지 / 이력" without a GUI on the headless ops PC. Reuses the
materials.db connection + schema from store.py.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from .datasets import DEFAULT_DATASET
from .schemas import MaterialRun
from .store import _get_conn, _now_iso

# A bot run takes minutes; a 'running' row this old can only be an orphan
# (server killed/rebooted before the worker thread could finish_run). Kept
# generous because the spawned bot child process can outlive an API restart —
# reaping too early would allow a second bot alongside a surviving one.
STALE_RUNNING_SEC = 6 * 3600


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


def record_backup_run(
    rows: int, inserted: int, updated: int,
    runs_table: str = DEFAULT_DATASET.runs_table,
    *,
    message: str | None = None,
) -> int:
    """Record a completed backup as a success run in `runs_table`.

    `message`는 비고란(message 컬럼)에 쓰는 짧은 메모. 예: tombstone으로
    행이 건너뛰어졌을 때 'tombstone skipped=N'. None이면 컬럼에 NULL.
    """
    now = _now_iso()
    conn = _get_conn()
    cur = conn.execute(
        f"INSERT INTO {runs_table} "
        "(kind, status, started_at, finished_at, rows, inserted, updated, message) "
        "VALUES ('backup', 'success', ?, ?, ?, ?, ?, ?)",
        (now, now, rows, inserted, updated, message),
    )
    conn.commit()
    return cur.lastrowid


def start_run(kind: str, runs_table: str = DEFAULT_DATASET.runs_table) -> int:
    """Create a 'running' run and return its id."""
    now = _now_iso()
    conn = _get_conn()
    cur = conn.execute(
        f"INSERT INTO {runs_table} (kind, status, started_at) VALUES (?, 'running', ?)",
        (kind, now),
    )
    conn.commit()
    return cur.lastrowid


def finish_run(
    run_id: int,
    status: str,
    *,
    runs_table: str = DEFAULT_DATASET.runs_table,
    exit_code: int | None = None,
    message: str | None = None,
) -> None:
    """Mark a run finished (status 'success' | 'failed')."""
    conn = _get_conn()
    conn.execute(
        f"UPDATE {runs_table} SET status = ?, finished_at = ?, exit_code = ?, "
        "message = ? WHERE id = ?",
        (status, _now_iso(), exit_code, message, run_id),
    )
    conn.commit()


def reap_stale_running(
    runs_table: str = DEFAULT_DATASET.runs_table,
    *,
    older_than_sec: float = STALE_RUNNING_SEC,
) -> int:
    """Mark orphaned 'running' automation rows as failed.

    A running row is finalized only by its worker thread; if the process dies
    first, the row stays 'running' forever and has_active_automation blocks
    every future trigger with 409. Returns # of rows reaped."""
    cutoff = (
        dt.datetime.now() - dt.timedelta(seconds=older_than_sec)
    ).isoformat(timespec="seconds")
    conn = _get_conn()
    cur = conn.execute(
        f"UPDATE {runs_table} SET status = 'failed', finished_at = ?, "
        "message = 'stale running run reaped (server restart?)' "
        "WHERE kind = 'automation' AND status = 'running' AND started_at <= ?",
        (_now_iso(), cutoff),
    )
    conn.commit()
    return cur.rowcount or 0


def has_active_automation(runs_table: str = DEFAULT_DATASET.runs_table) -> bool:
    """True if an automation run is currently 'running' (concurrency guard)."""
    row = _get_conn().execute(
        f"SELECT 1 FROM {runs_table} WHERE kind = 'automation' AND status = 'running' "
        "LIMIT 1"
    ).fetchone()
    return row is not None


def get_run(
    run_id: int, runs_table: str = DEFAULT_DATASET.runs_table
) -> MaterialRun | None:
    row = _get_conn().execute(
        f"SELECT * FROM {runs_table} WHERE id = ?", (run_id,)
    ).fetchone()
    return _row_to_run(row) if row else None


def list_runs(
    *, runs_table: str = DEFAULT_DATASET.runs_table,
    kind: str | None = None, limit: int = 50,
) -> list[MaterialRun]:
    limit = max(1, min(limit, 500))
    if kind:
        rows = _get_conn().execute(
            f"SELECT * FROM {runs_table} WHERE kind = ? ORDER BY id DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    else:
        rows = _get_conn().execute(
            f"SELECT * FROM {runs_table} ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_run(r) for r in rows]
