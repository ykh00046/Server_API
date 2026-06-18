"""Integration tests for the anomaly detector against a controlled DB."""
from __future__ import annotations

import importlib
import sqlite3
from datetime import date

import pytest

from api import anomaly
from shared.cache import clear_api_cache

# Same modules the conftest live_db fixture redirects for the live query path.
_DB_FILE_MODULES = ("shared.database", "shared._db_connection", "shared.cache")

TODAY = date(2026, 6, 19)


def _build(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE production_records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, production_date TEXT NOT NULL, "
        "item_code TEXT, item_name TEXT, good_quantity INTEGER, lot_number TEXT)"
    )
    conn.executemany(
        "INSERT INTO production_records "
        "(production_date, item_code, item_name, good_quantity, lot_number) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def _drop_conns():
    conn_mod = importlib.import_module("shared._db_connection")
    local = getattr(conn_mod, "_local", None)
    if local is not None:
        for attr in list(vars(local)):
            obj = getattr(local, attr)
            if isinstance(obj, sqlite3.Connection):
                obj.close()
            delattr(local, attr)


@pytest.fixture
def anomaly_db(tmp_path, monkeypatch):
    """Controlled production DB: a sharp volume drop on the latest day plus a
    stale item, wired into the live query path."""
    rows = []
    # 14 baseline days @ 1000 (2026-06-04 .. 2026-06-17)
    for d in range(4, 18):
        rows.append((f"2026-06-{d:02d}", "MN0001", "메인 렌즈", 1000, f"L{d}"))
    # latest completed day @ 100 -> -90% drop
    rows.append(("2026-06-18", "MN0001", "메인 렌즈", 100, "L18"))
    # stale item: last produced 2026-06-01 (18 days idle)
    rows.append(("2026-06-01", "ST0001", "정체 렌즈", 500, "LS1"))

    live_path = tmp_path / "live.db"
    archive_path = tmp_path / "archive_absent.db"
    _build(live_path, rows)

    for name in _DB_FILE_MODULES:
        mod = importlib.import_module(name)
        if hasattr(mod, "DB_FILE"):
            monkeypatch.setattr(mod, "DB_FILE", live_path)
        if hasattr(mod, "ARCHIVE_DB_FILE"):
            monkeypatch.setattr(mod, "ARCHIVE_DB_FILE", archive_path)

    monkeypatch.setattr("shared.config.ANOMALY_STATE_FILE", tmp_path / "state.json")
    clear_api_cache()
    _drop_conns()
    yield live_path
    clear_api_cache()
    _drop_conns()


def test_collect_findings_detects_drop_and_stale(anomaly_db):
    findings = anomaly.collect_findings(today=TODAY)
    kinds = {f.kind for f in findings}
    assert "volume_drop" in kinds
    assert "stale_item" in kinds
    drop = next(f for f in findings if f.kind == "volume_drop")
    assert drop.details["date"] == "2026-06-18"
    assert drop.details["change_pct"] == -90.0
    stale = next(f for f in findings if f.kind == "stale_item")
    assert stale.details["item_code"] == "ST0001"
    assert stale.details["days_idle"] == 18


def test_main_item_not_flagged_stale(anomaly_db):
    findings = anomaly.collect_findings(today=TODAY)
    stale_codes = {f.details["item_code"] for f in findings if f.kind == "stale_item"}
    assert "MN0001" not in stale_codes  # produced through 2026-06-18


def test_disabled_returns_empty(anomaly_db, monkeypatch):
    monkeypatch.setattr("shared.config.ANOMALY_ENABLED", False)
    assert anomaly.collect_findings(today=TODAY) == []


def test_run_detection_emit_marks_cooldown(anomaly_db):
    # First emit: new findings flow through (no webhooks registered -> no real
    # delivery, but cooldown is recorded).
    first = anomaly.run_detection(emit=True, today=TODAY)
    assert first["count"] >= 2
    assert first["emitted_count"] >= 2
    # Second emit immediately: cooldown suppresses re-emission.
    second = anomaly.run_detection(emit=True, today=TODAY)
    assert second["count"] == first["count"]
    assert second["emitted_count"] == 0


def test_dry_run_does_not_record_cooldown(anomaly_db):
    anomaly.run_detection(emit=False, today=TODAY)
    # emit=True afterwards should still fire (dry-run left no cooldown).
    after = anomaly.run_detection(emit=True, today=TODAY)
    assert after["emitted_count"] >= 2
