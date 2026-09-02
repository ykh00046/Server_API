# Server_API 감사 버그 수정 실행 지시서 (05)

> **상태: ✅ 완료** (2026-07-15) — F-01a/F-01b/F-02/F-03 5커밋 `main`(2b037e7~9603290) 병합·push, 697 tests green, coverage 88.6%. 각 건 red 재현 후 수정. 운영 반영은 운영 PC `update.bat`+매니저 재시작 별도(주별 x축 "None" 버킷 부재 수동 확인 1건).

> 작성일: 2026-07-12 · 대상: `C:\X\Server_API` · 근거: `docs/Server_API/03-audit.md` F-01/F-02/F-03
> 스코프: 위 3건만. 다른 발견(F-04~F-17)은 이 문서 범위 밖.
> 전제: 기존 테스트 657개 green 유지, coverage floor 88 (CI), ruff 게이트(`F, BLE001, I, UP, B, SIM, E501`) 통과.
> 재확인 방법: 소스 정독 + 프로젝트 `.venv`(google-genai 2.8.0)로 오류 객체·strftime·weakref 실행 검증. **운영 DB는 열지 않았다** (F-02 실데이터 수치는 03 감사의 실측을 인용).

---

## 1. [Critical] F-01 — Gemini 재시도·폴백 전면 사망

### 1.1 진단 재확인 결과 — 확정 (실행 재현)

**(a) 판정 함수의 `.status` 오용 — 재현 완료.** 설치된 google-genai 2.8.0의 `APIError`(`errors.py:31-66`)는:

- `code: int` = HTTP 상태코드
- `status: Optional[str]` = gRPC 스타일 문자열 (`"RESOURCE_EXHAUSTED"`, `"UNAVAILABLE"`)
- `str(e)` = `f"{code} {status}. {details}"` — 메시지에는 코드 숫자가 항상 포함됨

프로젝트 venv에서 실측:

```
e = ClientError(429, {"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED"}})
e.code == 429 (int), e.status == 'RESOURCE_EXHAUSTED'
is_fallbackable(e)      → False   # api/_gemini_client.py:56-65
_is_retryable_error(e)  → (False, 'RESOURCE_EXHAUSTED')   # api/chat.py:160-180
# 반면 테스트 픽스처 형태(status 필드 없음, tests/test_chat_fallback.py:57-69):
e2 = ClientError(429, {"error": {"message": "Too Many Requests"}})
e2.status is None → 'or 0' → 문자열 스캔 경로 → is_fallbackable(e2) → True  # 그래서 테스트만 green
```

핵심 메커니즘: 실제 API 오류 JSON에는 `error.status`가 항상 있으므로 `.status`는 비어 있지 않은 **문자열**이 되고, `status_code == 0` 분기(문자열 스캔)를 건너뛴 채 `"RESOURCE_EXHAUSTED" in {429, 503}` → False. 문자열 스캔 자체는 `str(e)`에 코드가 포함되므로 도달만 하면 동작했을 것 — 즉 `.status` 오용이 유일한 게이트다.

**(b) 스트리밍 폴백 구조적 도달 불가 — 재확인 완료.** `PRODUCTION_TOOLS`(`api/_tool_dispatch.py:20`)는 Python callable 목록 → SDK는 AFC 경로를 탄다. 2.8.0 `aio.models.generate_content_stream`(`models.py:8697~`)은 AFC 경로에서 **HTTP 요청 없이 async generator 객체만 반환**한다 (`await self._generate_content_stream(...)`이 generator 본문 안에 있어 첫 `__anext__`에서 실행됨 — SDK 소스로 확인). 따라서:

- `_open_model_stream`(`api/_chat_stream.py:124-166`)의 `try/except (ClientError, ServerError)`에는 429/503이 절대 도달하지 않는다.
- 오류는 `_consume_stream`(`:213-257`)의 `except Exception`에서 터져 `ERR_INTERNAL` + `str(error)[:500]`이 SSE로 나간다.
- 대시보드(`dashboard/components/ai_section.py:33-39`)의 `_ERROR_MESSAGES["rate_limited"]` 친화 메시지는 **어느 경로에서도 발행되지 않는 죽은 매핑**이다.

결론: 03 감사 진단 그대로 확정. `.status` 버그를 고쳐도 스트리밍은 프라이밍(첫 청크 소비) 없이는 폴백 불가.

### 1.2 수정 대안 비교와 선택

#### (a) 판정 함수

| 대안 | 내용 | 평가 |
|---|---|---|
| A1. `.code`만 사용 | `getattr(e, "code", 0)` | SDK가 code를 못 채우는 비정형 응답(HTML 502 등)에서 다시 0 → 판정 실패 |
| **A2. `.code` 우선 + `.status` 문자열 보조 + 메시지 스캔 최후 (선택)** | 3단 판정을 공용 헬퍼로 통일 | 실오류 형태(1순위), 비정형 응답(2·3순위) 모두 커버. 두 판정 함수의 로직 이중화도 해소 |
| A3. 문자열 스캔만 | `"429" in str(e)` | 오탐 위험(메시지에 우연히 429 포함), 정보 버림 |

**선택: A2.** 공용 헬퍼 `extract_http_code`를 `api/_gemini_client.py`에 두고 `is_fallbackable`과 `chat._is_retryable_error`가 함께 사용한다.

#### (b) 스트리밍 폴백 구조

| 대안 | 내용 | 평가 |
|---|---|---|
| **B1. 첫 청크 프라이밍 (선택)** | `_open_model_stream`이 스트림 열기 + 첫 `__anext__`까지 수행. 그 구간 오류를 폴백 판정 범위로 편입, 첫 청크는 소비 단계에 전달해 재생 | 429/503은 사실상 첫 HTTP 요청(=첫 청크 대기)에서 발생 → 실질 전량 커버. 프레임 방출 전이라 중복 위험 0. `meta.model/fallback` 정확성 유지. 변경 국소적 |
| B2. 전면 재시작 | 소비 중 오류 시 첫 토큰 방출 전이면 폴백 모델로 run 전체 재실행 | `meta`를 첫 청크 뒤로 미뤄야 하고, tool_call 프레임이 이미 나간 경우 "방출 전" 판정이 모호. 상태 관리 복잡 |
| B3. 투명 폴백 래퍼 | `__anext__` 오류를 잡아 내부에서 스트림 교체 | 중간 오류(텍스트 일부 방출 후)에서 답변 중복/절단 의미론 불명확. 디버깅 난해 |

**선택: B1.** 한계와 보완:

- AFC 다중 원격 호출의 2번째 이후 요청에서 터지는 429는 "첫 청크 이후"라 폴백하지 않는다(중간 폴백은 텍스트 중복 위험이 있어 **의도적으로 배제**). 대신 `_consume_stream`의 오류 분류를 개선해 fallbackable 오류는 `ERR_RATE_LIMITED` + 고정 한국어 메시지로 내보낸다 → raw 오류 노출(감사 지적 영향 항목)도 함께 해소.
- 프라이밍 동안(AFC는 도구 실행까지 끝나야 첫 청크가 옴 — 수 초 이상 가능) SSE가 무음이 되면 클라이언트 read timeout(60s, `ai_section.py:99`) 위험 → 프라이밍을 태스크로 띄우고 `STREAM_HEARTBEAT_SEC`(10s) 간격 heartbeat 코멘트를 계속 흘린다. 프라이밍에도 `STREAM_TIMEOUT_SEC` 예산을 적용한다.

### 1.3 파일별 변경 내용 (코드 골격)

#### `api/_gemini_client.py`

```python
FALLBACK_STATUS_CODES = {429, 503}          # 기존 이름 유지 (테스트/문서 호환)
_STATUS_NAME_TO_HTTP = {
    "RESOURCE_EXHAUSTED": 429,   # quota
    "UNAVAILABLE": 503,          # overload
    "INTERNAL": 500,
}

def extract_http_code(e: Exception) -> int:
    """google-genai APIError에서 HTTP 상태코드를 최선-노력으로 추출.

    2.8.0 계약: `.code`가 int HTTP 코드, `.status`는 문자열(RESOURCE_EXHAUSTED 등).
    비정형 응답 대비로 status 문자열 → 메시지 스캔 순으로 폴백한다.
    """
    code = getattr(e, "code", None)
    if isinstance(code, int) and code > 0:
        return code
    status = getattr(e, "status", None)
    if isinstance(status, str):
        mapped = _STATUS_NAME_TO_HTTP.get(status)
        if mapped:
            return mapped
    msg = str(e)                              # 최후 수단 (기존 동작 보존)
    for known in (429, 503, 500):
        if str(known) in msg:
            return known
    return 0

def is_fallbackable(e: Exception) -> bool:
    """429/503(쿼터·과부하)일 때만 모델 폴백."""
    if not isinstance(e, (ClientError, ServerError)):
        return False
    return extract_http_code(e) in FALLBACK_STATUS_CODES
```

#### `api/chat.py` — `_is_retryable_error`

```python
from ._gemini_client import extract_http_code, is_fallbackable

def _is_retryable_error(e: Exception) -> tuple[bool, int]:
    """(is_retryable, http_status_code). 판정은 extract_http_code로 단일화."""
    if not isinstance(e, (ClientError, ServerError)):
        return False, 0
    status_code = extract_http_code(e)
    return status_code in RETRYABLE_STATUS_CODES, status_code
```

(반환 튜플 2번째 요소가 항상 int가 되어 기존 로그 포맷 `status={status_code}` 그대로 유효.)

#### `api/_chat_stream.py` — 프라이밍 구조

```python
@dataclass
class _StreamOpenResult:
    stream: object | None            # aclose 대상 원본 스트림
    aiter: object | None = None      # 이미 __aiter__() 된 이터레이터
    first_chunk: object | None = None  # 프라이밍으로 확보한 첫 청크 (빈 스트림이면 None)
    model: str = ""
    fallback_used: bool = False
    error_frame: str | None = None


async def _open_and_prime(client_obj, model, contents, config):
    """스트림을 열고 첫 청크까지 소비한다.

    AFC(tools=Python callables) 경로에서 SDK는 lazy async generator를 반환하므로
    429/503은 열기가 아니라 첫 __anext__에서 발생한다 — 그 오류를 여기(폴백 판정
    범위)로 당기는 것이 이 함수의 존재 이유다. (google-genai 2.8.0 models.py:8697)
    """
    stream = await client_obj.aio.models.generate_content_stream(
        model=model, contents=contents, config=config,
    )
    aiter = stream.__aiter__()
    try:
        first_chunk = await aiter.__anext__()
    except StopAsyncIteration:
        first_chunk = None               # 빈 스트림: 유효 (done으로 정상 종료)
    except BaseException:
        await _safe_aclose(stream)       # 실패한 프라이밍의 스트림은 즉시 정리
        raise
    return stream, aiter, first_chunk


async def _safe_aclose(stream) -> None:
    aclose = getattr(stream, "aclose", None)
    if aclose is not None:
        with contextlib.suppress(Exception):
            await aclose()


async def _open_model_stream(client_obj, contents, config, request_id, start) -> _StreamOpenResult:
    """기존 골격 유지 — 열기 호출만 _open_and_prime으로 교체."""
    try:
        stream, aiter, first = await _open_and_prime(client_obj, GEMINI_MODEL, contents, config)
        return _StreamOpenResult(stream, aiter, first, model=GEMINI_MODEL)
    except (ClientError, ServerError) as error:
        if not (GEMINI_FALLBACK_ENABLED and is_fallbackable(error)):
            ...  # 기존과 동일: ERR_MODEL_ERROR error_frame (단, _classify_stream_error 사용 권장)
        logger.warning("[ChatStream Fallback] ...")
        try:
            stream, aiter, first = await _open_and_prime(
                client_obj, GEMINI_FALLBACK_MODEL, contents, config)
            return _StreamOpenResult(stream, aiter, first,
                                     model=GEMINI_FALLBACK_MODEL, fallback_used=True)
        except Exception as fallback_error:  # noqa: BLE001 — provider SDK boundary
            ...  # 기존과 동일: error_frame 반환
```

`run_stream` — 프라이밍 동안 heartbeat + 타임아웃 예산:

```python
    open_task = asyncio.ensure_future(
        _open_model_stream(client_obj, contents, config, request_id, start))
    try:
        while True:
            done, _ = await asyncio.wait({open_task}, timeout=STREAM_HEARTBEAT_SEC)
            if done:
                opened = open_task.result()
                break
            if time.perf_counter() - start > STREAM_TIMEOUT_SEC:
                open_task.cancel()
                yield _sse("error", {"code": ERR_TIMEOUT,
                           "message": f"스트리밍 시간 초과 ({int(STREAM_TIMEOUT_SEC)}초)"})
                return
            yield ": heartbeat\n\n"      # SSE 코멘트 — meta 이전에도 안전
    finally:
        if not open_task.done():
            open_task.cancel()           # 클라이언트 절단 시 프라이밍 태스크 회수

    if opened.error_frame:
        yield opened.error_frame
        return
    # meta 이하 기존 흐름. _consume_stream 호출만 시그니처 변경:
    async for frame in _consume_stream(opened, state, request_id, start):
        ...
```

`_consume_stream` — 첫 청크 재생 + 오류 분류 개선:

```python
async def _consume_stream(opened: _StreamOpenResult, state, request_id, start):
    buffer_flush_sec = STREAM_BUFFER_FLUSH_MS / 1000.0
    try:
        if opened.first_chunk is not None:               # 프라이밍 청크 재생
            for frame in _frames_from_chunk(opened.first_chunk, state, buffer_flush_sec):
                yield frame
        async with asyncio.timeout(STREAM_TIMEOUT_SEC), contextlib.aclosing(
            _iter_with_heartbeat(opened.aiter, STREAM_HEARTBEAT_SEC)   # stream 대신 aiter
        ) as heartbeat_iter:
            ...  # 기존과 동일
    except TimeoutError:
        ...  # 기존과 동일
    except Exception as error:  # noqa: BLE001 — SSE provider boundary
        state.failed = True
        code, message = _classify_stream_error(error)    # NEW
        logger.exception("[ChatStream Error] ...")
        yield _sse("error", {"code": code, "message": message})
    finally:
        await _safe_aclose(opened.stream)


def _classify_stream_error(error: Exception) -> tuple[str, str]:
    """중간 스트림 오류 → (SSE code, 사용자 메시지). raw str(error) 노출 제거."""
    if isinstance(error, (ClientError, ServerError)):
        http = extract_http_code(error)
        if http == 429:
            return ERR_RATE_LIMITED, "AI 사용량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."
        return ERR_MODEL_ERROR, f"AI 모델 오류가 발생했습니다. (HTTP {http or 'unknown'})"
    return ERR_INTERNAL, str(error)[:500]
```

`_iter_with_heartbeat`는 첫 줄 `aiter = stream.__aiter__()`를 "인자로 받은 iterator를 그대로 사용"으로 바꾼다 (프라이밍된 iterator를 이어서 소비해야 하므로).

주의: `asyncio.timeout(STREAM_TIMEOUT_SEC)`은 소비 시작 시점 기준이므로 프라이밍 소요와 합치면 최악 2×TIMEOUT까지 늘어난다. 정확한 전체 예산이 필요하면 `STREAM_TIMEOUT_SEC - (time.perf_counter() - start)`로 잔여 예산을 넘긴다 (권장, 1줄).

### 1.4 추가 테스트 (수정 전 red 재현 우선) — `tests/test_chat_fallback.py` 개편 + 신규

**픽스처를 실제 SDK 응답 형태로 교체** (기존 픽스처가 green을 만든 근본 원인 제거):

```python
def _make_429_error():
    """실서비스 응답 형태: error.status 문자열 포함 (google-genai 2.8.0 실측)."""
    return ClientError(429, {"error": {
        "code": 429,
        "message": "Resource has been exhausted (e.g. check quota).",
        "status": "RESOURCE_EXHAUSTED",
    }})

def _make_503_error():
    return ServerError(503, {"error": {
        "code": 503, "message": "The service is currently unavailable.",
        "status": "UNAVAILABLE",
    }})

def _make_500_error():
    return ServerError(500, {"error": {
        "code": 500, "message": "Internal error.", "status": "INTERNAL",
    }})
```

**(t1) SDK 오류 형태 계약 테스트 (신규, 항상 green — SDK 업그레이드 감시용):**

```python
def test_sdk_error_shape_contract():
    """google-genai가 .code(int)/.status(str) 계약을 바꾸면 여기서 먼저 깨진다."""
    e = _make_429_error()
    assert isinstance(e.code, int) and e.code == 429
    assert e.status == "RESOURCE_EXHAUSTED"
    assert "429" in str(e)
```

**(t2) 판정 함수 단위 테스트 (수정 전 red):**

```python
@pytest.mark.parametrize("err,expected", [
    (_make_429_error(), True), (_make_503_error(), True),
    (_make_500_error(), False),
    (ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}}), False),
])
def test_is_fallbackable_real_sdk_shape(err, expected):
    assert is_fallbackable(err) is expected          # 수정 전: 429/503에서 False → red

def test_is_retryable_real_sdk_shape():
    assert _is_retryable_error(_make_429_error()) == (True, 429)   # 수정 전: (False, 'RESOURCE_EXHAUSTED') → red

def test_is_fallbackable_status_absent_shape():
    """비정형 응답(status 없음)도 메시지 스캔으로 여전히 판정 — 하위 호환."""
    assert is_fallbackable(ClientError(429, {"error": {"message": "429 Too Many Requests"}})) is True
```

**(t3) 스트리밍 lazy-오류 구조 테스트 (수정 전 red — 핵심):** 기존 `_FakeAioModels`는 호출 시점에 raise하므로 AFC 실동작과 다르다. lazy 변형을 추가한다.

```python
class _FakeLazyAioModels(_FakeAioModels):
    """AFC 실동작 모사: generate_content_stream은 성공하고, 첫 __anext__에서 오류."""
    async def generate_content_stream(self, *, model, contents, config):
        from shared.config import GEMINI_MODEL
        primary = model == GEMINI_MODEL
        async def _gen():
            if primary and self._primary_exc:
                raise self._primary_exc
            if not primary and self._fallback_exc:
                raise self._fallback_exc
            for chunk in (self._fallback_chunks if not primary
                          else [_FakeChunk(text="primary stream")]):
                yield chunk
        return _gen()

def test_stream_fallback_on_lazy_429(client, monkeypatch):
    """AFC lazy-generator 경로에서도 429 → 폴백 도달 (수정 전: error(internal)로 종료 → red)."""
    fake = _FakeStreamClient(...)  # aio.models를 _FakeLazyAioModels로
    ...
    events = _parse_sse(r.text)
    names = [e[0] for e in events]
    assert "meta" in names and "done" in names
    meta = json.loads(events[names.index("meta")][1])
    assert meta["fallback"] is True
```

**(t4) 보조 테스트 (수정 후 green 확인):**

- lazy 429 + 폴백도 lazy 503 → `error` 이벤트, `meta` 없음.
- 첫 청크 수신 **후** lazy 429 (청크 1개 yield 후 raise) → 폴백하지 않고 `error.code == "rate_limited"`, 메시지에 raw `RESOURCE_EXHAUSTED` details 미포함.
- 빈 스트림(청크 0개) → `meta` + `done`, chars=0, 크래시 없음.
- 기존 eager-raise 테스트(`TestStreamFallback` 기존 3건)는 픽스처만 실형태로 바꿔 유지 — 비-AFC(open 시점 오류) 경로 회귀 방지.
- 기존 sync 테스트(`TestSyncFallback`) 전건은 새 픽스처로 그대로 green이어야 함.

### 1.5 수용 기준

1. (t2)(t3)가 수정 전 red → 수정 후 green (커밋 메시지에 red 재현 기록).
2. 실형태 429/503에서: sync 경로 재시도 로그(`[Chat Retry] ... status=429`) 및 폴백 로그 발생, 응답 `model_used`가 폴백 모델.
3. 스트리밍 경로: lazy 429에서 `meta.fallback == true`; 중간 오류에서 SSE `error.code`가 `rate_limited`/`model_error`로 분류되고 raw `str(error)` 본문이 그대로 노출되지 않음.
4. 프라이밍 대기 중 heartbeat 프레임이 `STREAM_HEARTBEAT_SEC` 간격으로 방출됨 (TestClient로 heartbeat 코멘트 존재 확인).
5. 전체 스위트 green, coverage floor 88 유지 (`api/_chat_stream.py`, `api/_gemini_client.py`는 source 측정 대상), `ruff check` 무경고. `api/chat.py`는 E501 예외 파일이므로 유지.

### 1.6 롤백

- 커밋 2개로 분리: **(c1) 판정 함수 + 픽스처**, **(c2) 스트리밍 프라이밍 구조**. 각각 독립 `git revert` 가능.
- c1만 살아도 sync 폴백·재시도는 부활한다(부분 가치). c2 롤백 시 스트리밍은 현행(폴백 불가) 동작으로 복귀 — 데이터/세션 저장 로직 무변경이라 상태 위험 없음.
- 환경 플래그 불필요: `GEMINI_FALLBACK_ENABLED=false`로 폴백 자체를 끄는 기존 스위치가 운영 중 완화 수단으로 이미 존재.

---

## 2. [High] F-02 — 주별 집계 SQL 전 행 NULL

### 2.1 진단 재확인 결과 — 확정 (형식·파서 실행 검증)

- `dashboard/data.py:298`: `week_expr = "strftime('%Y-W%W', production_date)"`. venv 실측:
  `strftime('%Y-W%W', '2026-01-13 오전 12:00:00')` → **NULL**, `strftime('%Y-W%W', substr(..., 1, 10))` → `'2026-W02'`.
- 소비처는 `dashboard/views/trends.py:117-119` ("주별" 선택 시 `year_week`를 x축으로 사용) 한 곳. `views/products.py:296`의 "주별"은 `charts.py`의 pandas 경로라 무관(정상).
- **형식 변형 가능성 검토**: `_parse_production_dt`(`data.py:72-118`)가 지원하는 형식 전부 — 한국어 `오전/오후`, 영어 `AM/PM`, 24h ISO — 가 **선두 10자는 항상 `YYYY-MM-DD`** 다. 같은 파일의 일별(`substr(...,1,10)`, `data.py:262`)·월별(`substr(...,1,7)`, `data.py:224`) 집계가 운영에서 정상 동작 중이라는 사실이 라이브·아카이브 공히 선두-ISO 형식임을 방증한다 (03 감사의 실데이터 실측: 라이브 1,542행·아카이브 25,587행 전량 한국어 오전/오후 형식, 22자 고정). 운영 DB 직접 재조회는 이번 작업 제약상 하지 않음 — 감사 실측을 근거로 채택.
- **pandas와의 주 경계 동등성 검증 완료**: SQLite `%W`와 Python(pandas) `%W`를 2024-12-23부터 800일 전수 비교 → **불일치 0건** (연 경계 포함). 둘 다 "월요일 시작, 첫 월요일 이전은 W00" 규칙.

### 2.2 수정 대안 비교와 선택

| 대안 | 내용 | 평가 |
|---|---|---|
| **A. SQL 수준 파싱 (선택)** — `strftime('%Y-W%W', substr(production_date, 1, 10))` | 1줄 수정 | 같은 파일의 일별 집계와 동일 관례. 집계가 DB 안에서 끝남(아카이브 25,587행을 앱으로 안 끌고 옴). 캐시(`@st.cache_data ttl=180`)·호출부 무변경. pandas `%W`와 규칙 동일함을 실측으로 확인 |
| B. Python 후처리 — 일별 집계를 불러와 pandas로 주 버킷 재집계 | `_parse_production_dt` 재사용 | 코드량 증가, 집계 로직이 SQL/pandas 이원화, Streamlit 프로세스로 연산 이동. 형제 로더(일별·월별)와 구조 불일치 |
| C. 정규화 날짜 컬럼 추가 | 스키마 변경 | ERP가 소유한 데이터 파일에 손대는 것 — 스코프 밖, 과대 수술 |

**선택: A.** 부가 규칙: 선두 10자가 날짜가 아닌 이상행은 `strftime`이 NULL을 반환해 NULL 버킷 1개로 모인다 — 이는 일별 뷰(`substr` 결과가 그대로 노출됨)와 동급의 관측 가능한 실패 모드이므로 별도 가드는 추가하지 않는다(현 데이터에서 미발동, F-16과 함께 후속).

### 2.3 파일별 변경 내용 (코드 골격)

#### `dashboard/data.py`

```python
# 모듈 수준으로 승격 (테스트에서 동일 식을 import하기 위한 SSOT —
# P1-2 shared/queries.py 통합 시 그쪽으로 이동)
# %W(월요일 시작 주번호): charts.py의 pandas strftime('%Y-W%W')와 동일 규칙.
# production_date는 '2026-01-13 오전 12:00:00' 형태라 strftime에 직접 넣으면
# NULL — 일별 집계와 동일하게 선두 10자(YYYY-MM-DD)만 잘라 넘긴다.
WEEK_BUCKET_EXPR = "strftime('%Y-W%W', substr(production_date, 1, 10))"
```

`load_weekly_summary` 내부(`:296-298`):

```python
    week_expr = WEEK_BUCKET_EXPR
```

(그 외 변경 없음. `views/trends.py`, `charts.py` 무변경.)

### 2.4 추가 테스트 (수정 전 red 재현 우선) — 신규 `tests/test_weekly_bucket.py`

conftest의 `_SEED_ROWS`는 `"2026-03-01"` 같은 **날짜-only 형식**이라 이 버그를 재현할 수 없다(감사가 지적한 "테스트-실환경 형태 불일치" 패턴 그대로). 실형식 전용 픽스처를 이 테스트 파일에 둔다.

```python
REAL_FORMAT_ROWS = [  # 실데이터 형식: 한국어 오전/오후, 22자
    ("2026-01-05 오전 12:00:00", "BW0021", "블루 렌즈", 100, "L1"),  # 2026-W01 (1/5 월)
    ("2026-01-07 오후 03:30:00", "BW0021", "블루 렌즈", 200, "L2"),  # 2026-W01
    ("2026-01-13 오전 12:00:00", "AA0001", "그린 렌즈", 300, "L3"),  # 2026-W02
    ("2026-01-01 오전 12:00:00", "CC0003", "레드 렌즈",  50, "L4"),  # 2026-W00 (첫 월요일 이전)
]
```

**(t1) SQL 특성화 테스트 (수정 전 red):** 임시 live DB에 위 행을 넣고, `DBRouter.build_aggregation_sql`에 `dashboard.data.WEEK_BUCKET_EXPR`을 넣어 실행:

```python
def test_weekly_bucket_expr_on_real_format(tmp_live_db_real_format):
    from dashboard.data import WEEK_BUCKET_EXPR
    sql, _ = DBRouter.build_aggregation_sql(
        inner_select=f"{WEEK_BUCKET_EXPR} AS year_week, SUM(good_quantity) AS total_prod, COUNT(*) AS cnt",
        inner_where="1=1", outer_select="year_week, SUM(total_prod) AS total_production, SUM(cnt) AS batch_count",
        outer_group_by="year_week", targets=DBTargets(use_archive=False, use_live=True),
        outer_order_by="year_week")
    rows = ...  # 실행
    assert [r["year_week"] for r in rows] == ["2026-W00", "2026-W01", "2026-W02"]
    # 수정 전: [None] 단일 버킷 (total=650) → red
    assert {r["year_week"]: r["total_production"] for r in rows} == {
        "2026-W00": 50, "2026-W01": 300, "2026-W02": 300}
```

**(t2) pandas 경로와의 수치 일치 (수용 기준 직결):** 같은 행을 DataFrame으로 만들어 `charts.py` 규칙(`_parse_production_dt` → `.dt.strftime('%Y-W%W')` → groupby sum)으로 집계한 결과가 (t1)의 SQL 결과와 버킷·합계 모두 동일함을 assert.

**(t3) 형식 혼재 내성:** 한국어/영어 AM-PM/24h ISO 세 형식이 섞인 행에서도 같은 날짜는 같은 버킷으로 묶임.

**(t4) 아카이브 경계:** `live_and_archive_db` 변형(아카이브에 2025-12-29~31, 라이브에 2026-01-01~) — 아카이브 행은 `2025-W52`, 라이브 행은 `2026-W00`으로 분리 집계됨(pandas 규칙과 동일, 연도 접두사 때문에 경계 주가 갈라지는 것은 **양쪽 공통의 기존 규칙**임을 특성화).

배치: `dashboard/data.py`는 coverage omit 목록에 있으므로 floor에 영향 없음. 테스트는 `WEEK_BUCKET_EXPR` 상수와 DBRouter만 사용하므로 Streamlit 런타임 불필요(모듈 import는 bare mode로 무해).

### 2.5 수용 기준

1. (t1)이 수정 전 red(단일 NULL 버킷) → 수정 후 green.
2. (t2)로 **pandas 기반 차트 페이지(charts.py 규칙)와 SQL 주별 집계의 버킷·합계 일치**가 테스트로 고정됨.
3. 수동 확인(운영 배포 후): 생산 추세 페이지 "주별" 선택 시 x축이 `YYYY-Www` 버킷들로 렌더되고 "None" 버킷이 없음. 같은 기간 제품 차트(주별)와 총합 일치.
4. 전체 스위트 green, ruff 무경고. (data.py 상수 승격은 E501 100자 이내 유지.)

### 2.6 롤백

- 단일 커밋, 1줄+상수 승격 — `git revert` 즉시 원복. 데이터 마이그레이션 없음, 캐시는 TTL 180s로 자연 만료(즉시 필요 시 대시보드 재시작).

---

## 3. [High] F-03 — SQLite 연결 영구 누수

### 3.1 진단 재확인 결과 — 확정 + **감사 수정안 일부 실현 불가 판명**

- `shared/database.py:174-180`: 연결을 thread-local에 캐시하고 `_all_connections`(`shared/_db_connection.py:22`)에 강참조 append. 제거 경로는 `_discard_connection`(같은 스레드에서 mtime 변경/죽은 연결 감지 시)과 atexit뿐 — 확인.
- Streamlit rerun-당-새-스레드, `compare_periods`(`api/tools/summary.py:306-310`)의 호출-당-새-`ThreadPoolExecutor(max_workers=2)` — 확인. 반면 FastAPI 도구 실행은 `asyncio.to_thread`(공유 기본 executor, 장수 스레드)라 캐시가 의도대로 동작 — 즉 누수는 Streamlit 대시보드와 `compare_periods` 두 경로에 집중된다.
- **추가 실측 1 — WeakSet 불가**: `weakref.ref(sqlite3.Connection)` → `TypeError: cannot create weak reference to 'sqlite3.Connection' object`. 감사의 "weakref.WeakSet 전환" 제안은 **그대로는 구현 불가** (subclass factory를 쓰면 가능하지만 아래 대안 비교 참조).
- **추가 실측 2 — 현행 atexit 정리도 사실상 무력**: 기본 `check_same_thread=True` 연결은 **타 스레드에서 `close()`조차 `sqlite3.ProgrammingError`를 던진다**. `_cleanup_all_connections`(`_db_connection.py:29-36`)의 `suppress(sqlite3.Error)`가 이를 조용히 삼키므로, 타 스레드 연결은 atexit에서도 실제로는 닫히지 않는다. (누수의 심각성을 한 단계 높이는 사실 — 정리 경로가 "적다"가 아니라 "메인 스레드 것 말고는 없다".)

### 3.2 수정 대안 비교와 선택

캐시의 존재 이유(스레드마다 자기 연결 = 동시성 안전 + PRAGMA/mmap 설정 1회 상각)는 보존해야 한다.

| 대안 | 내용 | 평가 |
|---|---|---|
| A. WeakSet (+ Connection subclass factory로 weakref 가능화) | GC가 죽은 스레드의 연결을 수거 | 구현은 가능하나 (1) close 시점이 GC 의존 — Windows에서 열린 ro 핸들이 ERP 파일 교체를 막는 문제의 해소 시점을 보장 못 함, (2) atexit cross-thread close 무력 문제를 그대로 둠, (3) subclass factory는 우회 트릭이라 의도 가독성 낮음 |
| **B. 소유 스레드 추적 + 명시적 sweep (선택)** | 연결마다 `weakref.ref(owner_thread)`를 기록(Thread는 weakref 가능), **새 연결 생성 시점마다** 죽은 스레드의 연결을 close+제거. 연결은 `check_same_thread=False`로 생성해 cross-thread close를 합법화 | 결정적 close(핸들 즉시 반납), atexit 정리도 실제 동작하게 됨, 테스트 가능성 최고. sweep 비용은 O(레지스트리 크기)인데 레지스트리는 "살아있는 스레드 수 × 캐시 키(≤4)"로 유계 |
| C. 캐시 제거 + 매 호출 연결/close | 구조 최단순 | 호출부 수십 곳이 `with DBRouter.get_connection(...)`인데 sqlite3의 `with`는 **트랜잭션 관리일 뿐 close가 아님** → 전 호출부 사용 방식 변경 필요. 쿼리마다 PRAGMA(mmap 256MB 등) 재설정 비용. 과대 수술 |
| D. Streamlit만 `st.cache_resource` 연결로 교체 | 대시보드 국소 해결 | `compare_periods` 누수 잔존, 연결 관리 아키텍처 이원화 |

**선택: B.** `check_same_thread=False`의 안전 논거: 연결의 배포 경로는 thread-local 캐시 하나뿐이라 **사용은 항상 소유 스레드에서만** 일어난다. cross-thread 접근은 "이미 죽은 스레드의 연결을 close"하는 sweep/atexit뿐이며, 그 시점엔 소유 스레드가 없어 경합 자체가 불가능하다. 이 불변식을 docstring으로 고정한다.

`compare_periods`: 호출-당 executor를 **순차 실행으로 교체**. 근거 — 두 쿼리는 소스별 사전집계(pre-aggregate) SQL이라 수십 ms 수준이고, `@api_cache`(TTL 5분)가 반복 호출을 흡수하므로 병렬 이득 < 스레드 2개·연결 2개 생성 비용. (지연이 실측으로 문제되면 모듈 수준 공유 executor가 차선 — 스레드가 장수하므로 sweep과도 양립.)

### 3.3 파일별 변경 내용 (코드 골격)

#### `shared/_db_connection.py`

```python
# _all_connections(list) → 소유 스레드를 함께 기록하는 레지스트리로 교체.
# key: id(conn). Thread 객체는 weakref 가능하므로 약참조로 잡아
# 레지스트리가 스레드 수명을 연장하지 않게 한다.
_conn_registry: dict[int, tuple[weakref.ref, sqlite3.Connection]] = {}
_connection_lock = threading.Lock()


def _register_connection(conn: sqlite3.Connection) -> None:
    with _connection_lock:
        _conn_registry[id(conn)] = (weakref.ref(threading.current_thread()), conn)


def _sweep_dead_thread_connections() -> int:
    """소유 스레드가 죽은 연결을 close하고 레지스트리에서 제거.

    Streamlit은 rerun마다 새 ScriptRunner 스레드를 만들므로 죽은 스레드의
    thread-local 연결은 스스로 _discard_connection될 기회가 없다 — 새 연결을
    만드는 스레드가 대신 청소한다(생성 경로에서만 호출되므로 비용은 유계:
    레지스트리 크기 ≈ 살아있는 스레드 수 × 캐시 키 수).
    연결이 check_same_thread=False로 생성되므로 cross-thread close가 합법.
    """
    to_close: list[sqlite3.Connection] = []
    with _connection_lock:
        for key, (thread_ref, conn) in list(_conn_registry.items()):
            owner = thread_ref()
            if owner is None or not owner.is_alive():
                to_close.append(conn)
                del _conn_registry[key]
    for conn in to_close:                      # I/O는 락 밖에서
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    if to_close:
        logger.debug(f"Swept {len(to_close)} connection(s) from dead threads")
    return len(to_close)


def _cleanup_all_connections() -> None:
    """atexit: 남은 연결 전부 close (check_same_thread=False라 이제 실제로 닫힘)."""
    with _connection_lock:
        conns = [c for _, c in _conn_registry.values()]
        _conn_registry.clear()
    for conn in conns:
        with contextlib.suppress(sqlite3.Error):
            conn.close()


def _discard_connection(conn: sqlite3.Connection) -> None:
    """(기존 역할 유지) close 후 레지스트리에서 제거 — list.remove → dict pop."""
    with contextlib.suppress(sqlite3.Error):
        conn.close()
    with _connection_lock:
        _conn_registry.pop(id(conn), None)
```

#### `shared/database.py` — `get_connection`

```python
        # check_same_thread=False: 연결은 thread-local로만 배포되어 사용은 항상
        # 소유 스레드에서 일어난다. cross-thread 접근은 죽은 스레드 연결의
        # close(sweep/atexit)뿐 — F-03 참조.
        conn = sqlite3.connect(db_uri, uri=True, timeout=DB_TIMEOUT, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragma_settings(conn)
        ...
        setattr(_local, cache_key, conn)
        setattr(_local, mtime_key, current_mtime)
        _register_connection(conn)
        _sweep_dead_thread_connections()   # 새 연결 생성 시점 = 청소 시점
        return conn
```

re-export 정리: `shared/database.py:28-35`의 `_all_connections` import를 `_conn_registry`/`_register_connection`/`_sweep_dead_thread_connections`로 교체 (`_all_connections` 참조처는 이 re-export뿐임을 grep으로 확인 — 테스트는 `_local`만 접근).

#### `api/tools/summary.py` — `compare_periods`

```python
            # (P1-1의 병렬화 롤백) 두 쿼리는 소스별 사전집계라 수십 ms 수준 —
            # 호출마다 ThreadPoolExecutor(스레드 2 + thread-local 연결 2)를 만들던
            # 비용/누수가 병렬 이득보다 컸다 (03-audit F-03).
            r1 = _query_stats(p1_from, p1_next)
            r2 = _query_stats(p2_from, p2_next)
            ql.set_row_count(2)
```

`import concurrent.futures` 제거 (ruff F401이 잡아줌).

### 3.4 추가 테스트 (수정 전 red 재현 우선) — 신규 `tests/test_db_connection_lifecycle.py`

**(t1) 죽은 스레드 연결 누적 재현 (수정 전 red):**

```python
def test_dead_thread_connections_are_swept(live_db):
    from shared import _db_connection as dbc

    held: list = []
    def worker():
        held.append(DBRouter.get_connection(use_archive=False))

    for _ in range(5):
        t = threading.Thread(target=worker)
        t.start(); t.join()

    DBRouter.get_connection(use_archive=False)   # 메인 스레드: 생성 → sweep 트리거

    with dbc._connection_lock:
        owners = [ref() for ref, _ in dbc._conn_registry.values()]
    assert all(o is not None and o.is_alive() for o in owners)   # 수정 전 상당: _all_connections에 6개 누적 → red
    # 죽은 스레드의 연결이 '실제로' 닫혔는지 (등록만 지운 게 아니라):
    with pytest.raises(sqlite3.ProgrammingError):
        held[0].execute("SELECT 1")
```

(수정 전 기준 red 형태: `len(dbc._all_connections)`가 스레드 수만큼 증가하고 `held[0].execute`가 성공 — 누수를 그대로 증명. 커밋 순서상 red 버전을 먼저 작성해 실패를 기록한 뒤 구현과 함께 green 버전으로 확정.)

**(t2) 캐시 의미 보존:** 같은 스레드에서 `get_connection` 2회 → 동일 객체(identity). mtime 변경 후 → 새 객체 + 이전 연결은 레지스트리에서 제거(기존 `_discard_connection` 경로 회귀 방지 — `test_db_router.py`의 기존 테스트와 중복되면 그쪽에 위임).

**(t3) sweep이 산 스레드 연결을 건드리지 않음:** 살아있는 worker 스레드(Event로 대기)가 보유한 연결은 sweep 후에도 레지스트리에 남고 `execute` 가능.

**(t4) atexit 정리 실효성:** `_cleanup_all_connections()` 직접 호출 후 모든 등록 연결이 closed (수정 전에는 타 스레드 연결이 ProgrammingError로 살아남음 — red 재현 가능).

**(t5) compare_periods 스레드 미증가 + 결과 동일:**

```python
def test_compare_periods_no_thread_spawn(live_db):
    before = threading.active_count()
    res = compare_periods("2026-03-01", "2026-03-31", "2026-04-01", "2026-04-30")
    assert res["status"] == "success"
    assert res["period1"]["total_quantity"] == 300   # 시드 데이터 기준 특성화
    assert threading.active_count() == before
```

기존 `test_ai_tools_db.py`의 `compare_periods` 결과 테스트는 무변경 green이어야 함(수치 계약 유지 증명).

conftest 상호작용: `_close_db_connections`/`_drop_thread_local_conns`는 `_local`만 만지므로 무변경으로 호환. 필요 시 teardown에 `_conn_registry.clear()` 한 줄 추가(테스트 간 오염 방지).

### 3.5 수용 기준

1. (t1)(t4)가 수정 전 red → 수정 후 green.
2. 반복 부하 시뮬레이션(스레드 생성/종료 × 100 사이클, 각 사이클에서 `get_connection`) 후 **레지스트리 크기 ≤ 살아있는 스레드 수 × 4(캐시 키 조합)** — 테스트로 고정.
3. 죽은 스레드의 연결은 다음 연결 생성 시점에 **실제 close**(파일 핸들 반납)됨 — Windows에서 pytest tmp_path 삭제 PermissionError 감소로도 간접 관측.
4. `compare_periods`: 결과 수치 기존과 동일(기존 테스트 green), 호출당 신규 스레드 0, 응답 지연 회귀는 로그 duration 기준 +50ms 이내(사전집계 쿼리 2개 직렬화 비용).
5. 전체 스위트 green, coverage floor 88 유지(`shared/_db_connection.py`는 측정 대상 — sweep 분기 테스트 포함), ruff 무경고.

### 3.6 롤백

- 커밋 2개로 분리: **(c1) 레지스트리+sweep+check_same_thread**, **(c2) compare_periods 순차화**. 독립 revert 가능.
- c1 롤백 시 현행(누수) 동작으로 복귀 — 기능 불변, 데이터 위험 없음(연결은 read-only 위주, 쓰기 경로도 트랜잭션 의미론 무변경).
- `check_same_thread=False`가 예기치 않은 cross-thread 사용을 노출(오류 은폐)하는 것이 우려되면: 롤백 대신 디버그 환경 변수로 `check_same_thread`를 되돌려 관측하는 방법이 있으나, thread-local 배포 불변식상 필요성은 낮다 — 스펙은 주석 문서화로 갈음.

---

## 4. 권장 실행 순서와 소요 추정

| 순서 | 작업 | 내용 | 추정 |
|---|---|---|---|
| 1 | **F-01a** 판정 함수 + 실형태 픽스처 | `extract_http_code` + `is_fallbackable`/`_is_retryable_error` 교체, test_chat_fallback 픽스처 개편, (t1)(t2) | 0.5일 |
| 2 | **F-02** 주별 집계 | `WEEK_BUCKET_EXPR` 승격+substr, test_weekly_bucket 신규 | 0.5일 |
| 3 | **F-01b** 스트리밍 프라이밍 | `_open_and_prime`/heartbeat 루프/`_classify_stream_error`, lazy 픽스처 (t3)(t4) | 1~1.5일 |
| 4 | **F-03** 연결 수명 | 레지스트리+sweep+atexit 교정, compare_periods 순차화, lifecycle 테스트 | 1일 |

- 합계 **약 3~3.5일** (리뷰·CI 왕복 제외).
- 순서 근거: ①은 Critical의 절반(동기 경로 폴백·재시도)을 최소 diff로 즉시 부활시키고 이후 작업의 판정 헬퍼를 먼저 확보한다. ②는 1줄 수정의 즉효 건으로 사이에 끼워 리스크 없이 출하. ③은 스트리밍 제너레이터 구조 변경이라 별도 리뷰 사이클이 필요. ④는 스레드 시나리오 테스트 작성이 본체라 마지막.
- 각 단계는 독립 커밋/독립 revert 가능하도록 위 롤백 절의 커밋 분할(c1/c2)을 지킨다.
- 공통 게이트: 각 단계에서 `ruff check .` → `pytest`(로컬, flaky 2건 제외 관례) → CI coverage floor 88 확인. red 재현 테스트는 "실패하는 상태"를 커밋 메시지나 PR 본문에 기록한 뒤 구현 커밋과 함께 green으로 만든다.
