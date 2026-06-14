"""Unit tests for dashboard SSE event parsing (coverage-blindspots-v1).

parse_sse_events is the streamlit-free wire-protocol parser extracted from
ai_section._stream_chat_tokens_once. Loaded directly from disk to avoid the
package __init__ streamlit import (same pattern as test_ai_table_parse).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PARSING = _ROOT / "dashboard" / "components" / "_parsing.py"


def _load_parsing():
    spec = importlib.util.spec_from_file_location("sse_parsing_under_test", _PARSING)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sse_parsing_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_parsing = _load_parsing()
parse_sse_events = _parsing.parse_sse_events


def _lines(*pairs: tuple[str, dict]) -> list[str]:
    """Build SSE wire lines from (event, data) pairs with blank separators."""
    out: list[str] = []
    for event, data in pairs:
        out.append(f"event: {event}")
        out.append(f"data: {json.dumps(data)}")
        out.append("")  # blank line separates events
    return out


def test_token_events_in_order():
    lines = _lines(("token", {"text": "안"}), ("token", {"text": "녕"}))
    events = list(parse_sse_events(lines))
    assert [e for e, _ in events] == ["token", "token"]
    assert [d["text"] for _, d in events] == ["안", "녕"]


def test_blank_line_resets_event_name():
    # data without a preceding event: → event_name is None
    lines = ["data: " + json.dumps({"x": 1})]
    events = list(parse_sse_events(lines))
    assert events == [(None, {"x": 1})]


def test_malformed_json_data_skipped():
    lines = [
        "event: token",
        "data: {not valid json}",
        "event: token",
        "data: " + json.dumps({"text": "ok"}),
    ]
    events = list(parse_sse_events(lines))
    # broken line skipped, valid one survives — no exception raised
    assert events == [("token", {"text": "ok"})]


def test_error_and_done_events_surfaced():
    lines = _lines(
        ("error", {"code": "rate_limited", "message": "too many"}),
        ("done", {"tokens": 42}),
    )
    events = list(parse_sse_events(lines))
    assert ("error", {"code": "rate_limited", "message": "too many"}) in events
    assert ("done", {"tokens": 42}) in events


def test_event_without_data_yields_nothing():
    lines = ["event: token", "event: done", ""]
    assert list(parse_sse_events(lines)) == []


def test_mixed_event_sequence_preserves_order():
    lines = [
        "event: tool_call",
        "data: " + json.dumps({"name": "search"}),
        "",
        "event: token",
        "data: " + json.dumps({"text": "결과"}),
        "",
        "event: done",
        "data: " + json.dumps({"ok": True}),
    ]
    events = list(parse_sse_events(lines))
    assert [e for e, _ in events] == ["tool_call", "token", "done"]
