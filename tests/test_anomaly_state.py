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


def test_save_state_atomic_replace(tmp_path):
    """save_state는 temp 파일 + os.replace 원자 교체 — 손상 파일로
    쿨다운 전체가 리셋(재발행 폭주)되는 경로를 막는다."""
    path = tmp_path / "state.json"
    store_state.save_state({"cooldowns": {"k": 1.0}, "last_scan_ts": 1.0}, path)
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()  # temp 잔재 없음
    assert store_state.load_state(path)["cooldowns"] == {"k": 1.0}


def test_emit_failure_not_marked(tmp_path, monkeypatch):
    """emit 실패한 finding은 쿨다운 마킹되지 않아 다음 스캔에서
    재시도된다 (full-review-202607: 실패분 1일 유실 방지)."""
    import api.notifications
    from api.anomaly import detector
    from shared import config as cfg

    state_file = tmp_path / "state.json"
    monkeypatch.setattr(cfg, "ANOMALY_STATE_FILE", state_file)

    def flaky_emit(event_type, payload):
        if payload["key"] == "volume_drop:fail":
            raise RuntimeError("enqueue failed")
        return []

    monkeypatch.setattr(api.notifications, "emit_event", flaky_emit)
    ok = _finding("volume_drop:ok")
    bad = _finding("volume_drop:fail")

    # filter_new는 `now - last(0) >= cooldown_sec`이므로 now가 쿨다운보다 커야 fresh
    now = float(cfg.ANOMALY_COOLDOWN_SEC * 10)
    emitted = detector._emit_new([ok, bad], now=now)

    assert emitted == ["volume_drop:ok"]
    state = store_state.load_state(state_file)
    assert "volume_drop:ok" in state["cooldowns"]
    assert "volume_drop:fail" not in state["cooldowns"]
