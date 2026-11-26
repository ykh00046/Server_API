"""Archive + live combined path around the 2026-01-01 cutoff (test-gap 공백 5, 7).

Uses conftest `live_and_archive_db` (temp live + temp archive, ATTACH whitelist
pointed at the temp archive) and adds boundary rows to both temp files:
same-date ties, the same ids in both DBs, and rows stored on the wrong side of
the cutoff (which the UNION parts must filter out).

- /records cursor pagination must return every row exactly once, in the
  documented order, for any page size.
- /summary/monthly_by_item must compute the next-month bound correctly for
  December and aggregate only the requested month.
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import app
from shared.database import DBRouter

# Rows added on top of the conftest seed.
#   conftest live seed: ids 1-6, 2026-03-01 .. 2026-05-25
#   conftest archive seed: ids 1-2, 2025-06-01 / 2025-07-01
_ARCHIVE_EXTRA = [
    ("2025-12-01", "AA0001", "그린 렌즈", 5, "LT2025C"),     # id 3
    ("2025-12-31", "BW0021", "블루 렌즈", 10, "LT2025D"),    # id 4
    ("2025-12-31", "BW0021", "블루 렌즈", 11, "LT2025E"),    # id 5 (same-date tie)
    ("2026-01-15", "BW0021", "블루 렌즈", 999, "LT2026X"),   # id 6: wrong side, must be dropped
]
_LIVE_EXTRA = [
    ("2026-01-01", "BW0021", "블루 렌즈", 20, "LT2026G"),    # id 7 (cutoff day)
    ("2026-01-01", "AA0001", "그린 렌즈", 21, "LT2026H"),    # id 8 (same-date tie)
    ("2026-12-31", "BW0021", "블루 렌즈", 30, "LT2026I"),    # id 9
    ("2027-01-01", "BW0021", "블루 렌즈", 40, "LT2027A"),    # id 10
    ("2025-12-31", "ZZ0000", "오적재", 777, "LT2025X"),      # id 11: wrong side, must be dropped
]

# (production_date, source, id) of every row the combined query should see.
_EXPECTED_KEYS = sorted(
    [
        ("2025-06-01", "archive", 1), ("2025-07-01", "archive", 2),
        ("2025-12-01", "archive", 3), ("2025-12-31", "archive", 4),
        ("2025-12-31", "archive", 5),
        ("2026-03-01", "live", 1), ("2026-03-15", "live", 2), ("2026-04-10", "live", 3),
        ("2026-04-20", "live", 4), ("2026-05-05", "live", 5), ("2026-05-25", "live", 6),
        ("2026-01-01", "live", 7), ("2026-01-01", "live", 8),
        ("2026-12-31", "live", 9), ("2027-01-01", "live", 10),
    ],
    reverse=True,  # production_date DESC, source DESC, id DESC
)


def _insert(path, rows) -> None:
    conn = sqlite3.connect(str(path))
    conn.executemany(
        "INSERT INTO production_records "
        "(production_date, item_code, item_name, good_quantity, lot_number) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


@pytest.fixture
def boundary_db(live_and_archive_db):
    live_path, archive_path = live_and_archive_db
    _insert(archive_path, _ARCHIVE_EXTRA)
    _insert(live_path, _LIVE_EXTRA)
    return live_path, archive_path


def _collect_pages(client, limit: int, **params) -> list[tuple[str, str, int]]:
    keys: list[tuple[str, str, int]] = []
    cursor = None
    for _ in range(100):  # hard stop against an endless cursor loop
        query = {"limit": limit, **params}
        if cursor:
            query["cursor"] = cursor
        r = client.get("/records", params=query)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == len(body["data"]) <= limit
        keys.extend((row["production_date"], row["source"], row["id"]) for row in body["data"])
        if not body["has_more"]:
            assert body["next_cursor"] is None
            return keys
        cursor = body["next_cursor"]
        assert cursor
    pytest.fail("cursor pagination did not terminate")


# ==========================================================
# 공백 5: /records cursor pagination over archive + live
# ==========================================================
class TestRecordsCursorAcrossArchiveAndLive:
    def test_single_page_sees_both_sources_without_wrong_side_rows(self, boundary_db):
        c = TestClient(app)
        r = c.get("/records", params={"limit": 5000})
        assert r.status_code == 200
        body = r.json()
        keys = [(row["production_date"], row["source"], row["id"]) for row in body["data"]]
        assert keys == _EXPECTED_KEYS
        assert body["has_more"] is False
        item_codes = {row["item_code"] for row in body["data"]}
        assert "ZZ0000" not in item_codes  # live row dated before cutoff
        assert 999 not in {row["good_quantity"] for row in body["data"]}  # archive row after cutoff

    @pytest.mark.parametrize("limit", [1, 2, 3, 4, 7, 14, 15])
    def test_cursor_pages_return_every_row_once_in_order(self, boundary_db, limit):
        c = TestClient(app)
        keys = _collect_pages(c, limit)
        assert len(keys) == len(set(keys))  # no duplicates
        assert keys == _EXPECTED_KEYS       # no gaps, documented order

    def test_cursor_pages_across_cutoff_with_date_range(self, boundary_db):
        c = TestClient(app)
        keys = _collect_pages(c, 1, date_from="2025-12-01", date_to="2026-01-31")
        assert keys == [
            ("2026-01-01", "live", 8),
            ("2026-01-01", "live", 7),
            ("2025-12-31", "archive", 5),
            ("2025-12-31", "archive", 4),
            ("2025-12-01", "archive", 3),
        ]

    def test_same_id_in_both_dbs_is_kept_apart_by_source(self, boundary_db):
        c = TestClient(app)
        keys = _collect_pages(c, 2)
        ids_with_both_sources = {
            i for i in range(1, 6)
            if (any(k[1:] == ("archive", i) for k in keys)
                and any(k[1:] == ("live", i) for k in keys))
        }
        assert ids_with_both_sources == {1, 2, 3, 4, 5}

    def test_archive_only_range_pages(self, boundary_db):
        c = TestClient(app)
        keys = _collect_pages(c, 2, date_from="2025-01-01", date_to="2025-12-31")
        assert keys == [k for k in _EXPECTED_KEYS if k[1] == "archive"]


# ==========================================================
# 공백 7: /summary/monthly_by_item December -> January
# ==========================================================
def _by_key(rows) -> dict[tuple[str, str], int]:
    return {(r["year_month"], r["item_code"]): r["total_production"] for r in rows}


class TestMonthlyByItemYearBoundary:
    @pytest.mark.parametrize(
        ("year_month", "expected_bounds"),
        [
            ("2025-12", ("2025-12-01", "2026-01-01")),
            ("2026-12", ("2026-12-01", "2027-01-01")),
            ("2026-11", ("2026-11-01", "2026-12-01")),
            ("2026-01", ("2026-01-01", "2026-02-01")),
        ],
    )
    def test_next_month_bound_passed_to_router(
        self, boundary_db, monkeypatch, year_month, expected_bounds
    ):
        original = DBRouter.pick_targets
        seen = []

        def spy(date_from, date_to=None):
            seen.append((date_from, date_to))
            return original(date_from, date_to)

        monkeypatch.setattr(DBRouter, "pick_targets", staticmethod(spy))
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item", params={"year_month": year_month})
        assert r.status_code == 200
        assert seen == [expected_bounds]

    def test_december_2025_aggregates_archive_month_only(self, boundary_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item", params={"year_month": "2025-12"})
        assert r.status_code == 200
        # 10 + 11 on 2025-12-31, 5 on 2025-12-01; the live row dated 2025-12-31
        # (wrong side of the cutoff) is not counted.
        assert _by_key(r.json()) == {("2025-12", "BW0021"): 21, ("2025-12", "AA0001"): 5}

    def test_january_2026_aggregates_live_month_only(self, boundary_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item", params={"year_month": "2026-01"})
        assert r.status_code == 200
        # the archive row dated 2026-01-15 (wrong side) is not counted
        assert _by_key(r.json()) == {("2026-01", "AA0001"): 21, ("2026-01", "BW0021"): 20}

    def test_december_2026_excludes_next_january(self, boundary_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item", params={"year_month": "2026-12"})
        assert r.status_code == 200
        assert _by_key(r.json()) == {("2026-12", "BW0021"): 30}

    def test_no_month_filter_keeps_months_separate_across_cutoff(self, boundary_db):
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item")
        assert r.status_code == 200
        got = _by_key(r.json())
        assert got[("2025-12", "BW0021")] == 21
        assert got[("2026-01", "BW0021")] == 20
        assert got[("2027-01", "BW0021")] == 40
        assert ("2025-12", "ZZ0000") not in got
        assert got.get(("2026-01", "BW0021")) != 20 + 999

    @pytest.mark.parametrize("year_month", ["2026-13", "2026-00"])
    def test_out_of_range_month_is_not_a_server_error(self, boundary_db, year_month):
        """The pattern ^\\d{4}-\\d{2}$ lets these through. Current code parses them
        without raising (map(int) succeeds) and returns no rows; a future 400 would
        also be acceptable. A 500 is not."""
        c = TestClient(app)
        r = c.get("/summary/monthly_by_item", params={"year_month": year_month})
        assert r.status_code != 500
        if r.status_code == 200:
            assert r.json() == []
