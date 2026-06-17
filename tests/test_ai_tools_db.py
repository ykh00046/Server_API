# tests/test_ai_tools_db.py
"""DB-backed AI tool tests (api/tools/summary.py, api/tools/items.py).

Exercises the real DBRouter query path against a seeded temp production_records
DB (see the `live_db` fixture in conftest.py). 2026-only dates route live-only.
"""

from api.tools.items import get_item_history, search_production_items
from api.tools.summary import (
    compare_periods,
    get_monthly_trend,
    get_production_summary,
    get_top_items,
)


# ==========================================================
# get_production_summary
# ==========================================================
class TestGetProductionSummary:
    def test_single_item_period(self, live_db):
        r = get_production_summary("2026-03-01", "2026-04-30", "BW0021")
        assert r["status"] == "success"
        assert r["item_code"] == "BW0021"
        data = r["data"]
        assert data["total_quantity"] == 600  # 100 + 200 + 300
        assert data["production_count"] == 3
        assert data["average_quantity"] == 200.0

    def test_all_items_period(self, live_db):
        r = get_production_summary("2026-03-01", "2026-05-31")
        assert r["status"] == "success"
        assert r["item_code"] == "all"
        # 100+200+300+50+150+400 = 1200 over 6 records
        assert r["data"]["total_quantity"] == 1200
        assert r["data"]["production_count"] == 6

    def test_empty_period_returns_zero(self, live_db):
        r = get_production_summary("2026-01-01", "2026-01-31", "BW0021")
        assert r["status"] == "success"
        assert r["data"]["total_quantity"] == 0
        assert r["data"]["production_count"] == 0
        assert r["data"]["average_quantity"] == 0

    def test_invalid_date_returns_error(self, live_db):
        r = get_production_summary("not-a-date", "2026-03-31")
        assert r["status"] == "error"
        assert "message" in r


# ==========================================================
# get_monthly_trend
# ==========================================================
class TestGetMonthlyTrend:
    def test_trend_buckets_by_month(self, live_db):
        r = get_monthly_trend("2026-03-01", "2026-04-30", "BW0021")
        assert r["status"] == "success"
        trend = {t["year_month"]: t for t in r["trend"]}
        assert trend["2026-03"]["total_production"] == 300  # 100 + 200
        assert trend["2026-03"]["batch_count"] == 2
        assert trend["2026-04"]["total_production"] == 300
        assert trend["2026-04"]["batch_count"] == 1

    def test_trend_all_items(self, live_db):
        r = get_monthly_trend("2026-03-01", "2026-05-31")
        assert r["status"] == "success"
        assert r["item_code"] == "all"
        months = {t["year_month"] for t in r["trend"]}
        assert {"2026-03", "2026-04", "2026-05"} <= months

    def test_invalid_date_returns_error(self, live_db):
        r = get_monthly_trend("2026-03-31", "bad-date")
        assert r["status"] == "error"
        assert "message" in r


# ==========================================================
# get_top_items
# ==========================================================
class TestGetTopItems:
    def test_ranking_order(self, live_db):
        r = get_top_items("2026-03-01", "2026-05-31", limit=5)
        assert r["status"] == "success"
        codes = [it["item_code"] for it in r["top_items"]]
        # BW0021=600, CC0003=400, AA0001=200
        assert codes == ["BW0021", "CC0003", "AA0001"]
        assert r["top_items"][0]["total_production"] == 600

    def test_limit_caps_results(self, live_db):
        r = get_top_items("2026-03-01", "2026-05-31", limit=1)
        assert r["status"] == "success"
        assert len(r["top_items"]) == 1
        assert r["top_items"][0]["item_code"] == "BW0021"

    def test_invalid_date_returns_error(self, live_db):
        r = get_top_items("bad", "2026-05-31")
        assert r["status"] == "error"
        assert "message" in r


# ==========================================================
# compare_periods
# ==========================================================
class TestComparePeriods:
    def test_increase_direction(self, live_db):
        # P1 April (BW: 300, AA: 50 = 350) vs P2 March (BW: 300) = 300
        r = compare_periods(
            "2026-04-01", "2026-04-30",
            "2026-03-01", "2026-03-31",
        )
        assert r["status"] == "success"
        assert r["period1"]["total_quantity"] == 350
        assert r["period2"]["total_quantity"] == 300
        assert r["comparison"]["quantity_diff"] == 50
        assert r["comparison"]["direction"] == "증가"

    def test_decrease_with_item_filter(self, live_db):
        # BW0021 only: P1 March (300) vs P2 April (300) -> 동일
        r = compare_periods(
            "2026-03-01", "2026-03-31",
            "2026-04-01", "2026-04-30",
            item_code="BW0021",
        )
        assert r["status"] == "success"
        assert r["comparison"]["direction"] == "동일"
        assert r["comparison"]["quantity_diff"] == 0

    def test_zero_baseline_change_rate_none(self, live_db):
        # P2 has no data -> change_rate_pct None
        r = compare_periods(
            "2026-03-01", "2026-03-31",
            "2026-01-01", "2026-01-31",
        )
        assert r["status"] == "success"
        assert r["comparison"]["change_rate_pct"] is None
        assert r["comparison"]["direction"] == "증가"

    def test_invalid_date_returns_error(self, live_db):
        r = compare_periods("bad", "2026-03-31", "2026-04-01", "2026-04-30")
        assert r["status"] == "error"


# ==========================================================
# search_production_items
# ==========================================================
class TestSearchProductionItems:
    def test_search_by_name(self, live_db):
        r = search_production_items("블루", include_archive=False)
        assert r["status"] == "success"
        codes = [it["item_code"] for it in r["found_items"]]
        assert codes == ["BW0021"]

    def test_search_by_common_suffix(self, live_db):
        r = search_production_items("렌즈", include_archive=False)
        assert r["status"] == "success"
        codes = {it["item_code"] for it in r["found_items"]}
        assert codes == {"BW0021", "AA0001", "CC0003"}

    def test_search_by_code_fragment(self, live_db):
        r = search_production_items("BW", include_archive=False)
        assert r["status"] == "success"
        assert r["found_items"][0]["item_code"] == "BW0021"
        assert r["found_items"][0]["record_count"] == 3

    def test_no_match(self, live_db):
        r = search_production_items("존재하지않음", include_archive=False)
        assert r["status"] == "success"
        assert r["found_items"] == []
        assert "현재 제품만" in r["message"]

    def test_include_archive_message_when_archive_absent(self, live_db):
        # Archive file does not exist -> falls into live-only branch but the
        # message still reflects the requested include_archive flag.
        r = search_production_items("블루", include_archive=True)
        assert r["status"] == "success"
        assert r["found_items"][0]["item_code"] == "BW0021"


# ==========================================================
# get_item_history
# ==========================================================
class TestGetItemHistory:
    def test_history_newest_first(self, live_db):
        r = get_item_history("BW0021")
        assert r["status"] == "success"
        assert r["record_count"] == 3
        dates = [rec["production_date"] for rec in r["records"]]
        assert dates == ["2026-04-10", "2026-03-15", "2026-03-01"]

    def test_history_limit(self, live_db):
        r = get_item_history("BW0021", limit=1)
        assert r["status"] == "success"
        assert r["record_count"] == 1
        assert r["records"][0]["production_date"] == "2026-04-10"

    def test_history_limit_clamped(self, live_db):
        # limit > 50 clamps to 50 (still returns the 3 available)
        r = get_item_history("BW0021", limit=999)
        assert r["status"] == "success"
        assert r["record_count"] == 3

    def test_history_no_records(self, live_db):
        r = get_item_history("NONEXISTENT")
        assert r["status"] == "success"
        assert r["record_count"] == 0
        assert "생산 이력이 없습니다" in r["message"]


# ==========================================================
# Archive-present branches (ATTACH + UNION ALL)
# ==========================================================
class TestArchiveBranches:
    def test_search_includes_discontinued(self, live_and_archive_db):
        # ZZ9999 lives only in the archive; include_archive=True must find it.
        r = search_production_items("단종", include_archive=True)
        assert r["status"] == "success"
        codes = [it["item_code"] for it in r["found_items"]]
        assert "ZZ9999" in codes
        assert "단종 제품 포함" in r["message"]

    def test_search_merges_counts_across_dbs(self, live_and_archive_db):
        # BW0021: 3 live + 1 archive = 4 total records.
        r = search_production_items("BW0021", include_archive=True)
        bw = next(it for it in r["found_items"] if it["item_code"] == "BW0021")
        assert bw["record_count"] == 4

    def test_item_history_spans_archive(self, live_and_archive_db):
        # BW0021 history should include the 2025 archive record.
        r = get_item_history("BW0021", limit=50)
        assert r["status"] == "success"
        dates = [rec["production_date"] for rec in r["records"]]
        assert "2025-07-01" in dates
        assert r["record_count"] == 4
