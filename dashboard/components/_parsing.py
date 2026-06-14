"""Streamlit-free parsing helpers for the AI section (coverage-blindspots-v1).

Extracted verbatim from ai_section.py so the brittle parsing heuristics can be
unit-tested without a Streamlit runtime. This module imports only io/json/pandas
— no streamlit — so tests can load it in isolation (see tests/test_ai_table_parse
and tests/test_sse_parse). Behavior is a 1:1 port; do not change the heuristics
without updating the characterization tests.
"""
from __future__ import annotations

import io
import json
from collections.abc import Iterable, Iterator

import pandas as pd


def parse_markdown_table(content: str) -> pd.DataFrame | None:
    """Extract the first markdown table in ``content`` as a DataFrame, or None.

    Pure port of the original _render_table_download heuristics:
    - requires a pipe and a newline-pipe to look like a table,
    - keeps only lines that contain '|' and start (stripped) with '|',
    - needs more than 2 such lines (header + separator + >=1 row),
    - strips '**' bold markers and ALL spaces before CSV parsing,
    - drops the markdown separator row (^-+$ in the first column).

    Known limitation (characterized, not a goal to fix here): spaces inside
    cell values are also removed, so multi-word cells get collapsed.
    """
    if "|" not in content or "\n|" not in content:
        return None
    lines = content.split("\n")
    table_lines = [
        line for line in lines if "|" in line and line.strip().startswith("|")
    ]
    if len(table_lines) <= 2:
        return None
    table_text = "\n".join(table_lines).replace("**", "")
    try:
        df = pd.read_csv(
            io.StringIO(table_text.replace(" ", "")), sep="|"
        ).dropna(how="all", axis=1)
        df = df[~df.iloc[:, 0].str.contains(r"^-+$", na=False)]
        df.columns = [col.strip() for col in df.columns]
    except Exception:  # noqa: BLE001 — 파싱 실패는 "표 없음"으로 취급(원동작 보존)
        return None
    if df.empty:
        return None
    return df


def parse_sse_events(lines: Iterable[str]) -> Iterator[tuple[str | None, dict]]:
    """Yield ``(event_name, data)`` for each valid SSE ``data:`` line.

    Pure: no I/O, no streamlit. Mirrors the wire-protocol parsing only — the
    caller decides per-event behavior (token/tool_call/error/done):
    - a blank line resets the current event name,
    - ``event:`` sets the current event name,
    - ``data:`` with valid JSON yields ``(event_name, data)``,
    - malformed JSON on a ``data:`` line is skipped silently.
    """
    event_name: str | None = None
    for line in lines:
        if not line:
            event_name = None
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            raw = line[5:].strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            yield event_name, data
