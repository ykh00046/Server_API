"""Unit tests for dashboard KPI pure logic (coverage-blindspots-v2).

calculate_kpis / get_sparkline_data / get_batch_count_sparkline /
get_avg_batch_sparkline /
_format_number / _has_signal are pure (DataFrame/scalar in, value out — no
Streamlit runtime). kpi_cards.py imports streamlit at module top-level, so we
load it directly from disk (importlib) to avoid the package __init__ pulling in
all components; the import of streamlit itself is harmless (installed), and the
pure functions never call st.*.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_KPI = _ROOT / "dashboard" / "components" / "kpi_cards.py"


def _load_kpi():
    spec = importlib.util.spec_from_file_location("kpi_cards_under_test", _KPI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kpi_cards_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_kpi = _load_kpi()


# ----------------------------------------------------------
# calculate_kpis
# ----------------------------------------------------------
def test_calculate_kpis_empty():
    kpis = _kpi.calculate_kpis(pd.DataFrame(), None, None)
    assert kpis["total_qty"] == 0
    assert kpis["batch_count"] == 0
    assert kpis["daily_avg"] == 0.0
    assert kpis["top_item"] == "-"
    assert kpis["top_item_name"] == "-"
    assert kpis["active_products"] == 0
    assert kpis["avg_batch_size"] == 0


def test_calculate_kpis_normal():
    df = pd.DataFrame(
        {
            "good_quantity": [100, 200, 300],
            "item_code": ["BW0021", "BW0021", "BW0022"],
            "item_name": ["P물", "P물", "Q물"],
        }
    )
    kpis = _kpi.calculate_kpis(df, None, None)
    assert kpis["total_qty"] == 600
    assert kpis["batch_count"] == 3
    assert kpis["active_products"] == 2
    assert kpis["avg_batch_size"] == 200
    # BW0021 has 300 total vs BW0022 300 — idxmax picks first max (BW0021)
    assert kpis["top_item"] == "BW0021"
    assert kpis["top_item_name"] == "P물"


def test_calculate_kpis_daily_avg_with_date_range():
    df = pd.DataFrame(
        {"good_quantity": [100, 100], "item_code": ["A", "A"], "item_name": ["a", "a"]}
    )
    # 10-day inclusive window → days = 10, daily_avg = 200/10 = 20
    kpis = _kpi.calculate_kpis(df, date(2026, 1, 1), date(2026, 1, 10))
    assert kpis["daily_avg"] == 20.0


def test_calculate_kpis_handles_nan_quantity():
    df = pd.DataFrame(
        {
            "good_quantity": [100, None, 50],
            "item_code": ["A", "A", "B"],
            "item_name": ["a", "a", "b"],
        }
    )
    kpis = _kpi.calculate_kpis(df, None, None)
    assert kpis["total_qty"] == 150  # NaN treated as 0


# ----------------------------------------------------------
# get_sparkline_data
# ----------------------------------------------------------
def test_get_sparkline_data_pads_to_days():
    df = pd.DataFrame(
        {"production_day": ["2026-01-01", "2026-01-02"], "good_quantity": [10, 20]}
    )
    spark = _kpi.get_sparkline_data(df, days=7)
    assert len(spark) == 7
    assert spark[-2:] == [10, 20]  # newest at the end
    assert spark[:5] == [0, 0, 0, 0, 0]  # left-padded


def test_get_sparkline_data_empty_or_missing_column():
    assert _kpi.get_sparkline_data(pd.DataFrame(), days=7) == [0] * 7
    df_no_col = pd.DataFrame({"good_quantity": [1, 2]})
    assert _kpi.get_sparkline_data(df_no_col, days=7) == [0] * 7


def test_get_batch_count_sparkline():
    """'배치 수' 카드는 건수 시계열 — 과거엔 생산량 합계가 그려졌다
    (full-review-202607 라벨-데이터 불일치)."""
    df = pd.DataFrame(
        {
            "production_day": ["2026-01-01", "2026-01-02", "2026-01-02"],
            "good_quantity": [5, 7, 99],
        }
    )
    spark = _kpi.get_batch_count_sparkline(df, days=7)
    assert len(spark) == 7
    assert spark[-2:] == [1, 2]  # 건수(count)지 수량(sum)이 아니다
    assert _kpi.get_batch_count_sparkline(pd.DataFrame(), days=7) == [0] * 7


def test_get_avg_batch_sparkline():
    df = pd.DataFrame(
        {
            "production_day": ["2026-01-01", "2026-01-02", "2026-01-02"],
            "good_quantity": [5, 7, 99],
        }
    )
    spark = _kpi.get_avg_batch_sparkline(df, days=7)
    assert len(spark) == 7
    assert spark[-2:] == [5.0, 53.0]  # 일별 평균
    assert _kpi.get_avg_batch_sparkline(pd.DataFrame(), days=7) == [0.0] * 7


# ----------------------------------------------------------
# _format_number / _has_signal
# ----------------------------------------------------------
def test_format_number_boundaries():
    assert _kpi._format_number(999) == "999"
    assert _kpi._format_number(1500) == "1,500"
    assert _kpi._format_number(2_500_000) == "2.5M"


def test_has_signal():
    assert _kpi._has_signal(None) is False
    assert _kpi._has_signal([]) is False
    assert _kpi._has_signal([0, 0, 0]) is False
    assert _kpi._has_signal([0, 1]) is True
