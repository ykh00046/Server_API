# tests/test_weekly_bucket.py
"""Weekly aggregation bucket tests (F-02).

conftest's _SEED_ROWS use date-only strings ('2026-03-01'), which cannot
reproduce this bug: strftime() only returns NULL on the *real* stored format
('2026-01-13 오전 12:00:00', 22 chars). These tests carry that real format and
pin the SQL bucket expression against the pandas rule used by charts.py.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from dashboard.data import WEEK_BUCKET_EXPR, _parse_production_dt
from shared import database as db_mod
from shared.database import DBRouter, DBTargets

# (production_date, item_code, item_name, good_quantity, lot_number)
REAL_FORMAT_ROWS = [
    ("2026-01-05 오전 12:00:00", "BW0021", "블루 렌즈", 100, "L1"),  # Mon → 2026-W01
    ("2026-01-07 오후 03:30:00", "BW0021", "블루 렌즈", 200, "L2"),  # Wed → 2026-W01
    ("2026-01-13 오전 12:00:00", "AA0001", "그린 렌즈", 300, "L3"),  # Tue → 2026-W02
    ("2026-01-01 오전 12:00:00", "CC0003", "레드 렌즈", 50, "L4"),  # before 1st Mon → W00
]

MIXED_FORMAT_ROWS = [
    ("2026-01-05 오전 12:00:00", "BW0021", "블루 렌즈", 10, "M1"),  # Korean
    ("2026-01-06 PM 02:00:00", "BW0021", "블루 렌즈", 20, "M2"),  # English AM/PM
    ("2026-01-07 14:30:00", "BW0021", "블루 렌즈", 30, "M3"),  # 24h ISO
]


def _make_db(path, rows) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE production_records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, production_date TEXT, "
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


def _weekly_rows(db_path) -> list[dict]:
    """Run load_weekly_summary's SQL (live-only) against db_path."""
    targets = DBTargets(use_archive=False, use_live=True)
    sql, _ = DBRouter.build_aggregation_sql(
        inner_select=(
            f"{WEEK_BUCKET_EXPR} AS year_week, "
            "SUM(good_quantity) AS total_prod, COUNT(*) AS cnt"
        ),
        inner_where="1=1",
        outer_select=(
            "year_week, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count"
        ),
        outer_group_by="year_week",
        targets=targets,
        outer_order_by="year_week",
    )
    params = DBRouter.build_query_params([], targets)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _weekly_via_pandas(rows) -> dict[str, int]:
    """Bucket the same rows through charts.py's rule (parse → strftime %Y-W%W)."""
    df = pd.DataFrame(rows, columns=["production_date", "item_code", "item_name",
                                     "good_quantity", "lot_number"])
    df["production_dt"] = _parse_production_dt(df["production_date"])
    df["period"] = df["production_dt"].dt.strftime("%Y-W%W")
    grouped = df.groupby("period")["good_quantity"].sum()
    return {k: int(v) for k, v in grouped.items()}


@pytest.fixture
def real_format_db(tmp_path):
    path = tmp_path / "weekly_real.db"
    _make_db(path, REAL_FORMAT_ROWS)
    return path


def test_weekly_bucket_expr_on_real_format(real_format_db):
    """Real stored format buckets by week — before the fix every row fell in one
    NULL bucket because strftime() cannot parse '오전 12:00:00'."""
    rows = _weekly_rows(real_format_db)

    assert [r["year_week"] for r in rows] == ["2026-W00", "2026-W01", "2026-W02"]
    assert {r["year_week"]: r["total_production"] for r in rows} == {
        "2026-W00": 50,
        "2026-W01": 300,
        "2026-W02": 300,
    }
    assert {r["year_week"]: r["batch_count"] for r in rows} == {
        "2026-W00": 1,
        "2026-W01": 2,
        "2026-W02": 1,
    }


def test_weekly_sql_matches_pandas_buckets(real_format_db):
    """SQL weekly summary and the pandas chart path agree on bucket *and* total."""
    sql_totals = {
        r["year_week"]: r["total_production"] for r in _weekly_rows(real_format_db)
    }
    assert sql_totals == _weekly_via_pandas(REAL_FORMAT_ROWS)


def test_weekly_bucket_tolerates_mixed_formats(tmp_path):
    """Korean 오전/오후, English AM/PM and 24h rows in the same week group together."""
    path = tmp_path / "weekly_mixed.db"
    _make_db(path, MIXED_FORMAT_ROWS)

    rows = _weekly_rows(path)
    assert [r["year_week"] for r in rows] == ["2026-W01"]
    assert rows[0]["total_production"] == 60
    assert rows[0]["batch_count"] == 3


def test_weekly_bucket_splits_across_year_boundary(tmp_path, monkeypatch):
    """Archive (2025) + live (2026) rows bucket independently across the UNION.

    The boundary week splits at the year prefix — 2025-W52 and 2026-W00 stay
    apart. That is the pandas rule too, so both pages tell the same story.
    """
    archive_rows = [
        ("2025-12-29 오전 12:00:00", "BW0021", "블루 렌즈", 70, "A1"),  # Mon → 2025-W52
        ("2025-12-31 오후 01:00:00", "BW0021", "블루 렌즈", 30, "A2"),  # → 2025-W52
    ]
    live_rows = [
        ("2026-01-01 오전 12:00:00", "BW0021", "블루 렌즈", 40, "L1"),  # → 2026-W00
    ]
    live_path = tmp_path / "boundary_live.db"
    archive_path = tmp_path / "boundary_archive.db"
    _make_db(live_path, live_rows)
    _make_db(archive_path, archive_rows)

    # build_aggregation_sql only emits the archive leg when the file exists.
    monkeypatch.setattr(db_mod, "ARCHIVE_DB_FILE", archive_path)

    targets = DBTargets(use_archive=True, use_live=True)
    sql, _ = DBRouter.build_aggregation_sql(
        inner_select=(
            f"{WEEK_BUCKET_EXPR} AS year_week, "
            "SUM(good_quantity) AS total_prod, COUNT(*) AS cnt"
        ),
        inner_where="1=1",
        outer_select="year_week, SUM(total_prod) AS total_production",
        outer_group_by="year_week",
        targets=targets,
        outer_order_by="year_week",
    )
    params = DBRouter.build_query_params([], targets)

    conn = sqlite3.connect(str(live_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("ATTACH DATABASE ? AS archive", (str(archive_path),))
        sql_totals = {
            r["year_week"]: r["total_production"]
            for r in conn.execute(sql, params).fetchall()
        }
    finally:
        conn.close()

    assert sql_totals == {"2025-W52": 100, "2026-W00": 40}
    assert sql_totals == _weekly_via_pandas(archive_rows + live_rows)
