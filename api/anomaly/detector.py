"""Anomaly detection orchestrator.

Reads recent production data (read-only), runs the pure rules, dedupes via
the cooldown store, and emits webhook events for newly-detected anomalies.

This is the only module here that performs I/O. It never raises to its
callers (runner / API): any failure is logged and yields an empty/partial
result so the schedule loop and HTTP endpoint stay alive.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta
from typing import Any

from shared import DBRouter, get_logger
from shared import config as cfg

from . import rules, store_state
from .schemas import Finding

logger = get_logger(__name__)


def _today() -> date:
    return datetime.now().date()


def _fetch_daily_totals(conn: sqlite3.Connection, since: str) -> list[dict]:
    """Daily good_quantity totals on/after `since`, ascending by date."""
    sql = (
        "SELECT production_date AS d, SUM(good_quantity) AS qty "
        "FROM production_records WHERE production_date >= ? "
        "GROUP BY production_date ORDER BY production_date"
    )
    rows = conn.execute(sql, (since,)).fetchall()
    return [{"date": r["d"], "qty": r["qty"] or 0} for r in rows]


def _fetch_item_last_dates(conn: sqlite3.Connection, since: str) -> list[dict]:
    """Per-item latest production date for items active on/after `since`."""
    sql = (
        "SELECT item_code, "
        "MAX(item_name) AS item_name, "
        "MAX(production_date) AS last_date "
        "FROM production_records WHERE production_date >= ? "
        "AND item_code IS NOT NULL AND item_code != '' "
        "GROUP BY item_code"
    )
    rows = conn.execute(sql, (since,)).fetchall()
    return [
        {
            "item_code": r["item_code"],
            "item_name": r["item_name"],
            "last_date": r["last_date"],
        }
        for r in rows
    ]


def _days_between(a: str, b: date) -> int | None:
    """Whole days from ISO date string `a` to date `b`; None if unparsable."""
    try:
        d = datetime.strptime(a[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (b - d).days


def collect_findings(today: date | None = None) -> list[Finding]:
    """Query data and run all rules. Returns findings without emitting.

    Pure-of-side-effects except for the read-only DB query; safe for the
    dry-run API path.
    """
    if not cfg.ANOMALY_ENABLED:
        return []

    today = today or _today()
    # Look back far enough to cover the baseline window plus the latest day,
    # with a small buffer for gaps (non-production days).
    lookback_days = cfg.ANOMALY_BASELINE_DAYS + max(cfg.ANOMALY_STALE_DAYS, 1) + 7
    since = (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    try:
        conn = DBRouter.get_connection(use_archive=False, read_only=True)
        daily = _fetch_daily_totals(conn, since)
        items = _fetch_item_last_dates(conn, since)
    except sqlite3.Error as e:
        logger.warning("[anomaly.detector] query failed: %s", e)
        return []

    findings: list[Finding] = []

    # --- Volume rules: latest *completed* day vs trailing average ---------
    # "completed" = strictly before today, so partial current-day ERP data
    # never triggers a false drop.
    completed = [d for d in daily if d["date"] < today_str]
    if completed and cfg.ANOMALY_BASELINE_DAYS > 0:
        latest = completed[-1]
        # [-0:]은 빈 슬라이스가 아니라 전체라서 0일 설정 시 의도와 반대가 된다
        window = completed[:-1][-cfg.ANOMALY_BASELINE_DAYS:]
        if window:
            baseline_avg = sum(d["qty"] for d in window) / len(window)
            findings += rules.detect_volume_anomalies(
                latest_date=latest["date"],
                latest_qty=float(latest["qty"]),
                baseline_avg=float(baseline_avg),
                drop_pct=cfg.ANOMALY_DROP_PCT,
                spike_pct=cfg.ANOMALY_SPIKE_PCT,
                min_baseline_qty=cfg.ANOMALY_MIN_BASELINE_QTY,
            )

    # --- Stale rule: active items not produced for STALE_DAYS+ -----------
    stale_input: list[dict] = []
    for it in items:
        days_idle = _days_between(it["last_date"], today)
        if days_idle is None:
            continue
        stale_input.append({**it, "days_idle": days_idle})
    findings += rules.detect_stale_items(
        items=stale_input,
        stale_days=cfg.ANOMALY_STALE_DAYS,
    )

    return findings


def run_detection(emit: bool = True, today: date | None = None) -> dict[str, Any]:
    """Full scan. When emit=True, fire webhook events for new findings only.

    Returns a summary dict (scan timestamp, counts, findings as dicts).
    """
    now = time.time()
    findings = collect_findings(today=today)

    emitted_keys: list[str] = []
    if emit and findings:
        emitted_keys = _emit_new(findings, now)

    return {
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "enabled": cfg.ANOMALY_ENABLED,
        "emitted": bool(emitted_keys),
        "emitted_count": len(emitted_keys),
        "count": len(findings),
        "findings": [f.to_dict() for f in findings],
    }


def _emit_new(findings: list[Finding], now: float) -> list[str]:
    """Emit findings outside their cooldown window; record + persist state."""
    # Imported lazily so the pure/dry-run path never pulls the webhook stack.
    from api.notifications import emit_event

    state = store_state.load_state()
    fresh = store_state.filter_new(
        findings, state, now=now, cooldown_sec=cfg.ANOMALY_COOLDOWN_SEC
    )
    emitted: list[Finding] = []
    for f in fresh:
        try:
            emit_event(f.event_type, f.to_dict())
        except Exception as e:  # noqa: BLE001 — 발행 실패가 스캔을 중단시키지 않는다
            # 실패분은 마킹하지 않는다 — 마킹하면 쿨다운(기본 1일) 동안
            # 재시도되지 않아 알림이 조용히 유실된다.
            logger.warning(
                "[anomaly.detector] emit failed key=%s (다음 스캔에서 재시도): %s",
                f.key, e,
            )
            continue
        emitted.append(f)

    store_state.mark_emitted(emitted, state, now=now)
    state["last_scan_ts"] = now
    # Keep the state file from growing without bound.
    store_state.prune(state, now=now, max_age_sec=cfg.ANOMALY_COOLDOWN_SEC * 7)
    store_state.save_state(state)

    if emitted:
        logger.info(
            "[anomaly.detector] emitted %d/%d findings", len(emitted), len(findings)
        )
    return [f.key for f in emitted]
