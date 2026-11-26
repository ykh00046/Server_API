"""tools/db_watcher.py DBWatcher thread (test-gap 공백 3).

The manager-embedded watcher must survive any exception inside a cycle: a past
incident had the thread die on an OSError while the UI kept showing 'Active'.
run() is driven synchronously in the test thread (no .start()), the module's
`time` is replaced by a fake whose sleep never blocks, and
wait_for_stabilization is faked (the real one sleeps 3 x 5 s). DB paths point
at tmp_path files.
"""
from __future__ import annotations

import os
import sqlite3
from queue import Queue
from types import SimpleNamespace

import pytest

from shared.db_maintenance import REQUIRED_INDEXES
from tools import db_watcher as dbw_mod


def _make_db(path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE production_records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, production_date TEXT, "
        "item_code TEXT, item_name TEXT, good_quantity INTEGER, lot_number TEXT)"
    )
    conn.commit()
    conn.close()


def _touch_db(path) -> None:
    """Simulate an ERP write: add a row so size/mtime change."""
    conn = sqlite3.connect(str(path))
    conn.executemany(
        "INSERT INTO production_records (production_date, item_code, good_quantity) "
        "VALUES ('2026-03-01', 'BW0021', ?)",
        [(i,) for i in range(200)],
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


def _messages(q: Queue) -> list[tuple[str, str]]:
    return list(q.queue)


@pytest.fixture
def denv(tmp_path, monkeypatch):
    live = tmp_path / "live.db"
    archive = tmp_path / "archive_absent.db"  # not created by default
    _make_db(live)
    monkeypatch.setattr(dbw_mod, "DB_FILE", live)
    monkeypatch.setattr(dbw_mod, "ARCHIVE_DB_FILE", archive)

    env = SimpleNamespace(live=live, archive=archive, stable=True, stab_calls=[], sleeps=[],
                          on_sleep=None)

    def fake_wait(path):
        env.stab_calls.append(path)
        return env.stable

    def fake_sleep(seconds):
        env.sleeps.append(seconds)
        if env.on_sleep is not None:
            env.on_sleep(seconds)

    monkeypatch.setattr(dbw_mod, "wait_for_stabilization", fake_wait)
    monkeypatch.setattr(dbw_mod, "time", SimpleNamespace(sleep=fake_sleep))
    return env


# ==========================================================
# Construction and _check_and_heal
# ==========================================================
def test_init_tracks_only_existing_db_files(denv):
    w = dbw_mod.DBWatcher(Queue(), interval=1)
    assert list(w.db_states) == [str(denv.live)]
    assert w.daemon is True


def test_change_detected_heals_indexes_and_refreshes_state(denv):
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=1)
    _touch_db(denv.live)

    w._check_and_heal()

    assert denv.stab_calls == [denv.live]
    assert _index_names(denv.live) == set(REQUIRED_INDEXES)
    levels = [lvl for lvl, _ in _messages(q)]
    assert levels == ["WARN", "INFO", "SUCCESS"]
    assert w.db_states[str(denv.live)] == (
        os.path.getmtime(denv.live), os.path.getsize(denv.live)
    )


def test_unchanged_db_is_not_touched(denv):
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=1)

    w._check_and_heal()

    assert denv.stab_calls == []
    assert _messages(q) == []
    assert _index_names(denv.live) == set()


def test_unstable_db_keeps_old_state_and_is_retried_next_cycle(denv):
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=1)
    before = w.db_states[str(denv.live)]
    _touch_db(denv.live)
    denv.stable = False

    w._check_and_heal()

    assert _messages(q)[-1][0] == "WARN"
    assert w.db_states[str(denv.live)] == before  # not advanced
    assert _index_names(denv.live) == set()

    denv.stable = True
    w._check_and_heal()

    assert _index_names(denv.live) == set(REQUIRED_INDEXES)


def test_deleted_db_file_is_skipped(denv):
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=1)
    denv.live.unlink()

    w._check_and_heal()  # must not raise

    assert _messages(q) == []


# ==========================================================
# run(): loop survival
# ==========================================================
def test_run_loop_survives_exceptions_in_a_cycle(denv, monkeypatch):
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=2)
    errors = [
        OSError("file replaced"),
        sqlite3.OperationalError("database is locked"),
        RuntimeError("unexpected"),
        KeyError("odd"),
    ]
    calls = []

    def fake_cycle():
        calls.append(1)
        if errors:
            raise errors.pop(0)
        w.running = False  # 5th cycle succeeds, then stop

    monkeypatch.setattr(w, "_check_and_heal", fake_cycle)

    w.run()

    assert len(calls) == 5
    msgs = _messages(q)
    assert msgs[0][0] == "SUCCESS"  # started
    error_msgs = [m for lvl, m in msgs if lvl == "ERROR"]
    assert error_msgs == [
        "Watcher Error: file replaced",
        "Watcher Error: database is locked",
        "Watcher Unexpected Error: unexpected",
        "Watcher Unexpected Error: 'odd'",
    ]
    # each error backs off 60 s; each cycle first sleeps `interval` x 1 s
    assert denv.sleeps.count(60) == 4
    assert denv.sleeps.count(1) == 5 * 2


def test_run_loop_survives_real_getmtime_oserror(denv, monkeypatch):
    """The real _check_and_heal path: os.path.getmtime raises while the ERP swaps
    the file (db_watcher.py:78). The thread must log and keep cycling."""
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=1)
    getmtime_calls = []

    def flaky_getmtime(path):
        getmtime_calls.append(path)
        if len(getmtime_calls) == 1:
            raise OSError("The process cannot access the file")
        return os.path.getmtime(path)

    fake_os = SimpleNamespace(
        path=SimpleNamespace(getmtime=flaky_getmtime, getsize=os.path.getsize)
    )
    monkeypatch.setattr(dbw_mod, "os", fake_os)

    def stop_after_second_cycle(_seconds):
        if len(getmtime_calls) >= 2:
            w.running = False

    denv.on_sleep = stop_after_second_cycle

    w.run()

    assert len(getmtime_calls) == 2  # a second cycle ran after the error
    assert ("ERROR", "Watcher Error: The process cannot access the file") in _messages(q)


def test_stop_during_interval_sleep_skips_the_cycle(denv, monkeypatch):
    q = Queue()
    w = dbw_mod.DBWatcher(q, interval=5)
    calls = []
    monkeypatch.setattr(w, "_check_and_heal", lambda: calls.append(1))
    denv.on_sleep = lambda _s: w.stop()

    w.run()

    assert calls == []
    assert denv.sleeps == [1]  # broke out of the interval loop right away
    assert _messages(q)[-1][0] == "INFO"  # "DB Watcher Stopped"
