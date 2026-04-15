# tests/test_input_validation.py
"""
Input Validation Unit Tests

Tests for date range validation and input length constraints.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from api.main import _validate_date_range, _validate_length


class TestValidateDateRange:
    """date_from <= date_to 검증 테스트"""

    def test_valid_range_equal(self):
        """같은 날짜는 유효"""
        # 예외 발생하지 않아야 함
        _validate_date_range("2026-01-15", "2026-01-15")

    def test_valid_range_from_before_to(self):
        """date_from < date_to는 유효"""
        _validate_date_range("2026-01-01", "2026-01-31")
        _validate_date_range("2025-12-01", "2026-01-31")
        _validate_date_range("2020-01-01", "2026-12-31")

    def test_invalid_range_from_after_to(self):
        """date_from > date_to는 무효"""
        with pytest.raises(HTTPException) as exc_info:
            _validate_date_range("2026-01-31", "2026-01-01")

        assert exc_info.value.status_code == 400
        assert "Invalid date range" in exc_info.value.detail
        assert "cannot be after" in exc_info.value.detail

    def test_none_values_pass(self):
        """None 값은 검증 스킵"""
        _validate_date_range(None, "2026-01-01")
        _validate_date_range("2026-01-01", None)
        _validate_date_range(None, None)

    def test_month_crossing_range(self):
        """월을 넘나드는 범위도 유효"""
        _validate_date_range("2026-01-25", "2026-02-05")
        _validate_date_range("2025-12-25", "2026-01-05")

    def test_year_crossing_range(self):
        """연도를 넘나드는 범위도 유효"""
        _validate_date_range("2025-12-01", "2026-01-31")
        _validate_date_range("2020-01-01", "2026-12-31")

    def test_error_message_contains_dates(self):
        """에러 메시지에 날짜 포함"""
        with pytest.raises(HTTPException) as exc_info:
            _validate_date_range("2026-06-01", "2026-05-01")

        detail = exc_info.value.detail
        assert "2026-06-01" in detail
        assert "2026-05-01" in detail


class TestValidateLength:
    """문자열 길이 제한 검증 테스트"""

    def test_valid_length_within_limit(self):
        """제한 내 길이는 통과"""
        result = _validate_length("hello", 10, "query")
        assert result == "hello"

    def test_valid_length_exact_limit(self):
        """정확히 제한 길이도 통과"""
        text = "a" * 100
        result = _validate_length(text, 100, "field")
        assert result == text

    def test_invalid_length_exceeds_limit(self):
        """제한 초과 시 에러"""
        text = "a" * 101
        with pytest.raises(HTTPException) as exc_info:
            _validate_length(text, 100, "query")

        assert exc_info.value.status_code == 400
        assert "exceeds maximum length" in exc_info.value.detail
        assert "100" in exc_info.value.detail
        assert "101" in exc_info.value.detail

    def test_none_value_passes(self):
        """None 값은 검증 스킵"""
        result = _validate_length(None, 100, "field")
        assert result is None

    def test_empty_string_passes(self):
        """빈 문자열도 통과"""
        result = _validate_length("", 100, "field")
        assert result == ""

    def test_unicode_string(self):
        """유니코드 문자열도 길이 검증"""
        korean_text = "한글테스트"  # 5 characters
        result = _validate_length(korean_text, 10, "query")
        assert result == korean_text

        # 초과 시 에러
        long_korean = "한글" * 100  # 200 characters
        with pytest.raises(HTTPException) as exc_info:
            _validate_length(long_korean, 100, "query")

        assert exc_info.value.status_code == 400

    def test_field_name_in_error(self):
        """필드명이 에러 메시지에 포함"""
        with pytest.raises(HTTPException) as exc_info:
            _validate_length("x" * 200, 100, "item_code")

        assert "item_code" in exc_info.value.detail


class TestInputConstraintsIntegration:
    """입력 제약 조건 통합 테스트 (FastAPI Query 파라미터)"""

    def test_session_id_max_length_in_chat_request(self):
        """ChatRequest session_id 최대 100자"""
        from api.chat import ChatRequest

        # 유효한 길이
        req = ChatRequest(query="test", session_id="a" * 100)
        assert len(req.session_id) == 100

        # 초과 시 Pydantic 에러
        with pytest.raises(Exception):  # ValidationError
            ChatRequest(query="test", session_id="a" * 101)

    def test_query_max_length_in_chat_request(self):
        """ChatRequest query 최대 2000자"""
        from api.chat import ChatRequest

        # 유효한 길이
        req = ChatRequest(query="a" * 2000)
        assert len(req.query) == 2000

        # 초과 시 Pydantic 에러
        with pytest.raises(Exception):  # ValidationError
            ChatRequest(query="a" * 2001)

    def test_chat_query_empty_blocked(self):
        """ChatRequest query 빈 문자열 거부 (min_length=1)"""
        from api.chat import ChatRequest

        with pytest.raises(Exception):  # ValidationError
            ChatRequest(query="")


class TestDateRangeEdgeCases:
    """날짜 범위 엣지 케이스 테스트"""

    def test_leap_year_range(self):
        """윤년 2월 29일 포함 범위"""
        _validate_date_range("2024-02-28", "2024-02-29")
        _validate_date_range("2024-02-29", "2024-03-01")

    def test_century_boundary(self):
        """세기 경계 테스트"""
        _validate_date_range("1999-12-31", "2000-01-01")
        _validate_date_range("2099-12-31", "2100-01-01")

    def test_far_future_range(self):
        """먼 미래 범위도 유효"""
        _validate_date_range("2026-01-01", "3000-12-31")
