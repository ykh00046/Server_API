"""HTTP endpoints for 자재요청 intake (materials-api-v1).

Thin layer over api/materials/*. Replaces the webcloring-pdf Google Sheets
backup target: the 포털 자동화 POSTs its Excel rows here at the end of a run.

Auth: these routes are NOT in shared.auth.PUBLIC_PATHS, so when API keys /
bearer tokens are configured they require credentials (opt-in auth layer).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from shared import get_logger

from ..materials import MaterialBackupRequest, store
from ..materials.schemas import BackupResult, MaterialPublic

logger = get_logger(__name__)
router = APIRouter(prefix="/materials", tags=["Materials"])


@router.post("/backup", response_model=BackupResult)
def backup_materials(req: MaterialBackupRequest) -> BackupResult:
    """Batch upsert 자재요청 rows by 문서번호 (doc_number).

    Idempotent: re-posting the same documents updates them in place.
    """
    result = store.upsert_materials(req.rows)
    logger.info(
        "[materials] backup: upserted=%d (inserted=%d, updated=%d)",
        result.upserted, result.inserted, result.updated,
    )
    return result


@router.get("", response_model=list[MaterialPublic])
def list_materials(
    request_dept: str | None = Query(default=None, max_length=200, description="요청부서 필터"),
    date_from: str | None = Query(
        default=None, description="doc_date 시작일 YYYY-MM-DD (문서번호 날짜, 포함)"
    ),
    date_to: str | None = Query(
        default=None, description="doc_date 종료일 YYYY-MM-DD (문서번호 날짜, 포함)"
    ),
    limit: int = Query(default=1000, ge=1, le=5000),
) -> list[MaterialPublic]:
    """List material requests ordered by 문서번호 날짜(doc_date) 최신순.

    날짜 필터(date_from/date_to)는 처리일시가 아닌 문서번호 날짜 기준입니다.
    """
    return store.list_materials(
        request_dept=request_dept, date_from=date_from, date_to=date_to, limit=limit
    )


@router.get("/{doc_number}", response_model=MaterialPublic)
def get_material(doc_number: str) -> MaterialPublic:
    """Fetch one material request by 문서번호."""
    mat = store.get_material(doc_number)
    if mat is None:
        raise HTTPException(status_code=404, detail=f"material {doc_number} not found")
    return mat
