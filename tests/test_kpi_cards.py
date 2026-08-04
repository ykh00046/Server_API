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

import contextlib
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

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


# ----------------------------------------------------------
# kpi_row — 지표 행의 통일 계약 (dashboard-ui-med)
#
# 렌더 함수라 Streamlit 런타임이 필요하지만, kpi_row 는 st.* 호출을 조립하는
# 얇은 층이므로 모듈의 `st` 를 기록용 스텁으로 갈아끼워 "무엇을 어떤 인자로
# 그리는지"를 검증한다 (test_ui_theme.py 의 monkeypatch 패턴과 동일).
# ----------------------------------------------------------
class _FakeSt:
    """st.container / st.metric 호출을 기록하는 최소 스텁."""

    def __init__(self) -> None:
        self.containers: list[dict] = []
        self.metrics: list[tuple[str, object, dict]] = []

    def container(self, **kwargs):
        self.containers.append(kwargs)
        return contextlib.nullcontext()

    def metric(self, label, value, **kwargs):
        self.metrics.append((label, value, kwargs))


@pytest.fixture
def fake_st(monkeypatch):
    fake = _FakeSt()
    monkeypatch.setattr(_kpi, "st", fake)
    return fake


def test_kpi_row_renders_uniform_bordered_cards(fake_st):
    _kpi.kpi_row([
        {"label": "총 레코드", "value": "10건"},
        {"label": "생산일 수", "value": "3일", "help": "고유 일수"},
    ])
    # 한 줄 = 가로 컨테이너 하나 (좁은 화면에서 st.columns 처럼 찌그러지지 않는다)
    assert fake_st.containers == [{"horizontal": True}]
    assert [(m[0], m[1]) for m in fake_st.metrics] == [("총 레코드", "10건"), ("생산일 수", "3일")]
    heights = {m[2]["height"] for m in fake_st.metrics}
    assert len(heights) == 1  # 카드 높이는 한 줄 안에서 항상 동일
    assert all(m[2]["border"] is True for m in fake_st.metrics)
    assert fake_st.metrics[0][2]["help"] is None
    assert fake_st.metrics[1][2]["help"] == "고유 일수"


def test_kpi_row_suppresses_flat_sparkline(fake_st):
    _kpi.kpi_row([
        {"label": "신호 있음", "value": "1", "chart_data": [0, 3], "chart_type": "bar"},
        {"label": "전부 0", "value": "0", "chart_data": [0, 0]},
        {"label": "없음", "value": "-"},
    ])
    assert fake_st.metrics[0][2]["chart_data"] == [0, 3]
    assert fake_st.metrics[0][2]["chart_type"] == "bar"
    assert fake_st.metrics[1][2]["chart_data"] is None
    assert fake_st.metrics[2][2]["chart_data"] is None


def test_kpi_row_trailing_widget_renders_in_same_row(fake_st):
    calls: list[str] = []
    _kpi.kpi_row([{"label": "A", "value": 1}], trailing=lambda: calls.append("btn"))
    assert calls == ["btn"]
    assert len(fake_st.containers) == 1  # 버튼도 같은 가로 컨테이너 안


def test_render_kpi_cards_delegates_to_kpi_row(fake_st):
    _kpi.render_kpi_cards(
        {"total_qty": 1500, "batch_count": 3, "active_products": 2, "avg_batch_size": 500},
        None,
        sparkline_data=[1, 2, 3],
        batch_sparkline=[0, 0, 0],
    )
    labels = [m[0] for m in fake_st.metrics]
    assert labels == ["총 생산량", "배치 수", "활성 제품", "평균 배치 크기"]
    assert fake_st.metrics[0][1] == "1,500"
    assert fake_st.metrics[0][2]["chart_data"] == [1, 2, 3]
    assert fake_st.metrics[1][2]["chart_data"] is None  # 전부 0 → 미표시
    assert all(m[2]["border"] is True for m in fake_st.metrics)
