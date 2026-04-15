# Design — UI Modernization (Streamlit + Extras, Option 1)

- **Feature ID**: ui-modernization-streamlit-extras
- **작성일**: 2026-04-15
- **Plan 참조**: `docs/01-plan/features/ui-modernization-streamlit-extras.plan.md`
- **상태**: Design

## 0. 설계 요약 (TL;DR)

1. **AI 챗 SSE**: 신규 `POST /chat/stream` 엔드포인트 추가. `client.aio.models.generate_content_stream` + FastAPI `StreamingResponse(media_type="text/event-stream")`. 기존 `POST /chat/` 동기 엔드포인트는 그대로 유지 (breaking change 없음).
2. **툴 호출 보존**: `_tool_dispatch.PRODUCTION_TOOLS` 그대로 재사용. Automatic Function Calling 유지 — SDK가 SQL 툴을 실행한 뒤 모델 텍스트를 스트림으로 흘려보낸다. 툴 실행 중에는 `tool_call` 이벤트로 중간 상태를 알린다.
3. **UI 시각 현대화**: `streamlit-shadcn-ui` 카드/버튼을 **핵심 영역(챗 헤더·KPI·스타터 프롬프트)에 한해** 선택 적용. 나머지는 기존 Streamlit 컴포넌트 + 중앙 CSS 토큰(`shared/ui/theme.py`).
4. **접근성(MA-04)**: 고대비 CSS 테마를 `shared/ui/theme.py` 에 추가, 사이드바 토글로 전환. `prefers-contrast: more` 자동 감지.
5. **호환성·리그레션 제로**: 기존 `/chat/`, 기존 테마, 기존 134+ 테스트 전부 유지. 신규 엔드포인트·신규 UI 컴포넌트는 **추가** 경로.

## 1. 아키텍처 개요

```
┌────────────────────────────────────────────────────────────────┐
│                    Dashboard (Streamlit)                       │
│                                                                │
│  ai_section.py                                                 │
│   ├─ Zero-State UI (starter cards)        [shadcn-ui 카드]     │
│   ├─ Active Chat (history)                                     │
│   └─ Streaming Chat Client ──── httpx.stream(GET/POST SSE)     │
│          │                                                     │
│          └─→ st.write_stream(token_generator())                │
│                                                                │
│  shared/ui/theme.py                                            │
│   ├─ CSS tokens (color / spacing / radius)                     │
│   ├─ High-contrast palette (MA-04)                             │
│   └─ apply_custom_css() — single injection point               │
└────────────────────────────────────────────────────────────────┘
                         │ HTTP SSE
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                       FastAPI (api/)                           │
│                                                                │
│  chat.py                                                       │
│   ├─ POST /chat/            (기존, 동기 JSON 응답)              │
│   └─ POST /chat/stream      (신규, text/event-stream)          │
│                                                                │
│  _chat_stream.py            (신규)                              │
│   ├─ run_stream()           async generator                    │
│   ├─ _format_sse()          event/data 직렬화                  │
│   └─ 공통: rate_limit, session_store, tool_dispatch            │
│                                                                │
│  _gemini_client.py                                             │
│   └─ get_client() (async 호출은 client.aio 경로 사용)          │
└────────────────────────────────────────────────────────────────┘
```

## 2. SSE 엔드포인트 설계

### 2.1 경로 및 계약

- **경로**: `POST /chat/stream`
- **요청 본문**: 기존 `ChatRequest` 그대로 재사용 (`query`, `session_id?`)
- **응답**: `text/event-stream`, Chunked, `X-Accel-Buffering: no`, `Cache-Control: no-cache`
- **Rate limit**: 기존 `chat_rate_limiter` (`RATE_LIMIT_CHAT=20/min`) 동일 적용
- **에러 처리**: 스트림 시작 **전** 에러는 HTTP 4xx/5xx JSON, 시작 **후** 에러는 `event: error` 이벤트로 전달 후 연결 종료

### 2.2 이벤트 타입 (SSE)

```
event: meta
data: {"request_id":"...","session_id":"...","model":"gemini-2.5-flash"}

event: tool_call
data: {"name":"get_production_summary","args":{"date_from":"2026-01-01"}}

event: token
data: {"text":"이번 달 총 생산량은 "}

event: token
data: {"text":"1,234 배치이며..."}

event: done
data: {"tools_used":["get_production_summary"],"duration_ms":812,"tokens":{"prompt":...,"response":...}}

event: error
data: {"code":"AI_TIMEOUT","message":"..."}
```

**설계 결정**:
- 토큰 이벤트는 `chunk.text` 를 그대로 흘림 — 프론트엔드는 문자열 concat.
- `tool_call` 은 response의 `automatic_function_calling_history` 를 **지연 방출**: `generate_content_stream` 이 내부에서 툴을 실행하는 특성상, 첫 텍스트 토큰이 도착하기 전에 tool 이벤트를 먼저 송출. (구현 상세: 스트림 iterate 중 `chunk.candidates[0].content.parts` 에 function_call 이 있으면 그 즉시 tool_call 이벤트 방출)
- `done` 이 와야만 클라이언트는 "정상 종료"로 판단한다.

### 2.3 구현 스케치 (`api/_chat_stream.py`)

```python
# api/_chat_stream.py
from __future__ import annotations
import json, time
from typing import AsyncIterator
from fastapi.responses import StreamingResponse
from google.genai import types

from shared.config import GEMINI_MODEL
from ._gemini_client import get_client
from ._tool_dispatch import PRODUCTION_TOOLS
from . import _session_store as _sstore


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_stream(
    query: str,
    session_id: str | None,
    client_ip: str,
    request_id: str,
    system_instruction: str,
) -> AsyncIterator[str]:
    client_obj = get_client()
    if client_obj is None:
        yield _sse("error", {"code": "AI_DISABLED", "message": "Gemini API Key not configured"})
        return

    history = _sstore.get_session_history(session_id, client_ip)
    user_content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
    contents = history + [user_content]

    yield _sse("meta", {"request_id": request_id, "session_id": session_id, "model": GEMINI_MODEL})

    full_text_parts: list[str] = []
    tools_emitted: set[str] = set()
    start = time.perf_counter()

    try:
        stream = await client_obj.aio.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=PRODUCTION_TOOLS,
            ),
        )
        async for chunk in stream:
            # 1. tool_call 감지 (automatic FC 경로에서도 candidates에 parts가 실림)
            for cand in (chunk.candidates or []):
                parts = getattr(cand.content, "parts", None) or []
                for p in parts:
                    fc = getattr(p, "function_call", None)
                    if fc and fc.name and fc.name not in tools_emitted:
                        tools_emitted.add(fc.name)
                        yield _sse("tool_call", {
                            "name": fc.name,
                            "args": dict(fc.args) if getattr(fc, "args", None) else {},
                        })
            # 2. 텍스트 토큰
            text = getattr(chunk, "text", None)
            if text:
                full_text_parts.append(text)
                yield _sse("token", {"text": text})
    except Exception as e:
        yield _sse("error", {"code": type(e).__name__, "message": str(e)[:300]})
        return

    duration_ms = (time.perf_counter() - start) * 1000
    full_text = "".join(full_text_parts)

    if session_id and full_text:
        model_content = types.Content(role="model", parts=[types.Part.from_text(text=full_text)])
        _sstore.save_session_history(session_id, history + [user_content, model_content], client_ip)

    yield _sse("done", {
        "tools_used": sorted(tools_emitted),
        "duration_ms": round(duration_ms, 1),
        "chars": len(full_text),
    })


def streaming_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

### 2.4 `api/chat.py` 추가 라우트

```python
from ._chat_stream import run_stream, streaming_response

@router.post("/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    request_id = get_request_id()
    client_ip = http_request.client.host if http_request.client else "unknown"
    _enforce_rate_limit(client_ip, request_id)      # 기존 함수 재사용
    _cleanup_expired_sessions()
    gen = run_stream(
        query=request.query,
        session_id=request.session_id,
        client_ip=client_ip,
        request_id=request_id,
        system_instruction=_build_system_instruction(),
    )
    return streaming_response(gen)
```

**핵심 재사용**: `_enforce_rate_limit`, `_cleanup_expired_sessions`, `_build_system_instruction`, `ChatRequest`, 세션 스토어 전체.

## 3. Gemini 스트리밍 호출 세부

### 3.1 API 선택

Context7 확인 결과 (`/googleapis/python-genai`):
- `client.aio.models.generate_content_stream(...)` → `async for chunk in stream`
- Automatic Function Calling과 스트리밍 **병용 가능**. SDK가 툴을 실행한 뒤 최종 응답을 청크로 반환.
- `chunk.text` 는 None 일 수 있음 (함수 호출 중간 턴). 항상 None 체크.

### 3.2 리트라이 전략

- 동기 `/chat/` 의 `_generate_with_retry` (3회, exponential+jitter, 15s budget) 는 **스트리밍에는 적용하지 않음**.
- 이유: 스트림 시작 후 중단된 부분 응답을 재전송하면 중복 토큰 발생.
- 대신 **스트림 시작 전**(연결 수립 실패)까지만 재시도. 시작 후 실패는 `event: error` 로 전달 → 클라이언트가 "다시 시도" 버튼 표시.

### 3.3 타임아웃

- 전체 스트림 wall-clock 예산: **45초** (기존 동기 60s 에서 하향 — 스트리밍이므로 UX 체감 빠름)
- asyncio.wait_for 로 감싸지 않고, 마지막 청크 도착 후 15s 무응답 시 강제 종료 (향후 개선 여지, 이번 사이클은 생략 가능)

## 4. 프론트엔드 (Streamlit) 설계

### 4.1 SSE 수신 — `httpx` 사용

`requests` 도 stream=True 가능하나 `httpx.stream()` 이 이벤트 파싱/타임아웃 제어에 더 적합.

```python
# dashboard/components/ai_section.py (발췌)
import httpx

def _parse_sse_line(line: str) -> tuple[str, dict] | None:
    # "event: token" / "data: {...}" 쌍 파싱
    ...

def _stream_chat_tokens(api_url: str, payload: dict):
    """Yield text tokens; side-effect: st.toast on tool_call."""
    with httpx.stream("POST", api_url, json=payload, timeout=60.0) as r:
        r.raise_for_status()
        event_name = None
        for line in r.iter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
                if event_name == "token":
                    yield data["text"]
                elif event_name == "tool_call":
                    st.toast(f"🔧 {data['name']}", icon="⚙️")
                elif event_name == "error":
                    st.error(data.get("message", "스트리밍 오류"))
                    return
                elif event_name == "done":
                    st.session_state["_last_chat_meta"] = data
                    return
```

### 4.2 Streamlit 렌더링 — `st.write_stream`

```python
with st.chat_message("assistant", avatar="🤖"):
    full = st.write_stream(_stream_chat_tokens(
        f"{API_BASE_URL}/chat/stream",
        {"query": latest_prompt, "session_id": st.session_state.get("chat_session_id")},
    ))
    st.session_state.messages.append({"role": "assistant", "content": full})
```

`st.write_stream` 은 제너레이터에서 yield되는 문자열을 자동으로 누적 표시하고 최종 문자열을 반환 (Streamlit ≥ 1.31).

### 4.3 Zero-State 카드 — shadcn

```python
import streamlit_shadcn_ui as sui

col1, col2 = st.columns(2)
with col1:
    if sui.card(
        title="📊 이번 달 제품별 생산 현황",
        content="최근 30일간 제품별 생산량, 배치 수, 점유율",
        key="starter-1",
    ):
        prompt_clicked = "최근 30일간 제품별 생산량, 배치 수, 점유율(%)을..."
```

**폴백 전략**: `streamlit_shadcn_ui` 임포트 실패 시 기존 `st.button` 경로로 자동 폴백 (try/except).

## 5. CSS 토큰 중앙화 — `shared/ui/theme.py`

### 5.1 확장 설계

기존 `apply_custom_css()` 는 pass. 이를 실제 CSS 주입으로 구현:

```python
TOKENS_LIGHT = {
    "--color-primary": "#667eea",
    "--color-primary-hover": "#5568d3",
    "--color-accent": "#764ba2",
    "--color-bg-card": "#ffffff",
    "--color-border": "rgba(102,126,234,0.15)",
    "--color-text": "#1a1a1a",
    "--color-text-muted": "#666",
    "--radius-card": "12px",
    "--shadow-card": "0 2px 8px rgba(0,0,0,0.05)",
    "--shadow-card-hover": "0 4px 12px rgba(102,126,234,0.1)",
}

TOKENS_DARK = {
    ...
    "--color-bg-card": "#1e1e2e",
    "--color-text": "#e0e0e0",
    ...
}

TOKENS_HIGH_CONTRAST = {     # MA-04
    "--color-primary": "#0000ff",
    "--color-text": "#000000",
    "--color-bg-card": "#ffffff",
    "--color-border": "#000000",
    "--shadow-card": "none",
    # WCAG AA 대비율 ≥ 7:1
    ...
}

def apply_custom_css() -> None:
    mode = _resolve_mode()  # "light" | "dark" | "high-contrast"
    tokens = {"light": TOKENS_LIGHT, "dark": TOKENS_DARK, "high-contrast": TOKENS_HIGH_CONTRAST}[mode]
    css_vars = "\n".join(f"  {k}: {v};" for k, v in tokens.items())
    st.markdown(
        f"<style>:root {{\n{css_vars}\n}}\n{_BASE_RULES}\n</style>",
        unsafe_allow_html=True,
    )
```

### 5.2 기존 컴포넌트 마이그레이션 규칙

`ai_section.py`, `kpi_cards.py`, `charts.py` 내 하드코딩된 `#667eea`, `#764ba2` 등을 `var(--color-primary)` 로 교체. **한 커밋**으로 일괄 sed-style 치환.

### 5.3 고대비 토글

```python
# dashboard/app.py 사이드바
with st.sidebar:
    mode = st.radio("표시 모드",
        ["자동", "라이트", "다크", "고대비"],
        horizontal=True, key="theme_mode")
    st.session_state["_theme_mode"] = mode
```

## 6. 파일 변경 계획

### Do 단계에서 변경

| 파일 | 변경 | LOC 영향 |
|------|------|----------|
| `api/_chat_stream.py` | **신규** | +120 |
| `api/chat.py` | `/stream` 라우트 추가 | +15 |
| `shared/ui/theme.py` | 토큰 + apply_custom_css 확장 | +100 |
| `dashboard/components/ai_section.py` | shadcn 카드 + SSE 클라이언트 | +80, -30 |
| `dashboard/components/kpi_cards.py` | 토큰 교체 | +0, ±10 |
| `dashboard/components/charts.py` | 토큰 교체 | +0, ±5 |
| `dashboard/app.py` | 모드 토글, apply_custom_css 호출 | +15 |
| `requirements.txt` | `streamlit-shadcn-ui`, `httpx` (httpx 이미 있을 수 있음 — 확인) | +1~2 |
| `tests/test_chat_stream.py` | **신규** — SSE 파싱, 이벤트 순서, rate limit | +100 |

**총 예상**: +430, -50, 신규 2파일.

### 건드리지 않는 것

- `api/_gemini_client.py`, `api/_session_store.py`, `api/_tool_dispatch.py`, `api/tools.py`
- `shared/metrics.py`, `shared/cache.py` (메트릭은 `/chat/` 만 계측, 스트림은 범위 밖)
- 기존 134+ 테스트

## 7. 테스트 전략

### 7.1 신규 `tests/test_chat_stream.py`

| 테스트 | 검증 항목 |
|--------|-----------|
| `test_stream_meta_first` | 첫 이벤트가 `meta` 여야 함 |
| `test_stream_emits_tokens_and_done` | `token` 이벤트 1개 이상 + `done` 이벤트로 종료 |
| `test_stream_tool_call_event` | 툴이 호출될 쿼리에서 `tool_call` 이벤트 발생 |
| `test_stream_rate_limited` | 20회 초과 시 HTTP 429 (스트림 시작 전 거부) |
| `test_stream_session_persisted` | `session_id` 제공 시 스트림 완료 후 `_sessions` 에 저장됨 |
| `test_stream_error_event_when_client_missing` | `GEMINI_API_KEY` 미설정 시 `event: error` |

**Gemini 모킹**: `_gemini_client.get_client` 반환값을 `AsyncMock` 으로 교체, `aio.models.generate_content_stream` 이 async generator를 돌려주도록 구성.

### 7.2 기존 테스트 영향

- `test_api_integration.py`: 신규 `/chat/stream` 1개 shape 테스트 추가
- 그 외 수정 없음 (기존 `/chat/` 계약 불변)

### 7.3 playwright UI 검증

이전 사이클 패턴 재사용:
1. dashboard 기동 → `/` → AI 탭 이동
2. starter card 클릭 → SSE 스트리밍 토큰이 점진 표시되는지 `browser_snapshot` 3회로 시계열 확인
3. 1024×768 태블릿 리사이즈 재검증
4. 고대비 모드 토글 → axe-core 대비율 검사 (또는 스크린샷 수기 비교)

## 8. 리스크 및 완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| `st.write_stream` 이 Streamlit 버전 미달 | UI 깨짐 | requirements.txt 에서 `streamlit>=1.31` 명시. 이미 최신 사용 중일 가능성 높음 — Do 시작 전 `streamlit --version` 확인 |
| `streamlit-shadcn-ui` 가 최신 Streamlit과 비호환 | 카드 렌더 실패 | try/except 폴백, 임포트 실패 시 기존 `st.button` 경로 |
| Gemini `aio` 가 기존 `to_thread` 동기 경로와 클라이언트 공유 문제 | 세션 얽힘 | `_gemini_client.get_client()` 는 싱글톤 — `client.aio` 는 같은 클라이언트의 attribute 이므로 안전 |
| SSE 중간 끊김 시 세션 history 반쪽 저장 | 잘못된 학습 | 스트림 **완료 `done` 이벤트 이후**에만 `save_session_history` 호출 (설계 §2.3 이미 반영) |
| 고대비 CSS 가 plotly 차트 가독성 저하 | 접근성 역행 | `get_colors()` 반환을 고대비 분기 추가 (차트 템플릿 `"plotly_white"` + 진한 color family) |
| 서드파티 라이브러리 추가로 콜드 스타트 느려짐 | UX 저하 | `streamlit-shadcn-ui` 1개만 추가. `streamlit-extras` 는 이미 쓰고 있지 않다면 **이번 사이클 제외** |

## 9. 마이그레이션 순서 (Do 단계 권장)

1. **SSE 백엔드** (선행, 단독 테스트 가능)
   - `api/_chat_stream.py` 작성
   - `api/chat.py` 라우트 추가
   - `tests/test_chat_stream.py` 작성·통과
   - smoke: `curl -N -X POST http://localhost:8000/chat/stream -H 'Content-Type: application/json' -d '{"query":"이번 달 총 생산량"}'`

2. **CSS 토큰 중앙화** (UI 변경 없이 리팩토링)
   - `shared/ui/theme.py` 토큰 추가 + `apply_custom_css` 구현
   - `dashboard/app.py` 호출
   - 컴포넌트 하드코딩 색상 → `var(--...)` 치환
   - 시각 리그레션 없는지 playwright 스냅샷 비교

3. **Zero-State 카드 shadcn 적용** (시각 변화)
   - `streamlit-shadcn-ui` 설치·임포트·폴백
   - `ai_section.py` starter card만 교체
   - 시각 검증 (스크린샷)

4. **SSE 프론트엔드 연결** (기능 변화)
   - `ai_section.py` 챗 전송 경로를 `/chat/stream` 으로 교체
   - `st.write_stream` 사용
   - 기존 `/chat/` 경로는 fallback으로 유지 (실패 시 자동 전환)

5. **고대비 모드** (접근성)
   - 사이드바 토글
   - `TOKENS_HIGH_CONTRAST` 추가
   - 차트 색 분기

**각 단계마다 `git commit`** — Check 단계에서 gap 추적 용이.

## 10. Success Criteria (Check에서 측정)

- ✅ `POST /chat/stream` 응답이 `text/event-stream`, 이벤트 순서 `meta → [tool_call?]* → token+ → done`
- ✅ 기존 `POST /chat/` 응답 계약 불변 (스냅샷 diff 0)
- ✅ 134+ 기존 테스트 + 신규 ≥6 테스트 통과
- ✅ playwright 데스크탑/태블릿 스냅샷 0 errors
- ✅ CSS 토큰 치환 후 `grep "#667eea" dashboard/components/*.py` 결과 0건 (토큰 var 로 완전 이전)
- ✅ 고대비 모드 활성 시 주요 텍스트/배경 대비율 ≥ 4.5:1 (수기 axe 또는 color-picker)
- ✅ 신규 의존성 ≤ 2개 (`streamlit-shadcn-ui`, 필요 시 `httpx`)

## 11. Non-Goals 재확인

- React/Next.js 교체 — 옵션 3 별도 사이클
- PWA/오프라인 — Streamlit 근본 제약
- 실시간 DB 푸시 — polling 유지
- `streamlit-extras` 전체 도입 — 본 사이클에선 shadcn 1개만
- 리트라이 로직의 스트리밍 확장 — 시작 전만 재시도

## 12. Open Items (Do 직전 확정)

1. **Streamlit 버전 확인**: `pip show streamlit` 으로 ≥1.31 여부 (write_stream)
2. **httpx 설치 여부**: `pip show httpx` — 없으면 requirements.txt 추가
3. **streamlit-shadcn-ui 호환성**: 실제 설치 후 10줄짜리 POC로 카드 렌더 확인
4. **_session_store 의 동기/비동기 혼용**: 현재 스레드-세이프 lock 기반. async 엔드포인트에서 호출해도 안전 (lock은 threading.Lock이지만 run_stream 내부 호출은 짧고 blocking OK)

---

*다음 단계: `/pdca do ui-modernization-streamlit-extras`*
