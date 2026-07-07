"""Unit tests for the anomaly findings history store (anomaly-dashboard-v2).

Covers record/list round-trip, filters, limit clamp, retention prune, and
the FR-6 contract: record/prune never raise to the emit path.
"""
from __future__ import annotations

import datetime as dt

import pytest

import shared.config as cfg
from api.anomaly import store_findings
from api.anomaly.schemas import Finding


@pytest.fixture
def findings_db(tmp_path, monkeypatch):
    """Point the findings store at a fresh tmp DB for each test."""
    db_path = tmp_path / "anomaly.db"
    monkeypatch.setattr(cfg, "ANOMALY_DB_FILE", db_path)
    store_findings.reset_for_tests()
    yield db_path
    store_findings.reset_for_tests()


def _finding(key="volume_drop:2026-07-06", kind="volume_drop",
             severity="warning"):
    return Finding(
        kind=kind, severity=severity, key=key,
        message="테스트 이상", details={"date": "2026-07-06", "qty": 10.0},
    )


def test_record_and_list_roundtrip(findings_db):
    n = store_findings.record_findings([_finding(), _finding(key="k2")])
    assert n == 2
    rows = store_findings.list_findings()
    assert len(rows) == 2
    top = rows[0]
    assert top["kind"] == "volume_drop"
    assert top["event_type"] == "production.anomaly.volume_drop"
    assert top["details"] == {"date": "2026-07-06", "qty": 10.0}  # dict 복원
    assert top["emitted_at"]


def test_record_empty_is_noop(findings_db):
    assert store_findings.record_findings([]) == 0
    assert store_findings.list_findings() == []


def test_list_filters_kind_severity_days(findings_db):
    store_findings.record_findings([
        _finding(key="a", kind="volume_drop", severity="critical"),
        _finding(key="b", kind="stale_item", severity="warning"),
    ])
    old = (dt.datetime.now() - dt.timedelta(days=40)).isoformat(
        timespec="seconds"
    )
    store_findings.record_findings(
        [_finding(key="old", kind="volume_spike")], now_iso=old
    )

    assert {r["key"] for r in store_findings.list_findings()} == {"a", "b"}
    assert [r["key"] for r in store_findings.list_findings(kind="stale_item")] == ["b"]
    assert [r["key"] for r in store_findings.list_findings(severity="critical")] == ["a"]
    # days 확장 시 오래된 행 포함
    assert len(store_findings.list_findings(days=60)) == 3


def test_list_limit_clamped(findings_db):
    store_findings.record_findings([_finding(key=f"k{i}") for i in range(5)])
    assert len(store_findings.list_findings(limit=2)) == 2
    # 상한(500) 초과 요청도 안전
    assert len(store_findings.list_findings(limit=99999)) == 5


def test_same_key_reemission_appends(findings_db):
    """key는 유니크가 아니다 — 쿨다운 만료 후 재발행은 새 이력 행."""
    store_findings.record_findings([_finding()])
    store_findings.record_findings([_finding()])
    assert len(store_findings.list_findings()) == 2


def test_prune_respects_retention(findings_db, monkeypatch):
    monkeypatch.setattr(cfg, "ANOMALY_FINDINGS_RETENTION_DAYS", 30)
    old = (dt.datetime.now() - dt.timedelta(days=31)).isoformat(
        timespec="seconds"
    )
    store_findings.record_findings([_finding(key="old")], now_iso=old)
    store_findings.record_findings([_finding(key="fresh")])

    assert store_findings.prune_findings() == 1
    assert [r["key"] for r in store_findings.list_findings(days=365)] == ["fresh"]


def test_record_never_raises(findings_db, monkeypatch):
    """FR-6: 이력 기록 실패가 발행 경로로 전파되면 안 된다."""
    def boom():
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(store_findings, "_get_conn", boom)
    assert store_findings.record_findings([_finding()]) == 0
    assert store_findings.prune_findings() == 0


def test_list_returns_empty_on_storage_error(findings_db, monkeypatch):
    import sqlite3

    def boom():
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(store_findings, "_get_conn", boom)
    assert store_findings.list_findings() == []
