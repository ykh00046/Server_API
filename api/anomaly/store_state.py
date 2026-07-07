"""Cooldown state persistence for anomaly alerts.

The detector emits a finding at most once per cooldown window, keyed by the
finding's stable `key`. State is a small JSON file (same approach as
tools/watcher.py's .watcher_state.json). All functions degrade gracefully:
a missing/corrupt file is treated as empty state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from shared import DATABASE_DIR, get_logger
from shared import config as cfg

from .schemas import Finding

logger = get_logger(__name__)


def _state_path(path: Path | None) -> Path:
    """Resolve the state-file path at call time (so config monkeypatch works)."""
    return path if path is not None else cfg.ANOMALY_STATE_FILE


def load_state(path: Path | None = None) -> dict:
    """Load cooldown state; return empty skeleton on missing/corrupt file."""
    path = _state_path(path)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("cooldowns", {})
                return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[anomaly.state] load failed, resetting: %s", e)
    return {"cooldowns": {}, "last_scan_ts": 0}


def save_state(state: dict, path: Path | None = None) -> None:
    """Persist state atomically; failures are logged, never raised.

    temp 파일에 쓰고 os.replace로 교체 — 쓰기 중 크래시로 파일이
    손상되면 load_state가 빈 상태로 리셋해 모든 쿨다운이 소실되고
    다음 스캔에서 알림이 재발행 폭주할 수 있다."""
    path = _state_path(path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp_path, path)
    except OSError as e:
        logger.warning("[anomaly.state] save failed: %s", e)


def filter_new(
    findings: list[Finding],
    state: dict,
    *,
    now: float,
    cooldown_sec: int,
) -> list[Finding]:
    """Return only findings whose key is outside its cooldown window.

    A finding is "new" if its key has never fired, or its last emit was more
    than `cooldown_sec` ago. Does not mutate state (use mark_emitted to record).
    """
    cooldowns: dict = state.get("cooldowns", {})
    fresh: list[Finding] = []
    for f in findings:
        last = cooldowns.get(f.key, 0)
        if now - last >= cooldown_sec:
            fresh.append(f)
    return fresh


def mark_emitted(findings: list[Finding], state: dict, *, now: float) -> dict:
    """Record `now` as the last-emit time for each finding key (in place)."""
    cooldowns: dict = state.setdefault("cooldowns", {})
    for f in findings:
        cooldowns[f.key] = now
    return state


def prune(state: dict, *, now: float, max_age_sec: int) -> dict:
    """Drop cooldown entries older than max_age_sec to bound file growth."""
    cooldowns: dict = state.get("cooldowns", {})
    state["cooldowns"] = {
        k: ts for k, ts in cooldowns.items() if now - ts < max_age_sec
    }
    return state
