# sse-streaming-optimization Design Document

> **Feature**: sse-streaming-optimization
> **Plan**: `docs/01-plan/features/sse-streaming-optimization.plan.md`
> **Date**: 2026-04-21
> **Status**: Design

---

## 1. Implementation Details

### S5: 구조화된 에러 코드 체계

**목표**: 에러 이벤트의 `code` 필드를 표준화하여 클라이언트가 에러 유형별로 분기 가능하게 한다.

**서버 (`api/_chat_stream.py`)**:

에러 코드 상수 정의:
```python
# Error code constants for SSE error events
ERR_AI_DISABLED = "ai_disabled"
ERR_TIMEOUT = "timeout"
ERR_MODEL_ERROR = "model_error"
ERR_RATE_LIMITED = "rate_limited"
ERR_INTERNAL = "internal"
```

현재 코드의 에러 이벤트 매핑:
| 현재 (line) | code 변경 | message 변경 |
|-------------|-----------|--------------|
| L70: `AI_DISABLED` | `ai_disabled` (소문자 통일) | 유지 |
| L111: `type(fb_err).__name__` | `model_error` | 유지 (300자 잘림 → 500자) |
| L119: `type(e).__name__` | `model_error` (fallbackable 아닌 경우) | 유지 |
| L160: `type(e).__name__` (mid-stream) | `internal` | 유지 |
| 신규: 타임아웃 (S2) | `timeout` | "스트리밍 시간 초과 (120초)" |

`message` 잘림 300 → 500자로 확대.

**클라이언트 (`dashboard/components/ai_section.py`)**:

에러 코드별 한글 메시지 매핑:
```python
_ERROR_MESSAGES = {
    "ai_disabled": "AI 엔진이 비활성화되어 있습니다.",
    "timeout": "AI 응답 시간이 초과되었습니다. 짧은 질문으로 다시 시도해 주세요.",
    "model_error": "AI 모델 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "rate_limited": "요청이 너무 많습니다. 1분 후 다시 시도해 주세요.",
    "internal": "내부 오류가 발생했습니다. 관리자에게 문의하세요.",
}
```

`_stream_chat_tokens` L93-94 변경:
```python
elif event_name == "error":
    code = data.get("code", "internal")
    msg = _ERROR_MESSAGES.get(code, data.get("message", "AI 스트리밍 오류"))
    st.error(msg)
    return
```

---

### S6: tool_call 중복 허용

**목표**: 동일 이름 함수의 복수 호출을 구분하여 모두 전송.

**파일**: `api/_chat_stream.py`

**변경**: `tools_emitted: set[str]` → `tools_emitted: list[tuple[str, dict]]`

```python
# Before (L130, L141-142):
tools_emitted: set[str] = set()
...
if fc and getattr(fc, "name", None) and fc.name not in tools_emitted:
    tools_emitted.add(fc.name)

# After:
tools_emitted: list[tuple[str, dict]] = []
...
if fc and getattr(fc, "name", None):
    try:
        args = dict(fc.args) if getattr(fc, "args", None) else {}
    except (TypeError, ValueError):
        args = {}
    tools_emitted.append((fc.name, args))
    yield _sse("tool_call", {"name": fc.name, "args": args})
```

`done` 이벤트의 `tools_used` 필드도 변경:
```python
# Before (L177):
"tools_used": sorted(tools_emitted),

# After:
"tools_used": [name for name, _ in tools_emitted],
```

로그 출력도 동일하게 수정 (L172).

---

### S1: 서버 Heartbeat

**목표**: 청크 간 10초 이상 간격이 발생하면 SSE 코멘트 프레임 (`: heartbeat\n\n`)을 전송하여 프록시/방화벽의 유휴 연결 종료를 방지.

**파일**: `api/_chat_stream.py`, `shared/config.py`

**설정 추가** (`shared/config.py`):
```python
# ==========================================================
# SSE Streaming Configuration
# ==========================================================
STREAM_HEARTBEAT_SEC = float(os.getenv("STREAM_HEARTBEAT_SEC", 10.0))
STREAM_TIMEOUT_SEC = float(os.getenv("STREAM_TIMEOUT_SEC", 120.0))
```

**구현** (`api/_chat_stream.py`):

`run_stream()` 내부의 `async for chunk in stream:` 루프를 `asyncio.timeout` + heartbeat wrapper로 교체:

```python
import asyncio
from shared.config import STREAM_HEARTBEAT_SEC, STREAM_TIMEOUT_SEC

async def _iter_with_heartbeat(
    stream, heartbeat_sec: float
) -> AsyncIterator[object | None]:
    """Wrap async stream iterator, yielding None as heartbeat on idle.

    Yields:
        chunk object from stream, or None if heartbeat_sec elapsed without a chunk.
    """
    aiter = stream.__aiter__()
    while True:
        try:
            chunk = await asyncio.wait_for(aiter.__anext__(), timeout=heartbeat_sec)
            yield chunk
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            yield None  # heartbeat signal
```

`run_stream()` 메인 루프:
```python
try:
    async with asyncio.timeout(STREAM_TIMEOUT_SEC):
        async for chunk in _iter_with_heartbeat(stream, STREAM_HEARTBEAT_SEC):
            if chunk is None:
                yield ": heartbeat\n\n"
                continue

            # 1) tool_call emission (기존 로직)
            ...
            # 2) token emission (기존 로직)
            ...
except TimeoutError:
    yield _sse("error", {"code": ERR_TIMEOUT, "message": f"스트리밍 시간 초과 ({int(STREAM_TIMEOUT_SEC)}초)"})
    return
except Exception as e:
    ...  # 기존 에러 핸들링
```

**클라이언트 호환성**: SSE 표준에서 `:` 으로 시작하는 라인은 코멘트로 자동 무시됨.
현재 클라이언트 파서 (`ai_section.py:76-82`)는 `event:` / `data:` 접두사만 처리하므로 heartbeat 라인은 자연스럽게 스킵됨 — **변경 불필요**.

---

### S2: 서버 스트림 타임아웃

**목표**: 총 스트리밍 시간이 120초 초과 시 `timeout` 에러 이벤트 발생 후 스트림 종료.

**구현**: S1의 `asyncio.timeout(STREAM_TIMEOUT_SEC)` 컨텍스트에 이미 포함.

`TimeoutError` 캐치 시:
- `error` 이벤트 전송 (`code: "timeout"`)
- 부분 텍스트가 있어도 세션에 저장하지 않음 (기존 정책 유지)
- 로그: `[ChatStream Timeout] request_id=... | partial_chars=N | duration_ms=120000`

**클라이언트**: S5에서 이미 `timeout` 코드 매핑 추가 완료 — **추가 변경 불필요**.

---

### S4: 청크 버퍼링

**목표**: 50ms 미만 간격으로 연속 도착하는 토큰을 버퍼에 모아 단일 `token` 이벤트로 병합, 네트워크 이벤트 수 감소.

**파일**: `api/_chat_stream.py`

**설계 원칙**:
1. **첫 토큰은 즉시 전송** — TTFT(Time to First Token) 보장
2. 이후 토큰은 50ms 버퍼 윈도우로 병합
3. heartbeat/timeout과 간섭 없음 (버퍼링은 token 이벤트 내부)

**구현**: `_iter_with_heartbeat`를 확장하여 버퍼링 레이어 추가:

```python
BUFFER_FLUSH_MS = 50  # milliseconds

# run_stream() 내부:
token_buffer: list[str] = []
last_token_time: float = 0.0
first_token_sent = False

async with asyncio.timeout(STREAM_TIMEOUT_SEC):
    async for chunk in _iter_with_heartbeat(stream, STREAM_HEARTBEAT_SEC):
        if chunk is None:
            # Flush buffer before heartbeat
            if token_buffer:
                merged = "".join(token_buffer)
                full_text_parts.append(merged)
                yield _sse("token", {"text": merged})
                token_buffer.clear()
            yield ": heartbeat\n\n"
            continue

        # 1) tool_call emission (기존)
        ...

        # 2) token buffering
        text = getattr(chunk, "text", None)
        if text:
            now = time.perf_counter()
            if not first_token_sent:
                # First token: emit immediately for TTFT
                full_text_parts.append(text)
                yield _sse("token", {"text": text})
                first_token_sent = True
                last_token_time = now
            else:
                token_buffer.append(text)
                elapsed_ms = (now - last_token_time) * 1000
                if elapsed_ms >= BUFFER_FLUSH_MS:
                    merged = "".join(token_buffer)
                    full_text_parts.append(merged)
                    yield _sse("token", {"text": merged})
                    token_buffer.clear()
                    last_token_time = now

# After loop: flush remaining buffer
if token_buffer:
    merged = "".join(token_buffer)
    full_text_parts.append(merged)
    yield _sse("token", {"text": merged})
    token_buffer.clear()
```

---

### S3: 클라이언트 자동 재연결

**목표**: `ConnectError` 또는 `ReadTimeout` 발생 시 2초 대기 후 1회 자동 재시도.

**파일**: `dashboard/components/ai_section.py`

**구현**: `_stream_chat_tokens()`의 try/except 블록을 래핑:

```python
_MAX_RETRIES = 1
_RETRY_DELAY_SEC = 2.0

def _stream_chat_tokens(stream_url: str, payload: dict) -> Iterator[str]:
    """Yield text tokens from the /chat/stream SSE endpoint with auto-retry."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            yield from _stream_chat_tokens_once(stream_url, payload)
            return  # Success
        except httpx.ConnectError:
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            st.error("AI 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요.")
        except httpx.ReadTimeout:
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            st.error("AI 응답 시간이 초과되었습니다. 다시 시도해 주세요.")
        except Exception as e:
            st.error(f"스트리밍 오류: {e}")
            return  # Don't retry unknown errors

def _stream_chat_tokens_once(stream_url: str, payload: dict) -> Iterator[str]:
    """Single-attempt SSE stream consumer. Raises on connection/timeout errors."""
    with httpx.stream("POST", stream_url, json=payload, timeout=60.0) as r:
        if r.status_code != 200:
            try:
                detail = r.read().decode("utf-8", "replace")
            except Exception:
                detail = ""
            st.error(f"스트리밍 요청 실패: HTTP {r.status_code} {detail[:200]}")
            return
        event_name: Optional[str] = None
        for line in r.iter_lines():
            if not line:
                event_name = None
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                raw = line[5:].strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if event_name == "token":
                    yield data.get("text", "")
                elif event_name == "tool_call":
                    st.toast(f"🔧 {data.get('name', '')}", icon="⚙️")
                elif event_name == "error":
                    code = data.get("code", "internal")
                    msg = _ERROR_MESSAGES.get(code, data.get("message", "AI 스트리밍 오류"))
                    st.error(msg)
                    return
                elif event_name == "done":
                    st.session_state["_last_chat_meta"] = data
                    return
```

**주의사항**:
- `import time` 추가 필요
- 재시도 시 이미 yield된 토큰은 복구 불가 → 재시도는 **연결 단계 실패**에만 적용
- `_stream_chat_tokens_once` 내부에서 `error` 이벤트 수신 시 재시도하지 않음 (서버 레벨 에러)
- `yield from`이 부분 yield 후 예외 발생 시 문제 가능 → `ConnectError`는 연결 전 발생, `ReadTimeout`은 스트림 중간에 발생할 수 있음

**ReadTimeout 재시도 제한**: `ReadTimeout`이 이미 토큰을 yield한 후 발생하면 재시도가 중복 텍스트를 생성할 수 있음. 이를 방지하려면:
```python
def _stream_chat_tokens(stream_url: str, payload: dict) -> Iterator[str]:
    for attempt in range(_MAX_RETRIES + 1):
        tokens_yielded = False
        try:
            for token in _stream_chat_tokens_once(stream_url, payload):
                tokens_yielded = True
                yield token
            return
        except httpx.ConnectError:
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            st.error("AI 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요.")
        except httpx.ReadTimeout:
            if attempt < _MAX_RETRIES and not tokens_yielded:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            st.error("AI 응답 시간이 초과되었습니다. 다시 시도해 주세요.")
        except Exception as e:
            st.error(f"스트리밍 오류: {e}")
            return
```

**핵심**: `ReadTimeout` 재시도는 **토큰 전송 전에만** 허용 (`not tokens_yielded`).

---

## 2. Implementation Order

```
S5 (에러 코드 체계)
  → S6 (tool_call 중복)
    → S1 (heartbeat) + S2 (timeout)  [동시 구현]
      → S4 (버퍼링)
        → S3 (클라이언트 재연결)
```

---

## 3. Acceptance Criteria

| Criterion | Target | Verification |
|-----------|--------|-------------|
| 에러 코드 4종 사용 | `ai_disabled`, `timeout`, `model_error`, `internal` | grep `ERR_` in _chat_stream.py |
| tool_call 중복 전송 | 동명 함수 2회 호출 시 2개 이벤트 | 테스트 |
| Heartbeat 전송 | 10초 간격 `: heartbeat\n\n` | Fake slow generator 테스트 |
| 총 타임아웃 | 120초 초과 시 `timeout` 에러 | Fake infinite generator 테스트 |
| 토큰 버퍼링 | 50ms 미만 연속 토큰 병합 | 이벤트 수 비교 테스트 |
| 첫 토큰 즉시 전송 | 버퍼링 미적용 | TTFT 측정 테스트 |
| 클라이언트 재연결 | ConnectError 1회 재시도 | mock httpx 테스트 |
| ReadTimeout 재시도 | 토큰 전송 전에만 | `tokens_yielded` 플래그 |
| Heartbeat 클라이언트 무시 | 파싱 영향 없음 | 기존 파서로 heartbeat 포함 스트림 |
| 기존 테스트 통과 | 149+ pass | pytest |

---

## 4. Test Plan

### 신규 테스트 (`tests/test_chat_stream.py` 추가)

| Test | Scope | 설명 |
|------|-------|------|
| `test_stream_error_code_timeout` | S2/S5 | 120초 초과 시 `timeout` 코드 에러 이벤트 |
| `test_stream_error_code_model_error` | S5 | 모델 예외 시 `model_error` 코드 |
| `test_stream_error_code_ai_disabled` | S5 | AI 비활성 시 `ai_disabled` 코드 |
| `test_stream_heartbeat_emitted` | S1 | Fake slow generator로 heartbeat 코멘트 확인 |
| `test_stream_heartbeat_not_breaks_events` | S1 | heartbeat 사이에 정상 토큰 이벤트 |
| `test_stream_tool_call_duplicate` | S6 | 동명 함수 2회 호출 시 2개 이벤트 |
| `test_stream_token_buffering` | S4 | 빠른 연속 토큰 → 병합된 이벤트 수 감소 |
| `test_stream_first_token_immediate` | S4 | 첫 토큰 즉시 전송 확인 |

### 신규 테스트 (`tests/test_stream_client.py` 신규 파일, 선택)

| Test | Scope | 설명 |
|------|-------|------|
| `test_client_retry_on_connect_error` | S3 | ConnectError → 1회 재시도 후 성공 |
| `test_client_no_retry_after_tokens` | S3 | ReadTimeout (토큰 전송 후) → 재시도 안 함 |

---

## 5. File Change Summary

| 구분 | 파일 | 변경 내용 | Lines (예상) |
|------|------|----------|-------------|
| MOD | `shared/config.py` | `STREAM_HEARTBEAT_SEC`, `STREAM_TIMEOUT_SEC` 추가 | +5 |
| MOD | `api/_chat_stream.py` | S1-S6 전체: heartbeat wrapper, timeout, 버퍼링, 에러 코드, tool_call | +60, -15 |
| MOD | `dashboard/components/ai_section.py` | S3: 재연결 래퍼, S5: 에러 메시지 매핑 | +35, -10 |
| MOD | `tests/test_chat_stream.py` | 신규 테스트 8개 | +120 |
| NEW | `tests/test_stream_client.py` | 클라이언트 재연결 테스트 (선택) | +60 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-21 | Initial design — S1-S6 상세 구현 명세 | interojo |
