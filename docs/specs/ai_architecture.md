# AI Chat System Architecture & Specification

## 1. 개요

본 문서는 `Production Data Hub`의 AI Chat 시스템(`api/chat.py` + 4개 내부 모듈, `api/tools.py`)의
동작 원리, 프롬프트 설계, 도구 명세를 기술합니다. AI 동작을 수정하거나 확장할 때 본 문서를 기준으로 합니다.

> **마지막 갱신**: 2026-04-23 (docs-sync 사이클, v1.6)

---

## 2. 시스템 구성 (Architecture)

### 2.1 모델 정보

| 항목 | 값 | SoT |
|------|------|-----|
| Provider | Google Gemini API (Google GenAI SDK, `google-genai`) | `requirements.txt` |
| Primary Model | `gemini-2.5-flash` | `shared/config.py:GEMINI_MODEL` |
| Fallback Model | `gemini-2.5-flash-lite` (GA, primary와 같은 family) | `shared/config.py:GEMINI_FALLBACK_MODEL` |
| Fallback 트리거 | HTTP 429, 503 | `api/_gemini_client.py:FALLBACK_STATUS_CODES` |
| Mode | Function Calling (Auto) | `api/chat.py` |

> **Note**: Migrated from deprecated `google-generativeai` to unified `google-genai` (2026-01).

### 2.2 핵심 컴포넌트

오케스트레이션 책임을 좁히기 위해 chat 관련 코드는 5개 파일로 분리되어 있습니다.
밑줄(`_`) 접두사는 internal API 의도 (외부 직접 import 비권장).

| 모듈 | 역할 |
|------|------|
| `api/chat.py` | **Orchestrator** — rate-limit, AI guard, /chat/ + /chat/stream 라우터, retry/backoff. 관련 코드는 위임. |
| `api/_gemini_client.py` | GenAI Client factory (lazy init, monkeypatch seam). `is_fallbackable(e)` 분류 로직. |
| `api/_tool_dispatch.py` | `PRODUCTION_TOOLS` 리스트 (Gemini가 읽는 tool registry). |
| `api/_session_store.py` | Multi-turn session in-memory store + TTL 정리 + per-IP 제한. |
| `api/_chat_stream.py` | SSE generator (`run_stream`, `streaming_response`) — heartbeat, timeout, buffer flush. |
| `api/tools.py` | 7개 tool 함수 구현체 (DB 조회). |
| `shared/database.py` (`DBRouter`) | 날짜 범위 → Archive/Live DB 자동 선택, UNION ALL 빌더. |
| Database (SQLite, ro 모드) | `production_analysis.db`(Live, 2026~) + `archive_2025.db`(~2025) |

---

## 3. 프롬프트 엔지니어링 (Prompt Engineering)

### 3.1 시스템 프롬프트 (Persona, 동적)

`api/chat.py:_build_system_instruction()` 함수가 호출 시점의 **오늘 날짜**를 주입하여 매 요청마다 새로 생성합니다.
(이전 버전의 `SYSTEM_INSTRUCTION` 모듈 상수에서 동적 함수로 변경 — 2026-02 이후 신규 사이클.)

> "너는 'Production Data Hub' 시스템의 전문 생산 데이터 분석가야..."

**핵심 원칙:**

1. **데이터 기반:** 반드시 도구(Tool)를 사용하여 조회된 데이터로만 답변한다.
2. **정직함:** 데이터가 없으면 "없다"고 말하고, 가능하면 인접 기간을 추가 조회해 참고 제공.
3. **검색 우선:** 제품명(키워드) 질문 시 `search_production_items`를 먼저 수행한다.
4. **단위/기간 명시:** 수치에는 단위(개, 건)와 기준 기간을 반드시 포함한다.
5. **표 우선:** 데이터 답변은 markdown 표(table)를 사용한다 (번호 리스트 금지).
6. **분석적 해석:** 단순 조회 결과 + 1~2문장 인사이트를 함께 제공한다.

전체 텍스트는 `api/chat.py:106-158`에 정의되어 있습니다.

---

## 4. 도구 명세 (Tools Specification)

`api/_tool_dispatch.py`의 `PRODUCTION_TOOLS` 리스트가 단일 진실 출처(SoT). 현재 7개.

> **외부 사용자용 상세 사용 가이드(트리거 예시 포함)는 `api_guide.md` §6.x 참고.**
> 본 문서는 내부 동작 원리에 초점.

### 4.1 `search_production_items(keyword, include_archive=True)`

- **목적:** 사용자가 불확실한 제품명(예: "P물")을 말했을 때, 정확한 `item_code`를 찾기 위해 사용.
- **동작:** `item_code` 또는 `item_name`에 키워드가 포함된(`LIKE %...%`, `ESCAPE '\\'`) 상위 10개 제품 검색.
- **DB 라우팅:** `include_archive=True`면 archive+live UNION, False면 live만.
- **반환:** 후보 제품 목록 (코드, 이름, 기록 수).

### 4.2 `get_production_summary(date_from, date_to, item_code=None)`

- **목적:** 특정 기간의 생산량 합계, 평균, 건수 조회.
- **DB 라우팅:** `DBRouter.pick_targets(date_from, date_to)`가 ARCHIVE_CUTOFF_DATE(2026-01-01) 기준으로 자동 선택.
- **날짜 정책:** `date_to`를 다음날 00:00 미만(`< next_day`)으로 변환하여 해당 일자 전체 포함.
- **반환:** `total_quantity`, `average_quantity`, `production_count`.

### 4.3 `get_monthly_trend(date_from, date_to, item_code=None)`

- **목적:** 기간 내 월별 합산(생산량, 배치 수) 추이.
- **반환:** `[{year_month, total_production, batch_count}, ...]` (월 오름차순).

### 4.4 `get_top_items(date_from, date_to, limit=5)`

- **목적:** 기간 내 생산량 상위 N개 품목.
- **반환:** `[{item_code, item_name, total_production}, ...]` 내림차순.

### 4.5 `compare_periods(period1_from, period1_to, period2_from, period2_to, item_code=None)`

- **목적:** 두 기간의 생산 통계 비교 ("이번 달 vs 저번 달", "전월 대비" 등).
- **동작:** `concurrent.futures.ThreadPoolExecutor(max_workers=2)`로 두 기간을 병렬 조회.
- **반환:** `period1`, `period2` 각각의 통계 + `comparison.{quantity_diff, change_rate_pct, direction}`.

### 4.6 `get_item_history(item_code, limit=10)`

- **목적:** 특정 품목의 최근 생산 기록 (Archive + Live 합산, 최신순).
- **제약:** `limit` 1~50으로 clamp.
- **반환:** `[{production_date, lot_number, good_quantity, source}, ...]`.

### 4.7 `execute_custom_query(sql, description="")`

- **목적:** 위 6개 도구로 해결 안 되는 복잡한 조건 (Text-to-SQL).
- **다층 보안 검증** (`api/tools.py:524-695`):
  1. `_strip_sql_comments()` — block/line 코멘트 제거 후 검증 (bypass 방지).
  2. 세미콜론 차단 (multi-statement 방지).
  3. `SELECT`로 시작하는지 확인.
  4. **Word-boundary 정규식**으로 forbidden keyword(`DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, REPLACE, PRAGMA, ATTACH, DETACH, VACUUM, REINDEX, EXECUTE, SYSTEM, SCRIPT, JAVASCRIPT, EVAL`) 검출.
  5. Substring 패턴(`LOAD_EXTENSION, SQLITE_, EXEC(`) 검출.
  6. `production_records` 테이블 참조 강제.
  7. `LIMIT` 미지정 시 자동 1000 추가.
- **격리 실행:** dedicated connection + `threading` + `conn.interrupt()` (timeout `CUSTOM_QUERY_TIMEOUT_SEC` 기본 10s).
- **Archive 접근:** `ARCHIVE_DB_WHITELIST`로 ATTACH 경로 검증 (security-and-test-improvement 사이클).

---

## 5. 데이터 처리 규칙 (Data Logic)

### 5.1 날짜 해석

- AI는 "오늘", "작년" 등의 자연어를 시스템 프롬프트의 오늘 날짜를 참조해 `YYYY-MM-DD`로 변환 후 도구에 전달.
- **시스템 규칙 (`shared/validators.py:validate_date_range_exclusive`):**
  - `date_from`: Inclusive (`>=`)
  - `date_to`: Exclusive (`< date_to + 1 day`)

### 5.2 DB 연결 정책

- 모든 도구는 `mode=ro` (Read-Only) 모드로 DB에 연결.
- `ATTACH DATABASE` 구문으로 물리적으로 분리된 연도별 DB를 논리적으로 통합 조회.
- `execute_custom_query`는 ATTACH 경로를 `ARCHIVE_DB_WHITELIST`로 화이트리스트 검증.

### 5.3 LIKE 안전성

- 모든 LIKE 절은 `shared/validators.escape_like_wildcards()` + `ESCAPE '\\'`로 `%`, `_` literal 처리
  (`security-and-test-improvement` 사이클).

---

## 6. Multi-turn 세션 관리

`api/_session_store.py`에서 in-memory dict로 관리.

| 설정 | 기본값 | 환경변수 | SoT |
|------|--------|---------|-----|
| TTL | 1800s (30분) | `CHAT_SESSION_TTL_SEC` | `shared/config.py:85` |
| 최대 동시 세션 | 1000 | `CHAT_SESSION_MAX_TOTAL` | `shared/config.py:87` |
| IP 당 최대 세션 | 20 | `CHAT_SESSION_MAX_PER_IP` | `shared/config.py:86` |
| 세션 당 최대 turn | 10 | (코드 상수) | `_session_store.py:SESSION_MAX_TURNS` |
| Cleanup 주기 | 100 요청마다 | (코드 상수) | `_session_store.py:SESSION_CLEANUP_INTERVAL` |

> **멀티-워커 주의**: in-memory dict이므로 `uvicorn --workers > 1`에서 세션 공유 불가. 단일 워커 운영 권장.

---

## 7. Fallback 정책

`api/_gemini_client.py:is_fallbackable()` 기준:

```
Primary call → 429/503/timeout 발생 →
  retry (BASE_DELAY 1s, exponential, jitter, MAX_RETRIES=3, MAX_TOTAL_DELAY=15s) →
    여전히 실패하면 fallback 모델로 1회 재시도
```

- Fallback 활성 여부: `GEMINI_FALLBACK_ENABLED` (기본 true)
- Fallback 모델: `GEMINI_FALLBACK_MODEL` (기본 `gemini-2.5-flash-lite`)
- 응답에 실제 사용된 모델은 `model_used` 필드로 클라이언트에 노출.

---

## 8. SSE 스트리밍 (`POST /chat/stream`)

`api/_chat_stream.py:run_stream` + `streaming_response`.

이벤트 계약 (메모리 `project_sse_contract.md` 참고):

```
event: meta
data: {"session_id": "...", "request_id": "..."}

event: tool_call            (0회 이상)
data: {"name": "search_production_items", "args": {...}}

event: token                 (1회 이상)
data: {"text": "BW0021은..."}

event: done | error          (마지막)
data: {"model_used": "gemini-2.5-flash", ...} | {"code": "timeout|model_error|...", "message": "..."}
```

| 설정 | 기본값 | 환경변수 |
|------|--------|---------|
| Heartbeat 주기 | 10s | `STREAM_HEARTBEAT_SEC` |
| 총 스트림 타임아웃 | 120s | `STREAM_TIMEOUT_SEC` |
| 토큰 버퍼 flush | 50ms | `STREAM_BUFFER_FLUSH_MS` |

---

## 9. 유지보수 가이드

### 9.1 모델 변경 시

`shared/config.py`의 `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL`을 수정 (또는 `.env` override).
`api/chat.py` 내부에서는 모델명을 직접 박지 않고 import한 상수를 사용.

### 9.2 도구 추가 시

1. `api/tools.py`에 새로운 함수 작성 (Docstring 필수 — Gemini가 schema로 읽음, `from __future__ import annotations` **금지**).
2. `api/_tool_dispatch.py`의 `PRODUCTION_TOOLS` 리스트에 함수 추가.
3. `api/chat.py:_build_system_instruction()` 안의 [데이터 조회 규칙]에 사용 가이드 라인 추가.
4. 본 문서 §4와 `api_guide.md` §6에 새 도구 섹션 추가.
5. `tests/test_tools_*.py`에 mock 기반 단위 테스트 추가.

### 9.3 Fallback / 세션 / SSE 정책 튜닝

`shared/config.py` 상수 또는 `.env`로 override 후 재배포. 코드 변경 불필요.
