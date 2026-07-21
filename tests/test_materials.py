"""Tests for the material-requests intake API (materials-api-v1).

Covers the store (upsert by doc_number, preserve received_at, batch dedupe,
query) and the HTTP router (POST /materials/backup, GET /materials).
"""
from __future__ import annotations

import datetime as dt

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
        store.upsert_materials([MaterialRow(**_row("DOC-001", reason="초안"))])
        res = store.upsert_materials([
            MaterialRow(**_row("DOC-001", reason="수정됨")),  # update (내용 변경)
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

    def test_identical_repost_is_noop(self, materials_db):
        # 봇이 전체 Excel을 재전송 — 동일 내용 행은 rewrite하지 않는다.
        rows = [MaterialRow(**_row("DOC-001", reason="초안"))]
        store.upsert_materials(rows)
        res = store.upsert_materials(rows)
        assert res.updated == 0           # 내용이 같으면 갱신하지 않는다
        assert res.inserted == 0
        assert res.upserted == 1

    def test_one_field_changed_updates_only_that_row(self, materials_db):
        # 한 품목만 한 필드를 바꿔 재전송 → updated==1, 바뀐 행의 updated_at만
        # 움직이고 건드리지 않은 행의 updated_at은 그대로 유지된다.
        rows = [
            MaterialRow(**_row("DOC-001", seq=1, reason="초안1")),
            MaterialRow(**_row("DOC-001", seq=2, reason="초안2")),
        ]
        store.upsert_materials(rows)
        before = {i.seq: i.updated_at for i in store.get_document("DOC-001")}
        # 1초 이상 경과 후 재전송 (timespec=seconds 이하로는 차이가 안 남).
        import time
        time.sleep(1.1)
        changed = [
            MaterialRow(**_row("DOC-001", seq=1, reason="초안1")),   # 동일 → no-op
            MaterialRow(**_row("DOC-001", seq=2, reason="수정2")),   # 변경 → 1행 갱신
        ]
        res = store.upsert_materials(changed)
        assert res.updated == 1
        after = {i.seq: i.updated_at for i in store.get_document("DOC-001")}
        assert after[1] == before[1]          # 건드리지 않은 행은 updated_at 유지
        assert after[2] != before[2]          # 바뀐 행만 updated_at 갱신


# ==========================================================
# 다품목 문서 (한 문서 = 여러 품목, (doc_number, seq) 복합키)
# 회귀: 과거 doc_number 단독 PK가 품목을 마지막 1개로 뭉개던 버그
# ==========================================================
class TestMultiItemDocument:
    def test_all_items_preserved(self, materials_db):
        # 한 문서에 품목 3개 (순번 1,2,3) — 전부 저장되어야 한다.
        rows = [
            MaterialRow(**_row("20260101P227-0001", seq=1, material_name="품목A")),
            MaterialRow(**_row("20260101P227-0001", seq=2, material_name="품목B")),
            MaterialRow(**_row("20260101P227-0001", seq=3, material_name="품목C")),
        ]
        res = store.upsert_materials(rows)
        assert (res.upserted, res.inserted, res.updated) == (3, 3, 0)
        items = store.get_document("20260101P227-0001")
        assert [i.seq for i in items] == [1, 2, 3]
        assert [i.material_name for i in items] == ["품목A", "품목B", "품목C"]
        assert store.count_materials() == 3

    def test_reupsert_updates_per_item_not_collapse(self, materials_db):
        base = [
            MaterialRow(**_row("D-1", seq=1, reason="초안1")),
            MaterialRow(**_row("D-1", seq=2, reason="초안2")),
        ]
        store.upsert_materials(base)
        # 같은 문서 재전송 (한 품목만 수정) → 행수 유지, 바뀐 품목만 1행 갱신.
        # 동일 내용 품목(seq=1)은 no-op이라 updated에 안 센다 (쓰기 최적화).
        again = [
            MaterialRow(**_row("D-1", seq=1, reason="초안1")),
            MaterialRow(**_row("D-1", seq=2, reason="수정2")),
        ]
        res = store.upsert_materials(again)
        assert (res.upserted, res.inserted, res.updated) == (2, 0, 1)
        items = store.get_document("D-1")
        assert [i.reason for i in items] == ["초안1", "수정2"]
        assert store.count_materials() == 2

    def test_missing_seq_normalized_to_zero(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("D-9", seq=None))])
        assert store.get_document("D-9")[0].seq == 0


class TestLegacyMigration:
    def test_legacy_single_pk_rebuilt_to_composite(self, materials_db):
        import sqlite3
        # 구 스키마(doc_number 단독 PK, keyword/doc_date 없음) 직접 생성 + 1행.
        conn = sqlite3.connect(str(materials_db))
        conn.executescript(
            """
            CREATE TABLE material_requests (
                doc_number TEXT PRIMARY KEY, seq INTEGER, material_code TEXT,
                material_name TEXT, request_qty_g TEXT, reason TEXT,
                request_dept TEXT, drafter TEXT, processed_at TEXT,
                received_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO material_requests VALUES
                ('OLD-1', 5, 'C', '기존품목', '10', 'r', 'D팀', 'drf', 'p', 'n', 'n');
            """
        )
        conn.commit()
        conn.close()
        store.reset_for_tests()  # 스키마 init 캐시 비우기 → 다음 호출 시 마이그레이션

        # 구 PK였다면 같은 doc_number 추가가 충돌했을 것 — 이제 품목별로 쌓인다.
        store.upsert_materials([
            MaterialRow(**_row("OLD-1", seq=1, material_name="새품목1")),
            MaterialRow(**_row("OLD-1", seq=2, material_name="새품목2")),
        ])
        items = store.get_document("OLD-1")
        assert sorted(i.seq for i in items) == [1, 2, 5]  # 기존 보존 + 신규 추가


# ==========================================================
# store: query
# ==========================================================
class TestStoreQuery:
    def test_get_missing_returns_none(self, materials_db):
        assert store.get_material("NOPE") is None


# ==========================================================
# store: delete (실수 기안·중복 문서 제거)
# ==========================================================
class TestStoreDelete:
    def test_delete_removes_all_items_of_document(self, materials_db):
        store.upsert_materials([
            MaterialRow(**_row("D-1", seq=1)),
            MaterialRow(**_row("D-1", seq=2)),
            MaterialRow(**_row("D-2", seq=1)),
        ])
        deleted = store.delete_document("D-1")
        assert deleted == 2                        # 두 품목 행 모두 삭제
        assert store.get_document("D-1") == []
        assert store.count_materials() == 1        # 다른 문서는 보존

    def test_delete_missing_returns_zero(self, materials_db):
        assert store.delete_document("NOPE") == 0  # 멱등

    def test_delete_is_dataset_scoped(self, materials_db):
        # 같은 doc_number라도 삭제는 지정 테이블에만 적용된다.
        store.upsert_materials([MaterialRow(**_row("D-1"))], table="material_requests")
        store.upsert_materials([MaterialRow(**_row("D-1"))], table="binder_requests")
        store.delete_document("D-1", table="material_requests")
        assert store.get_material("D-1", table="material_requests") is None
        assert store.get_material("D-1", table="binder_requests") is not None

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
# tombstone (삭제된 문서 묘비 — 봇 재전송으로 서버 삭제가 덮어씌워지지 않도록)
# ==========================================================
class TestTombstone:
    def test_delete_then_reupsert_filters_tombstoned_rows(self, materials_db):
        # 삭제 후 같은 문서 재전송 → skipped가 행 수와 같고 문서는 계속 없다.
        rows = [
            MaterialRow(**_row("20260706P001", seq=1)),
            MaterialRow(**_row("20260706P001", seq=2)),
            MaterialRow(**_row("20260706P001", seq=3)),
        ]
        store.upsert_materials(rows)
        assert store.delete_document("20260706P001") == 3
        # 봇이 같은 문서를 다시 전송해도 tombstone이 가로챈다.
        res = store.upsert_materials(rows)
        assert res.skipped == 3                       # 필터링된 행 수
        assert (res.upserted, res.inserted, res.updated) == (0, 0, 0)
        assert store.get_document("20260706P001") == []
        assert store.count_materials() == 0

    def test_restore_then_reupsert_brings_document_back(self, materials_db):
        rows = [MaterialRow(**_row("20260706P001", seq=1))]
        store.upsert_materials(rows)
        store.delete_document("20260706P001")
        # tombstone을 restore하면 다음 재전송이 다시 받아들여진다.
        assert store.restore_document("20260706P001") == 1
        res = store.upsert_materials(rows)
        assert res.skipped == 0
        assert res.inserted == 1
        assert store.get_material("20260706P001") is not None

    def test_tombstone_is_dataset_scoped(self, materials_db):
        # 한 데이터셋의 tombstone이 다른 데이터셋 upsert를 막지 않는다.
        rows = [MaterialRow(**_row("SHARED-1", seq=1))]
        store.upsert_materials(rows, table="material_requests")
        store.upsert_materials(rows, table="binder_requests")
        # materials 테이블에서만 삭제 → binder 테이블의 tombstone은 없음.
        store.delete_document("SHARED-1", table="material_requests")
        res = store.upsert_materials(rows, table="binder_requests")
        assert res.skipped == 0
        assert store.get_material("SHARED-1", table="binder_requests") is not None
        # 반대편(materials)은 여전히 차단.
        res_m = store.upsert_materials(rows, table="material_requests")
        assert res_m.skipped == 1

    def test_delete_missing_creates_no_tombstone(self, materials_db):
        # 존재하지 않는 문서 삭제는 0이며 tombstone도 남기지 않는다.
        assert store.delete_document("NOPE") == 0
        assert store.list_tombstones() == []

    def test_list_tombstones_present_after_delete_and_empty_after_restore(
        self, materials_db
    ):
        store.upsert_materials([MaterialRow(**_row("20260706P001", seq=1))])
        store.delete_document("20260706P001")
        tombs = store.list_tombstones()
        assert len(tombs) == 1
        assert tombs[0]["doc_number"] == "20260706P001"
        assert "deleted_at" in tombs[0] and tombs[0]["deleted_at"]
        # restore 후엔 비어야 한다.
        store.restore_document("20260706P001")
        assert store.list_tombstones() == []


# ==========================================================
# tombstone HTTP API (삭제된 문서 — 봇 재전송 차단 + 복원)
# ==========================================================
class TestTombstoneApi:
    def test_delete_then_backup_skipped_and_doc_absent(self, client):
        # 백업 후 API로 삭제 → 같은 rows 재전송 시 skipped가 발생하고 문서는 404.
        rows = [
            _row("20260721P001", seq=1),
            _row("20260721P001", seq=2),
        ]
        client.post("/materials/backup", json={"rows": rows})
        assert client.delete("/materials/20260721P001").status_code == 200

        r = client.post("/materials/backup", json={"rows": rows})
        assert r.status_code == 200
        body = r.json()
        assert body["skipped"] >= 1
        assert (body["upserted"], body["inserted"], body["updated"]) == (0, 0, 0)
        assert client.get("/materials/20260721P001").status_code == 404

    def test_tombstones_endpoint_lists_deleted_doc(self, client):
        client.post("/materials/backup", json={"rows": [_row("20260721P002")]})
        client.delete("/materials/20260721P002")
        r = client.get("/materials/tombstones")
        assert r.status_code == 200
        docs = [t["doc_number"] for t in r.json()]
        assert "20260721P002" in docs
        # deleted_at 키가 각 항목에 존재한다.
        assert all("deleted_at" in t for t in r.json())

    def test_restore_then_second_restore_404(self, client):
        client.post("/materials/backup", json={"rows": [_row("20260721P003")]})
        client.delete("/materials/20260721P003")
        r1 = client.post("/materials/20260721P003/restore")
        assert r1.status_code == 200
        assert r1.json() == {"doc_number": "20260721P003", "restored": 1}
        # tombstone이 이미 지워졌으므로 두 번째 restore는 404.
        r2 = client.post("/materials/20260721P003/restore")
        assert r2.status_code == 404
        assert "no tombstone for 20260721P003" in r2.json()["detail"]

    def test_after_restore_backup_brings_doc_back(self, client):
        rows = [_row("20260721P004")]
        client.post("/materials/backup", json={"rows": rows})
        client.delete("/materials/20260721P004")
        client.post("/materials/20260721P004/restore")
        # restore 후 백업 재전송 → 다시 들어온다.
        r = client.post("/materials/backup", json={"rows": rows})
        assert r.status_code == 200
        assert r.json()["skipped"] == 0
        assert client.get("/materials/20260721P004").status_code == 200

    def test_binder_tombstone_does_not_block_materials_backup(self, client):
        # binder에서 삭제한 tombstone은 materials 백업에 영향을 주지 않는다.
        rows = [_row("SHARED-DOC")]
        client.post("/materials/backup", json={"rows": rows})
        client.post("/binder/backup", json={"rows": [_row("SHARED-DOC")]})
        client.delete("/binder/SHARED-DOC")
        r = client.post("/materials/backup", json={"rows": rows})
        assert r.status_code == 200
        assert r.json()["skipped"] == 0
        assert client.get("/materials/SHARED-DOC").status_code == 200


# ==========================================================
# keyword (시간대별 멀티 프로필 크롤링 구분)
# ==========================================================
class TestKeyword:
    def test_keyword_roundtrip(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("DOC-001", keyword="비품"))])
        assert store.get_material("DOC-001").keyword == "비품"

    def test_keyword_defaults_none(self, materials_db):
        store.upsert_materials([MaterialRow(**_row("DOC-001"))])
        assert store.get_material("DOC-001").keyword is None

    def test_list_filters_by_keyword(self, materials_db):
        store.upsert_materials([
            MaterialRow(**_row("DOC-001", keyword="자재")),
            MaterialRow(**_row("DOC-002", keyword="비품")),
        ])
        rows = store.list_materials(keyword="비품")
        assert [r.doc_number for r in rows] == ["DOC-002"]


# ==========================================================
# 데이터셋 분리 (binder = 액상바인더출고, 별도 테이블/엔드포인트)
# ==========================================================
class TestBinderDataset:
    def test_binder_table_isolated_from_materials(self, materials_db):
        # 같은 doc_number라도 데이터셋이 다르면 서로 다른 테이블에 따로 저장.
        store.upsert_materials(
            [MaterialRow(**_row("DOC-1", reason="자재용"))], table="material_requests"
        )
        store.upsert_materials(
            [MaterialRow(**_row("DOC-1", reason="바인더용"))], table="binder_requests"
        )
        assert store.get_material("DOC-1", table="material_requests").reason == "자재용"
        assert store.get_material("DOC-1", table="binder_requests").reason == "바인더용"
        assert store.count_materials(table="material_requests") == 1
        assert store.count_materials(table="binder_requests") == 1

    def test_binder_backup_endpoint(self, client):
        r = client.post("/binder/backup", json={"rows": [_row("PB-1"), _row("PB-2")]})
        assert r.status_code == 200
        assert r.json()["upserted"] == 2
        # /binder 목록에는 보이고 /materials 목록에는 안 보인다.
        assert len(client.get("/binder").json()) == 2
        assert client.get("/materials").json() == []

    def test_binder_runs_isolated(self, client):
        client.post("/binder/backup", json={"rows": [_row("PB-1")]})
        assert len(client.get("/binder/runs").json()) == 1
        assert client.get("/materials/runs").json() == []


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
        assert r.json() == {"upserted": 2, "inserted": 2, "updated": 0, "skipped": 0}

    def test_backup_is_idempotent(self, client):
        payload = {"rows": [_row("DOC-001")]}
        client.post("/materials/backup", json=payload)
        r2 = client.post("/materials/backup", json=payload)
        # 동일 내용 재전송 → rewrite하지 않는다 (updated=0). upserted는 여전히 1.
        assert r2.json() == {"upserted": 1, "inserted": 0, "updated": 0, "skipped": 0}

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
        assert isinstance(body, list) and len(body) == 1   # 품목 행 리스트
        assert body[0]["doc_number"] == "20251127P001"
        assert body[0]["doc_date"] == "2025-11-27"   # 문서번호 날짜 기준
        assert "received_at" in body[0] and "updated_at" in body[0]

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

    def test_delete_document(self, client):
        client.post("/materials/backup", json={"rows": [
            _row("20260706P001", seq=1), _row("20260706P001", seq=2),
        ]})
        r = client.delete("/materials/20260706P001")
        assert r.status_code == 200
        assert r.json() == {"doc_number": "20260706P001", "deleted": 2}
        # 삭제 후 조회는 404.
        assert client.get("/materials/20260706P001").status_code == 404

    def test_delete_missing_returns_404(self, client):
        assert client.delete("/materials/NOPE").status_code == 404

    def test_delete_is_dataset_scoped(self, client):
        # /binder 삭제가 /materials 문서를 건드리지 않는다.
        client.post("/materials/backup", json={"rows": [_row("SHARED-1")]})
        client.post("/binder/backup", json={"rows": [_row("SHARED-1")]})
        assert client.delete("/binder/SHARED-1").status_code == 200
        assert client.get("/materials/SHARED-1").status_code == 200
        assert client.get("/binder/SHARED-1").status_code == 404


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
        # 일반 백업은 message가 None (tombstone skip이 없으면 비고 없음).
        assert run["message"] is None

    def test_backup_records_tombstone_skip_message(self, client):
        # tombstone으로 건너뛴 행이 있으면 run의 message에 'skipped='가 남는다.
        client.post("/materials/backup", json={"rows": [_row("DOC-X")]})
        client.delete("/materials/DOC-X")
        client.post("/materials/backup", json={"rows": [_row("DOC-X")]})
        r = client.get("/materials/runs")
        backup_runs = [r for r in r.json() if r["kind"] == "backup"]
        skip_run = next(r for r in backup_runs if r["message"])
        assert "skipped=" in skip_run["message"]
        assert skip_run["message"] is not None

    def test_runs_kind_filter_and_get(self, materials_db):
        runs.record_backup_run(1, 1, 0)
        rid = runs.start_run("automation")
        runs.finish_run(rid, "success", exit_code=0, message="ok")
        autos = runs.list_runs(kind="automation")
        assert [r.kind for r in autos] == ["automation"]
        assert runs.get_run(rid).status == "success"
        assert runs.get_run(99999) is None


class TestTrigger:
    def test_disabled_returns_503(self, client, monkeypatch):
        """기능 비활성은 '이미 실행 중'(409)이 아니라 503 (B-5)."""
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", False)
        r = client.post("/materials/run")
        assert r.status_code == 503
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
                            lambda python, bot_dir, keyword=None: (0, "완료"))
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
                            lambda python, bot_dir, keyword=None: (1, "에러"))
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

    def test_missing_bot_entrypoint_returns_500(self, client, monkeypatch, tmp_path):
        """설정 오류(봇 진입점 없음)는 500 (B-5)."""
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        monkeypatch.setattr(cfg, "MATERIALS_BOT_DIR", tmp_path / "nope")
        r = client.post("/materials/run")
        assert r.status_code == 500
        assert "봇 진입점" in r.json()["detail"]

    def test_stale_running_reaped_and_trigger_unblocked(
        self, client, monkeypatch, tmp_path
    ):
        """서버 강제 종료로 남은 오래된 'running' 행은 트리거를 영구 차단하지
        않는다 — 트리거 시 failed로 정리되고 새 실행이 시작된다."""
        bot = tmp_path / "bot"
        bot.mkdir()
        (bot / "main.py").write_text("# dummy")
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        monkeypatch.setattr(cfg, "MATERIALS_BOT_DIR", bot)
        monkeypatch.setattr(automation.threading, "Thread", _InlineThread)
        monkeypatch.setattr(automation, "_run_subprocess",
                            lambda python, bot_dir, keyword=None: (0, "완료"))
        # Orphan: a running row older than the stale window.
        stale_id = runs.start_run("automation")
        old = (
            dt.datetime.now()
            - dt.timedelta(seconds=runs.STALE_RUNNING_SEC + 60)
        ).isoformat(timespec="seconds")
        conn = store._get_conn()
        conn.execute(
            f"UPDATE {runs.DEFAULT_DATASET.runs_table} "
            "SET started_at = ? WHERE id = ?",
            (old, stale_id),
        )
        conn.commit()

        r = client.post("/materials/run")
        assert r.status_code == 200, r.text
        reaped = runs.get_run(stale_id)
        assert reaped.status == "failed"
        assert "stale" in (reaped.message or "")

    def test_list_rejects_bad_date_format(self, client):
        """records/summary와 동일 계약: 잘못된 날짜 형식은 400
        (기존엔 문자열 비교로 조용히 빈 결과가 됐다)."""
        r = client.get("/materials", params={"date_from": "2026-1-1"})
        assert r.status_code == 400
        assert "Invalid date format" in r.json()["detail"]

    def test_list_rejects_reversed_date_range(self, client):
        r = client.get(
            "/materials",
            params={"date_from": "2026-06-30", "date_to": "2026-06-01"},
        )
        assert r.status_code == 400

    def test_fresh_running_not_reaped(self, client, monkeypatch):
        """정상 진행 중(신선한 running)은 reap 대상이 아니어서 계속 409."""
        monkeypatch.setattr(cfg, "MATERIALS_RUN_ENABLED", True)
        rid = runs.start_run("automation")
        r = client.post("/materials/run")
        assert r.status_code == 409
        assert runs.get_run(rid).status == "running"
