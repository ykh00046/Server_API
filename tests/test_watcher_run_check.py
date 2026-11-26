"""tools/watcher.py execution core — run_check and its helpers (test-gap 공백 2).

The standalone watcher (Task Scheduler ProductionHubWatcher) heals indexes and
runs ANALYZE on the real DBs. These tests point every module-level path
(DB_FILE, ARCHIVE_DB_FILE, STATE_FILE, DATABASE_DIR, LOGS_DIR, LOG_FILE) at
tmp_path, replace wait_for_stabilization with a fake (the real one sleeps
3 x 5 s) and replace the module's `time` with a fake clock. Index healing and
ANALYZE run for real against the temp SQLite files.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from shared.db_maintenance import REQUIRED_INDEXES, check_and_heal_indexes, get_file_state
from tools import watcher as watcher_mod

NOW = 1_800_000_000.0


def _make_db(path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE production_records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, production_date TEXT, "
        "item_code TEXT, item_name TEXT, good_quantity INTEGER, lot_number TEXT)"
    )
    conn.execute(
        "INSERT INTO production_records "
        "(production_date, item_code, item_name, good_quantity, lot_number) "
        "VALUES ('2026-03-01', 'BW0021', 'x', 10, 'LT1')"
    )
    conn.commit()
    conn.close()


def _index_names(path) -> set[str]:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


@pytest.fixture
def wenv(tmp_path, monkeypatch):
    """Watcher wired entirely to tmp files, with fake stabilization and clock."""
    live = tmp_path / "live.db"
    archive = tmp_path / "archive.db"
    _make_db(live)
    _make_db(archive)
    state_file = tmp_path / "state" / ".watcher_state.json"
    logs_dir = tmp_path / "logs"

    monkeypatch.setattr(watcher_mod, "DB_FILE", live)
    monkeypatch.setattr(watcher_mod, "ARCHIVE_DB_FILE", archive)
    monkeypatch.setattr(watcher_mod, "STATE_FILE", state_file)
    monkeypatch.setattr(watcher_mod, "DATABASE_DIR", state_file.parent)
    monkeypatch.setattr(watcher_mod, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(watcher_mod, "LOG_FILE", logs_dir / "watcher.log")

    env = SimpleNamespace(
        live=live,
        archive=archive,
        state_file=state_file,
        log_file=logs_dir / "watcher.log",
        stable={live: True, archive: True},
        stab_calls=[],
        now=NOW,
        sleeps=[],
    )

    def fake_wait(path):
        env.stab_calls.append(path)
        return env.stable[path]

    monkeypatch.setattr(watcher_mod, "wait_for_stabilization", fake_wait)
    monkeypatch.setattr(
        watcher_mod,
        "time",
        SimpleNamespace(time=lambda: env.now, sleep=lambda s: env.sleeps.append(s)),
    )
    return env


def _write_state(env, **overrides) -> None:
    lm, ls = get_file_state(env.live)
    am, asz = get_file_state(env.archive)
    state = {
        "live_mtime": lm, "live_size": ls,
        "archive_mtime": am, "archive_size": asz,
        "last_analyze_ts": env.now,
    }
    state.update(overrides)
    env.state_file.parent.mkdir(parents=True, exist_ok=True)
    env.state_file.write_text(json.dumps(state), encoding="utf-8")


def _read_state(env) -> dict:
    return json.loads(env.state_file.read_text(encoding="utf-8"))


# ==========================================================
# run_check: first run (no state file -> all zeros)
# ==========================================================
def test_first_run_heals_both_dbs_runs_analyze_and_saves_state(wenv):
    assert not wenv.state_file.exists()

    summary = watcher_mod.run_check()

    # Both DBs count as changed against the all-zero default state
    assert summary["live"]["changed"] is True
    assert summary["archive"]["changed"] is True
    assert wenv.stab_calls == [wenv.live, wenv.archive]
    assert sorted(summary["live"]["result"]["healed"]) == sorted(REQUIRED_INDEXES)
    assert sorted(summary["archive"]["result"]["healed"]) == sorted(REQUIRED_INDEXES)
    assert _index_names(wenv.live) == set(REQUIRED_INDEXES)
    assert _index_names(wenv.archive) == set(REQUIRED_INDEXES)

    # last_analyze_ts=0 -> ANALYZE runs on both files immediately
    assert summary["analyze"]["ran"] is True
    assert [r["success"] for r in summary["analyze"]["results"]] == [True, True]

    # State was written with real (non-zero) file states and the clock
    saved = _read_state(wenv)
    assert saved["live_mtime"] > 0 and saved["live_size"] > 0
    assert saved["archive_mtime"] > 0 and saved["archive_size"] > 0
    assert saved["last_analyze_ts"] == NOW


def test_state_is_refreshed_after_heal_so_next_cycle_sees_unchanged(wenv):
    """With ANALYZE not due, the post-heal file state is what gets saved
    (watcher.py:126,152), so the heal's own write is not seen as a change."""
    _write_state(wenv, live_mtime=0, live_size=0, archive_mtime=0, archive_size=0)

    first = watcher_mod.run_check()
    assert first["live"]["changed"] is True and first["archive"]["changed"] is True
    assert first["analyze"]["ran"] is False
    saved = _read_state(wenv)
    assert (saved["live_mtime"], saved["live_size"]) == get_file_state(wenv.live)
    assert (saved["archive_mtime"], saved["archive_size"]) == get_file_state(wenv.archive)

    wenv.stab_calls.clear()
    second = watcher_mod.run_check()

    assert second["live"]["changed"] is False
    assert second["archive"]["changed"] is False
    assert wenv.stab_calls == []  # no stabilization wait when nothing changed


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known, accepted (low severity, not fixed): run_check captures file states in "
        "_check_live_db/_check_archive_db (watcher.py:205,208) and only then runs ANALYZE "
        "(211), which writes sqlite_stat1 into both files; the stale pre-ANALYZE states "
        "are saved (214-220). The next cycle reports both DBs 'changed' (false positive) "
        "and waits for stabilization again (real cost: 3 x 5 s per DB). "
        "See docs/watcher-archive-retry-RESULT.md."
    ),
)
def test_cycle_after_analyze_does_not_report_its_own_write_as_change(wenv):
    watcher_mod.run_check()  # first run: heal + ANALYZE
    wenv.stab_calls.clear()

    second = watcher_mod.run_check()

    assert second["live"]["changed"] is False
    assert second["archive"]["changed"] is False
    assert wenv.stab_calls == []


# ==========================================================
# _check_live_db: "unchanged but still heals" branch (watcher.py:129-133)
# ==========================================================
def test_unchanged_live_db_is_still_healed(wenv):
    _write_state(wenv)
    assert _index_names(wenv.live) == set()

    summary = watcher_mod.run_check()

    assert summary["live"]["changed"] is False
    assert wenv.live not in wenv.stab_calls  # no stabilization wait on this path
    assert sorted(summary["live"]["result"]["healed"]) == sorted(REQUIRED_INDEXES)
    assert _index_names(wenv.live) == set(REQUIRED_INDEXES)


def test_unchanged_archive_db_is_not_healed(wenv):
    """Pins current behaviour: only the live DB gets the periodic heal.
    An unchanged archive is left alone (watcher.py:155-157)."""
    _write_state(wenv)

    summary = watcher_mod.run_check()

    assert summary["archive"]["changed"] is False
    assert summary["archive"]["result"] is None
    assert _index_names(wenv.archive) == set()


def test_changed_but_unstable_live_db_skips_heal(wenv):
    _write_state(wenv, live_mtime=0, live_size=0)
    wenv.stable[wenv.live] = False

    summary = watcher_mod.run_check()

    assert summary["live"]["changed"] is True
    assert summary["live"]["result"] is None
    assert _index_names(wenv.live) == set()
    assert "Live DB not stable" in wenv.log_file.read_text(encoding="utf-8")


def test_archive_skipped_as_unstable_is_healed_on_next_cycle(wenv):
    _write_state(wenv, archive_mtime=0, archive_size=0)
    wenv.stable[wenv.archive] = False

    first = watcher_mod.run_check()
    assert first["archive"]["changed"] is True
    assert first["archive"]["result"] is None
    assert _index_names(wenv.archive) == set()

    # Next hourly cycle: the file is now stable and was not touched in between.
    wenv.stable[wenv.archive] = True
    watcher_mod.run_check()

    assert _index_names(wenv.archive) == set(REQUIRED_INDEXES)


def test_skipped_archive_heal_keeps_old_state_then_retries_once(wenv):
    """Unstable archive: the old state is kept (not the fresh file state), the
    next cycle retries with a stabilization wait and heals, and the cycle after
    that does not heal or wait again because nothing changed."""
    check_and_heal_indexes(wenv.live)  # keep the live DB out of the picture
    _write_state(wenv, archive_mtime=0, archive_size=0)
    wenv.stable[wenv.archive] = False

    watcher_mod.run_check()
    saved = _read_state(wenv)
    assert (saved["archive_mtime"], saved["archive_size"]) == (0, 0)
    assert "Archive DB not stable" in wenv.log_file.read_text(encoding="utf-8")

    # Retry cycle: now stable
    wenv.stable[wenv.archive] = True
    wenv.stab_calls.clear()
    retry = watcher_mod.run_check()

    assert retry["archive"]["changed"] is True
    assert wenv.stab_calls == [wenv.archive]
    assert sorted(retry["archive"]["result"]["healed"]) == sorted(REQUIRED_INDEXES)
    saved = _read_state(wenv)
    assert (saved["archive_mtime"], saved["archive_size"]) == get_file_state(wenv.archive)

    # Following cycle: nothing changed -> no repeat heal, no wait
    wenv.stab_calls.clear()
    third = watcher_mod.run_check()

    assert third["archive"] == {"changed": False, "result": None}
    assert wenv.stab_calls == []


def test_skipped_archive_heal_is_retried_even_when_analyze_ran_that_cycle(wenv):
    """The post-ANALYZE state refresh must not overwrite the kept old state of
    an archive whose heal was skipped as unstable."""
    check_and_heal_indexes(wenv.live)
    _write_state(wenv, archive_mtime=0, archive_size=0, last_analyze_ts=0)
    wenv.stable[wenv.archive] = False

    first = watcher_mod.run_check()
    assert first["analyze"]["ran"] is True
    saved = _read_state(wenv)
    assert (saved["archive_mtime"], saved["archive_size"]) == (0, 0)

    wenv.stable[wenv.archive] = True
    retry = watcher_mod.run_check()

    assert retry["archive"]["changed"] is True
    assert _index_names(wenv.archive) == set(REQUIRED_INDEXES)


def test_completed_archive_heal_is_not_repeated_when_nothing_changed(wenv):
    check_and_heal_indexes(wenv.live)  # keep the live DB out of the picture
    _write_state(wenv, archive_mtime=0, archive_size=0)

    first = watcher_mod.run_check()
    assert first["archive"]["changed"] is True
    assert sorted(first["archive"]["result"]["healed"]) == sorted(REQUIRED_INDEXES)

    for _ in range(2):
        wenv.stab_calls.clear()
        nxt = watcher_mod.run_check()
        assert nxt["archive"] == {"changed": False, "result": None}
        assert wenv.stab_calls == []


def test_missing_archive_is_skipped_and_state_zeroed(wenv, tmp_path, monkeypatch):
    absent = tmp_path / "no_archive.db"
    monkeypatch.setattr(watcher_mod, "ARCHIVE_DB_FILE", absent)

    summary = watcher_mod.run_check()

    assert summary["archive"] == {"changed": False, "result": None}
    assert absent not in wenv.stab_calls
    assert not absent.exists()  # never created
    saved = _read_state(wenv)
    assert (saved["archive_mtime"], saved["archive_size"]) == (0, 0)
    # ANALYZE only touches the file that exists
    assert [r["db"] for r in summary["analyze"]["results"]] == ["live.db"]


def test_missing_live_db_is_skipped(wenv, tmp_path, monkeypatch):
    absent = tmp_path / "no_live.db"
    monkeypatch.setattr(watcher_mod, "DB_FILE", absent)

    summary = watcher_mod.run_check()

    assert summary["live"] == {"changed": False, "result": None}
    assert not absent.exists()
    saved = _read_state(wenv)
    assert (saved["live_mtime"], saved["live_size"]) == (0, 0)


# ==========================================================
# _run_periodic_analyze: 24 h boundary
# ==========================================================
@pytest.mark.parametrize(
    ("last_ts", "should_run"),
    [
        (0, True),                                    # first run
        (NOW - watcher_mod.ANALYZE_INTERVAL - 1, True),
        (NOW - watcher_mod.ANALYZE_INTERVAL, True),   # exactly 24 h -> runs (< is strict)
        (NOW - watcher_mod.ANALYZE_INTERVAL + 1, False),
        (NOW, False),
    ],
)
def test_periodic_analyze_boundary(wenv, last_ts, should_run):
    summary = {"analyze": {"ran": False, "results": []}}

    new_ts = watcher_mod._run_periodic_analyze(summary, last_ts)

    assert summary["analyze"]["ran"] is should_run
    if should_run:
        assert new_ts == NOW
        assert len(summary["analyze"]["results"]) == 2
    else:
        assert new_ts == last_ts
        assert summary["analyze"]["results"] == []


def test_failed_analyze_is_recorded_and_still_advances_timestamp(wenv, monkeypatch):
    """Pins current behaviour: a failed ANALYZE is logged and recorded in the
    summary, but last_analyze_ts still advances, so it is not retried for 24 h."""
    monkeypatch.setattr(
        watcher_mod,
        "run_analyze",
        lambda p: {"db": p.name, "success": False, "duration_ms": 0.0, "error": "boom"},
    )
    summary = {"analyze": {"ran": False, "results": []}}

    new_ts = watcher_mod._run_periodic_analyze(summary, 0)

    assert new_ts == NOW
    assert summary["analyze"]["ran"] is True
    assert [r["error"] for r in summary["analyze"]["results"]] == ["boom", "boom"]
    assert "ANALYZE failed" in wenv.log_file.read_text(encoding="utf-8")


# ==========================================================
# main() exit code and run_daemon loop survival
# ==========================================================
def test_main_returns_1_when_heal_reports_error(wenv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["watcher.py"])
    monkeypatch.setattr(
        watcher_mod,
        "check_and_heal_indexes",
        lambda p: {"db": p.name, "checked": False, "healed": [], "error": "disk I/O error"},
    )
    assert watcher_mod.main() == 1


def test_main_returns_0_on_clean_run(wenv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["watcher.py"])
    assert watcher_mod.main() == 0


class _StopDaemon(BaseException):
    """Escapes run_daemon's `while True` (not caught by its except tuple)."""


def test_daemon_survives_a_failed_cycle(wenv, monkeypatch):
    calls = []

    def fake_run_check():
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        if len(calls) == 2:
            raise OSError("file replaced mid-read")
        raise _StopDaemon

    monkeypatch.setattr(watcher_mod, "run_check", fake_run_check)

    with pytest.raises(_StopDaemon):
        watcher_mod.run_daemon(interval=3)

    assert len(calls) == 3  # loop went on after both failures
    assert wenv.sleeps == [1, 1, 1, 1, 1, 1]  # interval slept per cycle, in 1 s steps
    log_text = wenv.log_file.read_text(encoding="utf-8")
    assert "Check cycle failed: database is locked" in log_text
    assert "Check cycle failed: file replaced mid-read" in log_text
