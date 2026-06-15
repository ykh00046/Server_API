"""Unit tests for tools/watcher.py state persistence (coverage-blindspots-v2).

load_state / save_state are file-backed but small and deterministic. STATE_FILE
is a module-level global the functions read at call time, so monkeypatching it to
a tmp path isolates each test. run_check (DB+FS+time orchestration) is out of
scope — not unit-friendly, see the v2 plan.
"""
from __future__ import annotations

import json

from tools import watcher as watcher_mod

_DEFAULT = {
    "live_mtime": 0,
    "live_size": 0,
    "archive_mtime": 0,
    "archive_size": 0,
    "last_analyze_ts": 0,
}


def test_load_state_missing_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher_mod, "STATE_FILE", tmp_path / "nope.json")
    assert watcher_mod.load_state() == _DEFAULT


def test_load_state_corrupt_json_returns_default(tmp_path, monkeypatch):
    bad = tmp_path / "state.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(watcher_mod, "STATE_FILE", bad)
    assert watcher_mod.load_state() == _DEFAULT


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(watcher_mod, "STATE_FILE", state_file)
    # save_state also needs DATABASE_DIR to exist for mkdir; point it at tmp
    monkeypatch.setattr(watcher_mod, "DATABASE_DIR", tmp_path)
    state = {
        "live_mtime": 123,
        "live_size": 456,
        "archive_mtime": 789,
        "archive_size": 10,
        "last_analyze_ts": 1700000000,
    }
    watcher_mod.save_state(state)
    assert state_file.exists()
    assert watcher_mod.load_state() == state


def test_save_state_writes_valid_json(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(watcher_mod, "STATE_FILE", state_file)
    monkeypatch.setattr(watcher_mod, "DATABASE_DIR", tmp_path)
    watcher_mod.save_state({"live_mtime": 1})
    loaded = json.loads(state_file.read_text(encoding="utf-8"))
    assert loaded["live_mtime"] == 1
