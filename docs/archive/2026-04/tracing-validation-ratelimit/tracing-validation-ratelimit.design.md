# Design: Request Tracing + Input Validation + Rate Limiting

> PDCA Phase: **Design**
> Feature: `tracing-validation-ratelimit`
> Plan Reference: `docs/01-plan/features/tracing-validation-ratelimit.plan.md`
> Created: 2026-02-13
> Status: Draft

---

## 1. Implementation Order

```
L1 (Rate Limiter Module) → V1-V3 (Input Validation) → R1-R2 (Request Tracing) → L2-L3 (Rate Limit 적용) → T1 (Tests)
```

L1 모듈을 먼저 생성하고, Validation 강화 → Tracing 개선 → Rate Limit 적용 → 테스트 순서로 진행합니다.

---

## 2. L1: Rate Limiter 모듈

### 2.1 신규 파일

`shared/rate_limiter.py`

### 2.2 설계

인메모리 Sliding Window 방식의 Rate Limiter입니다.

```python
from __future__ import annotations

import time
from collections import defaultdict

from .config import RATE_LIMIT_CHAT, RATE_LIMIT_API, RATE_LIMIT_WINDOW


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed for given key (e.g., IP address)."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Remove expired timestamps
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        # Check limit
        if len(self._requests[key]) >= self.max_requests:
            return False

        # Record request
        self._requests[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        """Get remaining requests for key in current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        current = len([t for t in self._requests.get(key, []) if t > cutoff])
        return max(0, self.max_requests - current)

    def retry_after(self, key: str) -> int:
        """Get seconds until next request is allowed."""
        timestamps = self._requests.get(key, [])
        if not timestamps:
            return 0
        now = time.time()
        cutoff = now - self.window_seconds
        valid = [t for t in timestamps if t > cutoff]
        if len(valid) < self.max_requests:
            return 0
        # Oldest valid timestamp + window = when it expires
        return max(0, int(valid[0] + self.window_seconds - now) + 1)

    def cleanup(self) -> None:
        """Remove keys with no active timestamps (memory cleanup)."""
        now = time.time()
        empty_keys = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [t for t in timestamps if t > now - self.window_seconds]
            if not self._requests[key]:
                empty_keys.append(key)
        for key in empty_keys:
            del self._requests[key]


# Pre-configured instances
chat_limiter = RateLimiter(
    max_requests=RATE_LIMIT_CHAT,
    window_seconds=RATE_LIMIT_WINDOW,
)

api_limiter = RateLimiter(
    max_requests=RATE_LIMIT_API,
    window_seconds=RATE_LIMIT_WINDOW,
)
```

### 2.3 설정 상수

`shared/config.py`에 추가:

```python
# ==========================================================
# Rate Limiting
# ==========================================================
RATE_LIMIT_CHAT = 20   # AI Chat: max requests per window
RATE_LIMIT_API = 60    # General API: max requests per window
RATE_LIMIT_WINDOW = 60  # Window size in seconds (1 minute)
```

---

## 3. V1-V3: Input Validation 강화

### 3.1 변경 파일

`api/main.py`, `api/chat.py`

### 3.2 V1: 날짜 논리 검증

`api/main.py`에 헬퍼 함수 추가 (`_normalize_date` 함수 뒤):

```python
def _validate_date_range(date_from: str | None, date_to: str | None) -> None:
    """Validate date_from <= date_to. Raises HTTPException if invalid."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail=f"date_from ({date_from}) must be before or equal to date_to ({date_to})."
        )
```

적용 위치 (날짜 파라미터를 사용하는 3개 엔드포인트):

- `get_records()` — `_normalize_date` 후, `pick_targets` 전에 호출
- `monthly_total()` — `_normalize_date` 후 호출
- `summary_by_item()` — `_normalize_date` 후 호출

### 3.3 V2: ChatRequest.query 길이 제한

`api/chat.py` ChatRequest 변경:

현재:
```python
class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
```

변경 후:
```python
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)
```

### 3.4 V3: 문자열 파라미터 길이 제한

`api/main.py` `get_records()` 파라미터 변경:

현재:
```python
item_code: str | None = None,
q: str | None = None,
lot_number: str | None = Query(default=None, ...),
```

변경 후:
```python
item_code: str | None = Query(default=None, max_length=50, description="Exact item code"),
q: str | None = Query(default=None, max_length=100, description="Search keyword"),
lot_number: str | None = Query(default=None, max_length=50, description="Lot number prefix filter (e.g., LT2026)"),
```

`list_items()` 파라미터 변경:

현재:
```python
q: str | None = None,
```

변경 후:
```python
q: str | None = Query(default=None, max_length=100),
```

`summary_by_item()` 파라미터 변경:

현재:
```python
item_code: str | None = Query(default=None, description="Filter by specific item"),
```

변경 후:
```python
item_code: str | None = Query(default=None, max_length=50, description="Filter by specific item"),
```

`monthly_by_item()` 파라미터 변경:

현재:
```python
year_month: str | None = Query(default=None, description="e.g., 2026-01"),
item_code: str | None = None,
```

변경 후:
```python
year_month: str | None = Query(default=None, max_length=7, description="e.g., 2026-01"),
item_code: str | None = Query(default=None, max_length=50),
```

---

## 4. R1-R2: Request Tracing 강화

### 4.1 변경 파일

`api/chat.py`

### 4.2 R1: ChatResponse에 request_id 추가

현재:
```python
class ChatResponse(BaseModel):
    answer: str
    status: str = "success"
    tools_used: List[str] = []
```

변경 후:
```python
class ChatResponse(BaseModel):
    answer: str
    status: str = "success"
    tools_used: List[str] = []
    request_id: str = ""
```

### 4.3 R2: chat_with_data() 응답에 request_id 포함

성공 응답 (현재 283-286행 부근):
```python
return ChatResponse(
    answer=response.text,
    tools_used=tools_used,
    request_id=request_id,
)
```

에러 응답 (현재 316-319행 부근):
```python
return ChatResponse(
    answer=error_message,
    status="error",
    request_id=request_id,
)
```

---

## 5. L2-L3: Rate Limiting 적용

### 5.1 변경 파일

`api/main.py`, `api/chat.py`

### 5.2 L2: AI Chat Rate Limiting

`api/chat.py` — `chat_with_data()` 함수 시작 부분, client 체크 후:

```python
from shared.rate_limiter import chat_limiter

# ... 기존 코드 ...

# Rate limiting (after client check, before processing)
client_ip = request_obj.client.host if hasattr(request_obj, 'client') and request_obj.client else "unknown"
if not chat_limiter.is_allowed(client_ip):
    retry_after = chat_limiter.retry_after(client_ip)
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )
```

**함수 시그니처 변경** — FastAPI Request 객체 주입:

현재:
```python
@router.post("/", response_model=ChatResponse)
async def chat_with_data(request: ChatRequest):
```

변경 후:
```python
from fastapi import Request as FastAPIRequest

@router.post("/", response_model=ChatResponse)
async def chat_with_data(request: ChatRequest, request_obj: FastAPIRequest):
```

### 5.3 L3: 일반 API Rate Limiting (미들웨어)

`api/main.py` — 기존 `add_request_id` 미들웨어 뒤에 추가:

```python
from shared.rate_limiter import api_limiter, chat_limiter

@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    # Skip health check endpoints
    if request.url.path.startswith("/healthz"):
        return await call_next(request)

    # Chat endpoint uses its own limiter (applied in chat_with_data)
    if request.url.path.startswith("/chat"):
        return await call_next(request)

    # General API rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not api_limiter.is_allowed(client_ip):
        retry_after = api_limiter.retry_after(client_ip)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded. Try again in {retry_after} seconds."},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
```

### 5.4 Rate Limiting 제외 대상

| 엔드포인트 | Rate Limiter | 이유 |
|-----------|:----------:|------|
| `/healthz`, `/healthz/ai` | 제외 | 모니터링 용도 |
| `/chat/` | chat_limiter (20/min) | AI API 쿼터 보호 |
| `/records`, `/items`, `/summary/*` | api_limiter (60/min) | 일반 API |
| `/` (root) | api_limiter (60/min) | 일반 API |

---

## 6. T1: 테스트

### 6.1 신규 파일

`tests/test_rate_limiter.py`, `tests/test_input_validation.py`

### 6.2 Rate Limiter 테스트

```python
import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.rate_limiter import RateLimiter


class TestRateLimiter:
    """RateLimiter 단위 테스트"""

    def test_allows_within_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed("test_ip") is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("test_ip")
        assert limiter.is_allowed("test_ip") is False

    def test_different_keys_independent(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("ip_a")
        limiter.is_allowed("ip_a")
        assert limiter.is_allowed("ip_a") is False
        assert limiter.is_allowed("ip_b") is True

    def test_remaining_count(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.remaining("test_ip") == 5
        limiter.is_allowed("test_ip")
        assert limiter.remaining("test_ip") == 4

    def test_retry_after_when_blocked(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("test_ip")
        retry = limiter.retry_after("test_ip")
        assert retry > 0
        assert retry <= 61

    def test_retry_after_when_allowed(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.retry_after("test_ip") == 0

    def test_cleanup_removes_empty_keys(self):
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        limiter.is_allowed("temp_ip")
        assert "temp_ip" in limiter._requests
        # Wait for window to expire
        time.sleep(1.1)
        limiter.cleanup()
        assert "temp_ip" not in limiter._requests

    def test_window_expiry_allows_again(self):
        limiter = RateLimiter(max_requests=1, window_seconds=1)
        assert limiter.is_allowed("test_ip") is True
        assert limiter.is_allowed("test_ip") is False
        time.sleep(1.1)
        assert limiter.is_allowed("test_ip") is True
```

### 6.3 Input Validation 테스트

```python
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDateRangeValidation:
    """날짜 범위 검증 테스트"""

    def test_valid_range_passes(self):
        from api.main import _validate_date_range
        # Should not raise
        _validate_date_range("2026-01-01", "2026-12-31")

    def test_same_date_passes(self):
        from api.main import _validate_date_range
        _validate_date_range("2026-01-01", "2026-01-01")

    def test_none_values_pass(self):
        from api.main import _validate_date_range
        _validate_date_range(None, None)
        _validate_date_range("2026-01-01", None)
        _validate_date_range(None, "2026-12-31")

    def test_invalid_range_raises(self):
        from api.main import _validate_date_range
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_date_range("2026-12-31", "2026-01-01")
        assert exc_info.value.status_code == 400

    def test_chat_query_length_limit(self):
        from api.chat import ChatRequest
        from pydantic import ValidationError
        # Valid: 2000 chars
        ChatRequest(query="a" * 2000)
        # Invalid: 2001 chars
        with pytest.raises(ValidationError):
            ChatRequest(query="a" * 2001)

    def test_chat_query_empty_blocked(self):
        from api.chat import ChatRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ChatRequest(query="")

    def test_session_id_length_limit(self):
        from api.chat import ChatRequest
        from pydantic import ValidationError
        # Valid: 100 chars
        ChatRequest(query="test", session_id="a" * 100)
        # Invalid: 101 chars
        with pytest.raises(ValidationError):
            ChatRequest(query="test", session_id="a" * 101)
```

### 6.4 테스트 구조

- `TestRateLimiter` (8 tests): 순수 RateLimiter 클래스 테스트
- `TestDateRangeValidation` (4 tests): 날짜 검증 헬퍼 테스트
- `TestChatRequestValidation` (3 tests in same file): Pydantic 검증 테스트
- 총 **15 테스트 케이스**

---

## 7. 전체 변경 사양 요약

### 7.1 수정 파일

| 파일 | 항목 | 변경 내용 |
|------|------|----------|
| `shared/config.py` | L1 | Rate Limit 설정 상수 3개 추가 |
| `shared/rate_limiter.py` | L1 | 신규 생성: RateLimiter 클래스 + 인스턴스 2개 |
| `api/main.py` | V1, V3, L3 | `_validate_date_range()` 추가, 파라미터 `max_length`, Rate Limit 미들웨어 |
| `api/chat.py` | R1, V2, L2 | ChatResponse.request_id, Field 제약, Rate Limit 체크 |
| `tests/test_rate_limiter.py` | T1 | 신규 생성: 8 테스트 케이스 |
| `tests/test_input_validation.py` | T1 | 신규 생성: 7 테스트 케이스 |

### 7.2 변경하지 않는 파일

| 파일 | 이유 |
|------|------|
| `api/tools.py` | 변경 불필요 (SQL 검증은 이미 강화됨) |
| `shared/database.py` | 변경 불필요 |
| `shared/cache.py` | 변경 불필요 |
| `shared/logging_config.py` | 변경 불필요 (Request ID 인프라 이미 존재) |

### 7.3 구현 순서

| 순서 | ID | 작업 | 의존성 |
|:----:|:--:|------|--------|
| 1 | L1 | Rate Limiter 모듈 + config 상수 | 없음 |
| 2 | V1-V3 | Input Validation 강화 | 없음 |
| 3 | R1-R2 | Request Tracing 강화 | 없음 |
| 4 | L2-L3 | Rate Limiting 적용 | L1 |
| 5 | T1 | 테스트 작성 및 실행 | L1, V1-V3, R1-R2 |

---

## 8. 검증 체크리스트

### L1 Rate Limiter 모듈 검증
- [ ] `shared/rate_limiter.py` 파일 존재
- [ ] `RateLimiter` 클래스: `is_allowed()`, `remaining()`, `retry_after()`, `cleanup()` 메서드
- [ ] `chat_limiter` 인스턴스 (20 req/min)
- [ ] `api_limiter` 인스턴스 (60 req/min)
- [ ] `shared/config.py`에 `RATE_LIMIT_CHAT`, `RATE_LIMIT_API`, `RATE_LIMIT_WINDOW` 상수

### V1 날짜 검증
- [ ] `_validate_date_range()` 함수 존재
- [ ] `get_records()`에서 호출
- [ ] `monthly_total()`에서 호출
- [ ] `summary_by_item()`에서 호출
- [ ] `date_from > date_to` 시 400 에러

### V2 ChatRequest 검증
- [ ] `query: str = Field(..., min_length=1, max_length=2000)`
- [ ] `session_id: str | None = Field(default=None, max_length=100)`

### V3 파라미터 길이 제한
- [ ] `get_records()`: item_code max 50, q max 100, lot_number max 50
- [ ] `list_items()`: q max 100
- [ ] `summary_by_item()`: item_code max 50
- [ ] `monthly_by_item()`: year_month max 7, item_code max 50

### R1 ChatResponse 검증
- [ ] `ChatResponse.request_id: str = ""` 필드 존재
- [ ] 성공 응답에 request_id 포함
- [ ] 에러 응답에 request_id 포함

### L2 AI Rate Limiting 검증
- [ ] `chat_with_data()` 시그니처에 `request_obj: FastAPIRequest` 추가
- [ ] `chat_limiter.is_allowed(client_ip)` 체크
- [ ] 초과 시 429 + Retry-After 헤더

### L3 일반 API Rate Limiting 검증
- [ ] `rate_limit_middleware` 미들웨어 존재
- [ ] `/healthz` 제외
- [ ] `/chat` 제외 (자체 limiter 사용)
- [ ] 일반 API에 `api_limiter` 적용
- [ ] 초과 시 429 + Retry-After 헤더

### T1 테스트 검증
- [ ] `tests/test_rate_limiter.py`: 8 테스트
- [ ] `tests/test_input_validation.py`: 7 테스트
- [ ] `pytest` 전체 통과
