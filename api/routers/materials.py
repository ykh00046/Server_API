"""HTTP endpoints for 자재요청 intake (materials-api-v1).

Thin layer over api/materials/*. Replaces the webcloring-pdf Google Sheets
backup target: the 포털 자동화 POSTs its Excel rows here at the end of a run.

Auth: these routes are NOT in shared.auth.PUBLIC_PATHS, so when API keys /
bearer tokens are configured they require credentials (opt-in auth layer).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from shared import get_logger

from ..materials import MaterialBackupRequest, automation, runs, store
from ..materials.schemas import (
    BackupResult,
    MaterialPublic,
    MaterialRun,
    RunTriggerResult,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/materials", tags=["Materials"])


@router.post("/backup", response_model=BackupResult)
def backup_materials(req: MaterialBackupRequest) -> BackupResult:
    """Batch upsert 자재요청 rows by 문서번호 (doc_number).

    Idempotent: re-posting the same documents updates them in place. Each
    backup is recorded as a 'backup' run for the dashboard history.
    """
    result = store.upsert_materials(req.rows)
    runs.record_backup_run(result.upserted, result.inserted, result.updated)
    logger.info(
        "[materials] backup: upserted=%d (inserted=%d, updated=%d)",
        result.upserted, result.inserted, result.updated,
    )
    return result


# ----------------------------------------------------------
# Runs: manual automation trigger + history
# (registered before /{doc_number} so "runs" isn't captured as a doc_number)
# ----------------------------------------------------------
@router.post("/run", response_model=RunTriggerResult)
def trigger_run() -> RunTriggerResult:
    """수동으로 webcloring-pdf 포털 자동화를 실행한다 (같은 PC 백그라운드).

    MATERIALS_RUN_ENABLED=1일 때만 동작. 이미 실행 중이면 409.
    """
    try:
        run_id = automation.trigger_automation()
    except automation.TriggerError as e:
        # 비활성/중복 실행 → 409 (클라이언트가 구분해 처리)
        raise HTTPException(status_code=409, detail=str(e)) from e
    return RunTriggerResult(run_id=run_id, status="running", message="자동화 실행을 시작했습니다.")


@router.get("/runs", response_model=list[MaterialRun])
def list_runs(
    kind: str | None = Query(default=None, description="'backup' | 'automation'"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[MaterialRun]:
    """실행 이력 (백업 수신 + 수동 자동화), 최신순."""
    return runs.list_runs(kind=kind, limit=limit)


@router.get("/runs/{run_id}", response_model=MaterialRun)
def get_run(run_id: int) -> MaterialRun:
    """단일 실행 상태 (대시보드 폴링용)."""
    run = runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return run


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
