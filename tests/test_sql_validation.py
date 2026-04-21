import pytest

from api.tools import _strip_sql_comments, execute_custom_query


class TestStripSqlComments:
    """_strip_sql_comments 함수 테스트"""

    def test_block_comment_removed(self):
        result = _strip_sql_comments("/* comment */ SELECT 1")
        assert "/*" not in result
        assert result.startswith("SELECT")

    def test_line_comment_removed(self):
        result = _strip_sql_comments("SELECT 1 -- this is comment")
        assert "--" not in result
        assert "SELECT 1" in result

    def test_multiline_block_comment(self):
        sql = "/* line1\nline2\nline3 */ SELECT 1"
        result = _strip_sql_comments(sql)
        assert result.startswith("SELECT")

    def test_no_comments_unchanged(self):
        sql = "SELECT * FROM production_records"
        result = _strip_sql_comments(sql)
        assert result == sql


class TestExecuteCustomQueryValidation:
    """execute_custom_query 검증 로직 테스트 (DB 미사용)"""

    def test_semicolon_blocked(self):
        result = execute_custom_query("SELECT 1 FROM production_records; DROP TABLE x")
        assert result["status"] == "error"
        assert "semicolon" in result["message"].lower()

    def test_semicolon_in_comment_ok(self):
        # 주석 안의 세미콜론은 제거되므로 세미콜론 차단 안 됨
        # SELECT ... FROM production_records 형태이므로 검증은 통과
        result = execute_custom_query("SELECT /* ; */ 1 FROM production_records LIMIT 1")
        # DB가 없으므로 실행 에러가 날 수 있지만, "semicolon" 에러는 아님
        assert "semicolon" not in result.get("message", "").lower()

    def test_non_select_blocked(self):
        result = execute_custom_query("DELETE FROM production_records")
        assert result["status"] == "error"
        assert "SELECT" in result["message"]

    def test_comment_bypass_select_blocked(self):
        result = execute_custom_query("/* */ DELETE FROM production_records")
        assert result["status"] == "error"
        # 주석 제거 후 DELETE로 시작 → SELECT only 에러
        assert "SELECT" in result["message"] or "DELETE" in result["message"]

    def test_forbidden_pragma(self):
        result = execute_custom_query("SELECT PRAGMA table_info FROM production_records")
        assert result["status"] == "error"
        assert "PRAGMA" in result["message"]

    def test_forbidden_attach(self):
        result = execute_custom_query("SELECT ATTACH FROM production_records")
        assert result["status"] == "error"
        assert "ATTACH" in result["message"]

    def test_forbidden_drop_with_comment(self):
        result = execute_custom_query("SELECT 1 FROM production_records -- \nDROP TABLE x")
        assert result["status"] == "error"
        # 주석 제거 후 세미콜론 or DROP 차단
        assert result["status"] == "error"

    def test_table_reference_required(self):
        result = execute_custom_query("SELECT 1 FROM users")
        assert result["status"] == "error"
        assert "production_records" in result["message"]

    def test_valid_query_passes_validation(self):
        # 검증은 통과하지만 DB 없으므로 실행 에러 발생 가능
        result = execute_custom_query("SELECT * FROM production_records LIMIT 10")
        # 검증 통과 → status는 error(DB 없음) 또는 success(DB 있으면)
        # 중요: "Only SELECT", "semicolon", "Forbidden", "production_records" 에러가 아님
        if result["status"] == "error":
            msg = result["message"].lower()
            assert "only select" not in msg
            assert "semicolon" not in msg
            assert "forbidden" not in msg
            assert "must reference" not in msg

    def test_auto_limit_appended(self):
        # LIMIT이 없는 쿼리 → LIMIT 1000 자동 추가 검증
        # DB 없이는 직접 확인 불가하므로 _strip 후 검증 로직만 테스트
        result = execute_custom_query("SELECT * FROM production_records")
        # 검증 자체는 통과해야 함 (LIMIT 없어도 자동 추가)
        if result["status"] == "error":
            msg = result["message"].lower()
            assert "limit" not in msg

    def test_forbidden_keywords_list(self):
        """13개 금지 키워드 전체 테스트"""
        forbidden = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
            "TRUNCATE", "CREATE", "REPLACE", "PRAGMA",
            "ATTACH", "DETACH", "VACUUM", "REINDEX",
        ]
        for word in forbidden:
            sql = f"SELECT {word} FROM production_records"
            result = execute_custom_query(sql)
            assert result["status"] == "error", f"{word} should be blocked"
            assert word in result["message"], f"{word} not in error message"

    def test_forbidden_delete_standalone(self):
        """DELETE 단독 사용 차단 (non-SELECT)"""
        result = execute_custom_query("DELETE FROM production_records WHERE 1=1")
        assert result["status"] == "error"

    def test_word_boundary_no_false_positive(self):
        """Column names containing forbidden substrings should not be blocked.

        e.g. LAST_UPDATED contains UPDATE, CREATED_AT contains CREATE.
        """
        # These should pass validation (may fail at DB level if DB is absent)
        for sql in [
            "SELECT last_updated FROM production_records LIMIT 1",
            "SELECT created_at FROM production_records LIMIT 1",
            "SELECT replaced_by FROM production_records LIMIT 1",
        ]:
            result = execute_custom_query(sql)
            if result["status"] == "error":
                assert "forbidden" not in result["message"].lower(), (
                    f"False positive on: {sql}"
                )
