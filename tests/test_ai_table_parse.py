"""Unit tests for dashboard AI markdown-table parsing (coverage-blindspots-v1).

The parser lives in dashboard/components/_parsing.py and is streamlit-free, but
importing it via the package would pull in dashboard/components/__init__.py
(which eagerly imports streamlit). Load it directly from disk — same boundary
pattern as test_webhook_admin_ui.

These are characterization tests: they capture the CURRENT behavior of the
ported heuristics (including the known space-stripping limitation), so the
extraction refactor is provably behavior-preserving.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PARSING = _ROOT / "dashboard" / "components" / "_parsing.py"


def _load_parsing():
    spec = importlib.util.spec_from_file_location("ai_parsing_under_test", _PARSING)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_parsing_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_parsing = _load_parsing()
parse_markdown_table = _parsing.parse_markdown_table


def test_normal_table_parsed():
    content = (
        "결과입니다:\n"
        "| 코드 | 수량 |\n"
        "| --- | --- |\n"
        "| BW0021 | 100 |\n"
        "| BW0022 | 200 |\n"
    )
    df = parse_markdown_table(content)
    assert df is not None
    assert list(df.columns) == ["코드", "수량"]
    assert len(df) == 2
    assert df.iloc[0]["코드"] == "BW0021"
    assert str(df.iloc[1]["수량"]) == "200"


def test_no_pipe_returns_none():
    assert parse_markdown_table("표가 없는 일반 텍스트 답변입니다.") is None


def test_header_and_separator_only_returns_none():
    # header + separator = 2 table_lines, needs > 2
    content = "| a | b |\n| --- | --- |\n"
    assert parse_markdown_table(content) is None


def test_bold_markers_stripped():
    content = (
        "| 코드 | 수량 |\n"
        "| --- | --- |\n"
        "| **BW0021** | 100 |\n"
        "| BW0022 | 200 |\n"
    )
    df = parse_markdown_table(content)
    assert df is not None
    # '**' removed before parsing
    assert df.iloc[0]["코드"] == "BW0021"


def test_separator_row_filtered_out():
    content = (
        "| 코드 | 수량 |\n"
        "| --- | --- |\n"
        "| BW0021 | 100 |\n"
    )
    df = parse_markdown_table(content)
    assert df is not None
    # The '---' separator row must not appear as data
    assert "---" not in df.iloc[:, 0].astype(str).tolist()
    assert len(df) == 1


def test_spaces_inside_cells_are_collapsed_known_limitation():
    # Characterization: ALL spaces are stripped, so multi-word cells collapse.
    content = (
        "| 제품명 | 수량 |\n"
        "| --- | --- |\n"
        "| 일반 식염수 | 100 |\n"
    )
    df = parse_markdown_table(content)
    assert df is not None
    # 'A B' -> 'AB' (documented limitation, not a goal to fix in this cycle)
    assert df.iloc[0]["제품명"] == "일반식염수"


def test_malformed_table_returns_none():
    # Lines with '|' but not starting with '|' after strip → too few table_lines
    content = "code | qty\nBW0021 | 100\n"
    assert parse_markdown_table(content) is None
