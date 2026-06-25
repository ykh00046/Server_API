"""HTTP endpoints for keyword-partitioned 문서 intake (materials-datasets-v1).

A dataset registry (api/materials/datasets.py) maps each 검색 키워드 to an
isolated table pair + route prefix. This module is a *factory*: `make_router`
builds the identical endpoint set bound to one Dataset, so every dataset gets
the same API under its own prefix. 자재 keeps `/materials/*` byte-for-byte;
액상바인더출고(PBHAv1.0) is served under `/binder/*`.

Auth: these routes are NOT in shared.auth.PUBLIC_PATHS, so when API keys /
bearer tokens are configured they require credentials (opt-in auth layer).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from shared import get_logger

from ..materials import MaterialBackupRequest, automation, runs, store
from ..materials.datasets import DEFAULT_DATASET, Dataset, all_datasets
from ..materials.schemas import (
    BackupResult,
    MaterialPublic,
    MaterialRun,
    RunTriggerResult,
)

logger = get_logger(__name__)


def make_router(ds: Dataset) -> APIRouter:
    """Build the full endpoint set bound to one dataset."""
    router = APIRouter(prefix=ds.prefix, tags=[ds.title])
    # 기본(materials) 데이터셋은 봇 기본 키워드(자재)로 실행해 기존 동작을
    # 그대로 유지한다. 그 외 데이터셋은 자기 검색어로 트리거한다.
    trigger_keyword = None if ds.key == DEFAULT_DATASET.key else ds.keywords[0]

    @router.post("/backup", response_model=BackupResult)
    def backup(req: MaterialBackupRequest) -> BackupResult:
        """Batch upsert rows by 문서번호 (doc_number) into this dataset.

        Idempotent: re-posting the same documents updates them in place. Each
        backup is recorded as a 'backup' run for the dashboard history.
        """
        result = store.upsert_materials(req.rows, table=ds.table)
        runs.record_backup_run(
            result.upserted, result.inserted, result.updated,
            runs_table=ds.runs_table,
        )
        logger.info(
            "[%s] backup: upserted=%d (inserted=%d, updated=%d)",
            ds.key, result.upserted, result.inserted, result.updated,
        )
        return result

    # Runs: manual automation trigger + history
    # (registered before /{doc_number} so "runs" isn't captured as a doc_number)
    @router.post("/run", response_model=RunTriggerResult)
    def trigger_run() -> RunTriggerResult:
        """수동으로 webcloring-pdf 포털 자동화를 실행한다 (같은 PC 백그라운드).

        MATERIALS_RUN_ENABLED=1일 때만 동작. 이미 실행 중이면 409.
        """
        try:
            run_id = automation.trigger_automation(
                keyword=trigger_keyword, runs_table=ds.runs_table
            )
        except automation.TriggerError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return RunTriggerResult(
            run_id=run_id, status="running", message="자동화 실행을 시작했습니다."
        )

    @router.get("/runs", response_model=list[MaterialRun])
    def list_runs(
        kind: str | None = Query(default=None, description="'backup' | 'automation'"),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[MaterialRun]:
        """실행 이력 (백업 수신 + 수동 자동화), 최신순."""
        return runs.list_runs(runs_table=ds.runs_table, kind=kind, limit=limit)

    @router.get("/runs/{run_id}", response_model=MaterialRun)
    def get_run(run_id: int) -> MaterialRun:
        """단일 실행 상태 (대시보드 폴링용)."""
        run = runs.get_run(run_id, runs_table=ds.runs_table)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return run

    @router.get("", response_model=list[MaterialPublic])
    def list_rows(
        request_dept: str | None = Query(default=None, max_length=200, description="요청부서 필터"),
        keyword: str | None = Query(default=None, max_length=100, description="수집 키워드 필터"),
        date_from: str | None = Query(
            default=None, description="doc_date 시작일 YYYY-MM-DD (문서번호 날짜, 포함)"
        ),
        date_to: str | None = Query(
            default=None, description="doc_date 종료일 YYYY-MM-DD (문서번호 날짜, 포함)"
        ),
        limit: int = Query(default=1000, ge=1, le=5000),
    ) -> list[MaterialPublic]:
        """List rows ordered by 문서번호 날짜(doc_date) 최신순.

        날짜 필터(date_from/date_to)는 처리일시가 아닌 문서번호 날짜 기준입니다.
        """
        return store.list_materials(
            table=ds.table, request_dept=request_dept, keyword=keyword,
            date_from=date_from, date_to=date_to, limit=limit,
        )

    @router.get("/{doc_number}", response_model=MaterialPublic)
    def get_row(doc_number: str) -> MaterialPublic:
        """Fetch one row by 문서번호."""
        mat = store.get_material(doc_number, table=ds.table)
        if mat is None:
            raise HTTPException(status_code=404, detail=f"document {doc_number} not found")
        return mat

    return router


# 등록된 데이터셋별 라우터. 새 데이터셋 추가 = datasets.py에 한 줄이면 끝.
ROUTERS: list[APIRouter] = [make_router(ds) for ds in all_datasets()]

# 하위 호환: 기존 `materials.router`(자재) 단일 참조 유지.
router = next(r for r in ROUTERS if r.prefix == DEFAULT_DATASET.prefix)
