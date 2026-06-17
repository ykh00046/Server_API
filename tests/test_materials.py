"""Tests for the material-requests intake API (materials-api-v1).

Covers the store (upsert by doc_number, preserve received_at, batch dedupe,
query) and the HTTP router (POST /materials/backup, GET /materials).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import shared.config as cfg
from api.main import app
from api.materials import automation, runs, store
from api.materials.schemas import MaterialRow


@pytest.fixture
def materials_db(tmp_path, monkeypatch):
    """Point the materials store at a fresh tmp DB for each test."""
    db_path = tmp_path / "materials.db"
    monkeypatch.setattr(cfg, "MATERIALS_DB_FILE", db_path)
    store.reset_for_tests()
    yield db_path
    store.reset_for_tests()


@pytest.fixture
def client(materials_db):
    return TestClient(app)


def _row(doc_number="20260617P001", **kw):
    base = {
        "doc_number": doc_number,
        "seq": 1,
        "material_code": "M-100",
        "material_name": "테스트 자재",
        "request_qty_g": 500,
        "reason": "보충",
        "request_dept": "생산1팀",
        "drafter": "홍길동",
        "processed_at": "2026-06-17 10:00:00",
    }
    base.update(kw)
    return base


# ==========================================================
# store: upsert
# ==========================================================
class TestStoreUpsert:
    def test_insert_new_rows(self, materials_db):
        rows = [MaterialRow(**_row("DOC-001")), MaterialRow(**_row("DOC-002"))]
        res = store.upsert_materials(rows)
        assert (res.upserted, res.inserted, res.updated) == (2, 2, 0)
        assert store.count_materials() == 2

    def test_update_existing_keeps_received_at(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("DOC-001", reason="초안"))])
        first = store.get_material("DOC-001")
        # Re-post same doc with a changed field -> update in place.
        res = store.upsert_materials([MaterialRow(**_row("DOC-001", reason="수정됨"))])
        assert (res.upserted, res.inserted, res.updated) == (1, 0, 1)
        again = store.get_material("DOC-001")
        assert again.reason == "수정됨"
        assert again.received_at == first.received_at  # preserved on update
        assert store.count_materials() == 1  # no duplicate row

    def test_mixed_insert_and_update(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("DOC-001"))])
        res = store.upsert_materials([
            MaterialRow(**_row("DOC-001")),  # update
            MaterialRow(**_row("DOC-002")),  # insert
            MaterialRow(**_row("DOC-003")),  # insert
        ])
        assert (res.upserted, res.inserted, res.updated) == (3, 2, 1)

    def test_intra_batch_dedupe_last_wins(self, materials_db):
        res = store.upsert_materials([
            MaterialRow(**_row("DOC-001", reason="first")),
            MaterialRow(**_row("DOC-001", reason="second")),
        ])
        # Deduped to a single doc -> one insert, last write wins.
        assert (res.upserted, res.inserted, res.updated) == (1, 1, 0)
        assert store.get_material("DOC-001").reason == "second"

    def test_qty_coerced_to_string(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("DOC-001", request_qty_g=500))])
        assert store.get_material("DOC-001").request_qty_g == "500"


# ==========================================================
# store: query
# ==========================================================
class TestStoreQuery:
    def test_get_missing_returns_none(self, materials_db):
        assert store.get_material("NOPE") is None

    def test_list_filters_by_dept(self, materials_db):
        store.upsert_materials([
            MaterialRow(**_row("DOC-001", request_dept="생산1팀")),
            MaterialRow(**_row("DOC-002", request_dept="생산2팀")),
        ])
        rows = store.list_materials(request_dept="생산2팀")
        assert [r.doc_number for r in rows] == ["DOC-002"]

    def test_list_orders_by_doc_date_desc(self, materials_db):
        # Ordering is by 문서번호 날짜(doc_date), NOT processed_at. Here the
        # older doc was scraped later, but doc_date wins.
        store.upsert_materials([
            MaterialRow(**_row("20251101P001", processed_at="2026-06-17 09:00:00")),
            MaterialRow(**_row("20251227P002", processed_at="2026-06-01 09:00:00")),
        ])
        rows = store.list_materials()
        assert [r.doc_number for r in rows] == ["20251227P002", "20251101P001"]


# ==========================================================
# doc_date (문서번호 날짜 기준)
# ==========================================================
class TestDocDate:
    def test_derives_from_doc_number(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("20251127P001"))])
        assert store.get_material("20251127P001").doc_date == "2025-11-27"

    def test_none_when_prefix_not_a_date(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("DOC-XYZ"))])
        assert store.get_material("DOC-XYZ").doc_date is None

    def test_none_when_invalid_calendar_date(self, materials_db):
        # 20251345 → month 13 / day 45 invalid → None (no crash)
        store.upsert_materials([MaterialRow(**_row("20251345P001"))])
        assert store.get_material("20251345P001").doc_date is None

    def test_date_range_filter(self, materials_db):
        store.upsert_materials([
            MaterialRow(**_row("20251101P001")),
            MaterialRow(**_row("20251215P002")),
            MaterialRow(**_row("20260105P003")),
        ])
        rows = store.list_materials(date_from="2025-12-01", date_to="2025-12-31")
        assert [r.doc_number for r in rows] == ["20251215P002"]

    def test_doc_date_updates_on_reupsert(self, materials_db):
        # If a doc_number is corrected, doc_date follows it.
        store.upsert_materials([MaterialRow(**_row("20251101P001"))])
        store.upsert_materials([MaterialRow(**_row("20251101P001"))])
        assert store.get_material("20251101P001").doc_date == "2025-11-01"


# ==========================================================
# HTTP router
# ==========================================================
class TestRouter:
    def test_backup_endpoint(self, client):
        r = client.post("/materials/backup", json={"rows": [_row("DOC-001"), _row("DOC-002")]})
        assert r.status_code == 200
        assert r.json() == {"upserted": 2, "inserted": 2, "updated": 0}

    def test_backup_is_idempotent(self, client):
        payload = {"rows": [_row("DOC-001")]}
        client.post("/materials/backup", json=payload)
        r2 = client.post("/materials/backup", json=payload)
        assert r2.json() == {"upserted": 1, "inserted": 0, "updated": 1}

    def test_backup_empty_rows_rejected(self, client):
        r = client.post("/materials/backup", json={"rows": []})
        assert r.status_code == 422  # min_length=1

    def test_backup_missing_doc_number_rejected(self, client):
        bad = _row("DOC-001")
        del bad["doc_number"]
        r = client.post("/materials/backup", json={"rows": [bad]})
        assert r.status_code == 422

    def test_get_list_and_filter(self, client):
        client.post("/materials/backup", json={"rows": [
            _row("DOC-001", request_dept="A팀"),
            _row("DOC-002", request_dept="B팀"),
        ]})
        r = client.get("/materials")
        assert r.status_code == 200
        assert len(r.json()) == 2
        r2 = client.get("/materials", params={"request_dept": "A팀"})
        assert [m["doc_number"] for m in r2.json()] == ["DOC-001"]

    def test_get_by_doc_number(self, client):
        client.post("/materials/backup", json={"rows": [_row("20251127P001")]})
        r = client.get("/materials/20251127P001")
        assert r.status_code == 200
        body = r.json()
        assert body["doc_number"] == "20251127P001"
        assert body["doc_date"] == "2025-11-27"   # 문서번호 날짜 기준
        assert "received_at" in body and "updated_at" in body

    def test_list_date_filter(self, client):
        client.post("/materials/backup", json={"rows": [
            _row("20251101P001"),
            _row("20251215P002"),
        ]})
        r = client.get("/materials", params={"date_from": "2025-12-01"})
        assert r.status_code == 200
        assert [m["doc_number"] for m in r.json()] == ["20251215P002"]

    def test_get_missing_returns_404(self, client):
        r = client.get("/materials/NOPE")
        assert r.status_code == 404


# ==========================================================
# Run history + manual automation trigger (materials-run-v1)
# ==========================================================
class _InlineThread:
    """Run the thread target inline (deterministic, no real background thread)."""

    def __init__(self, target, args=(), **kw):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


class TestRunsHistory:
    def test_backup_records_run(self, client):
        client.post("/materials/backup", json={"rows": [_row("DOC-1"), _row("DOC-2")]})
        r = client.get("/materials/runs")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        run = body[0]
        assert run["kind"] == "backup"
        assert run["status"] == "success"
        assert (run["rows"], run["inserted"], run["updated"]) == (2, 2, 0)

    def test_runs_kind_filter_and_get(self, materials_db):
        runs.record_backup_run(1, 1, 0)
        rid = runs.start_run("automation")
        runs.finish_run(rid, "success", exit_code=0, message="ok")
        autos = runs.list_runs(kind="automation")
        assert [r.kind for r in autos] == ["automation"]
        assert runs.get_run(rid).status == "success"
        assert runs.get_run(99999) is None


class TestTrigger:
    def test_disabled_by_default(self, client, monkeypatch):
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", False)
        r = client.post("/materials/run")
        assert r.status_code == 409
        assert "MATERIALS_RUN_ENABLED" in r.json()["detail"]

    def test_trigger_runs_and_records(self, client, monkeypatch, tmp_path):
        # Enable, point bot dir at a dummy (avoids submodule dependency), and
        # run the worker inline with a faked subprocess (exit 0).
        bot = tmp_path / "bot"
        bot.mkdir()
        (bot / "main.py").write_text("# dummy")
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        monkeypatch.setattr(cfg, "MATERIALS_BOT_DIR", bot)
        monkeypatch.setattr(automation.threading, "Thread", _InlineThread)
        monkeypatch.setattr(automation, "_run_subprocess",
                            lambda python, bot_dir: (0, "완료"))
        r = client.post("/materials/run")
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        got = client.get(f"/materials/runs/{run_id}")
        assert got.status_code == 200
        run = got.json()
        assert run["kind"] == "automation"
        assert run["status"] == "success"
        assert run["exit_code"] == 0

    def test_trigger_failure_recorded(self, client, monkeypatch, tmp_path):
        bot = tmp_path / "bot"
        bot.mkdir()
        (bot / "main.py").write_text("# dummy")
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        monkeypatch.setattr(cfg, "MATERIALS_BOT_DIR", bot)
        monkeypatch.setattr(automation.threading, "Thread", _InlineThread)
        monkeypatch.setattr(automation, "_run_subprocess",
                            lambda python, bot_dir: (1, "에러"))
        run_id = client.post("/materials/run").json()["run_id"]
        run = client.get(f"/materials/runs/{run_id}").json()
        assert run["status"] == "failed"
        assert run["exit_code"] == 1

    def test_concurrent_run_blocked(self, client, monkeypatch):
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        # A pre-existing 'running' automation blocks a new trigger.
        runs.start_run("automation")
        r = client.post("/materials/run")
        assert r.status_code == 409
        assert "이미 실행 중" in r.json()["detail"]

    def test_missing_bot_entrypoint(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        monkeypatch.setattr(cfg, "MATERIALS_BOT_DIR", tmp_path / "nope")
        r = client.post("/materials/run")
        assert r.status_code == 409
        assert "봇 진입점" in r.json()["detail"]
