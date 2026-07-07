"""Streamlit-free helpers for the anomaly dashboard page (anomaly-dashboard-v2).

Pure transforms only (pandas in, pandas/str out) so the timeline aggregation
and remaining-time formatting can be unit-tested without a Streamlit runtime
— same policy as components/_parsing.py.
"""
from __future__ import annotations

import pandas as pd

KIND_LABELS: dict[str, str] = {
    "volume_drop": "생산량 급감",
    "volume_spike": "생산량 급증",
    "stale_item": "장기 미생산",
}

SEVERITY_COLORS: dict[str, str] = {
    "critical": "#dc2626",
    "warning": "#f59e0b",
    "info": "#64748b",
}


def findings_to_daily_counts(findings: list[dict]) -> pd.DataFrame:
    """발행 이력 → 일별·severity별 건수 (타임라인 stacked bar 입력).

    Returns columns: day (YYYY-MM-DD), severity, count — day 오름차순.
    빈 입력이면 빈 프레임(컬럼 유지).
    """
    if not findings:
        return pd.DataFrame(columns=["day", "severity", "count"])
    df = pd.DataFrame(findings)
    df["day"] = df["emitted_at"].astype(str).str[:10]
    out = (
        df.groupby(["day", "severity"]).size().reset_index(name="count")
    )
    return out.sort_values(["day", "severity"]).reset_index(drop=True)


def humanize_remaining(sec: float) -> str:
    """남은 쿨다운 초 → 사람이 읽는 한국어 (0 이하 → '-')."""
    total = int(max(0, sec))
    if total == 0:
        return "-"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"{days}일 {hours}시간"
    if hours:
        return f"{hours}시간 {minutes}분"
    if minutes:
        return f"{minutes}분"
    return f"{seconds}초"
