"""Anomaly detection endpoints (anomaly-detection-v1 + dashboard-v2).

- GET  /anomaly/scan     : preview current findings (read-only). Optional
                           what-if threshold overrides — preview only.
- POST /anomaly/scan     : scan + emit new findings as webhook events.
- GET  /anomaly/rules    : expose active thresholds + registered event types.
- GET  /anomaly/findings : emitted-findings history (dashboard timeline).
- GET  /anomaly/state    : cooldown status + last scan time (read-only).

Routine emission is the scheduled runner's job (tools/anomaly_watch.py, which
calls run_detection directly); POST here is the manual operator trigger.
GET used to accept emit=true, but a GET with side effects (webhook 발행 +
cooldown 상태 변경) violates HTTP safety — proxies/prefetchers could fire it.
What-if overrides exist ONLY on the GET route (and run_detection re-rejects
emit+overrides), so a preview can never distort a real emission decision.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Query

from shared import config as cfg
from shared import get_logger

from .. import anomaly
from ..anomaly import store_findings, store_state
from ..anomaly.schemas import KIND_EVENT_TYPES, RuleOverrides

logger = get_logger(__name__)
router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/scan")
def scan_preview(
    drop_pct: float | None = Query(default=None, gt=0, description="what-if 급감 임계 %"),
    spike_pct: float | None = Query(default=None, gt=0, description="what-if 급증 임계 %"),
    stale_days: int | None = Query(default=None, ge=1, description="what-if 미생산 일수"),
    min_baseline_qty: float | None = Query(default=None, ge=0, description="what-if 최소 기준선"),
    baseline_days: int | None = Query(
        default=None, ge=1, le=365, description="what-if 기준선 일수"
    ),
):
    """Detection preview — never emits (GET must be side-effect free).

    임계치 파라미터를 주면 해당 값으로만 재판정하는 what-if 미리보기
    (dashboard-v2 F5). 서버 설정·쿨다운 상태는 어떤 것도 변하지 않는다."""
    overrides = RuleOverrides(
        drop_pct=drop_pct,
        spike_pct=spike_pct,
        stale_days=stale_days,
        min_baseline_qty=min_baseline_qty,
        baseline_days=baseline_days,
    )
    return anomaly.run_detection(
        emit=False, overrides=overrides if overrides.to_dict() else None
    )


@router.post("/scan")
def scan_and_emit(
    emit: bool = Query(default=True, description="False면 미리보기만 (발행 안 함)"),
):
    """Run a detection scan and emit new findings as webhook events."""
    return anomaly.run_detection(emit=emit)


@router.get("/findings")
def findings(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간(일)"),
    kind: str | None = Query(default=None, max_length=50),
    severity: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=200, ge=1, le=500),
):
    """발행 이력 (dashboard-v2 F2) — emitted_at 내림차순."""
    rows = store_findings.list_findings(
        days=days, kind=kind, severity=severity, limit=limit
    )
    return {"days": days, "count": len(rows), "findings": rows}


@router.get("/state")
def state():
    """쿨다운/스캔 상태 (dashboard-v2 F3) — read-only, 상태 파일 무변경."""
    st = store_state.load_state()
    now = time.time()
    cooldown_sec = cfg.ANOMALY_COOLDOWN_SEC
    cooldowns = []
    for key, ts in sorted(
        st.get("cooldowns", {}).items(), key=lambda kv: kv[1], reverse=True
    ):
        remaining = max(0.0, cooldown_sec - (now - float(ts)))
        cooldowns.append({
            "key": key,
            "emitted_ts": float(ts),
            "remaining_sec": round(remaining, 1),
            "active": remaining > 0,
        })
    return {
        "last_scan_ts": float(st.get("last_scan_ts", 0) or 0),
        "cooldown_sec": cooldown_sec,
        "cooldowns": cooldowns,
    }


@router.get("/rules")
def rules():
    """Active detection thresholds and the event types findings map to."""
    return {
        "enabled": cfg.ANOMALY_ENABLED,
        "baseline_days": cfg.ANOMALY_BASELINE_DAYS,
        "drop_pct": cfg.ANOMALY_DROP_PCT,
        "spike_pct": cfg.ANOMALY_SPIKE_PCT,
        "stale_days": cfg.ANOMALY_STALE_DAYS,
        "min_baseline_qty": cfg.ANOMALY_MIN_BASELINE_QTY,
        "cooldown_sec": cfg.ANOMALY_COOLDOWN_SEC,
        "event_types": sorted(set(KIND_EVENT_TYPES.values())),
    }
