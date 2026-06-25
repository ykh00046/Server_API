"""SQLite repository for 자재요청 (material request) intake.

A dedicated DB file (materials.db) keeps this backup data out of the
ERP-rewritten production_analysis.db and notifications.db. Modeled on the
api/notifications store pattern: path resolved at call time so tests can
monkeypatch shared.config.MATERIALS_DB_FILE, thread-local connection cache,
idempotent schema init.

Upsert semantics: `doc_number` (문서번호) is the primary key. Re-posting a
document updates it in place; `received_at` is preserved from first insert,
`updated_at` always refreshes.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
import threading
from pathlib import Path

import shared.config as _cfg
from shared import get_logger

from .datasets import DEFAULT_DATASET, all_datasets
from .schemas import BackupResult, MaterialPublic, MaterialRow

logger = get_logger(__name__)

_local = threading.local()
_schema_lock = threading.Lock()
_schema_initialized: set[str] = set()  # keyed by str(db_path)

# Column order for the material_requests table (excludes server timestamps).
_ROW_COLUMNS = (
    "doc_number",
    "seq",
    "material_code",
    "material_name",
    "request_qty_g",
    "reason",
    "request_dept",
    "drafter",
    "processed_at",
    "keyword",
)


def _db_path() -> Path:
    return Path(_cfg.MATERIALS_DB_FILE)


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _doc_date(doc_number: str) -> str | None:
    """Derive the document business date (YYYY-MM-DD) from the leading
    YYYYMMDD of doc_number (e.g. '20251127P001' -> '2025-11-27').

    This is the primary date basis for material requests (the date the
    document was drafted), NOT the scrape/처리 시각 in processed_at. Returns
    None if the 8-char prefix is not a valid date (sorts last).
    """
    if doc_number and len(doc_number) >= 8 and doc_number[:8].isdigit():
        try:
            return dt.datetime.strptime(doc_number[:8], "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


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
        logger.warning(f"[materials.store] PRAGMA setup failed: {e}")

    _ensure_schema(conn, path)
    setattr(_local, cache_key, conn)
    return conn


def _dataset_schema_sql(table: str, runs_table: str) -> str:
    """CREATE 문 생성 (데이터 테이블 + 실행이력 테이블). table/runs_table은
    registry에서 온 신뢰된 식별자이므로 f-string 보간이 안전하다."""
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            doc_number     TEXT PRIMARY KEY,
            seq            INTEGER,
            material_code  TEXT,
            material_name  TEXT,
            request_qty_g  TEXT,
            reason         TEXT,
            request_dept   TEXT,
            drafter        TEXT,
            processed_at   TEXT,
            keyword        TEXT,
            doc_date       TEXT,
            received_at    TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_{table}_dept ON {table}(request_dept);
        CREATE INDEX IF NOT EXISTS idx_{table}_doc_date ON {table}(doc_date DESC);
        CREATE INDEX IF NOT EXISTS idx_{table}_keyword ON {table}(keyword);

        CREATE TABLE IF NOT EXISTS {runs_table} (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kind         TEXT NOT NULL,        -- 'backup' | 'automation'
            status       TEXT NOT NULL,        -- 'running' | 'success' | 'failed'
            started_at   TEXT NOT NULL,
            finished_at  TEXT,
            rows         INTEGER,
            inserted     INTEGER,
            updated      INTEGER,
            exit_code    INTEGER,
            message      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_{runs_table}_started
            ON {runs_table}(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_{runs_table}_active
            ON {runs_table}(kind, status);
    """


def _migrate_table(conn: sqlite3.Connection, table: str) -> None:
    """기존 DB(데이터셋 도입 전)에 누락된 컬럼을 멱등 추가한다.

    materials-api-v1 시절의 material_requests는 doc_date/keyword가 없었다.
    새로 생성되는 데이터셋 테이블은 풀스키마라 이 마이그레이션이 no-op이다.
    """
    existing = {
        r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if "doc_date" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN doc_date TEXT")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_doc_date "
            f"ON {table}(doc_date DESC)"
        )
    if "keyword" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN keyword TEXT")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_keyword ON {table}(keyword)"
        )


def _ensure_schema(conn: sqlite3.Connection, path: Path) -> None:
    key = str(path)
    with _schema_lock:
        if key in _schema_initialized:
            return
        # 등록된 모든 데이터셋의 테이블을 한 DB 파일에 생성한다.
        for ds in all_datasets():
            conn.executescript(_dataset_schema_sql(ds.table, ds.runs_table))
            _migrate_table(conn, ds.table)
        conn.commit()
        _schema_initialized.add(key)


def _row_values(row: MaterialRow) -> tuple:
    """Project a MaterialRow into the _ROW_COLUMNS tuple (qty coerced to str)."""
    qty = row.request_qty_g
    qty_str = None if qty is None else str(qty)
    return (
        row.doc_number,
        row.seq,
        row.material_code,
        row.material_name,
        qty_str,
        row.reason,
        row.request_dept,
        row.drafter,
        row.processed_at,
        row.keyword,
    )


def upsert_materials(
    rows: list[MaterialRow], table: str = DEFAULT_DATASET.table
) -> BackupResult:
    """Batch upsert by doc_number into `table`. Returns inserted vs updated.

    Within a single batch, later rows with a duplicate doc_number overwrite
    earlier ones (last-write-wins), matching the full-snapshot intent.
    """
    conn = _get_conn()
    now = _now_iso()

    # Dedupe within the batch (last-write-wins) so counts are unambiguous.
    deduped: dict[str, MaterialRow] = {}
    for r in rows:
        deduped[r.doc_number] = r
    incoming = list(deduped.values())

    incoming_docs = list(deduped.keys())
    existing: set[str] = set()
    # SQLite caps parameters per statement (~999/32766); chunk the IN clause.
    for start in range(0, len(incoming_docs), 500):
        chunk = incoming_docs[start:start + 500]
        placeholders = ",".join("?" * len(chunk))
        existing.update(
            r["doc_number"]
            for r in conn.execute(
                f"SELECT doc_number FROM {table} "
                f"WHERE doc_number IN ({placeholders})",
                chunk,
            ).fetchall()
        )

    sql = f"""
        INSERT INTO {table}
            (doc_number, seq, material_code, material_name, request_qty_g,
             reason, request_dept, drafter, processed_at, keyword, doc_date,
             received_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_number) DO UPDATE SET
            seq           = excluded.seq,
            material_code = excluded.material_code,
            material_name = excluded.material_name,
            request_qty_g = excluded.request_qty_g,
            reason        = excluded.reason,
            request_dept  = excluded.request_dept,
            drafter       = excluded.drafter,
            processed_at  = excluded.processed_at,
            keyword       = excluded.keyword,
            doc_date      = excluded.doc_date,
            updated_at    = excluded.updated_at
    """
    # doc_date is server-derived from doc_number (SSOT) — the primary date basis.
    params = [(*_row_values(r), _doc_date(r.doc_number), now, now) for r in incoming]
    conn.executemany(sql, params)
    conn.commit()

    updated = sum(1 for d in incoming_docs if d in existing)
    inserted = len(incoming_docs) - updated
    return BackupResult(upserted=len(incoming_docs), inserted=inserted, updated=updated)


def _row_to_public(row: sqlite3.Row) -> MaterialPublic:
    return MaterialPublic(
        doc_number=row["doc_number"],
        seq=row["seq"],
        material_code=row["material_code"],
        material_name=row["material_name"],
        request_qty_g=row["request_qty_g"],
        reason=row["reason"],
        request_dept=row["request_dept"],
        drafter=row["drafter"],
        processed_at=row["processed_at"],
        keyword=row["keyword"],
        doc_date=row["doc_date"],
        received_at=row["received_at"],
        updated_at=row["updated_at"],
    )


def get_material(
    doc_number: str, table: str = DEFAULT_DATASET.table
) -> MaterialPublic | None:
    row = _get_conn().execute(
        f"SELECT * FROM {table} WHERE doc_number = ?", (doc_number,)
    ).fetchone()
    return _row_to_public(row) if row else None


def list_materials(
    *,
    table: str = DEFAULT_DATASET.table,
    request_dept: str | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 1000,
) -> list[MaterialPublic]:
    """List rows ordered by 문서번호 date (doc_date) descending.

    Filters (all optional): department, 수집 키워드, and a doc_date range
    (YYYY-MM-DD, inclusive). doc_date is the document business date derived
    from doc_number — the primary date basis, not the scrape time.
    """
    limit = max(1, min(limit, 5000))
    where: list[str] = []
    params: list = []
    if request_dept:
        where.append("request_dept = ?")
        params.append(request_dept)
    if keyword:
        where.append("keyword = ?")
        params.append(keyword)
    if date_from:
        where.append("doc_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("doc_date <= ?")
        params.append(date_to)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    rows = _get_conn().execute(
        f"SELECT * FROM {table}{clause} "
        "ORDER BY doc_date DESC, doc_number DESC LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_public(r) for r in rows]


def count_materials(table: str = DEFAULT_DATASET.table) -> int:
    return _get_conn().execute(
        f"SELECT COUNT(*) AS n FROM {table}"
    ).fetchone()["n"]


def reset_for_tests() -> None:
    """Drop thread-local connection cache + schema-init cache. Test-only."""
    for attr in list(vars(_local)):
        if attr.startswith("conn::"):
            conn = getattr(_local, attr, None)
            if conn is not None:
                with contextlib.suppress(sqlite3.Error, OSError):
                    conn.close()
            setattr(_local, attr, None)
    with _schema_lock:
        _schema_initialized.clear()
