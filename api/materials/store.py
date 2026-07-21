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


# 데이터 테이블의 전체 컬럼(순서 고정) — PK 재구성 시 복사에 사용.
_TABLE_COLUMNS = (
    "doc_number, seq, material_code, material_name, request_qty_g, reason, "
    "request_dept, drafter, processed_at, keyword, doc_date, received_at, updated_at"
)


def _table_ddl(table: str) -> str:
    """데이터 테이블 CREATE (인덱스 제외). table은 registry의 신뢰된 식별자.

    PK는 (doc_number, seq) 복합키 — 한 문서(doc_number)에 품목이 여러 행
    (순번만 다름)이므로 doc_number 단독 PK는 품목을 마지막 1개로 뭉갠다.
    인덱스는 컬럼 마이그레이션 이후에 따로 생성한다(_indexes_ddl).
    """
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            doc_number     TEXT NOT NULL,
            seq            INTEGER NOT NULL DEFAULT 0,
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
            updated_at     TEXT NOT NULL,
            PRIMARY KEY (doc_number, seq)
        );
    """


def _indexes_ddl(table: str) -> str:
    """데이터 테이블 인덱스 (모든 컬럼이 존재한 뒤 생성)."""
    return f"""
        CREATE INDEX IF NOT EXISTS idx_{table}_dept ON {table}(request_dept);
        CREATE INDEX IF NOT EXISTS idx_{table}_doc_date ON {table}(doc_date DESC);
        CREATE INDEX IF NOT EXISTS idx_{table}_keyword ON {table}(keyword);
        CREATE INDEX IF NOT EXISTS idx_{table}_doc ON {table}(doc_number);
    """


def _runs_ddl(runs_table: str) -> str:
    """실행이력 테이블 CREATE + 인덱스."""
    return f"""
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


# 삭제된 문서의 묘비(tombstone) 테이블 — 모든 데이터셋이 공유한다.
# (table_name, doc_number) 단위로 삭제 시각을 기록하여, 봇이 같은 문서를
# 재전송해도 upsert가 무시되도록 한다. restore가 아니면 사라지지 않는다.
_TOMBSTONE_DDL = """
CREATE TABLE IF NOT EXISTS deleted_documents (
    table_name  TEXT NOT NULL,
    doc_number  TEXT NOT NULL,
    deleted_at  TEXT NOT NULL,
    PRIMARY KEY (table_name, doc_number)
);
"""


def _migrate_table(conn: sqlite3.Connection, table: str) -> None:
    """기존 DB를 현재 스키마로 멱등 마이그레이션한다.

    1) materials-api-v1 시절 누락 컬럼(doc_date/keyword) 추가.
    2) PK를 doc_number 단독 → (doc_number, seq) 복합키로 재구성. 단독 PK는
       한 문서의 여러 품목을 마지막 1행으로 뭉개므로(데이터 손실) 반드시 교정.
    새로 생성되는 테이블은 풀스키마라 둘 다 no-op이다. (인덱스는 호출부에서
    이 함수 이후에 생성하므로 doc_date/keyword 컬럼 의존 문제가 없다.)
    """
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {r["name"] for r in info}
    if "doc_date" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN doc_date TEXT")
    if "keyword" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN keyword TEXT")

    # PK 재구성: 현재 PK 컬럼이 doc_number 단독이면 복합키로 재빌드.
    pk_cols = [r["name"] for r in info if r["pk"]]
    if pk_cols == ["doc_number"]:
        logger.info(
            "[materials.store] %s PK 재구성: doc_number → (doc_number, seq) "
            "— 문서당 품목 다행 복원", table
        )
        conn.executescript(
            f"ALTER TABLE {table} RENAME TO _mig_{table};\n"
            + _table_ddl(table)
            + f"""
            INSERT OR IGNORE INTO {table} ({_TABLE_COLUMNS})
                SELECT doc_number, COALESCE(seq, 0), material_code, material_name,
                       request_qty_g, reason, request_dept, drafter, processed_at,
                       keyword, doc_date, received_at, updated_at
                FROM _mig_{table};
            DROP TABLE _mig_{table};
            """
        )


def _ensure_schema(conn: sqlite3.Connection, path: Path) -> None:
    key = str(path)
    with _schema_lock:
        if key in _schema_initialized:
            return
        # 등록된 모든 데이터셋의 테이블을 한 DB 파일에 생성한다.
        # 순서: 테이블 생성 → 컬럼/PK 마이그레이션 → 인덱스 생성
        # (인덱스를 마지막에 둬야 레거시 테이블의 신규 컬럼 의존이 깨지지 않음)
        for ds in all_datasets():
            conn.executescript(_runs_ddl(ds.runs_table))
            conn.executescript(_table_ddl(ds.table))
            _migrate_table(conn, ds.table)
            conn.executescript(_indexes_ddl(ds.table))
        # 삭제된 문서 묘비 테이블 — 모든 데이터셋이 공유 (dataset마다 table_name으로 격리).
        conn.executescript(_TOMBSTONE_DDL)
        conn.commit()
        _schema_initialized.add(key)


def _seq_key(row: MaterialRow) -> int:
    """복합 PK용 순번 키. None/비정수는 0으로 정규화(품목 단위 식별)."""
    try:
        return int(row.seq) if row.seq is not None else 0
    except (TypeError, ValueError):
        return 0


def _row_values(row: MaterialRow) -> tuple:
    """Project a MaterialRow into the _ROW_COLUMNS tuple (qty coerced to str)."""
    qty = row.request_qty_g
    qty_str = None if qty is None else str(qty)
    return (
        row.doc_number,
        _seq_key(row),
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
    """Batch upsert by (doc_number, seq) into `table`.

    한 문서(doc_number)는 품목마다 순번이 다른 여러 행을 가지므로 (doc_number,
    seq) 단위로 upsert한다. 같은 키가 배치 안에 중복이면 마지막 값이 이긴다
    (full-snapshot 의도). 반환 카운트는 행(품목) 단위.

    삭제된 문서(tombstone)의 행은 이 배치에서 제외된다 — 서버에서 지운 문서를
    봇이 재전송해도 다시 살아나지 않는다. 제외된 행 수는 `skipped`로 반환.
    """
    conn = _get_conn()
    now = _now_iso()

    # Dedupe within the batch by (doc_number, seq) — last-write-wins.
    deduped: dict[tuple[str, int], MaterialRow] = {}
    for r in rows:
        deduped[(r.doc_number, _seq_key(r))] = r
    incoming_keys = list(deduped.keys())

    # 서버에서 삭제된 문서(tombstone) 조회 — 이 배치의 doc_number에 한해.
    # existing-keys 조회와 동일한 청크 패턴(500단위)을 쓴다. tombstone에 있는
    # doc_number는 배치에서 완전히 빠진다(모든 seq). skipped는 제외된 '행' 수.
    batch_docs = list({k[0] for k in incoming_keys})
    tombstoned_docs: set[str] = set()
    for start in range(0, len(batch_docs), 500):
        chunk = batch_docs[start:start + 500]
        placeholders = ",".join("?" * len(chunk))
        tombstoned_docs.update(
            r["doc_number"]
            for r in conn.execute(
                "SELECT doc_number FROM deleted_documents "
                "WHERE table_name = ? "
                f"AND doc_number IN ({placeholders})",
                [table, *chunk],
            ).fetchall()
        )
    if tombstoned_docs:
        incoming_keys = [k for k in incoming_keys if k[0] not in tombstoned_docs]
    incoming = [deduped[k] for k in incoming_keys]
    skipped = sum(1 for k in deduped if k[0] in tombstoned_docs)

    # 기존 (doc_number, seq) 조합 조회 — inserted/updated 카운트용.
    # doc_number로 모아 조회 후 (doc, seq) 집합을 만든다(복합 IN 회피).
    batch_docs = list({k[0] for k in incoming_keys})
    existing: set[tuple[str, int]] = set()
    for start in range(0, len(batch_docs), 500):
        chunk = batch_docs[start:start + 500]
        placeholders = ",".join("?" * len(chunk))
        existing.update(
            (r["doc_number"], r["seq"])
            for r in conn.execute(
                f"SELECT doc_number, seq FROM {table} "
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
        ON CONFLICT(doc_number, seq) DO UPDATE SET
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

    updated = sum(1 for k in incoming_keys if k in existing)
    inserted = len(incoming_keys) - updated
    return BackupResult(
        upserted=len(incoming_keys),
        inserted=inserted,
        updated=updated,
        skipped=skipped,
    )


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


def get_document(
    doc_number: str, table: str = DEFAULT_DATASET.table
) -> list[MaterialPublic]:
    """한 문서(doc_number)의 모든 품목 행을 순번 오름차순으로 반환."""
    rows = _get_conn().execute(
        f"SELECT * FROM {table} WHERE doc_number = ? ORDER BY seq ASC",
        (doc_number,),
    ).fetchall()
    return [_row_to_public(r) for r in rows]


def get_material(
    doc_number: str, table: str = DEFAULT_DATASET.table
) -> MaterialPublic | None:
    """문서의 첫 품목(최소 순번) 1행. 단건 조회/하위호환용."""
    row = _get_conn().execute(
        f"SELECT * FROM {table} WHERE doc_number = ? ORDER BY seq ASC LIMIT 1",
        (doc_number,),
    ).fetchone()
    return _row_to_public(row) if row else None


def delete_document(
    doc_number: str, table: str = DEFAULT_DATASET.table
) -> int:
    """한 문서(doc_number)의 모든 품목 행을 삭제하고 삭제된 행 수를 반환한다.

    실수로 기안된 문서·중복 문서를 서버에서 제거하기 위한 관리용 연산. 문서
    번호가 없으면 0을 반환한다(멱등). 삭제는 이 데이터셋 테이블에만 적용된다
    (table은 registry의 신뢰된 식별자).

    행이 실제로 지워졌으면(rowcount>0) 같은 커밋에 묘비(tombstone)를 남긴다
    — 이후 봇이 전체 Excel을 재전송해도 이 문서는 upsert에서 제외되어 다시
    살아나지 않는다. 되돌리려면 restore_document()로 tombstone만 지우면
    다음 백업 시 재유입된다.
    """
    conn = _get_conn()
    cur = conn.execute(f"DELETE FROM {table} WHERE doc_number = ?", (doc_number,))
    if cur.rowcount > 0:
        conn.execute(
            "INSERT OR REPLACE INTO deleted_documents "
            "(table_name, doc_number, deleted_at) VALUES (?, ?, ?)",
            (table, doc_number, _now_iso()),
        )
    conn.commit()
    return cur.rowcount


def restore_document(
    doc_number: str, table: str = DEFAULT_DATASET.table
) -> int:
    """한 문서의 묘비(tombstone)를 제거해 봇 재전송 시 다시 받아들이도록 한다.

    delete_document가 남긴 tombstone을 지운다 — 데이터 행 자체는 복구하지
    않으므로, 문서 내용은 봇의 다음 재전송으로 upsert되어야 돌아온다.
    tombstone이 없으면 0(멱등). 반환은 제거된 tombstone 행 수.
    """
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM deleted_documents WHERE table_name = ? AND doc_number = ?",
        (table, doc_number),
    )
    conn.commit()
    return cur.rowcount


def list_tombstones(
    table: str = DEFAULT_DATASET.table
) -> list[dict]:
    """해당 데이터셋의 tombstone 목록을 반환 (최근 삭제 순).

    반환 항목: [{'doc_number': str, 'deleted_at': str}, ...]
    정렬: deleted_at DESC, doc_number (tie-breaker).
    """
    rows = _get_conn().execute(
        "SELECT doc_number, deleted_at FROM deleted_documents "
        "WHERE table_name = ? "
        "ORDER BY deleted_at DESC, doc_number ASC",
        (table,),
    ).fetchall()
    return [{"doc_number": r["doc_number"], "deleted_at": r["deleted_at"]}
            for r in rows]


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
        "ORDER BY doc_date DESC, doc_number DESC, seq ASC LIMIT ?",
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
