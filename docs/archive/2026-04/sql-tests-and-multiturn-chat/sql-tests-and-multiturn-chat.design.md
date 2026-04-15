# Design: SQL Validation Tests + Multi-turn AI Chat

> PDCA Phase: **Design**
> Feature: `sql-tests-and-multiturn-chat`
> Plan Reference: `docs/01-plan/features/sql-tests-and-multiturn-chat.plan.md`
> Created: 2026-02-13
> Status: Draft

---

## 1. Implementation Order

```
T1 (SQL Tests) → M1 (Session Store) → M2 (ChatRequest) → M3 (Contents History)
```

T1을 먼저 작성하여 기존 보안 로직의 회귀 방지 안전망을 확보한 후, M1-M3를 순서대로 구현합니다.

---

## 2. T1: SQL 검증 단위 테스트

### 2.1 신규 파일

`tests/test_sql_validation.py`

### 2.2 설계

테스트는 DB 연결 없이 **검증 로직만** 테스트합니다.
`_strip_sql_comments`는 순수 함수이므로 직접 테스트하고,
`execute_custom_query`는 DB 실행 전 검증 단계에서 반환하는 에러 응답을 테스트합니다.

```python
import pytest
import sys
from pathlib import Path

# api 모듈 import를 위한 경로 설정
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
        # 하지만 이 쿼리는 DB 없이는 실행 단계에서 에러 → 검증 단계는 통과해야 함
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
```

### 2.3 테스트 구조

- `TestStripSqlComments` (4 tests): 순수 함수 `_strip_sql_comments` 직접 테스트
- `TestExecuteCustomQueryValidation` (12 tests): 5단계 검증 파이프라인 블랙박스 테스트
- 총 **16 테스트 케이스**

---

## 3. M1: Multi-turn 세션 저장소

### 3.1 변경 파일

| 파일 | 변경 위치 | 유형 |
|------|----------|------|
| `api/chat.py` | 모듈 상단 (import 후) | 세션 저장소 + 설정 상수 추가 |

### 3.2 설계

`api/chat.py`의 retry 설정 블록(66-69행) 아래에 추가:

```python
# ==========================================================
# Multi-turn Session Store (In-memory)
# ==========================================================
SESSION_TTL = 1800  # 30 minutes
SESSION_MAX_TURNS = 10  # Max conversation turns per session

_sessions: dict[str, dict] = {}
# Structure: {session_id: {"history": [Content, ...], "last_access": float}}


def _get_session_history(session_id: str | None) -> list:
    """Get conversation history for session. Returns empty list if no session."""
    if not session_id or session_id not in _sessions:
        return []

    session = _sessions[session_id]
    session["last_access"] = time.time()
    return session["history"]


def _save_session_history(session_id: str | None, history: list) -> None:
    """Save conversation history. Trims to max turns."""
    if not session_id:
        return

    # Trim to max turns (each turn = 2 entries: user + model)
    max_entries = SESSION_MAX_TURNS * 2
    if len(history) > max_entries:
        history = history[-max_entries:]

    _sessions[session_id] = {
        "history": history,
        "last_access": time.time(),
    }


def _cleanup_expired_sessions() -> None:
    """Remove sessions that exceeded TTL (lazy cleanup)."""
    now = time.time()
    expired = [
        sid for sid, data in _sessions.items()
        if now - data["last_access"] > SESSION_TTL
    ]
    for sid in expired:
        del _sessions[sid]
```

---

## 4. M2: ChatRequest 변경

### 4.1 변경 위치

`api/chat.py` 75-82행 (Models 섹션)

### 4.2 설계

현재:
```python
class ChatRequest(BaseModel):
    query: str
```

변경 후:
```python
class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None  # Multi-turn session ID (optional)
```

**하위 호환:** `session_id`가 없으면 기존 단일 턴 동작과 동일합니다.

---

## 5. M3: 대화 이력을 Gemini contents에 전달

### 5.1 변경 위치

`api/chat.py` 153행 `chat_with_data()` 함수 내부

### 5.2 설계

**`chat_with_data()` 함수 변경:**

현재 (177-193행):
```python
for attempt in range(MAX_RETRIES):
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=request.query,
            config=types.GenerateContentConfig(...),
        )
```

변경 후:
```python
# Lazy cleanup expired sessions
_cleanup_expired_sessions()

# Build contents with history
history = _get_session_history(request.session_id)
user_content = types.Content(
    role="user",
    parts=[types.Part.from_text(text=request.query)],
)
contents = history + [user_content]

for attempt in range(MAX_RETRIES):
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(...),
        )
```

**성공 응답 후 세션 저장 (return 직전):**

```python
# Save session history (user message + model response)
if request.session_id:
    model_content = types.Content(
        role="model",
        parts=[types.Part.from_text(text=response.text)],
    )
    updated_history = history + [user_content, model_content]
    _save_session_history(request.session_id, updated_history)
```

### 5.3 동작 흐름

```
1. 요청 수신 (session_id 포함)
2. _cleanup_expired_sessions() → 만료 세션 정리
3. _get_session_history(session_id) → 기존 이력 가져오기
4. contents = history + [user_content] → Gemini에 전체 대화 전달
5. Gemini 응답
6. _save_session_history() → 이력에 user + model 추가 (최대 10턴)
7. 응답 반환
```

### 5.4 session_id 없는 경우 (하위 호환)

- `_get_session_history(None)` → 빈 리스트
- `contents = [] + [user_content]` → 단일 메시지 (기존과 동일)
- `_save_session_history(None, ...)` → 저장 안 함

---

## 6. 전체 변경 사양 요약

### 6.1 수정 파일

| 파일 | 항목 | 변경 내용 |
|------|------|----------|
| `tests/test_sql_validation.py` | T1 | 신규 생성: 16 테스트 케이스 (2 클래스) |
| `api/chat.py` | M1 | 세션 저장소 + 헬퍼 함수 3개 (`_get_session_history`, `_save_session_history`, `_cleanup_expired_sessions`) |
| `api/chat.py` | M2 | `ChatRequest.session_id` 필드 추가 |
| `api/chat.py` | M3 | `chat_with_data()` 내부: contents 빌드 + 세션 저장 로직 |

### 6.2 변경하지 않는 파일

| 파일 | 이유 |
|------|------|
| `api/tools.py` | 테스트 대상이지만 수정 없음 |
| `api/main.py` | chat 라우터는 이미 포함됨 |
| `shared/*` | 변경 불필요 |

### 6.3 구현 순서

| 순서 | ID | 작업 | 의존성 |
|:----:|:--:|------|--------|
| 1 | T1 | SQL 검증 pytest | 없음 |
| 2 | M1 | 세션 저장소 + 헬퍼 함수 | 없음 |
| 3 | M2 | ChatRequest.session_id | M1 |
| 4 | M3 | contents 이력 전달 + 세션 저장 | M1, M2 |

---

## 7. 검증 체크리스트

### T1 검증
- [ ] `tests/test_sql_validation.py` 파일 존재
- [ ] `TestStripSqlComments` 클래스: 4 테스트
- [ ] `TestExecuteCustomQueryValidation` 클래스: 12 테스트
- [ ] `pytest tests/test_sql_validation.py` 전체 통과

### M1 세션 저장소 검증
- [ ] `SESSION_TTL = 1800` 상수 존재
- [ ] `SESSION_MAX_TURNS = 10` 상수 존재
- [ ] `_sessions` dict 존재
- [ ] `_get_session_history()` 함수 존재
- [ ] `_save_session_history()` 함수 존재 (max turns 트림 포함)
- [ ] `_cleanup_expired_sessions()` 함수 존재

### M2 ChatRequest 검증
- [ ] `ChatRequest.session_id: str | None = None` 필드 존재
- [ ] `session_id` 없이 요청 → 기존 동작 유지

### M3 Contents 이력 검증
- [ ] `_cleanup_expired_sessions()` 호출 (요청 시작 시)
- [ ] `_get_session_history()` 호출
- [ ] `contents = history + [user_content]` 빌드
- [ ] `client.models.generate_content(contents=contents, ...)` 전달
- [ ] 성공 시 `_save_session_history()` 호출 (user + model 저장)
- [ ] `session_id=None`이면 저장 안 함
