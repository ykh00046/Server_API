"""Unit tests for dataset_page display-only formatting (dashboard-ui-med).

`_display_view` decides which st.column_config entries are *safe* for the
materials/binder table: the API stores 요청수량·처리일시 as TEXT, so a
NumberColumn/DatetimeColumn is only attached when every value parses. The
frame handed to the Excel/CSV downloads must never be mutated.

dataset_page.py imports streamlit and the sibling `components`/`data`
modules, so we load it by file path with `dashboard/` temporarily on
sys.path (same importlib idiom as tests/test_kpi_cards.py). Nothing here
touches the Streamlit runtime — `st.column_config.*` are plain dict
builders and the pure helpers never call st.*.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_DASHBOARD = _ROOT / "dashboard"


def _load_dataset_page():
    added = [str(_ROOT), str(_DASHBOARD)]
    for p in added:
        sys.path.insert(0, p)
    try:
        spec = importlib.util.spec_from_file_location(
            "dataset_page_under_test", _DASHBOARD / "dataset_page.py"
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["dataset_page_under_test"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for p in added:
            if p in sys.path:
                sys.path.remove(p)


_dp = _load_dataset_page()

_QTY = "요청수량(g단위)"
_TS = "처리일시"


def _rows(qty_values, ts_values):
    return [
        {
            "seq": i + 1,
            "material_code": f"M{i}",
            "material_name": "품명",
            "request_qty_g": qty,
            "reason": "사유",
            "request_dept": "생산1팀",
            "drafter": "홍길동",
            "doc_number": f"20260721P227-{i:04d}",
            "processed_at": ts,
        }
        for i, (qty, ts) in enumerate(zip(qty_values, ts_values, strict=True))
    ]


# ----------------------------------------------------------
# _to_excel_frame
# ----------------------------------------------------------
def test_to_excel_frame_empty_keeps_korean_headers():
    df = _dp._to_excel_frame([], _dp.EXCEL_COLUMNS)
    assert df.empty
    assert list(df.columns) == [ko for _, ko in _dp.EXCEL_COLUMNS]


def test_to_excel_frame_preserves_column_order():
    df = _dp._to_excel_frame(_rows(["100"], ["2026-07-21 09:12:33"]), _dp.EXCEL_COLUMNS)
    assert list(df.columns) == [ko for _, ko in _dp.EXCEL_COLUMNS]
    assert df["문서번호"].tolist() == ["20260721P227-0000"]


# ----------------------------------------------------------
# _display_view — safe conversions
# ----------------------------------------------------------
def test_display_view_formats_parsable_qty_and_timestamp():
    df = _dp._to_excel_frame(
        _rows(["100", "2500.5"], ["2026-07-21 09:12:33", "2026-07-22 10:00:00"]),
        _dp.EXCEL_COLUMNS,
    )
    view, config = _dp._display_view(df, _dp.EXCEL_COLUMNS)

    assert set(config) == {_QTY, _TS}
    assert pd.api.types.is_numeric_dtype(view[_QTY])
    assert pd.api.types.is_datetime64_any_dtype(view[_TS])


def test_display_view_never_mutates_the_download_frame():
    df = _dp._to_excel_frame(
        _rows(["100", "2500.5"], ["2026-07-21 09:12:33", "2026-07-22 10:00:00"]),
        _dp.EXCEL_COLUMNS,
    )
    before_qty = df[_QTY].tolist()
    before_ts = df[_TS].tolist()

    view, _ = _dp._display_view(df, _dp.EXCEL_COLUMNS)

    assert view is not df
    assert df[_QTY].tolist() == before_qty == ["100", "2500.5"]
    assert df[_TS].tolist() == before_ts
    assert not pd.api.types.is_numeric_dtype(df[_QTY])


def test_display_view_tolerates_missing_values():
    """None 은 파싱 실패가 아니다 — notna 개수가 같으면 서식을 붙인다."""
    df = _dp._to_excel_frame(
        _rows(["100", None], ["2026-07-21 09:12:33", None]), _dp.EXCEL_COLUMNS
    )
    view, config = _dp._display_view(df, _dp.EXCEL_COLUMNS)
    assert set(config) == {_QTY, _TS}
    assert pd.isna(view[_QTY].iloc[1])


# ----------------------------------------------------------
# _display_view — unsafe dtypes are skipped, 원문 문자열 유지
# ----------------------------------------------------------
def test_display_view_skips_qty_when_any_value_is_not_numeric():
    df = _dp._to_excel_frame(
        _rows(["100", "약 3봉"], ["2026-07-21 09:12:33", "2026-07-22 10:00:00"]),
        _dp.EXCEL_COLUMNS,
    )
    view, config = _dp._display_view(df, _dp.EXCEL_COLUMNS)
    assert _QTY not in config
    assert view[_QTY].tolist() == ["100", "약 3봉"]


def test_display_view_skips_timestamp_when_unparsable():
    df = _dp._to_excel_frame(
        _rows(["100", "200"], ["2026-07-21 09:12:33", "언제인지 모름"]),
        _dp.EXCEL_COLUMNS,
    )
    view, config = _dp._display_view(df, _dp.EXCEL_COLUMNS)
    assert _TS not in config
    assert view[_TS].tolist() == ["2026-07-21 09:12:33", "언제인지 모름"]


def test_display_view_returns_original_frame_when_nothing_is_formattable():
    df = _dp._to_excel_frame(
        _rows(["약 3봉"], ["언제인지 모름"]), _dp.EXCEL_COLUMNS
    )
    view, config = _dp._display_view(df, _dp.EXCEL_COLUMNS)
    assert config == {}
    assert view is df


def test_display_view_ignores_columns_absent_from_the_mapping():
    """헤더 매핑에 요청수량·처리일시가 없으면 서식 대상도 없다."""
    columns = [("doc_number", "문서번호"), ("material_name", "품명")]
    df = _dp._to_excel_frame(_rows(["100"], ["2026-07-21 09:12:33"]), columns)
    view, config = _dp._display_view(df, columns)
    assert config == {}
    assert view is df
