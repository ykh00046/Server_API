# tests/test_routers_db.py
"""Router integration tests against the seeded live DB (conftest `live_db`).

Covers api/routers/summary.py, records.py, and the DB/metrics paths of
system.py via the FastAPI TestClient. Archive is absent -> live-only routing.
"""

from fastapi.testclient import TestClient

from api.main import app
from api.routers import system as system_router
from api.routers.records import RecordsFilters, _build_records_filters


# ==========================================================
# /summary/* endpoints
# ==========================================================
class TestSummaryRouter:
    def test_monthly_total(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_total", params={"date_from": "2026-03-01", "date_to": "2026-05-31"})
        assert r.status_code == 200
        rows = {row["year_month"]: row for row in r.json()}
        assert rows["2026-03"]["total_production"] == 300
        assert rows["2026-05"]["total_production"] == 550  # 150 + 400

    def test_monthly_total_no_filter(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_total")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_monthly_total_bad_date(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_total", params={"date_from": "nope"})
        assert r.status_code == 400

    def test_by_item(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/by_item", params={"date_from": "2026-03-01", "date_to": "2026-05-31"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 3
        # Ordered by total_production DESC -> BW0021 (600) first
        assert body["data"][0]["item_code"] == "BW0021"

    def test_by_item_filtered(self, live_db):
        c = TestClient(app)
        r = c.get(
            "/summary/by_item",
            params={"date_from": "2026-03-01", "date_to": "2026-05-31", "item_code": "AA0001"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["data"][0]["total_production"] == 200

    def test_by_item_bad_date(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/by_item", params={"date_from": "x", "date_to": "2026-05-31"})
        assert r.status_code == 400

    def test_monthly_by_item_with_month(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item", params={"year_month": "2026-04"})
        assert r.status_code == 200
        rows = r.json()
        codes = {row["item_code"] for row in rows}
        assert codes == {"BW0021", "AA0001"}

    def test_monthly_by_item_no_filter(self, live_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ==========================================================
# /records and /items
# ==========================================================
class TestRecordsRouter:
    def test_records_all(self, live_db):
        c = TestClient(app)
        r = c.get("/records")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 6
        assert body["has_more"] is False

    def test_records_item_filter(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"item_code": "BW0021"})
        assert r.status_code == 200
        assert r.json()["count"] == 3

    def test_records_search_q(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"q": "그린"})
        assert r.status_code == 200
        assert r.json()["count"] == 2  # AA0001 x2

    def test_records_lot_prefix(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"lot_number": "LT2026A"})
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_records_quantity_range(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"min_quantity": 150, "max_quantity": 300})
        assert r.status_code == 200
        # 200, 300, 150 -> 3 rows
        assert r.json()["count"] == 3

    def test_records_date_range(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"date_from": "2026-03-01", "date_to": "2026-03-31"})
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_records_pagination_cursor(self, live_db):
        c = TestClient(app)
        r1 = c.get("/records", params={"limit": 2})
        body1 = r1.json()
        assert body1["count"] == 2
        assert body1["has_more"] is True
        assert body1["next_cursor"]
        # Follow the cursor
        r2 = c.get("/records", params={"limit": 2, "cursor": body1["next_cursor"]})
        assert r2.status_code == 200
        assert r2.json()["count"] == 2

    def test_records_offset_deprecated(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"limit": 2, "offset": 2})
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_records_invalid_cursor_ignored(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"cursor": "!!!not-base64!!!"})
        assert r.status_code == 200
        # Invalid cursor decodes to None -> behaves like no cursor
        assert r.json()["count"] == 6

    def test_records_bad_date(self, live_db):
        c = TestClient(app)
        r = c.get("/records", params={"date_from": "not-a-date"})
        assert r.status_code == 400

    def test_record_by_item_code(self, live_db):
        c = TestClient(app)
        r = c.get("/records/BW0021")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_items_list(self, live_db):
        c = TestClient(app)
        r = c.get("/items")
        assert r.status_code == 200
        rows = r.json()
        assert {row["item_code"] for row in rows} == {"BW0021", "AA0001", "CC0003"}

    def test_items_search(self, live_db):
        c = TestClient(app)
        r = c.get("/items", params={"q": "BW"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["record_count"] == 3


# ==========================================================
# _build_records_filters: WHERE/params builder (pure, no DB)
# c901-complexity-refactor-v1 — clause/param order must be preserved
# ==========================================================
class TestBuildRecordsFilters:
    def test_empty_filters_no_where(self):
        where, params = _build_records_filters(RecordsFilters(), None, None, None)
        assert where == []
        assert params == []

    def test_item_code(self):
        where, params = _build_records_filters(
            RecordsFilters(item_code="BW0021"), None, None, None
        )
        assert where == ["item_code = ?"]
        assert params == ["BW0021"]

    def test_search_q_expands_to_three_params(self):
        where, params = _build_records_filters(RecordsFilters(q="green"), None, None, None)
        assert len(where) == 1
        assert "LIKE" in where[0]
        assert len(params) == 3  # item_code / item_name / lot_number

    def test_quantity_range(self):
        where, params = _build_records_filters(
            RecordsFilters(min_quantity=100, max_quantity=500), None, None, None
        )
        assert where == ["good_quantity >= ?", "good_quantity <= ?"]
        assert params == [100, 500]

    def test_dates_use_normalized_values_not_raw(self):
        # The builder consumes the normalized dates passed by the route,
        # not the raw model fields.
        where, params = _build_records_filters(
            RecordsFilters(date_from="2026-03-01"), "2026-03-01", "2026-04-02", None
        )
        assert "production_date >= ?" in where
        assert "production_date < ?" in where
        assert "2026-03-01" in params
        assert "2026-04-02" in params

    def test_cursor_clause_six_params(self):
        cursor_data = {"d": "2026-05-01", "src": "live", "id": 42}
        where, params = _build_records_filters(RecordsFilters(), None, None, cursor_data)
        assert len(where) == 1
        assert params == ["2026-05-01", "2026-05-01", "live", "2026-05-01", "live", 42]

    def test_combined_order_preserved(self):
        f = RecordsFilters(item_code="BW0021", min_quantity=10)
        where, params = _build_records_filters(f, "2026-01-01", None, None)
        assert where == ["item_code = ?", "production_date >= ?", "good_quantity >= ?"]
        assert params == ["BW0021", "2026-01-01", 10]


# ==========================================================
# system.py: metrics + health DB paths
# ==========================================================
class TestSystemRouter:
    def test_metrics_performance(self, live_db):
        c = TestClient(app)
        r = c.get("/metrics/performance")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_metrics_cache(self, live_db):
        c = TestClient(app)
        r = c.get("/metrics/cache")
        assert r.status_code == 200
        body = r.json()
        assert "api_cache" in body
        assert "performance" in body

    def test_healthz_db_connected(self, live_db):
        c = TestClient(app)
        r = c.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["database"] == "connected"
        assert "db_size_mb" in body
        # Archive absent in the fixture
        assert body["archive_db"] == "not_found"
        # disk fallback now runs on Windows too (statvfs/shutil branch fix)
        assert "disk_free_gb" in body
        assert body["disk_free_gb"] > 0
        assert body["cache"]["size"] == 0

    def test_healthz_ai_no_key(self, live_db, monkeypatch):
        # Force the no-API-key branch deterministically (no network ping).
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr(
            system_router,
            "_ai_health_cache",
            {"status": "unknown", "last_check": 0, "message": "Not checked yet"},
        )
        c = TestClient(app)
        r1 = c.get("/healthz/ai")
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["status"] == "error"
        assert b1["cached"] is False
        # Second call should now hit the cached branch
        r2 = c.get("/healthz/ai")
        assert r2.status_code == 200
        assert r2.json()["cached"] is True

    def _fresh_cache(self, monkeypatch):
        monkeypatch.setattr(
            system_router,
            "_ai_health_cache",
            {"status": "unknown", "last_check": 0, "message": "Not checked yet"},
        )
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def test_healthz_ai_ok_ping(self, live_db, monkeypatch):
        # Mock the genai client so the success ping path runs (no network).
        from google import genai

        self._fresh_cache(monkeypatch)

        class _Models:
            def list(self):
                return iter([object(), object(), object()])

        class _Client:
            models = _Models()

        monkeypatch.setattr(genai, "Client", lambda api_key: _Client())
        c = TestClient(app)
        r = c.get("/healthz/ai")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "3 models" in body["message"]

    def test_healthz_ai_generic_error(self, live_db, monkeypatch):
        # models.list() raising a non-genai error hits the broad except branch.
        from google import genai

        self._fresh_cache(monkeypatch)

        class _Models:
            def list(self):
                raise RuntimeError("boom")

        class _Client:
            models = _Models()

        monkeypatch.setattr(genai, "Client", lambda api_key: _Client())
        c = TestClient(app)
        r = c.get("/healthz/ai")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert "boom" in body["message"]
