"""Pure anomaly-detection rules.

These functions take already-fetched, plain Python data and return Findings.
They perform NO I/O (no DB, no files, no network, no clock) — every input
that varies (today's date, the data series) is passed in. This keeps them
trivially unit-testable and deterministic.
"""
from __future__ import annotations

from .schemas import Finding


def _fmt(n: float) -> str:
    """Human-friendly integer-ish formatting with thousands separators."""
    return f"{round(n):,}"


def detect_volume_anomalies(
    *,
    latest_date: str,
    latest_qty: float,
    baseline_avg: float,
    drop_pct: float,
    spike_pct: float,
    min_baseline_qty: float,
) -> list[Finding]:
    """Compare the latest completed day against the trailing baseline average.

    Args:
        latest_date: ISO date (YYYY-MM-DD) of the latest *completed* day.
        latest_qty: total good_quantity for latest_date.
        baseline_avg: mean daily good_quantity over the trailing window
            (excluding latest_date).
        drop_pct: trigger a drop when the decrease >= this percent.
        spike_pct: trigger a spike when the increase >= this percent.
        min_baseline_qty: skip entirely when baseline below this (noise/zero-div).

    Returns:
        Zero or one Finding (a day cannot be both a drop and a spike).
    """
    if baseline_avg < min_baseline_qty:
        return []

    change_pct = (latest_qty - baseline_avg) / baseline_avg * 100.0

    if change_pct <= -drop_pct:
        severity = "critical" if change_pct <= -(drop_pct + 25.0) else "warning"
        msg = (
            f"{latest_date} 양품 {_fmt(latest_qty)}개 — "
            f"최근 평균 {_fmt(baseline_avg)}개 대비 {abs(change_pct):.1f}% 급감"
        )
        return [
            Finding(
                kind="volume_drop",
                severity=severity,
                key=f"volume_drop:{latest_date}",
                message=msg,
                details={
                    "date": latest_date,
                    "current": round(latest_qty, 2),
                    "baseline": round(baseline_avg, 2),
                    "change_pct": round(change_pct, 2),
                },
            )
        ]

    if change_pct >= spike_pct:
        severity = "critical" if change_pct >= spike_pct + 100.0 else "warning"
        msg = (
            f"{latest_date} 양품 {_fmt(latest_qty)}개 — "
            f"최근 평균 {_fmt(baseline_avg)}개 대비 {change_pct:.1f}% 급증"
        )
        return [
            Finding(
                kind="volume_spike",
                severity=severity,
                key=f"volume_spike:{latest_date}",
                message=msg,
                details={
                    "date": latest_date,
                    "current": round(latest_qty, 2),
                    "baseline": round(baseline_avg, 2),
                    "change_pct": round(change_pct, 2),
                },
            )
        ]

    return []


def detect_stale_items(
    *,
    items: list[dict],
    days_idle_key: str = "days_idle",
    stale_days: int,
) -> list[Finding]:
    """Flag previously-active items that have not been produced recently.

    Args:
        items: each dict has at least `item_code`, optional `item_name`,
            and `days_idle` (whole days since its last production date).
            The caller is responsible for restricting this list to items that
            were active within the lookback window (so brand-new or one-off
            items are not flagged).
        days_idle_key: key holding the idle-day count (test seam).
        stale_days: flag when days_idle >= this.

    Returns:
        One Finding per stale item, sorted by idle days descending.
    """
    findings: list[Finding] = []
    for it in items:
        days_idle = it.get(days_idle_key)
        if days_idle is None or days_idle < stale_days:
            continue
        code = it.get("item_code") or "?"
        name = it.get("item_name") or code
        last = it.get("last_date", "?")
        severity = "critical" if days_idle >= stale_days * 2 else "warning"
        msg = (
            f"{name}({code}) — 마지막 생산 {last} 이후 {days_idle}일 미생산"
        )
        findings.append(
            Finding(
                kind="stale_item",
                severity=severity,
                key=f"stale_item:{code}",
                message=msg,
                details={
                    "item_code": code,
                    "item_name": name,
                    "last_date": last,
                    "days_idle": days_idle,
                },
            )
        )
    findings.sort(key=lambda f: f.details.get("days_idle", 0), reverse=True)
    return findings
