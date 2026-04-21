# tests/test_cache.py
"""
Cache Module Unit Tests

Tests for mtime-based cache invalidation, api_cache decorator,
and cache utility functions.
"""

import pytest
from unittest.mock import patch, MagicMock


# ==========================================================
# get_db_version Tests
# ==========================================================
class TestGetDbVersion:
    """DB mtime 기반 버전 문자열 검증"""

    @patch("shared.cache.ARCHIVE_DB_FILE")
    @patch("shared.cache.DB_FILE")
    @patch("shared.cache.os.path.getmtime")
    def test_normal_version_string(self, mock_getmtime, mock_db, mock_archive):
        """정상: mtime 조합 문자열 반환"""
        mock_db.exists.return_value = True
        mock_archive.exists.return_value = True
        mock_getmtime.side_effect = lambda p: {
            mock_db: 1700000000.123,
            mock_archive: 1700000500.456,
        }[p]

        from shared.cache import get_db_version
        version = get_db_version()
        assert version == "1700000000_1700000500"

    @patch("shared.cache.ARCHIVE_DB_FILE")
    @patch("shared.cache.DB_FILE")
    def test_no_files_returns_zeros(self, mock_db, mock_archive):
        """파일 없으면 '0_0' 반환"""
        mock_db.exists.return_value = False
        mock_archive.exists.return_value = False

        from shared.cache import get_db_version
        version = get_db_version()
        assert version == "0_0"

    @patch("shared.cache.ARCHIVE_DB_FILE")
    @patch("shared.cache.DB_FILE")
    @patch("shared.cache.os.path.getmtime")
    def test_only_live_exists(self, mock_getmtime, mock_db, mock_archive):
        """Live만 존재 시 archive mtime=0"""
        mock_db.exists.return_value = True
        mock_archive.exists.return_value = False
        mock_getmtime.return_value = 1700000000.0

        from shared.cache import get_db_version
        version = get_db_version()
        assert "_0" in version

    @patch("shared.cache.ARCHIVE_DB_FILE")
    @patch("shared.cache.DB_FILE")
    @patch("shared.cache.os.path.getmtime", side_effect=OSError("disk error"))
    def test_error_returns_fallback(self, mock_getmtime, mock_db, mock_archive):
        """예외 발생 시 '0_0' 반환"""
        mock_db.exists.return_value = True
        mock_archive.exists.return_value = True

        from shared.cache import get_db_version
        version = get_db_version()
        assert version == "0_0"


# ==========================================================
# _make_cache_key Tests
# ==========================================================
class TestMakeCacheKey:
    """캐시 키 생성 검증"""

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_same_args_same_key(self, mock_ver):
        """같은 인자 → 같은 키"""
        from shared.cache import _make_cache_key
        key1 = _make_cache_key("items", "q1", limit=10)
        key2 = _make_cache_key("items", "q1", limit=10)
        assert key1 == key2

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_different_args_different_key(self, mock_ver):
        """다른 인자 → 다른 키"""
        from shared.cache import _make_cache_key
        key1 = _make_cache_key("items", "q1")
        key2 = _make_cache_key("items", "q2")
        assert key1 != key2

    def test_different_db_version_different_key(self):
        """DB mtime 변경 → 다른 키 (자동 무효화)"""
        from shared.cache import _make_cache_key

        with patch("shared.cache.get_db_version", return_value="100_200"):
            key1 = _make_cache_key("items", "q1")

        with patch("shared.cache.get_db_version", return_value="100_300"):
            key2 = _make_cache_key("items", "q1")

        assert key1 != key2

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_different_prefix_different_key(self, mock_ver):
        """다른 prefix → 다른 키"""
        from shared.cache import _make_cache_key
        key1 = _make_cache_key("items", "q1")
        key2 = _make_cache_key("records", "q1")
        assert key1 != key2


# ==========================================================
# api_cache Decorator Tests
# ==========================================================
class TestApiCacheDecorator:
    """api_cache 데코레이터 기능 검증"""

    def setup_method(self):
        """각 테스트 전 캐시 초기화"""
        from shared.cache import clear_api_cache
        clear_api_cache()

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_cache_hit_avoids_recomputation(self, mock_ver):
        """같은 인자 재호출 시 함수 1번만 실행"""
        from shared.cache import api_cache

        call_count = 0

        @api_cache("test_endpoint")
        def expensive_query(q: str):
            nonlocal call_count
            call_count += 1
            return {"data": q, "count": call_count}

        result1 = expensive_query("hello")
        result2 = expensive_query("hello")

        assert result1 == result2
        assert call_count == 1  # 함수는 1번만 실행됨

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_cache_miss_different_args(self, mock_ver):
        """다른 인자 → 캐시 미스 → 재실행"""
        from shared.cache import api_cache

        call_count = 0

        @api_cache("test_endpoint")
        def query(q: str):
            nonlocal call_count
            call_count += 1
            return q

        query("a")
        query("b")

        assert call_count == 2

    def test_cache_invalidation_on_mtime_change(self):
        """DB mtime 변경 시 캐시 무효화"""
        from shared.cache import api_cache

        call_count = 0

        @api_cache("test_endpoint")
        def query():
            nonlocal call_count
            call_count += 1
            return call_count

        with patch("shared.cache.get_db_version", return_value="100_200"):
            r1 = query()

        with patch("shared.cache.get_db_version", return_value="100_300"):
            r2 = query()

        assert call_count == 2  # mtime 변경으로 재실행
        assert r1 == 1
        assert r2 == 2

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_kwargs_cache_key(self, mock_ver):
        """kwargs도 캐시 키에 포함"""
        from shared.cache import api_cache

        call_count = 0

        @api_cache("test_endpoint")
        def query(limit=10):
            nonlocal call_count
            call_count += 1
            return limit

        query(limit=10)
        query(limit=10)
        query(limit=20)

        assert call_count == 2  # limit=10은 캐시 히트, limit=20은 미스

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_preserves_function_name(self, mock_ver):
        """@wraps로 원본 함수 이름 보존"""
        from shared.cache import api_cache

        @api_cache("test")
        def my_function():
            return 42

        assert my_function.__name__ == "my_function"


# ==========================================================
# Cache Utility Tests
# ==========================================================
class TestCacheUtilities:
    """캐시 유틸리티 함수 검증"""

    def setup_method(self):
        from shared.cache import clear_api_cache
        clear_api_cache()

    def test_clear_api_cache(self):
        """clear_api_cache 후 캐시 비어있음"""
        from shared.cache import _api_cache, clear_api_cache
        _api_cache["test_key"] = "test_value"
        assert len(_api_cache) > 0

        clear_api_cache()
        assert len(_api_cache) == 0

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_get_cache_stats_format(self, mock_ver):
        """get_cache_stats 반환 형식 검증"""
        from shared.cache import get_cache_stats

        stats = get_cache_stats()
        assert "size" in stats
        assert "maxsize" in stats
        assert "ttl" in stats
        assert "db_version" in stats
        assert isinstance(stats["size"], int)
        assert stats["maxsize"] == 200
        assert stats["ttl"] == 300
        assert stats["db_version"] == "100_200"

    @patch("shared.cache.get_db_version", return_value="100_200")
    def test_cache_stats_size_increases(self, mock_ver):
        """캐시 항목 추가 후 size 증가"""
        from shared.cache import api_cache, get_cache_stats, clear_api_cache

        clear_api_cache()
        assert get_cache_stats()["size"] == 0

        @api_cache("stats_test")
        def query(x):
            return x

        query(1)
        query(2)
        assert get_cache_stats()["size"] == 2
