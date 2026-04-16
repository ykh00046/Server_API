# Design: Gemini Model Fallback (Flash → 3.1 Flash Lite)

> Plan: [gemini-fallback.plan.md](../../01-plan/features/gemini-fallback.plan.md)

## 1. 설계 요약

| 항목 | 값 |
|------|-----|
| 기본 모델 | `gemini-2.5-flash` (RPM 5 / RPD 20) |
| 폴백 모델 | `gemini-3.1-flash-lite` (RPM 15 / RPD 500) |
| 폴백 트리거 | 429 (TooManyRequests), 503 (ServiceUnavailable) — retry 소진 후 |
| 폴백 횟수 | 1회 (폴백 모델도 실패 시 에러 반환) |

## 2. 파일별 변경 상세

### 2.1 `shared/config.py` — 설정 추가

```python
# AI / Gemini 섹션에 추가
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
GEMINI_FALLBACK_ENABLED = os.getenv("GEMINI_FALLBACK_ENABLED", "true").lower() == "true"
```

### 2.2 `api/chat.py` — sync 엔드포인트

#### 2.2.1 `_generate_with_retry()` 시그니처 변경

```python
async def _generate_with_retry(
    client_obj, contents, system_instruction, request_id, query_preview
) -> tuple[response, str]:
    """Returns (response, model_used)."""
```

- 반환값을 `(response, model_used)` 튜플로 변경
- 기존 retry 로직(3회, 같은 모델) 유지
- retry 소진 후 `GEMINI_FALLBACK_ENABLED`이면 폴백 모델로 1회 시도
- 폴백 성공 시 `logger.warning("[Fallback]")` 로그

#### 2.2.2 폴백 로직 흐름

```python
# 기존 retry 루프 (Flash, 최대 3회)
for attempt in range(MAX_RETRIES):
    try:
        response = call(GEMINI_MODEL)
        return response, GEMINI_MODEL
    except retryable:
        backoff...

# retry 소진 → 폴백 시도
if GEMINI_FALLBACK_ENABLED and _is_retryable_error(last_error):
    try:
        response = call(GEMINI_FALLBACK_MODEL)
        logger.warning(f"[Fallback] {GEMINI_MODEL} → {GEMINI_FALLBACK_MODEL}")
        return response, GEMINI_FALLBACK_MODEL
    except Exception as fb_err:
        logger.error(f"[Fallback Failed] {fb_err}")
        raise last_error  # 원래 에러를 raise

raise last_error
```

#### 2.2.3 `ChatResponse` 모델 확장

```python
class ChatResponse(BaseModel):
    answer: str
    status: str = "success"
    tools_used: List[str] = []
    request_id: str = ""
    model_used: str = ""  # 추가: 실제 응답한 모델명
```

#### 2.2.4 `chat_with_data()` 호출부 수정

```python
response, model_used = await _generate_with_retry(...)
# ...
return ChatResponse(
    answer=response.text, tools_used=tools_used,
    request_id=request_id, model_used=model_used,
)
```

### 2.3 `api/_chat_stream.py` — SSE 스트리밍 엔드포인트

#### 2.3.1 `run_stream()` 폴백 추가

```python
async def run_stream(...) -> AsyncIterator[str]:
    # ...
    model_to_use = GEMINI_MODEL
    fallback_used = False

    try:
        stream = await client_obj.aio.models.generate_content_stream(
            model=model_to_use, ...)
        # stream 소비 시도 — 첫 chunk에서 에러 발생 가능
    except (ClientError, ServerError) as e:
        if GEMINI_FALLBACK_ENABLED and _is_fallbackable(e):
            model_to_use = GEMINI_FALLBACK_MODEL
            fallback_used = True
            logger.warning(f"[Stream Fallback] {GEMINI_MODEL} → {GEMINI_FALLBACK_MODEL}")
            try:
                stream = await client_obj.aio.models.generate_content_stream(
                    model=model_to_use, ...)
            except Exception as fb_err:
                yield _sse("error", {...})
                return
        else:
            yield _sse("error", {...})
            return

    # meta 이벤트 — 폴백 정보 포함
    yield _sse("meta", {
        "request_id": request_id,
        "session_id": session_id,
        "model": model_to_use,
        "fallback": fallback_used,
    })

    # 이후 token 스트리밍은 기존과 동일
```

#### 2.3.2 `_is_fallbackable()` 헬퍼

```python
FALLBACK_STATUS_CODES = {429, 503}

def _is_fallbackable(e: Exception) -> bool:
    """폴백 대상 에러인지 판단. 404도 포함 (장애 시 모델 라우팅 실패)."""
    if isinstance(e, (ClientError, ServerError)):
        status = getattr(e, 'status', 0) or 0
        if status == 0:
            for code in FALLBACK_STATUS_CODES:
                if str(code) in str(e):
                    return True
        return status in FALLBACK_STATUS_CODES
    return False
```

> `chat.py`의 `_is_retryable_error()`와 유사하지만, 폴백 전용으로 분리.
> 500은 서버 내부 에러로 모델 변경해도 동일할 수 있어 폴백 대상에서 제외.

### 2.4 `shared/config.py` import 업데이트

`_chat_stream.py`에서 새 config 참조:

```python
from shared.config import GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_FALLBACK_ENABLED
```

## 3. SSE 이벤트 변경

### meta 이벤트 (변경)

```json
{
  "request_id": "abc123",
  "session_id": "sess_1",
  "model": "gemini-3.1-flash-lite",
  "fallback": true
}
```

- `model` 필드: 기존에도 있음 — 실제 사용된 모델로 변경
- `fallback` 필드: 신규 추가 (boolean)

### 나머지 이벤트 (변경 없음)

`tool_call`, `token`, `done`, `error` — 구조 변경 없음

## 4. 프론트엔드 영향

`dashboard/components/ai_section.py`에서 `meta` 이벤트의 `fallback` 필드를 읽어 `st.toast`로 표시 가능하나, **이번 스코프에서는 백엔드만 변경**. 프론트 표시는 후속 작업.

## 5. 테스트 설계

### 5.1 `test_chat_fallback.py` (신규)

| 케이스 | 시나리오 | 기대 결과 |
|--------|----------|-----------|
| `test_sync_fallback_on_429` | Flash 429 3회 → Lite 성공 | 응답 정상, `model_used=gemini-3.1-flash-lite` |
| `test_sync_both_fail` | Flash 429 3회 → Lite도 실패 | 에러 응답 |
| `test_sync_no_fallback_on_500` | Flash 500 | retry만 시도, 폴백 안 함 |
| `test_stream_fallback_on_429` | Stream Flash 429 → Lite 성공 | SSE meta에 `fallback=true` |
| `test_stream_both_fail` | Stream 양쪽 실패 | SSE error 이벤트 |
| `test_fallback_disabled` | `FALLBACK_ENABLED=false` + Flash 429 | 폴백 없이 에러 |

### 5.2 기존 테스트

`test_chat_stream.py`, `test_chat.py` — 기존 테스트는 수정 불필요 (Flash 성공 경로는 변경 없음)

## 6. 구현 순서

1. `shared/config.py` — 설정 추가
2. `api/chat.py` — `_generate_with_retry()` 폴백 + `ChatResponse.model_used`
3. `api/_chat_stream.py` — `run_stream()` 폴백 + meta 이벤트 확장
4. `tests/test_chat_fallback.py` — 폴백 테스트
5. 기존 테스트 통과 확인
