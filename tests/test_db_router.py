# tests/test_db_router.py
"""
DBRouter Unit Tests

Tests for database routing logic, DBTargets properties,
SQL building, and parameter construction.
All tests use mocks to avoid real DB/filesystem dependencies.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from shared.database import DBTargets, DBRouter


# ==========================================================
# DBTargets Dataclass Tests
# ==========================================================
class TestDBTargets:
    """DBTargets frozen dataclass 속성 검증"""

    def test_both_dbs(self):
        t = DBTargets(use_archive=True, use_live=True)
        assert t.need_union is True
        assert t.archive_only is False
        assert t.live_only is False

    def test_archive_only(self):
        t = DBTargets(use_archive=True, use_live=False)
        assert t.need_union is False
        assert t.archive_only is True
        assert t.live_only is False

    def test_live_only(self):
        t = DBTargets(use_archive=False, use_live=True)
        assert t.need_union is False
        assert t.archive_only is False
        assert t.live_only is True

    def test_neither_db(self):
        """Edge case: 둘 다 False"""
        t = DBTargets(use_archive=False, use_live=False)
        assert t.need_union is False
        assert t.archive_only is False
        assert t.live_only is False

    def test_frozen_immutable(self):
        """frozen=True 확인: 속성 변경 불가"""
        t = DBTargets(use_archive=True, use_live=True)
        with pytest.raises(AttributeError):
            t.use_archive = False


# ==========================================================
# pick_targets Tests (ARCHIVE_CUTOFF_DATE = "2026-01-01")
# ==========================================================
class TestPickTargets:
    """날짜 범위에 따른 DB 라우팅 결정 테스트"""

    def test_no_dates_returns_both(self):
        """None, None → 양쪽 모두 쿼리"""
        targets = DBRouter.pick_targets(None, None)
        assert targets.use_archive is True
        assert targets.use_live is True

    def test_archive_only_range(self):
        """2025년 범위만 → archive only"""
        targets = DBRouter.pick_targets("2025-11-01", "2025-12-01")
        assert targets.use_archive is True
        assert targets.use_live is False

    def test_live_only_range(self):
        """2026년 범위만 → live only"""
        targets = DBRouter.pick_targets("2026-01-01", "2026-02-01")
        assert targets.use_archive is False
        assert targets.use_live is True

    def test_boundary_crossing_range(self):
        """연도 경계를 넘는 범위 → 양쪽 모두"""
        targets = DBRouter.pick_targets("2025-12-15", "2026-01-15")
        assert targets.use_archive is True
        assert targets.use_live is True

    def test_date_from_none_date_to_in_archive(self):
        """date_from=None, date_to가 archive 범위 → archive only"""
        targets = DBRouter.pick_targets(None, "2025-06-01")
        assert targets.use_archive is True
        assert targets.use_live is False

    def test_date_from_none_date_to_in_live(self):
        """date_from=None, date_to가 live 범위 → 양쪽 모두"""
        targets = DBRouter.pick_targets(None, "2026-06-01")
        assert targets.use_archive is True
        assert targets.use_live is True

    def test_date_from_archive_date_to_none(self):
        """date_from=archive, date_to=None → 양쪽 모두"""
        targets = DBRouter.pick_targets("2025-06-01", None)
        assert targets.use_archive is True
        assert targets.use_live is True

    def test_date_from_live_date_to_none(self):
        """date_from=live, date_to=None → live only"""
        targets = DBRouter.pick_targets("2026-06-01", None)
        assert targets.use_archive is False
        assert targets.use_live is True

    def test_exact_cutoff_date(self):
        """date_from=cutoff → archive 불필요"""
        targets = DBRouter.pick_targets("2026-01-01", "2026-01-02")
        assert targets.use_archive is False
        assert targets.use_live is True

    def test_day_before_cutoff(self):
        """date_from=cutoff-1 → 양쪽 모두"""
        targets = DBRouter.pick_targets("2025-12-31", "2026-01-01")
        assert targets.use_archive is True
        assert targets.use_live is True

    def test_cutoff_as_date_to_exclusive(self):
        """date_to=cutoff(exclusive) → live 포함 (>= 비교)"""
        targets = DBRouter.pick_targets("2025-11-01", "2026-01-01")
        assert targets.use_archive is True
        assert targets.use_live is True

    def test_far_past_archive_only(self):
        """먼 과거 범위 → archive only"""
        targets = DBRouter.pick_targets("2020-01-01", "2024-12-31")
        assert targets.use_archive is True
        assert targets.use_live is False

    def test_far_future_live_only(self):
        """먼 미래 범위 → live only"""
        targets = DBRouter.pick_targets("2030-01-01", "2030-12-31")
        assert targets.use_archive is False
        assert targets.use_live is True


# ==========================================================
# build_union_sql Tests
# ==========================================================
class TestBuildUnionSql:
    """SQL 빌드 결과 검증"""

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_archive_only_sql(self, mock_archive):
        """Archive only → archive.production_records 참조"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=False)

        sql, doubled = DBRouter.build_union_sql(
            "id, item_code", "production_date >= ?", targets
        )
        assert "archive.production_records" in sql
        assert "'archive' AS source" in sql
        assert "UNION ALL" not in sql
        assert doubled is False

    def test_live_only_sql(self):
        """Live only → production_records 참조"""
        targets = DBTargets(use_archive=False, use_live=True)

        sql, doubled = DBRouter.build_union_sql(
            "id, item_code", "production_date >= ?", targets
        )
        assert "FROM production_records" in sql
        assert "'live' AS source" in sql
        assert "archive.production_records" not in sql
        assert doubled is False

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_both_dbs_union(self, mock_archive):
        """Both → UNION ALL 포함, params_doubled=True"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, doubled = DBRouter.build_union_sql(
            "id, item_code", "item_code = ?", targets
        )
        assert "UNION ALL" in sql
        assert "'archive' AS source" in sql
        assert "'live' AS source" in sql
        assert doubled is True

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_no_source_column(self, mock_archive):
        """include_source=False → source 컬럼 없음"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, _ = DBRouter.build_union_sql(
            "id, item_code", "1=1", targets, include_source=False
        )
        assert "AS source" not in sql

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_limit_clause(self, mock_archive):
        """limit 지정 시 LIMIT 절 포함"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, _ = DBRouter.build_union_sql(
            "id", "1=1", targets, limit=100
        )
        assert "LIMIT 100" in sql

    def test_no_targets_safe_fallback(self):
        """Both=False → WHERE 1=0 안전 쿼리"""
        targets = DBTargets(use_archive=False, use_live=False)

        sql, doubled = DBRouter.build_union_sql(
            "id", "1=1", targets
        )
        assert "1=0" in sql
        assert doubled is False

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_order_by_default(self, mock_archive):
        """기본 ORDER BY 포함"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, _ = DBRouter.build_union_sql(
            "id", "1=1", targets
        )
        assert "ORDER BY production_date DESC" in sql

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_custom_order_by(self, mock_archive):
        """커스텀 ORDER BY"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, _ = DBRouter.build_union_sql(
            "id", "1=1", targets, order_by="item_code ASC"
        )
        assert "ORDER BY item_code ASC" in sql

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_archive_not_exists_skipped(self, mock_archive):
        """Archive 파일이 없으면 archive 쿼리 생략"""
        mock_archive.exists.return_value = False
        targets = DBTargets(use_archive=True, use_live=True)

        sql, doubled = DBRouter.build_union_sql(
            "id", "1=1", targets
        )
        # Archive file doesn't exist → only live query
        assert "archive.production_records" not in sql
        assert doubled is False


# ==========================================================
# build_query_params Tests
# ==========================================================
class TestBuildQueryParams:
    """쿼리 파라미터 빌드 검증"""

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_archive_only_params(self, mock_archive):
        """Archive only → base_params + [cutoff]"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=False)
        base = ["item_A"]

        params = DBRouter.build_query_params(base, targets, cutoff="2026-01-01")
        assert params == ["item_A", "2026-01-01"]

    def test_live_only_params(self):
        """Live only → base_params + [cutoff]"""
        targets = DBTargets(use_archive=False, use_live=True)
        base = ["item_A"]

        params = DBRouter.build_query_params(base, targets, cutoff="2026-01-01")
        assert params == ["item_A", "2026-01-01"]

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_both_params_doubled(self, mock_archive):
        """Both → params doubled"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)
        base = ["item_A", "2025-12-01"]

        params = DBRouter.build_query_params(base, targets, cutoff="2026-01-01")
        assert params == [
            "item_A", "2025-12-01", "2026-01-01",  # archive part
            "item_A", "2025-12-01", "2026-01-01",  # live part
        ]

    def test_no_targets_empty(self):
        """Neither → empty params"""
        targets = DBTargets(use_archive=False, use_live=False)
        base = ["item_A"]

        params = DBRouter.build_query_params(base, targets, cutoff="2026-01-01")
        assert params == []

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_empty_base_params(self, mock_archive):
        """빈 base_params + both → cutoff만"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        params = DBRouter.build_query_params([], targets, cutoff="2026-01-01")
        assert params == ["2026-01-01", "2026-01-01"]

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_archive_file_not_exists(self, mock_archive):
        """Archive file 없으면 archive params 생략"""
        mock_archive.exists.return_value = False
        targets = DBTargets(use_archive=True, use_live=True)
        base = ["item_A"]

        params = DBRouter.build_query_params(base, targets, cutoff="2026-01-01")
        # Archive skipped due to file not existing
        assert params == ["item_A", "2026-01-01"]


# ==========================================================
# build_aggregation_sql Tests
# ==========================================================
class TestBuildAggregationSql:
    """집계 UNION SQL 빌드 검증"""

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_aggregation_both_dbs(self, mock_archive):
        """양쪽 DB 집계 → UNION ALL + outer GROUP BY"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, doubled = DBRouter.build_aggregation_sql(
            inner_select="item_code, SUM(quantity) as total",
            inner_where="production_date >= ?",
            outer_select="item_code, SUM(total) as total",
            outer_group_by="item_code",
            targets=targets,
            outer_order_by="total DESC",
        )
        assert "UNION ALL" in sql
        assert "GROUP BY item_code" in sql
        assert "ORDER BY total DESC" in sql
        assert doubled is True

    def test_aggregation_live_only(self):
        """Live only 집계"""
        targets = DBTargets(use_archive=False, use_live=True)

        sql, doubled = DBRouter.build_aggregation_sql(
            inner_select="item_code, COUNT(*) as cnt",
            inner_where="1=1",
            outer_select="item_code, SUM(cnt) as cnt",
            outer_group_by="item_code",
            targets=targets,
        )
        assert "UNION ALL" not in sql
        assert "production_records" in sql
        assert doubled is False

    @patch("shared.database.ARCHIVE_DB_FILE")
    def test_aggregation_with_limit(self, mock_archive):
        """LIMIT 포함 집계"""
        mock_archive.exists.return_value = True
        targets = DBTargets(use_archive=True, use_live=True)

        sql, _ = DBRouter.build_aggregation_sql(
            inner_select="item_code, SUM(quantity) as total",
            inner_where="1=1",
            outer_select="item_code, SUM(total) as total",
            outer_group_by="item_code",
            targets=targets,
            limit=50,
        )
        assert "LIMIT 50" in sql
