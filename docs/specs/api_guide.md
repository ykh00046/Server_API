# Production Data Hub - API 사용 가이드

> 대상: API 연동 개발자, 내부 사용자
> 기준 버전: v8 (2026-02-26)
> Base URL: `http://localhost:8000`

---

## 목차

1. [공통 사항](#1-공통-사항)
2. [헬스체크 & Metrics](#2-헬스체크--metrics)
3. [레코드 조회](#3-레코드-조회)
4. [제품 목록](#4-제품-목록)
5. [집계 API](#5-집계-api)
6. [AI Chat](#6-ai-chat)
7. [에러 코드](#7-에러-코드)
8. [Cursor Pagination 가이드](#8-cursor-pagination-가이드)

---

## 1. 공통 사항

### Rate Limiting

| 엔드포인트 | 제한 | 초과 시 |
|-----------|------|---------|
| `POST /chat/` | 20 req/min per IP | 429 + `Retry-After` 헤더 |
| 나머지 전체 | 60 req/min per IP | 429 + `Retry-After` 헤더 |

응답 헤더:
```
X-RateLimit-Remaining: 58
X-Request-ID: a1b2c3d4
Retry-After: 12          # 429 시에만
```

### 응답 형식

- Content-Type: `application/json`
- 인코딩: UTF-8
- 압축: GZip (응답 500 bytes 초과 시 자동)

### 날짜 형식

- 모든 날짜 파라미터: `YYYY-MM-DD` (예: `2026-01-15`)
- `date_from` / `date_to` 모두 **포함(inclusive)**
- 잘못된 형식 → `400 Bad Request`

---

## 2. 헬스체크 & Metrics

### `GET /healthz` — 서버 상태 (경량)

```bash
curl http://localhost:8000/healthz
```

```json
{
  "status": "ok",
  "timestamp": "2026-02-26T03:00:00.000000",
  "database": "connected",
  "db_size_mb": 4.07,
  "archive_db": "available",
  "archive_size_mb": 8.99,
  "ai_api": {
    "key_configured": true,
    "cached_status": "ok",
    "last_check_age_sec": 120
  },
  "cache": {
    "size": 12,
    "maxsize": 200,
    "ttl": 300,
    "db_version": "1740512400_1740512000"
  },
  "disk_free_gb": 45.2
}
```

### `GET /healthz/ai` — AI API 상태 (실제 핑, 10분 캐시)

```bash
curl http://localhost:8000/healthz/ai
```

```json
{
  "status": "ok",
  "message": "Connected, 8 models available",
  "cached": false
}
```

> 쿼터를 소모하므로 자주 호출하지 마세요. 모니터링에는 `/healthz`의 `cached_status`를 사용하세요.

---

### `GET /metrics/performance` — 쿼리 성능 지표

Rolling-window 기반 카운트/평균/p50/p95/p99/cache hit rate 통계를 반환합니다.
모니터링/Grafana 등에서 polling용으로 사용.

```bash
curl http://localhost:8000/metrics/performance
```

```json
{
  "search_items": {
    "count": 142,
    "avg_ms": 12.3,
    "p50_ms": 9.8,
    "p95_ms": 28.4,
    "p99_ms": 41.2,
    "cache_hit_rate": 0.74
  },
  "production_summary": { "...": "..." }
}
```

> Rate-limit 면제 대상이 아니므로 polling 주기는 30s 이상 권장.

---

### `GET /metrics/cache` — 캐시 + 성능 스냅샷

`/healthz`의 `cache` 필드와 동일한 캐시 통계 + `/metrics/performance` 결과를 결합합니다.

```bash
curl http://localhost:8000/metrics/cache
```

```json
{
  "api_cache": {
    "size": 12,
    "maxsize": 200,
    "ttl": 300,
    "db_version": "1740512400_1740512000"
  },
  "performance": {
    "search_items": { "count": 142, "avg_ms": 12.3, "...": "..." }
  }
}
```

> 캐시 강제 무효화 엔드포인트는 제공하지 않습니다. 5분 TTL 자연 만료 또는 서버 재시작을 사용하세요
> (자세한 운영 절차는 `operations_manual.md` §7.4 참고).

---

## 3. 레코드 조회

### `GET /records` — 생산 레코드 목록

날짜 범위에 따라 Archive / Live DB를 자동으로 선택합니다.

**파라미터**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `date_from` | string | - | 시작일 (포함) |
| `date_to` | string | - | 종료일 (포함) |
| `item_code` | string | - | 제품 코드 (완전 일치) |
| `q` | string | - | 제품 코드/이름 검색 (부분 일치) |
| `lot_number` | string | - | 로트 번호 prefix (예: `LT2026`) |
| `min_quantity` | int | - | 최소 생산량 |
| `max_quantity` | int | - | 최대 생산량 |
| `limit` | int | 1000 | 반환 건수 (1~5000) |
| `cursor` | string | - | Cursor Pagination 토큰 (권장) |
| `offset` | int | 0 | 오프셋 (Deprecated, cursor 사용 권장) |

**예제 1: 날짜 범위 조회**
```bash
curl "http://localhost:8000/records?date_from=2026-01-01&date_to=2026-01-31&limit=100"
```

**예제 2: 제품 + 기간 필터**
```bash
curl "http://localhost:8000/records?item_code=BW0021&date_from=2026-02-01&date_to=2026-02-28"
```

**예제 3: 로트 번호 prefix 검색**
```bash
curl "http://localhost:8000/records?lot_number=LT2026&min_quantity=500"
```

**예제 4: Cursor Pagination (대용량)**
```bash
# 첫 페이지
curl "http://localhost:8000/records?limit=1000"

# 다음 페이지 (응답의 next_cursor 사용)
curl "http://localhost:8000/records?limit=1000&cursor=eyJkIjoiMjAyNi0wMS0yMCIsImlkIjoxMjM0NSwic3JjIjoibGl2ZSJ9"
```

**응답**
```json
{
  "data": [
    {
      "source": "live",
      "id": 12345,
      "production_date": "2026-01-20",
      "lot_number": "LT2026001",
      "item_code": "BW0021",
      "item_name": "제품명A",
      "good_quantity": 1500
    }
  ],
  "count": 1000,
  "next_cursor": "eyJkIjoiMjAyNi0wMS0yMCIsImlkIjoxMjM0NSwic3JjIjoibGl2ZSJ9",
  "has_more": true
}
```

| 응답 필드 | 설명 |
|----------|------|
| `data` | 레코드 배열 |
| `count` | 이번 페이지에 반환된 건수 |
| `next_cursor` | 다음 페이지 토큰 (마지막 페이지면 `null`) |
| `has_more` | 다음 페이지 존재 여부 boolean (`next_cursor`와 동치이지만 명시적) |

---

### `GET /records/{item_code}` — 특정 품목 전체 이력

Archive + Live 양쪽에서 최신순으로 조회합니다.

**파라미터**

| 파라미터 | 위치 | 기본값 | 설명 |
|----------|------|--------|------|
| `item_code` | path | (필수) | 제품 코드 |
| `limit` | query | 5000 | 반환 건수 |

```bash
curl "http://localhost:8000/records/BW0021?limit=50"
```

```json
[
  {
    "source": "live",
    "id": 12345,
    "production_date": "2026-02-15",
    "lot_number": "LT2026050",
    "item_code": "BW0021",
    "item_name": "제품명A",
    "good_quantity": 2000
  }
]
```

---

## 4. 제품 목록

### `GET /items` — 제품 목록 (Live DB)

```bash
# 전체 목록
curl "http://localhost:8000/items"

# 검색 (코드 또는 이름 부분 일치)
curl "http://localhost:8000/items?q=BW&limit=50"
```

**응답**
```json
[
  {
    "item_code": "BW0021",
    "item_name": "제품명A",
    "record_count": 342
  }
]
```

> Live DB만 조회합니다. 단종 제품은 포함되지 않을 수 있습니다.

---

## 5. 집계 API

### `GET /summary/monthly_total` — 월별 총생산량

```bash
# 전체 기간
curl "http://localhost:8000/summary/monthly_total"

# 특정 기간
curl "http://localhost:8000/summary/monthly_total?date_from=2025-01-01&date_to=2026-02-28"
```

**응답**
```json
[
  {
    "year_month": "2026-01",
    "total_production": 4072174,
    "batch_count": 215,
    "avg_batch_size": 18940.6
  },
  {
    "year_month": "2025-12",
    "total_production": 3850000,
    "batch_count": 198,
    "avg_batch_size": 19444.4
  }
]
```

---

### `GET /summary/by_item` — 기간 내 제품별 집계

`date_from`, `date_to` 모두 **필수**입니다.

```bash
# 이번 달 전체 제품 집계
curl "http://localhost:8000/summary/by_item?date_from=2026-02-01&date_to=2026-02-28"

# 특정 제품만
curl "http://localhost:8000/summary/by_item?date_from=2026-01-01&date_to=2026-01-31&item_code=BW0021"
```

**응답**
```json
{
  "data": [
    {
      "item_code": "BW0021",
      "item_name": "제품명A",
      "total_production": 850000,
      "batch_count": 42
    }
  ],
  "count": 1,
  "date_range": {
    "from": "2026-02-01",
    "to": "2026-03-01"
  }
}
```

---

### `GET /summary/monthly_by_item` — 월별 제품별 집계

```bash
# 특정 월 전체 제품
curl "http://localhost:8000/summary/monthly_by_item?year_month=2026-01"

# 특정 제품의 월별 이력
curl "http://localhost:8000/summary/monthly_by_item?item_code=BW0021"
```

**파라미터**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `year_month` | - | 형식: `YYYY-MM` (미지정 시 전체) |
| `item_code` | - | 제품 코드 필터 |
| `limit` | 5000 | 최대 50000 |

**응답**
```json
[
  {
    "year_month": "2026-01",
    "item_code": "BW0021",
    "item_name": "제품명A",
    "total_production": 420000,
    "batch_count": 21,
    "avg_batch_size": 20000.0
  }
]
```

---

## 6. AI Chat

### `POST /chat/` — 자연어 쿼리

**Request Body**

```json
{
  "query": "이번 달 BW0021 총 생산량은?",
  "session_id": "optional-session-id"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `query` | ✅ | 질문 (최대 2000자) |
| `session_id` | - | 멀티턴 세션 ID (최대 100자). 같은 ID 재사용 시 대화 맥락 유지. |

**응답**

```json
{
  "answer": "2026년 2월 BW0021(제품명A)의 총 생산량은 42만 개(42건)입니다.",
  "status": "success",
  "tools_used": ["search_production_items", "get_production_summary"],
  "request_id": "a1b2c3d4",
  "model_used": "gemini-2.5-flash"
}
```

| 응답 필드 | 설명 |
|----------|------|
| `answer` | AI 답변 (markdown 표 포함 가능) |
| `status` | `"success"` 또는 `"error"` |
| `tools_used` | 이번 요청에서 호출된 도구명 배열 (순서 보장 X, 중복 제거됨) |
| `request_id` | 추적용 ID (서버 로그와 매칭) |
| `model_used` | 실제 응답에 사용된 모델명. fallback 발동 시 `gemini-2.5-flash-lite`로 보고 |

---

### 멀티턴 대화

같은 `session_id`를 사용하면 이전 대화 맥락을 유지합니다.

```bash
# 1번째 질문
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"query": "BW0021 이번 달 생산량은?", "session_id": "user-001"}'

# 2번째 질문 (맥락 유지)
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"query": "그럼 저번 달이랑 비교하면?", "session_id": "user-001"}'

# 3번째 질문 (같은 세션)
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"query": "최근 10건 이력도 알려줘", "session_id": "user-001"}'
```

**세션 정책**
- TTL: 30분 (마지막 요청 기준, env `CHAT_SESSION_TTL_SEC`)
- 최대 대화 턴: 10턴 (초과 시 오래된 순으로 자동 제거)
- 최대 동시 세션: 1,000개 (env `CHAT_SESSION_MAX_TOTAL`)
- IP 당 최대 세션: 20개 (env `CHAT_SESSION_MAX_PER_IP`)

---

### `POST /chat/stream` — 자연어 쿼리 (SSE 스트리밍)

`POST /chat/`와 동일한 요청 본문을 받지만, 응답을 **Server-Sent Events**로 점진 송신합니다.
대시보드의 `st.write_stream`과 같은 점진 렌더링 UX에 사용.

**Request Body**

```json
{ "query": "이번 달 BW0021 총 생산량은?", "session_id": "user-001" }
```

**응답** (`Content-Type: text/event-stream; charset=utf-8`)

이벤트 순서:

```
event: meta
data: {"session_id": "user-001", "request_id": "a1b2c3d4"}

event: tool_call
data: {"name": "search_production_items", "args": {"keyword": "BW0021"}}

event: token
data: {"text": "BW0021"}

event: token
data: {"text": "(제품명A)의 "}

…

event: done
data: {"model_used": "gemini-2.5-flash", "tools_used": ["search_production_items", "get_production_summary"]}
```

**오류 시**

```
event: error
data: {"code": "timeout", "message": "Stream exceeded 120s budget"}
```

| 에러 코드 | 의미 |
|----------|------|
| `ai_disabled` | `GEMINI_API_KEY` 미설정 |
| `timeout` | 총 스트리밍 시간이 `STREAM_TIMEOUT_SEC` 초과 |
| `model_error` | Gemini API 오류 |
| `rate_limited` | Chat 요청 제한 초과 |
| `internal` | 그 외 내부 오류 |

**스트리밍 정책 (env override 가능)**

| 항목 | 기본값 | env |
|------|--------|-----|
| 청크 간 heartbeat 주기 (`: heartbeat\n\n` 코멘트 프레임) | 10s | `STREAM_HEARTBEAT_SEC` |
| 총 스트림 타임아웃 | 120s | `STREAM_TIMEOUT_SEC` |
| 토큰 버퍼 flush | 50ms | `STREAM_BUFFER_FLUSH_MS` |

**Python 클라이언트 예제 (httpx)**

```python
import httpx
import json

with httpx.stream("POST", "http://localhost:8000/chat/stream",
                  json={"query": "올해 1분기 총 생산량은?", "session_id": "user-001"},
                  timeout=130.0) as r:
    event = None
    for line in r.iter_lines():
        if not line:
            event = None
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:") and event == "token":
            chunk = json.loads(line[5:].strip())
            print(chunk["text"], end="", flush=True)
        elif line.startswith("data:") and event == "done":
            print("\n[done]", json.loads(line[5:].strip()))
```

> Rate-limit은 `POST /chat/`와 동일(20 req/min/IP).

---

### AI 도구 상세 (7개)

AI가 질문을 분석하여 아래 도구들을 자동으로 선택합니다.

---

#### `search_production_items` — 제품 코드 검색

제품 이름이나 키워드로 실제 `item_code`를 찾습니다.
다른 도구를 사용하기 전에 **반드시 먼저 호출**됩니다.

| 파라미터 | 설명 |
|----------|------|
| `keyword` | 검색 키워드 (코드 또는 이름 일부) |
| `include_archive` | 단종 제품 포함 여부 (기본: True) |

**트리거 예시**
```
"P물 제품 코드가 뭐야?"
"에이 시리즈 제품 찾아줘"
"BW로 시작하는 제품들"
"단종된 XX 제품 있어?"
```

---

#### `get_production_summary` — 기간 생산 통계

특정 기간의 총량, 건수, 평균을 반환합니다.

| 파라미터 | 설명 |
|----------|------|
| `date_from` | 시작일 (YYYY-MM-DD) |
| `date_to` | 종료일 (YYYY-MM-DD) |
| `item_code` | 제품 코드 (선택) |

**트리거 예시**
```
"이번 달 총 생산량은?"
"BW0021 1월 생산량 알려줘"
"작년 전체 생산 건수"
"2025년 12월 평균 배치 크기"
```

---

#### `get_monthly_trend` — 월별 생산 추이

기간 내 월별 합산 데이터를 반환합니다.

| 파라미터 | 설명 |
|----------|------|
| `date_from` | 시작일 |
| `date_to` | 종료일 |
| `item_code` | 제품 코드 (선택) |

**트리거 예시**
```
"최근 6개월 월별 생산 추이"
"올해 월별 추이 보여줘"
"BW0021 작년부터 이번 달까지 월별 흐름"
"분기별 생산량 변화"
```

---

#### `get_top_items` — 상위 생산 품목

기간 내 생산량 상위 N개 품목을 반환합니다.

| 파라미터 | 설명 |
|----------|------|
| `date_from` | 시작일 |
| `date_to` | 종료일 |
| `limit` | 반환 개수 (기본: 5) |

**트리거 예시**
```
"이번 달 가장 많이 만든 제품 5개"
"올해 상위 10개 품목 순위"
"작년에 제일 많이 생산한 거 뭐야?"
"생산량 랭킹 알려줘"
```

---

#### `compare_periods` — 두 기간 생산량 비교 ⭐ v8 신규

두 기간의 생산 통계를 비교하여 증감률을 반환합니다.

| 파라미터 | 설명 |
|----------|------|
| `period1_from` | 비교 기준 기간 시작일 (주로 최신 기간) |
| `period1_to` | 비교 기준 기간 종료일 |
| `period2_from` | 이전/기준 기간 시작일 |
| `period2_to` | 이전/기준 기간 종료일 |
| `item_code` | 제품 코드 (선택) |

**반환 데이터**
- `period1`, `period2` 각각의 총량, 건수, 평균
- `quantity_diff`: 생산량 차이 (period1 - period2)
- `change_rate_pct`: 증감률 (%)
- `direction`: "증가" / "감소" / "동일"

**트리거 예시**
```
"이번 달 vs 저번 달 비교"
"전월 대비 생산량 어때?"
"올해 1분기랑 작년 1분기 비교해줘"
"BW0021 이번 달이랑 지난달 차이"
"작년 대비 올해 생산 얼마나 늘었어?"
```

---

#### `get_item_history` — 품목 최근 생산 이력 ⭐ v8 신규

특정 품목의 최근 생산 기록을 최신순으로 반환합니다.
Archive + Live 양쪽을 합쳐서 조회합니다.

| 파라미터 | 설명 |
|----------|------|
| `item_code` | 제품 코드 |
| `limit` | 반환 건수 (기본: 10, 최대: 50) |

**반환 데이터**
- 각 레코드: `production_date`, `lot_number`, `good_quantity`, `source`

**트리거 예시**
```
"BW0021 최근 생산 이력 10건"
"제품 A 마지막으로 생산한 게 언제야?"
"XX 품목 최근 5건 로트번호 알려줘"
"이 제품 최근에 언제 만들었어?"
```

---

#### `execute_custom_query` — 커스텀 SQL

위 도구로 해결 안 되는 복잡한 조건에 사용합니다.

**사용 가능한 테이블/컬럼**
```sql
-- production_records (Live DB)
-- archive.production_records (Archive DB)
-- 사용 가능 컬럼:
production_date, item_code, item_name, good_quantity, lot_number
```

**Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `sql` | string | (필수) | SELECT 쿼리. 값은 `?` placeholder로 표기 |
| `params` | list[string] | `null` | `?` 바인딩 값 (순서대로). 미지정 시 no-bind |
| `description` | string | `""` | 로그용 설명 |

**제약 사항**
- SELECT만 허용 (INSERT/UPDATE/DELETE 불가)
- 세미콜론(`;`) 금지 (multi-statement 방지)
- LIMIT 필수 (미지정 시 자동으로 1000 추가)
- 실행 타임아웃: 환경변수 `CUSTOM_QUERY_TIMEOUT_SEC` 기본 10초
- `params`는 `list[str]`만 허용 (dict/tuple/숫자 원소 거부 → `code: INVALID_PARAMS`)

**파라미터 바인딩 (권장)**

SQL 본문에 값을 직접 박지 말고 `?` placeholder + `params` 배열로 분리하여 인젝션을 방지합니다.
모든 값은 **문자열로 전달**하며, SQLite가 자동으로 컬럼 타입에 맞게 cast합니다.

```json
// 안전한 방식 (권장)
{
  "sql": "SELECT item_code, SUM(good_quantity) AS total FROM production_records WHERE item_code = ? AND production_date >= ? GROUP BY item_code LIMIT 100",
  "params": ["BW0021", "2026-01-20"]
}

// backward compat (literal 포함, 기존 코드 호환)
{
  "sql": "SELECT COUNT(*) FROM production_records WHERE lot_number LIKE 'LT2026%' LIMIT 1"
}
```

> 컬럼명·테이블명·`ASC/DESC` 같은 SQL **식별자**는 placeholder로 쓸 수 없으므로 SQL 본문에 직접 작성하세요.

**트리거 예시**
```
"로트번호가 LT2026으로 시작하고 생산량 1000개 이상인 것만"
"BW0021이랑 BW0022 합산 생산량"
"2025년에 로트번호 A로 시작한 것들 집계"
"날짜별로 여러 제품 비교 분석"
```

---

## 7. 에러 코드

| 상태코드 | 원인 | 응답 예시 |
|---------|------|----------|
| `400` | 잘못된 파라미터 (날짜 형식, 범위 오류) | `{"detail": "Invalid date format: '2026-13-01'. Expected YYYY-MM-DD"}` |
| `429` | Rate Limit 초과 | `{"detail": "Rate limit exceeded. Try again in 12 seconds."}` |
| `500` | 서버 내부 오류 | `{"detail": "Internal server error"}` |

**429 처리 예시 (Python)**
```python
import time
import requests

def chat_with_retry(query, session_id=None, max_retries=3):
    for attempt in range(max_retries):
        resp = requests.post(
            "http://localhost:8000/chat/",
            json={"query": query, "session_id": session_id}
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 10))
            print(f"Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            continue
        return resp.json()
    raise Exception("Max retries exceeded")
```

---

## 8. Cursor Pagination 가이드

대용량 데이터 조회 시 `cursor` 파라미터를 사용하면 `offset` 방식보다 훨씬 빠릅니다.

### 동작 원리

```
1회 요청 → 응답에 next_cursor 포함
2회 요청 → cursor=next_cursor 전달 → 다음 페이지
...
마지막 페이지 → next_cursor: null
```

### Python 예제 — 전체 데이터 순회

```python
import requests

def fetch_all_records(date_from, date_to, page_size=1000):
    url = "http://localhost:8000/records"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "limit": page_size,
    }
    all_records = []

    while True:
        resp = requests.get(url, params=params).json()
        all_records.extend(resp["data"])

        if not resp.get("next_cursor"):
            break
        params["cursor"] = resp["next_cursor"]
        params.pop("date_from", None)  # cursor 사용 시 날짜 파라미터 불필요
        params.pop("date_to", None)

    return all_records

records = fetch_all_records("2026-01-01", "2026-01-31")
print(f"총 {len(records)}건 조회")
```

### offset vs cursor 비교

| 항목 | offset | cursor (권장) |
|------|--------|--------------|
| 10,000건 이후 속도 | 느려짐 | 일정함 |
| 구현 복잡도 | 낮음 | 약간 높음 |
| 데이터 일관성 | 중간 삽입 시 누락 가능 | 안정적 |
| 권장 상황 | 소량 데이터, 테스트 | 프로덕션 전수 조회 |
