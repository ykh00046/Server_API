"""Unit tests for cooldown state persistence + dedup filtering."""
from __future__ import annotations

from api.anomaly import store_state
from api.anomaly.schemas import Finding


def _finding(key="volume_drop:2026-06-18"):
    return Finding(kind="volume_drop", severity="warning", key=key, message="x")


def test_load_missing_returns_skeleton(tmp_path):
    state = store_state.load_state(tmp_path / "nope.json")
    assert state == {"cooldowns": {}, "last_scan_ts": 0}


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    store_state.save_state({"cooldowns": {"k": 123}, "last_scan_ts": 5}, p)
    assert store_state.load_state(p)["cooldowns"]["k"] == 123


def test_load_corrupt_file_resets(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert store_state.load_state(p) == {"cooldowns": {}, "last_scan_ts": 0}


def test_filter_new_passes_unseen():
    state = {"cooldowns": {}}
    fresh = store_state.filter_new([_finding()], state, now=1000, cooldown_sec=100)
    assert len(fresh) == 1


def test_filter_new_suppresses_within_cooldown():
    f = _finding()
    state = {"cooldowns": {f.key: 950}}
    fresh = store_state.filter_new([f], state, now=1000, cooldown_sec=100)
    assert fresh == []


def test_filter_new_passes_after_cooldown():
    f = _finding()
    state = {"cooldowns": {f.key: 800}}
    fresh = store_state.filter_new([f], state, now=1000, cooldown_sec=100)
    assert len(fresh) == 1


def test_mark_emitted_records_now():
    f = _finding()
    state = store_state.mark_emitted([f], {"cooldowns": {}}, now=1234)
    assert state["cooldowns"][f.key] == 1234


def test_prune_drops_old_entries():
    state = {"cooldowns": {"old": 100, "recent": 990}}
    store_state.prune(state, now=1000, max_age_sec=100)
    assert "old" not in state["cooldowns"]
    assert "recent" in state["cooldowns"]
