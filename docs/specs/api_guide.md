# Production Data Hub - API 사용 가이드

> 대상: API 연동 개발자, 내부 사용자
> 기준 버전: v8 (2026-02-26), 2026-10-05 챗 API 폐지 반영
> Base URL: `http://localhost:8000`

---

## 목차

1. [공통 사항](#1-공통-사항)
2. [헬스체크 & Metrics](#2-헬스체크--metrics)
3. [레코드 조회](#3-레코드-조회)
4. [제품 목록](#4-제품-목록)
5. [집계 API](#5-집계-api)
6. [관리 조작 curl 레시피 (8502 폐지 후)](#6-관리-조작-curl-레시피-8502-폐지-후)
7. [에러 코드](#7-에러-코드)
8. [Cursor Pagination 가이드](#8-cursor-pagination-가이드)

---

## 1. 공통 사항

### Rate Limiting

| 엔드포인트 | 제한 | 초과 시 |
|-----------|------|---------|
| 전체 | 60 req/min per IP | 429 + `Retry-After` 헤더 |

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
  "cache": {
    "size": 12,
    "maxsize": 200,
    "ttl": 300,
    "db_version": "1740512400_1740512000"
  },
  "disk_free_gb": 45.2
}
```

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

## 6. 관리 조작 curl 레시피 (8502 폐지 후)

Server_API 자체 대시보드(8502)가 2026-10에 폐지되면서, 그 화면에서 하던 관리 조작은 API를 직접 호출한다.
조회·Excel·수동 실행 화면은 Dashboard-Raw_material(8503) `/data-hub`가 담당한다.

> **인증:** `API_AUTH_ENABLED=true`인 서버에서는 모든 관리 호출에 `-H "X-API-Key: $KEY"`
> (또는 `-H "Authorization: Bearer $TOKEN"`)가 필요하다. 비활성(기본)이면 헤더를 생략해도 된다.

```bash
BASE=http://localhost:8000
KEY=your-api-key          # API_AUTH_ENABLED=true 일 때만 필요
```

### Webhook 관리 (`/notifications`)

```bash
# 이벤트 카탈로그 (구독 가능한 event_type 목록)
curl -H "X-API-Key: $KEY" "$BASE/notifications/events"

# 등록 — 응답의 secret은 이때 한 번만 노출된다 (HMAC 서명 검증용으로 보관)
curl -X POST "$BASE/notifications/webhooks" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://hooks.example.com/prod", "event_types": ["production.anomaly.volume_drop", "production.anomaly.stale_item"], "description": "이상탐지 알림", "active": true}'

# 목록 / 단건 (active=true|false 필터 선택)
curl -H "X-API-Key: $KEY" "$BASE/notifications/webhooks?active=true"
curl -H "X-API-Key: $KEY" "$BASE/notifications/webhooks/1"

# 수정 — 보낸 필드만 바뀐다 (event_types / description / active)
curl -X PATCH "$BASE/notifications/webhooks/1" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"active": false}'

# secret 회전 — 응답에 새 secret이 한 번만 포함된다
curl -X PATCH "$BASE/notifications/webhooks/1" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"rotate_secret": true}'

# 삭제
curl -X DELETE -H "X-API-Key: $KEY" "$BASE/notifications/webhooks/1"

# 테스트 핑 (구독 event_types·active 여부와 무관하게 이 webhook에만 즉시 발송)
curl -X POST "$BASE/notifications/webhooks/1/test" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"payload": {"ok": true}}'

# 전달 이력 (limit≤500, status 필터, before_id keyset 커서)
curl -H "X-API-Key: $KEY" "$BASE/notifications/webhooks/1/deliveries?limit=50&status=dead"

# 큐 상태
curl -H "X-API-Key: $KEY" "$BASE/notifications/queue/stats"

# 일괄 재시도 — statuses는 "dead"/"failure"만 허용. dry_run=true로 대상부터 확인
curl -X POST "$BASE/notifications/deliveries/bulk-retry" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"statuses": ["dead", "failure"], "webhook_id": null, "limit": 500, "dry_run": true}'

# 단건 재시도
curl -X POST -H "X-API-Key: $KEY" "$BASE/notifications/deliveries/42/retry"
```

### 이상탐지 what-if (`/anomaly`)

| 호출 | 발행(webhook·쿨다운) | 용도 |
|------|----------------------|------|
| `GET /anomaly/scan` | **발행 안 함** (side-effect 0) | 미리보기 + what-if 임계 재판정 |
| `POST /anomaly/scan` | 발행 (기본 `emit=true`) | 수동 발행 트리거. `?emit=false`면 미리보기만 (what-if 파라미터 없음) |

```bash
# 현재 임계치 확인
curl -H "X-API-Key: $KEY" "$BASE/anomaly/rules"

# what-if 미리보기 — GET 전용. 서버 설정·쿨다운 상태는 바뀌지 않는다
# (drop_pct/spike_pct >0, stale_days ≥1, min_baseline_qty ≥0, baseline_days 1~365 — 준 값만 덮어씀)
curl -H "X-API-Key: $KEY" "$BASE/anomaly/scan?drop_pct=30&spike_pct=80&stale_days=5"

# 실제 발행 (운영 정기 발행은 tools/anomaly_watch.py 담당 — 이건 수동 트리거)
curl -X POST -H "X-API-Key: $KEY" "$BASE/anomaly/scan"

# 발행 이력 / 쿨다운 상태
curl -H "X-API-Key: $KEY" "$BASE/anomaly/findings?days=30&limit=200"
curl -H "X-API-Key: $KEY" "$BASE/anomaly/state"
```

### 문서 삭제·복원 (`/{dataset}` — `materials`, `binder`)

`{dataset}`은 `api/materials/datasets.py`에 등록된 prefix(`/materials`, `/binder`)다.

```bash
# 문서 삭제 (문서번호의 모든 품목 행). tombstone이 남아 봇 재전송에도 부활하지 않는다. 없으면 404
curl -X DELETE -H "X-API-Key: $KEY" "$BASE/materials/20261005P001"

# 삭제된 문서(tombstone) 목록 — 최근 삭제순
curl -H "X-API-Key: $KEY" "$BASE/materials/tombstones"

# 복원 — tombstone만 제거한다. 데이터 행은 다음 봇 백업(전체 Excel 재전송) 때 다시 upsert된다. 없으면 404
curl -X POST -H "X-API-Key: $KEY" "$BASE/materials/20261005P001/restore"

# 바인더 데이터셋도 같은 형태
curl -H "X-API-Key: $KEY" "$BASE/binder/tombstones"
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

def get_with_retry(path, params=None, max_retries=3):
    for attempt in range(max_retries):
        resp = requests.get(
            f"http://localhost:8000{path}",
            params=params,
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
