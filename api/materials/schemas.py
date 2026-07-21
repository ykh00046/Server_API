"""Pydantic schemas for the material-requests intake API (materials-api-v1).

Mirrors the columns the webcloring-pdf 포털 자동화 writes to its local Excel
(자재요청목록). `doc_number` (문서번호) is the upsert key.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MaterialRow(BaseModel):
    """A single 자재요청 품목 row. Keyed by (doc_number, seq).

    한 문서(doc_number)는 품목마다 순번(seq)이 다른 여러 행을 가진다 — upsert
    키는 (doc_number, seq) 복합키다. seq 미지정 시 0으로 정규화된다.
    """

    doc_number: str = Field(min_length=1, max_length=100, description="문서번호 (upsert 키의 일부)")
    seq: int | None = Field(default=None, description="순번 (upsert 키의 일부, 품목 식별)")
    material_code: str | None = Field(default=None, max_length=100, description="자재코드")
    material_name: str | None = Field(default=None, max_length=300, description="품명")
    # 요청수량(g단위): source may be numeric or string; kept loose for fidelity.
    request_qty_g: str | int | float | None = Field(default=None, description="요청수량(g단위)")
    reason: str | None = Field(default=None, max_length=1000, description="사유")
    request_dept: str | None = Field(default=None, max_length=200, description="요청부서")
    drafter: str | None = Field(default=None, max_length=100, description="기안자")
    processed_at: str | None = Field(default=None, max_length=40, description="처리일시")
    # 수집 키워드 (시간대별 멀티 프로필 크롤링 구분용). 미지정 시 None.
    keyword: str | None = Field(default=None, max_length=100, description="수집 키워드")


class MaterialBackupRequest(BaseModel):
    """Batch upsert payload (one POST per automation run)."""

    rows: list[MaterialRow] = Field(min_length=1, max_length=5000)


class BackupResult(BaseModel):
    """Outcome of a batch upsert.

    `skipped` counts rows filtered out because their doc_number has a
    tombstone in `deleted_documents` for this table (서버에서 삭제된 문서가
    봇의 재전송으로 다시 살아나는 것을 방지). 항상 직렬화된다 — additive
    JSON 필드라 봇 쪽 payload contract에 무해하다(봇은 아는 키만 읽음).
    """

    upserted: int
    inserted: int
    updated: int
    skipped: int = 0


class MaterialRun(BaseModel):
    """A backup or automation run record (materials-run-v1)."""

    id: int
    kind: str          # 'backup' | 'automation'
    status: str        # 'running' | 'success' | 'failed'
    started_at: str
    finished_at: str | None = None
    rows: int | None = None
    inserted: int | None = None
    updated: int | None = None
    exit_code: int | None = None
    message: str | None = None


class RunTriggerResult(BaseModel):
    """Response of POST /materials/run."""

    run_id: int
    status: str
    message: str


class DeleteResult(BaseModel):
    """Outcome of a document delete (DELETE {prefix}/{doc_number})."""

    doc_number: str
    deleted: int   # 삭제된 품목 행 수


class TombstoneEntry(BaseModel):
    """삭제된 문서의 묘비(tombstone) 1행 (GET {prefix}/tombstones)."""

    doc_number: str
    deleted_at: str


class RestoreResult(BaseModel):
    """Outcome of restoring a tombstoned doc (POST {prefix}/{doc_number}/restore)."""

    doc_number: str
    restored: int   # 제거된 tombstone 행 수 (0이면 404)


class MaterialPublic(MaterialRow):
    """Stored row enriched with server-derived fields.

    `doc_date` (YYYY-MM-DD) is derived from doc_number and is the primary date
    basis for the record (the document's business date), distinct from
    `processed_at` (the scrape/처리 시각).
    """

    doc_date: str | None = None
    received_at: str
    updated_at: str
