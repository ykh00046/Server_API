"""Anomaly detection endpoints (anomaly-detection-v1).

- GET /anomaly/scan   : preview current findings (dry-run by default).
- GET /anomaly/rules  : expose active thresholds + registered event types.

Routine emission is the scheduled runner's job (tools/anomaly_watch.py);
the `emit=true` query here is a manual operator trigger.
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
def scan(emit: bool = Query(default=False, description="True면 신규 이상을 webhook으로 발행")):
    """Run a detection scan. By default does NOT emit (preview only)."""
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
