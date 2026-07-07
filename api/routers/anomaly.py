"""Anomaly detection endpoints (anomaly-detection-v1).

- GET  /anomaly/scan  : preview current findings (read-only, no side effects).
- POST /anomaly/scan  : scan + emit new findings as webhook events.
- GET  /anomaly/rules : expose active thresholds + registered event types.

Routine emission is the scheduled runner's job (tools/anomaly_watch.py, which
calls run_detection directly); POST here is the manual operator trigger.
GET used to accept emit=true, but a GET with side effects (webhook 발행 +
cooldown 상태 변경) violates HTTP safety — proxies/prefetchers could fire it.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from shared import config as cfg
from shared import get_logger

from .. import anomaly
from ..anomaly.schemas import KIND_EVENT_TYPES

logger = get_logger(__name__)
router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/scan")
def scan_preview():
    """Detection preview — never emits (GET must be side-effect free)."""
    return anomaly.run_detection(emit=False)


@router.post("/scan")
def scan_and_emit(
    emit: bool = Query(default=True, description="False면 미리보기만 (발행 안 함)"),
):
    """Run a detection scan and emit new findings as webhook events."""
    return anomaly.run_detection(emit=emit)


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
