"""Pydantic schemas for the material-requests intake API (materials-api-v1).

Mirrors the columns the webcloring-pdf 포털 자동화 writes to its local Excel
(자재요청목록). `doc_number` (문서번호) is the upsert key.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MaterialRow(BaseModel):
    """A single 자재요청 row. Keyed by `doc_number`."""

    doc_number: str = Field(min_length=1, max_length=100, description="문서번호 (upsert key)")
    seq: int | None = Field(default=None, description="순번 (per-run row order, not stable)")
    material_code: str | None = Field(default=None, max_length=100, description="자재코드")
    material_name: str | None = Field(default=None, max_length=300, description="품명")
    # 요청수량(g단위): source may be numeric or string; kept loose for fidelity.
    request_qty_g: str | int | float | None = Field(default=None, description="요청수량(g단위)")
    reason: str | None = Field(default=None, max_length=1000, description="사유")
    request_dept: str | None = Field(default=None, max_length=200, description="요청부서")
    drafter: str | None = Field(default=None, max_length=100, description="기안자")
    processed_at: str | None = Field(default=None, max_length=40, description="처리일시")


class MaterialBackupRequest(BaseModel):
    """Batch upsert payload (one POST per automation run)."""

    rows: list[MaterialRow] = Field(min_length=1, max_length=5000)


class BackupResult(BaseModel):
    """Outcome of a batch upsert."""

    upserted: int
    inserted: int
    updated: int


class MaterialPublic(MaterialRow):
    """Stored row enriched with server-derived fields.

    `doc_date` (YYYY-MM-DD) is derived from doc_number and is the primary date
    basis for the record (the document's business date), distinct from
    `processed_at` (the scrape/처리 시각).
    """

    doc_date: str | None = None
    received_at: str
    updated_at: str
