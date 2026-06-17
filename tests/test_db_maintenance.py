# tests/test_db_maintenance.py
"""Unit tests for shared/db_maintenance.py.

Index healing, ANALYZE, VACUUM, file-state and stabilization helpers. All run
against real temp SQLite files (no mocks of sqlite itself).
"""

import sqlite3

import pytest

from shared import db_maintenance as dbm
from shared.db_maintenance import (
    REQUIRED_INDEXES,
    check_and_heal_indexes,
    get_file_state,
    run_analyze,
    run_vacuum,
    wait_for_stabilization,
)


def _make_db(path, *, with_table=True):
    conn = sqlite3.connect(str(path))
    if with_table:
        conn.execute(
            "CREATE TABLE production_records ("
            "id INTEGER PRIMARY KEY, production_date TEXT, item_code TEXT, "
            "lot_number TEXT, good_quantity INTEGER)"
        )
        conn.execute(
            "INSERT INTO production_records "
            "(production_date, item_code, lot_number, good_quantity) "
            "VALUES ('2026-01-01', 'X', 'L1', 5)"
        )
    conn.commit()
    conn.close()


# ==========================================================
# get_file_state
# ==========================================================
class TestGetFileState:
    def test_missing_file(self, tmp_path):
        assert get_file_state(tmp_path / "nope.db") == (0, 0)

    def test_existing_file(self, tmp_path):
        p = tmp_path / "f.db"
        p.write_bytes(b"hello")
        mtime, size = get_file_state(p)
        assert mtime > 0
        assert size == 5


# ==========================================================
# check_and_heal_indexes
# ==========================================================
class TestCheckAndHealIndexes:
    def test_missing_file(self, tmp_path):
        res = check_and_heal_indexes(tmp_path / "nope.db")
        assert res["error"] == "File not found"
        assert res["checked"] is False
        assert res["healed"] == []

    def test_heals_all_indexes_on_fresh_db(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        res = check_and_heal_indexes(p)
        assert res["checked"] is True
        assert res["error"] is None
        assert set(res["healed"]) == set(REQUIRED_INDEXES.keys())

    def test_idempotent_second_run_heals_nothing(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        check_and_heal_indexes(p)
        res = check_and_heal_indexes(p)
        assert res["checked"] is True
        assert res["healed"] == []

    def test_partial_heal(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        # Pre-create one index; the rest should be healed.
        conn = sqlite3.connect(str(p))
        conn.execute(REQUIRED_INDEXES["idx_item_code"])
        conn.commit()
        conn.close()
        res = check_and_heal_indexes(p)
        assert "idx_item_code" not in res["healed"]
        assert len(res["healed"]) == len(REQUIRED_INDEXES) - 1

    def test_custom_indexes(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        custom = {
            "idx_custom": "CREATE INDEX IF NOT EXISTS idx_custom "
            "ON production_records(good_quantity)"
        }
        res = check_and_heal_indexes(p, indexes=custom)
        assert res["healed"] == ["idx_custom"]

    def test_sqlite_error_on_missing_table(self, tmp_path):
        # DB without production_records -> CREATE INDEX fails -> error captured.
        p = tmp_path / "empty.db"
        _make_db(p, with_table=False)
        res = check_and_heal_indexes(p)
        assert res["checked"] is True
        assert res["error"] is not None


# ==========================================================
# run_analyze
# ==========================================================
class TestRunAnalyze:
    def test_missing_file(self, tmp_path):
        res = run_analyze(tmp_path / "nope.db")
        assert res["error"] == "File not found"
        assert res["success"] is False

    def test_success(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        res = run_analyze(p)
        assert res["success"] is True
        assert res["error"] is None
        assert res["duration_ms"] >= 0

    def test_error_on_missing_table(self, tmp_path):
        p = tmp_path / "empty.db"
        _make_db(p, with_table=False)
        res = run_analyze(p)
        assert res["success"] is False
        assert res["error"] is not None


# ==========================================================
# run_vacuum
# ==========================================================
class TestRunVacuum:
    def test_missing_file(self, tmp_path):
        res = run_vacuum(tmp_path / "nope.db")
        assert res["error"] == "File not found"
        assert res["success"] is False

    def test_success(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        res = run_vacuum(p)
        assert res["success"] is True
        assert res["error"] is None


# ==========================================================
# wait_for_stabilization
# ==========================================================
class TestWaitForStabilization:
    def test_missing_file(self, tmp_path):
        assert wait_for_stabilization(tmp_path / "nope.db", wait_seconds=0) is False

    def test_stable_file(self, tmp_path):
        p = tmp_path / "live.db"
        _make_db(p)
        # No writes between checks -> stable immediately (wait_seconds=0).
        assert wait_for_stabilization(p, wait_seconds=0, checks=2) is True

    def test_changing_file_hits_retry_cap(self, tmp_path, monkeypatch):
        p = tmp_path / "live.db"
        _make_db(p)

        # Make every state read look different so the file never "stabilizes",
        # forcing recursion up to MAX_STABILIZATION_RETRIES then returning False.
        counter = {"n": 0}

        def _ever_changing(_path):
            counter["n"] += 1
            return float(counter["n"]), counter["n"]

        monkeypatch.setattr(dbm, "get_file_state", _ever_changing)
        assert (
            wait_for_stabilization(p, wait_seconds=0, checks=1) is False
        )
        assert counter["n"] >= dbm.MAX_STABILIZATION_RETRIES


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
