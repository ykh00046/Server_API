"""Unit tests for the streamlit-free anomaly page helpers (dashboard-v2).

Loaded directly from disk — importing via the components package would pull
dashboard/components/__init__.py (which eagerly imports streamlit). Same
boundary pattern as tests/test_ai_table_parse.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HELPERS = _ROOT / "dashboard" / "components" / "anomaly_view_helpers.py"


def _load_helpers():
    spec = importlib.util.spec_from_file_location(
        "anomaly_helpers_under_test", _HELPERS
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["anomaly_helpers_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_helpers = _load_helpers()
findings_to_daily_counts = _helpers.findings_to_daily_counts
humanize_remaining = _helpers.humanize_remaining


def test_daily_counts_empty():
    df = findings_to_daily_counts([])
    assert list(df.columns) == ["day", "severity", "count"]
    assert len(df) == 0


def test_daily_counts_groups_by_day_and_severity():
    rows = [
        {"emitted_at": "2026-07-06T09:00:00", "severity": "warning"},
        {"emitted_at": "2026-07-06T18:00:00", "severity": "warning"},
        {"emitted_at": "2026-07-06T19:00:00", "severity": "critical"},
        {"emitted_at": "2026-07-07T08:00:00", "severity": "warning"},
    ]
    df = findings_to_daily_counts(rows)
    as_dict = {
        (r["day"], r["severity"]): r["count"] for _, r in df.iterrows()
    }
    assert as_dict == {
        ("2026-07-06", "warning"): 2,
        ("2026-07-06", "critical"): 1,
        ("2026-07-07", "warning"): 1,
    }
    # day 오름차순
    assert list(df["day"]) == sorted(df["day"])


def test_humanize_remaining():
    assert humanize_remaining(0) == "-"
    assert humanize_remaining(-5) == "-"
    assert humanize_remaining(59) == "59초"
    assert humanize_remaining(60) == "1분"
    assert humanize_remaining(3_700) == "1시간 1분"
    assert humanize_remaining(90_000) == "1일 1시간"
