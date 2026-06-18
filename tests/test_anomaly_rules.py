"""Unit tests for the pure anomaly rules (no I/O)."""
from __future__ import annotations

from api.anomaly import rules


def _vol(latest_qty, baseline, drop=50.0, spike=100.0, min_baseline=1.0):
    return rules.detect_volume_anomalies(
        latest_date="2026-06-18",
        latest_qty=latest_qty,
        baseline_avg=baseline,
        drop_pct=drop,
        spike_pct=spike,
        min_baseline_qty=min_baseline,
    )


def test_drop_at_boundary_triggers():
    # exactly -50% should trigger (>= boundary)
    out = _vol(500, 1000)
    assert len(out) == 1
    assert out[0].kind == "volume_drop"
    assert out[0].key == "volume_drop:2026-06-18"
    assert out[0].details["change_pct"] == -50.0


def test_drop_just_below_boundary_no_trigger():
    out = _vol(501, 1000)  # -49.9%
    assert out == []


def test_severe_drop_is_critical():
    out = _vol(100, 1000)  # -90% <= -(50+25)
    assert out[0].severity == "critical"


def test_spike_at_boundary_triggers():
    out = _vol(2000, 1000)  # +100%
    assert len(out) == 1
    assert out[0].kind == "volume_spike"
    assert out[0].details["change_pct"] == 100.0


def test_spike_just_below_boundary_no_trigger():
    out = _vol(1999, 1000)  # +99.9%
    assert out == []


def test_baseline_below_minimum_is_skipped():
    out = _vol(0, 0.5, min_baseline=1.0)
    assert out == []


def test_normal_range_no_finding():
    assert _vol(1100, 1000) == []  # +10%, well within both thresholds


def test_event_type_mapping():
    out = _vol(100, 1000)
    assert out[0].event_type == "production.anomaly.volume_drop"


# --- stale -------------------------------------------------------------

def _stale(days_idle, stale_days=7):
    items = [
        {
            "item_code": "BW0021",
            "item_name": "블루 렌즈",
            "last_date": "2026-06-01",
            "days_idle": days_idle,
        }
    ]
    return rules.detect_stale_items(items=items, stale_days=stale_days)


def test_stale_at_boundary_triggers():
    out = _stale(7)
    assert len(out) == 1
    assert out[0].kind == "stale_item"
    assert out[0].key == "stale_item:BW0021"


def test_stale_below_boundary_no_trigger():
    assert _stale(6) == []


def test_stale_double_threshold_is_critical():
    assert _stale(14)[0].severity == "critical"


def test_stale_missing_days_idle_skipped():
    out = rules.detect_stale_items(
        items=[{"item_code": "X", "last_date": "2026-06-01"}], stale_days=7
    )
    assert out == []


def test_stale_sorted_by_idle_desc():
    items = [
        {"item_code": "A", "last_date": "2026-06-10", "days_idle": 8},
        {"item_code": "B", "last_date": "2026-06-01", "days_idle": 18},
    ]
    out = rules.detect_stale_items(items=items, stale_days=7)
    assert [f.details["item_code"] for f in out] == ["B", "A"]
