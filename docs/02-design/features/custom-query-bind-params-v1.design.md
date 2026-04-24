# custom-query-bind-params-v1 Design Document

> **Summary**: `execute_custom_query` 시그니처 확장 + 검증 + 바인딩 + spec/prompt 동기화 구현 설계
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-24
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: Positional `?` + `list[str]` vs Named `:name` + `dict`

| 옵션 | 장점 | 단점 | 결정 |
|------|------|------|------|
| A. Positional `?` + `list[str]` | SQLite native, 단순, Gemini schema 간단, backward compat 자연 | 순서 의존 → 긴 쿼리에서 가독성 ↓ | **✓** |
| B. Named `:name` + `dict[str, str]` | 가독성 ↑, 재사용 용이 | Gemini `dict` schema 복잡 (properties 명시 필요), backward compat 어려움 | ✗ |
| C. JSON string `params_json` | schema 단순 | AI가 JSON 작성 실수 가능, 파싱 추가 오버헤드 | ✗ |

**선택 근거**: A
- SQLite는 둘 다 native 지원하지만 `?`가 가장 단순하고 빈번한 사용 패턴.
- `list[str]`은 google-genai SDK가 자연스럽게 schema 생성 (Context7 확인).
- `params=None` 기본값으로 기존 호출 100% 호환.

### AD-2: 모든 값을 `str`로 받는 이유

- Gemini tool 파라미터 schema는 element type이 **단일** 이어야 이상적. `list[str | int | float]` union은 OpenAPI `anyOf`로 표현되지만 Gemini 지원이 inconsistent.
- SQLite는 **dynamic typing** — TEXT 값이 INTEGER 컬럼과 비교될 때 자동으로 NUMERIC cast 시도 (sqlite.org §4.2).
- `production_records` 컬럼 타입:
  - `item_code, item_name, lot_number, production_date`: TEXT — string 비교 OK
  - `good_quantity`: INTEGER — SQLite auto cast TEXT → INTEGER, 안전
- 타입 안전이 필요한 edge case(`good_quantity > ?`)는 system prompt에서 `CAST(? AS INTEGER)` 패턴 안내.

### AD-3: `params` 원소 타입 검증

```python
def _validate_params(params):
    if params is None:
        return ()  # empty tuple for SQLite
    if not isinstance(params, list):
        raise ValueError("params must be a list or None")
    for i, p in enumerate(params):
        if not isinstance(p, str):
            raise ValueError(
                f"params[{i}] must be a string (got {type(p).__name__}); "
                f"convert numbers to str client-side, SQLite auto-casts for comparison"
            )
    return tuple(params)
```

- `None` → `()` (기존 코드와 동일 동작)
- 원소는 **반드시 `str`**. int/float/None/dict/list 거부 — 명시적, 예측 가능한 동작.
- 빈 리스트 `[]`는 허용 (no-op binding).

### AD-4: System prompt 가이드 전략

`_build_system_instruction()`의 [데이터 조회 규칙] rule 9 갱신:

```
9. 복잡한 조건(로트번호 패턴, 다중 필터 등)이 필요하면 `execute_custom_query`로 직접 SQL을 작성해.
   사용 가능한 컬럼: production_date, item_code, item_name, good_quantity, lot_number
   **중요 — 파라미터 바인딩 (SQL 인젝션 방지)**:
   - 사용자 입력값(제품코드, 날짜, 수량 임계값 등)은 SQL 본문에 직접 박지 말고
     `?` placeholder + `params` 배열로 분리해서 전달해.
     예: sql="SELECT item_code, SUM(good_quantity) as total FROM production_records
             WHERE item_code = ? AND production_date >= ? GROUP BY item_code",
         params=["BW0021", "2026-01-01"]
   - `params`의 모든 값은 문자열로 전달. 숫자 비교도 "1000"처럼 문자열로 보내면
     SQLite가 자동으로 타입 변환해.
   - 컬럼명, 테이블명, ORDER BY 방향(ASC/DESC) 같은 **SQL 식별자는 placeholder로 쓸 수 없으니**
     SQL 본문에 직접 써.
   - LIMIT 수치는 literal로 써도 되고 (예: `LIMIT 100`), params로 전달해도 돼.
```

### AD-5: Backward compat 경로

- `params=None` (기본값) → 기존 코드와 동일 `conn.execute(sql_clean)` 호출
- `params=[]` → 명시적 빈 list, 동일 결과
- 기존 테스트(`test_sql_validation.py`) 전혀 수정 불필요

---

## 2. File-Level Changes

### 2.1 `api/tools.py`

```python
def execute_custom_query(
    sql: str,
    params: list[str] = None,
    description: str = ""
) -> Dict[str, Any]:
    """
    Execute a custom SQL query for flexible data analysis.

    Use this tool when other tools cannot handle complex filtering conditions
    (e.g., lot_number patterns, multiple conditions, custom aggregations).

    IMPORTANT RULES:
    - Only SELECT queries are allowed (database is read-only)
    - Only 'production_records' table is available (use 'archive.production_records' for pre-2026)
    - Available columns: production_date, item_code, item_name, good_quantity, lot_number
    - Always include LIMIT clause (max 1000 rows)
    - **Use ? placeholders + params for any values (SQL injection safe)**

    Args:
        sql: The SELECT SQL query. Use ? for each parameter, e.g. "... WHERE item_code = ?".
        params: List of string values bound to ? placeholders in order. Optional (default: None).
            All values must be strings; SQLite dynamically casts for numeric comparisons.
            Example: params=["BW0021", "2026-01-01", "1000"].
        description: Brief description of what this query does (for logging only).

    Returns:
        Dict with query results or error message.

    Example queries:
        - sql="SELECT SUM(good_quantity) as total FROM production_records WHERE item_code = ? AND production_date >= ?"
          params=["BW0021", "2026-01-20"]
        - sql="SELECT lot_number, SUM(good_quantity) as qty FROM production_records WHERE item_code = ? GROUP BY lot_number ORDER BY qty DESC LIMIT 10"
          params=["ABC001"]
    """
    # ... existing validation (comments strip, semicolon, SELECT-only, forbidden keywords, production_records check, LIMIT auto-add) ...

    # NEW: params validation
    try:
        bound_params = _validate_params(params)
    except ValueError as e:
        return {
            "status": "error",
            "code": "INVALID_PARAMS",
            "message": str(e),
        }

    # ... existing connection setup, ATTACH, threading ...

    def run_query(connection):
        try:
            cursor = connection.execute(sql_clean, bound_params)  # CHANGED: pass bound_params
            # ... rest same ...
```

helper `_validate_params` 모듈 레벨 정의:

```python
def _validate_params(params) -> tuple:
    """Validate execute_custom_query params: None or list[str]. Returns tuple for bind."""
    if params is None:
        return ()
    if not isinstance(params, list):
        raise ValueError(
            f"params must be a list or None (got {type(params).__name__})"
        )
    for i, p in enumerate(params):
        if not isinstance(p, str):
            raise ValueError(
                f"params[{i}] must be a string (got {type(p).__name__}); "
                f"convert numbers to str — SQLite auto-casts for comparison"
            )
    return tuple(params)
```

### 2.2 `api/chat.py:_build_system_instruction()`

Rule 9 전면 갱신 (AD-4 내용).

### 2.3 `docs/specs/ai_architecture.md §4.7`

`execute_custom_query` 섹션 갱신:
- 다층 보안 검증 목록 유지
- **Parameter binding** 새 subsection 추가 (`?` placeholder + `params` list[str])
- 예시 2개 추가

### 2.4 `docs/specs/api_guide.md §6 execute_custom_query`

외부 사용자용 문서 — Args 표에 `params` 추가, 예시를 `?` placeholder 형태로 업데이트.

### 2.5 `tests/test_sql_validation.py`

기존 클래스 `TestExecuteCustomQueryValidation` 유지. 신규 클래스 `TestCustomQueryParams` 추가:

```python
class TestCustomQueryParams:
    """params bind parameter 검증"""

    def test_params_none_backward_compat(self):
        """params 미지정 시 기존 동작 유지 (검증만 통과, DB 실행은 환경 의존)."""
        # 검증 에러 없이 통과 → DB 실행 단계로 진입
        result = execute_custom_query(
            "SELECT COUNT(*) FROM production_records LIMIT 1"
        )
        assert result.get("code") != "INVALID_PARAMS"

    def test_params_empty_list_ok(self):
        result = execute_custom_query(
            "SELECT COUNT(*) FROM production_records LIMIT 1",
            params=[],
        )
        assert result.get("code") != "INVALID_PARAMS"

    def test_params_dict_rejected(self):
        result = execute_custom_query(
            "SELECT * FROM production_records WHERE item_code = ? LIMIT 1",
            params={"item": "BW0021"},  # type: ignore
        )
        assert result["status"] == "error"
        assert result["code"] == "INVALID_PARAMS"
        assert "list" in result["message"].lower()

    def test_params_tuple_rejected(self):
        result = execute_custom_query(
            "SELECT * FROM production_records WHERE item_code = ? LIMIT 1",
            params=("BW0021",),  # type: ignore
        )
        assert result["status"] == "error"
        assert result["code"] == "INVALID_PARAMS"

    def test_params_non_string_element_rejected(self):
        result = execute_custom_query(
            "SELECT * FROM production_records WHERE good_quantity > ? LIMIT 1",
            params=[1000],  # type: ignore — should be "1000"
        )
        assert result["status"] == "error"
        assert result["code"] == "INVALID_PARAMS"
        assert "string" in result["message"].lower()

    def test_params_none_element_rejected(self):
        result = execute_custom_query(
            "SELECT * FROM production_records WHERE item_code = ? LIMIT 1",
            params=[None],  # type: ignore
        )
        assert result["status"] == "error"
        assert result["code"] == "INVALID_PARAMS"

    def test_params_valid_strings_accepted(self):
        """Valid list[str] passes validation (DB execution may error in test env, but not INVALID_PARAMS)."""
        result = execute_custom_query(
            "SELECT item_code FROM production_records WHERE item_code = ? LIMIT 1",
            params=["BW0021"],
        )
        assert result.get("code") != "INVALID_PARAMS"
```

---

## 3. Test Plan

| Test | 명령 | 기대 |
|------|------|------|
| 신규 params 테스트 | `pytest tests/test_sql_validation.py::TestCustomQueryParams -v` | 7 passed |
| 기존 검증 테스트 (backward compat) | `pytest tests/test_sql_validation.py::TestExecuteCustomQueryValidation -v` | 전부 passed |
| 전체 회귀 | `pytest tests/ -q` | 기존 163 + 신규 7 = 170 passed 목표 |
| docstring schema 검증 | `python -c "from api.tools import execute_custom_query; help(execute_custom_query)"` | params 설명 포함 |
| 시스템 프롬프트 렌더 | `python -c "from api.chat import _build_system_instruction; print('?' in _build_system_instruction() and 'params' in _build_system_instruction())"` | True |

---

## 4. Rollback

| Commit | Revert 영향 |
|--------|-----------|
| Plan/Design | 기능 영향 없음 |
| B1+B2+B3 (도구 구현) | 시그니처 원복. backward compat 때문에 기존 호출은 무영향 |
| B4 (system prompt) | AI 가이드만 원복. 동작은 동일 (AI가 literal 방식 fallback) |
| B5+B6 (docs) | 문서만 원복 |
| B7 (tests) | 신규 테스트 제거 |

각 layer 독립적 — 부분 revert 가능.

---

## 5. Open Questions

- (해결됨) schema 호환성 → Context7 확인: `list[str]`은 Gemini native 지원.
- (해결됨) 타입 안전 → SQLite dynamic cast + system prompt `CAST(? AS INTEGER)` 가이드.
- (해결됨) backward compat → `params=None` 기본값으로 완전 호환.
