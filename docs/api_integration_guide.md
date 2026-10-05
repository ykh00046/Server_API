# Production Data Hub API 통합 가이드

> 다른 프로젝트에서 Production Data Hub API를 사용하기 위한 통합 안내서

---

## 목차

1. [개요](#1-개요)
2. [빠른 시작](#2-빠른-시작)
3. [API 엔드포인트](#3-api-엔드포인트)
4. [코드 예제](#4-코드-예제)
5. [페이지네이션](#5-페이지네이션)
6. [관리 조작 curl 레시피 (8502 폐지 후)](#6-관리-조작-curl-레시피-8502-폐지-후)
7. [에러 처리](#7-에러-처리)
8. [모범 사례](#8-모범-사례)
9. [Rate Limiting](#9-rate-limiting-new)
10. [FAQ](#10-faq)

---

## 1. 개요

### 1.1 API 소개

Production Data Hub API는 생산 데이터를 조회하고 분석하기 위한 REST API입니다.

**주요 기능:**
- 생산 레코드 조회 및 검색
- 제품 목록 조회
- 월별/제품별 집계 데이터
- 관리 조작 API (webhook·이상탐지·문서 삭제/복원 — [6장](#6-관리-조작-curl-레시피-8502-폐지-후))

### 1.2 기본 정보

| 항목 | 값 |
|------|-----|
| Base URL | `http://{서버주소}:8001` |
| 프로토콜 | HTTP/HTTPS |
| 데이터 형식 | JSON |
| 인코딩 | UTF-8 |
| 인증 | 없음 (내부 네트워크 전용) |

### 1.3 응답 형식

모든 API 응답은 JSON 형식입니다:

```json
// 성공 응답
{
  "data": [...],
  "count": 100,
  "has_more": true,
  "next_cursor": "eyJkIjogIjIwMjYtMDEtMjAiLCAiaWQiOiAxMDB9"
}

// 에러 응답
{
  "detail": "에러 메시지"
}
```

---

## 2. 빠른 시작

### 2.1 연결 테스트

```bash
# API 상태 확인
curl http://localhost:8001/

# 응답
{"status":"active","system":"Production Data Hub API"}
```

### 2.2 첫 번째 요청

```bash
# 최근 생산 레코드 10건 조회
curl "http://localhost:8001/records?limit=10"
```

### 2.3 Python 예제

```python
import requests

BASE_URL = "http://localhost:8001"

# 생산 레코드 조회
response = requests.get(f"{BASE_URL}/records", params={"limit": 10})
data = response.json()

for record in data["data"]:
    print(f"{record['production_date']} | {record['item_name']} | {record['good_quantity']}")
```

---

## 3. API 엔드포인트

### 3.1 상태 확인

#### `GET /`
API 상태 확인

**응답:**
```json
{"status": "active", "system": "Production Data Hub API"}
```

---

#### `GET /healthz`
상세 헬스 체크 (DB, 캐시 상태 포함)

**응답:**
```json
{
  "status": "healthy",
  "database": "connected",
  "cache": {
    "items": 15,
    "max_size": 200
  }
}
```

---

### 3.2 생산 레코드 조회

#### `GET /records`
생산 레코드 목록 조회

**쿼리 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `item_code` | string | X | - | 제품 코드로 필터링 |
| `q` | string | X | - | 제품명/코드 검색 (부분 일치) |
| `lot_number` | string | X | - | 로트 번호 필터 (prefix 매칭) **NEW** |
| `date_from` | string | X | - | 시작일 (YYYY-MM-DD) |
| `date_to` | string | X | - | 종료일 (YYYY-MM-DD) |
| `min_quantity` | int | X | - | 최소 생산량 **NEW** |
| `max_quantity` | int | X | - | 최대 생산량 **NEW** |
| `limit` | int | X | 1000 | 조회 건수 (1-5000) |
| `cursor` | string | X | - | 페이지네이션 커서 |

**입력 검증 (v1.0.2):**
- `date_from > date_to`인 경우 **400 Bad Request** 반환
- 문자열 파라미터 최대 길이 제한 적용

**응답:**
```json
{
  "data": [
    {
      "id": 1,
      "production_date": "2026-01-20",
      "lot_number": "LOT20260120-001",
      "item_code": "B0061",
      "item_name": "제품A",
      "good_quantity": 150,
      "source": "live"
    }
  ],
  "next_cursor": "eyJkIjogIjIwMjYtMDEtMjAiLCAiaWQiOiAxMDB9",
  "has_more": true,
  "count": 1000
}
```

**예제:**
```bash
# 특정 제품 조회
curl "http://localhost:8001/records?item_code=B0061"

# 날짜 범위 조회
curl "http://localhost:8001/records?date_from=2026-01-01&date_to=2026-01-31"

# 제품명 검색
curl "http://localhost:8001/records?q=물"

# 로트 번호 검색 (NEW)
curl "http://localhost:8001/records?lot_number=LT2026"

# 생산량 범위 필터 (NEW)
curl "http://localhost:8001/records?min_quantity=100&max_quantity=500"

# 복합 필터 (NEW)
curl "http://localhost:8001/records?lot_number=LT2026&min_quantity=100&item_code=B0061"

# 페이지네이션
curl "http://localhost:8001/records?limit=100&cursor=eyJkIjogIjIwMjYtMDEtMjAifQ=="
```

---

#### `GET /records/{item_code}`
특정 제품의 전체 기간 레코드 조회

**경로 파라미터:**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `item_code` | string | O | 제품 코드 |

**쿼리 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `limit` | int | X | 1000 | 조회 건수 (1-5000) |

**예제:**
```bash
curl "http://localhost:8001/records/B0061?limit=500"
```

---

### 3.3 제품 목록

#### `GET /items`
등록된 제품 목록 조회

**쿼리 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `q` | string | X | - | 제품명/코드 검색 |
| `limit` | int | X | 200 | 조회 건수 (1-2000) |

**응답:**
```json
[
  {
    "item_code": "B0061",
    "item_name": "제품A",
    "record_count": 1500
  },
  {
    "item_code": "B0062",
    "item_name": "제품B",
    "record_count": 800
  }
]
```

**예제:**
```bash
# 전체 제품 목록
curl "http://localhost:8001/items"

# 제품 검색
curl "http://localhost:8001/items?q=물"
```

---

### 3.4 집계 데이터

#### `GET /summary/monthly_total`
월별 총 생산량 집계

**쿼리 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `date_from` | string | X | - | 시작일 (YYYY-MM-DD) |
| `date_to` | string | X | - | 종료일 (YYYY-MM-DD) |

**응답:**
```json
[
  {
    "year_month": "2026-01",
    "total_production": 50000,
    "batch_count": 125,
    "avg_batch_size": 400.0
  },
  {
    "year_month": "2025-12",
    "total_production": 48000,
    "batch_count": 120,
    "avg_batch_size": 400.0
  }
]
```

**예제:**
```bash
# 전체 월별 집계
curl "http://localhost:8001/summary/monthly_total"

# 특정 기간 집계
curl "http://localhost:8001/summary/monthly_total?date_from=2025-01-01&date_to=2026-01-31"
```

---

#### `GET /summary/by_item`
**임의 기간** 제품별 생산량 집계 (월 구분 없이 합산)

**쿼리 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `date_from` | string | **O** | - | 시작일 (YYYY-MM-DD) |
| `date_to` | string | **O** | - | 종료일 (YYYY-MM-DD) |
| `item_code` | string | X | - | 특정 제품 코드 |
| `limit` | int | X | 100 | 조회 건수 (1-1000) |

**응답:**
```json
{
  "data": [
    {
      "item_code": "B0061",
      "item_name": "제품A",
      "total_production": 12500,
      "batch_count": 50
    },
    {
      "item_code": "B0062",
      "item_name": "제품B",
      "total_production": 8000,
      "batch_count": 32
    }
  ],
  "count": 2,
  "date_range": {"from": "2025-10-23", "to": "2026-01-23"}
}
```

**예제:**
```bash
# 3개월간 제품별 누적 생산량 (TOP 100)
curl "http://localhost:8001/summary/by_item?date_from=2025-10-23&date_to=2026-01-23"

# 특정 제품의 기간 내 총 생산량
curl "http://localhost:8001/summary/by_item?date_from=2025-10-23&date_to=2026-01-23&item_code=B0061"
```

---

#### `GET /summary/monthly_by_item`
월별 제품별 생산량 집계

**쿼리 파라미터:**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `year_month` | string | X | - | 특정 월 (YYYY-MM) |
| `item_code` | string | X | - | 특정 제품 코드 |
| `limit` | int | X | 5000 | 조회 건수 (1-50000) |

**응답:**
```json
[
  {
    "year_month": "2026-01",
    "item_code": "B0061",
    "item_name": "제품A",
    "total_production": 2500,
    "batch_count": 10,
    "avg_batch_size": 250.0
  }
]
```

**예제:**
```bash
# 2026년 1월 제품별 집계
curl "http://localhost:8001/summary/monthly_by_item?year_month=2026-01"

# 특정 제품의 월별 추이
curl "http://localhost:8001/summary/monthly_by_item?item_code=B0061"
```

---

## 4. 코드 예제

### 4.1 Python

#### 기본 사용

```python
import requests
from typing import Optional, Generator
from dataclasses import dataclass

@dataclass
class ProductionHubClient:
    """Production Data Hub API 클라이언트"""
    base_url: str = "http://localhost:8001"
    timeout: int = 30

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """GET 요청"""
        response = requests.get(
            f"{self.base_url}{endpoint}",
            params=params,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: dict) -> dict:
        """POST 요청"""
        response = requests.post(
            f"{self.base_url}{endpoint}",
            json=data,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def health_check(self) -> dict:
        """API 상태 확인"""
        return self._get("/healthz")

    def get_records(
        self,
        item_code: Optional[str] = None,
        q: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 1000,
        cursor: Optional[str] = None
    ) -> dict:
        """생산 레코드 조회"""
        params = {"limit": limit}
        if item_code:
            params["item_code"] = item_code
        if q:
            params["q"] = q
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if cursor:
            params["cursor"] = cursor
        return self._get("/records", params)

    def get_items(self, q: Optional[str] = None, limit: int = 200) -> list:
        """제품 목록 조회"""
        params = {"limit": limit}
        if q:
            params["q"] = q
        return self._get("/items", params)

    def get_monthly_total(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> list:
        """월별 총 생산량"""
        params = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return self._get("/summary/monthly_total", params)

    def get_monthly_by_item(
        self,
        year_month: Optional[str] = None,
        item_code: Optional[str] = None,
        limit: int = 5000
    ) -> list:
        """월별 제품별 집계"""
        params = {"limit": limit}
        if year_month:
            params["year_month"] = year_month
        if item_code:
            params["item_code"] = item_code
        return self._get("/summary/monthly_by_item", params)

    def iter_all_records(
        self,
        item_code: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        batch_size: int = 1000
    ) -> Generator[dict, None, None]:
        """전체 레코드 순회 (페이지네이션 자동 처리)"""
        cursor = None
        while True:
            result = self.get_records(
                item_code=item_code,
                date_from=date_from,
                date_to=date_to,
                limit=batch_size,
                cursor=cursor
            )
            for record in result["data"]:
                yield record

            if not result["has_more"]:
                break
            cursor = result["next_cursor"]


# 사용 예제
if __name__ == "__main__":
    client = ProductionHubClient()

    # 헬스 체크
    print(client.health_check())

    # 최근 레코드 조회
    records = client.get_records(limit=10)
    print(f"조회된 레코드: {records['count']}건")

    # 제품 목록
    items = client.get_items()
    print(f"등록된 제품: {len(items)}개")

    # 전체 레코드 순회
    for record in client.iter_all_records(date_from="2026-01-01"):
        print(record)
```

#### pandas 연동

```python
import pandas as pd
from production_hub_client import ProductionHubClient

client = ProductionHubClient()

# 레코드를 DataFrame으로 변환
records = client.get_records(date_from="2026-01-01", limit=5000)
df = pd.DataFrame(records["data"])

# 날짜 타입 변환
df["production_date"] = pd.to_datetime(df["production_date"])

# 제품별 합계
summary = df.groupby("item_name")["good_quantity"].sum().sort_values(ascending=False)
print(summary.head(10))

# Excel로 내보내기
df.to_excel("production_data.xlsx", index=False)
```

---

### 4.2 JavaScript / TypeScript

#### 기본 사용

```typescript
interface RecordResponse {
  data: ProductionRecord[];
  next_cursor: string | null;
  has_more: boolean;
  count: number;
}

interface ProductionRecord {
  id: number;
  production_date: string;
  lot_number: string;
  item_code: string;
  item_name: string;
  good_quantity: number;
  source: 'live' | 'archive';
}

class ProductionHubClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8001') {
    this.baseUrl = baseUrl;
  }

  private async get<T>(endpoint: string, params?: Record<string, string | number>): Promise<T> {
    const url = new URL(`${this.baseUrl}${endpoint}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }
    const response = await fetch(url.toString());
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  private async post<T>(endpoint: string, data: object): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async healthCheck(): Promise<object> {
    return this.get('/healthz');
  }

  async getRecords(params?: {
    item_code?: string;
    q?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    cursor?: string;
  }): Promise<RecordResponse> {
    return this.get('/records', params as Record<string, string | number>);
  }

  async getItems(params?: { q?: string; limit?: number }): Promise<object[]> {
    return this.get('/items', params as Record<string, string | number>);
  }

  async getMonthlyTotal(params?: { date_from?: string; date_to?: string }): Promise<object[]> {
    return this.get('/summary/monthly_total', params as Record<string, string>);
  }

  async *iterAllRecords(params?: {
    item_code?: string;
    date_from?: string;
    date_to?: string;
    batchSize?: number;
  }): AsyncGenerator<ProductionRecord> {
    let cursor: string | null = null;
    const batchSize = params?.batchSize ?? 1000;

    while (true) {
      const result = await this.getRecords({
        item_code: params?.item_code,
        date_from: params?.date_from,
        date_to: params?.date_to,
        limit: batchSize,
        cursor: cursor ?? undefined,
      });

      for (const record of result.data) {
        yield record;
      }

      if (!result.has_more) break;
      cursor = result.next_cursor;
    }
  }
}

// 사용 예제
async function main() {
  const client = new ProductionHubClient();

  // 헬스 체크
  console.log(await client.healthCheck());

  // 레코드 조회
  const records = await client.getRecords({ limit: 10 });
  console.log(`조회된 레코드: ${records.count}건`);

  // 전체 레코드 순회
  for await (const record of client.iterAllRecords({ date_from: '2026-01-01' })) {
    console.log(record);
  }
}

main();
```

---

### 4.3 C# (.NET)

```csharp
using System.Net.Http.Json;
using System.Text.Json;

public class ProductionHubClient : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly string _baseUrl;

    public ProductionHubClient(string baseUrl = "http://localhost:8001")
    {
        _baseUrl = baseUrl;
        _httpClient = new HttpClient { BaseAddress = new Uri(baseUrl) };
    }

    public async Task<JsonElement> HealthCheckAsync()
    {
        return await _httpClient.GetFromJsonAsync<JsonElement>("/healthz");
    }

    public async Task<RecordResponse> GetRecordsAsync(
        string? itemCode = null,
        string? q = null,
        string? dateFrom = null,
        string? dateTo = null,
        int limit = 1000,
        string? cursor = null)
    {
        var queryParams = new List<string> { $"limit={limit}" };
        if (!string.IsNullOrEmpty(itemCode)) queryParams.Add($"item_code={itemCode}");
        if (!string.IsNullOrEmpty(q)) queryParams.Add($"q={q}");
        if (!string.IsNullOrEmpty(dateFrom)) queryParams.Add($"date_from={dateFrom}");
        if (!string.IsNullOrEmpty(dateTo)) queryParams.Add($"date_to={dateTo}");
        if (!string.IsNullOrEmpty(cursor)) queryParams.Add($"cursor={cursor}");

        var url = $"/records?{string.Join("&", queryParams)}";
        return await _httpClient.GetFromJsonAsync<RecordResponse>(url);
    }

    public void Dispose() => _httpClient.Dispose();
}

public record RecordResponse(
    List<ProductionRecord> Data,
    string? NextCursor,
    bool HasMore,
    int Count);

public record ProductionRecord(
    int Id,
    string ProductionDate,
    string LotNumber,
    string ItemCode,
    string ItemName,
    int GoodQuantity,
    string Source);

// 사용 예제
var client = new ProductionHubClient();
var records = await client.GetRecordsAsync(limit: 10);
Console.WriteLine($"조회된 레코드: {records.Count}건");
```

---

## 5. 페이지네이션

### 5.1 커서 기반 페이지네이션

대용량 데이터 조회 시 커서 기반 페이지네이션을 사용합니다.

**작동 방식:**
1. 첫 번째 요청: `cursor` 파라미터 없이 요청
2. 응답에서 `next_cursor` 값 확인
3. `has_more`가 `true`면 `next_cursor` 값으로 다음 페이지 요청
4. `has_more`가 `false`가 될 때까지 반복

**예제:**
```python
def fetch_all_records(client, **filters):
    """모든 레코드를 페이지네이션으로 조회"""
    all_records = []
    cursor = None

    while True:
        result = client.get_records(cursor=cursor, **filters)
        all_records.extend(result["data"])

        print(f"조회: {len(result['data'])}건, 누적: {len(all_records)}건")

        if not result["has_more"]:
            break
        cursor = result["next_cursor"]

    return all_records

# 2026년 1월 전체 데이터 조회
records = fetch_all_records(client, date_from="2026-01-01", date_to="2026-01-31")
```

### 5.2 커서 구조

커서는 Base64 인코딩된 JSON입니다:

```json
{
  "d": "2026-01-20",  // production_date
  "id": 100,          // record id
  "s": "live"         // source (live/archive)
}
```

> **주의:** 커서는 불투명한 문자열로 취급하세요. 직접 생성하거나 수정하지 마세요.

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

#### Webhook 관리 (`/notifications`)

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

#### 이상탐지 what-if (`/anomaly`)

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

#### 문서 삭제·복원 (`/{dataset}` — `materials`, `binder`)

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

## 7. 에러 처리

### 7.1 HTTP 상태 코드

| 코드 | 의미 | 대응 |
|------|------|------|
| 200 | 성공 | 정상 처리 |
| 400 | 잘못된 요청 | 파라미터 확인 |
| 404 | 리소스 없음 | 경로 또는 ID 확인 |
| 422 | 유효성 검사 실패 | 파라미터 형식 확인 |
| 500 | 서버 에러 | 잠시 후 재시도 |
| 503 | 서비스 불가 | 서버 상태 확인 |

### 7.2 에러 응답 형식

```json
{
  "detail": "에러 메시지",
  "type": "validation_error",  // 선택적
  "loc": ["query", "limit"]    // 선택적 - 에러 위치
}
```

### 7.3 Python 에러 처리 예제

```python
import requests
from requests.exceptions import RequestException, Timeout, HTTPError

def safe_request(client, method, *args, **kwargs):
    """안전한 API 요청"""
    try:
        if method == "get_records":
            return client.get_records(*args, **kwargs)
    except Timeout:
        print("요청 시간 초과. 잠시 후 다시 시도하세요.")
        return None
    except HTTPError as e:
        if e.response.status_code == 400:
            print(f"잘못된 요청: {e.response.json().get('detail')}")
        elif e.response.status_code == 500:
            print("서버 에러. 잠시 후 다시 시도하세요.")
        return None
    except RequestException as e:
        print(f"연결 실패: {e}")
        return None
```

---

## 8. 모범 사례

### 8.1 성능 최적화

```python
# 좋은 예: 필요한 필드만 조회
records = client.get_records(
    item_code="B0061",           # 특정 제품만
    date_from="2026-01-01",      # 기간 제한
    limit=100                     # 적절한 limit
)

# 나쁜 예: 전체 데이터 조회
records = client.get_records(limit=5000)  # 불필요하게 많은 데이터
```

### 8.2 캐싱 활용

```python
import functools
import time

# 클라이언트 측 캐싱
@functools.lru_cache(maxsize=100)
def get_items_cached(q: str = None):
    """제품 목록 캐싱 (서버에서도 캐싱됨)"""
    return tuple(client.get_items(q=q))

# TTL 캐싱
class TTLCache:
    def __init__(self, ttl=300):
        self.ttl = ttl
        self.cache = {}

    def get(self, key, fetch_func):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
        value = fetch_func()
        self.cache[key] = (value, time.time())
        return value

cache = TTLCache(ttl=300)
monthly_total = cache.get("monthly_total", client.get_monthly_total)
```

### 8.3 연결 재사용

```python
# 좋은 예: 세션 재사용
import requests

session = requests.Session()
session.headers.update({"Accept": "application/json"})

for i in range(100):
    response = session.get(f"{BASE_URL}/records", params={"limit": 10})

# 나쁜 예: 매번 새 연결
for i in range(100):
    response = requests.get(f"{BASE_URL}/records", params={"limit": 10})
```

### 8.4 배치 처리

```python
# 대용량 데이터 처리 시 제너레이터 사용
def process_all_records():
    """메모리 효율적인 대용량 처리"""
    for record in client.iter_all_records(date_from="2025-01-01"):
        # 한 건씩 처리 (메모리에 전체 로드하지 않음)
        process_record(record)
```

---

## 9. Rate Limiting (NEW)

### 9.1 제한 정책

| 엔드포인트 | 제한 | 윈도우 |
|-----------|------|--------|
| 기타 모든 API | 60 requests | 1분 (IP 기준) |

### 9.2 응답 헤더

모든 API 응답에 다음 헤더가 포함됩니다:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
```

### 9.3 제한 초과 처리

**429 응답:**
```json
{
  "detail": "Rate limit exceeded. Try again in 30 seconds."
}
```

**헤더:**
```
Retry-After: 30
```

### 9.4 Python 예제

```python
import requests
import time

def safe_get(path, params=None, max_retries=3):
    """Rate Limit을 고려한 안전한 조회"""
    for attempt in range(max_retries):
        response = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            response.raise_for_status()

    raise Exception("Max retries exceeded")
```

---

## 10. FAQ

### Q1. API 인증은 어떻게 하나요?

현재 버전은 인증이 없습니다. 내부 네트워크에서만 사용하도록 설계되었습니다.
외부 노출 시 리버스 프록시에서 인증을 추가하세요.

### Q2. 요청 제한(Rate Limit)이 있나요?

**네, 다음과 같은 Rate Limit이 적용됩니다:**

| 엔드포인트 | 제한 | 초과 시 응답 |
|-----------|------|-------------|
| 기타 API | 60 req/min per IP | 429 Too Many Requests |

**Rate Limit 초과 시 응답:**
```json
{
  "detail": "Rate limit exceeded. Try again in 30 seconds."
}
```

**응답 헤더:**
- `Retry-After`: 재시도 가능까지 남은 초
- `X-RateLimit-Limit`: 분당 최대 요청 수
- `X-RateLimit-Remaining`: 남은 요청 수

### Q3. 데이터는 어디까지 조회 가능한가요?

- **Live DB (2026~)**: 실시간 데이터
- **Archive DB (~2025)**: 과거 데이터

날짜 범위를 지정하면 자동으로 적절한 DB에서 조회합니다.

### Q4. 커서가 만료되나요?

커서는 만료되지 않지만, 데이터가 변경되면 결과가 달라질 수 있습니다.
실시간 동기화가 필요하면 새로운 쿼리를 시작하세요.

### Q5. 쓰기 API는 없나요?

보안상 읽기 전용으로 설계되었습니다.
데이터 입력은 별도 시스템에서 처리됩니다.

### Q6. 대용량 데이터 내보내기는 어떻게 하나요?

```python
# 전체 데이터를 CSV로 내보내기
import csv

with open("export.csv", "w", newline="", encoding="utf-8") as f:
    writer = None
    for record in client.iter_all_records():
        if writer is None:
            writer = csv.DictWriter(f, fieldnames=record.keys())
            writer.writeheader()
        writer.writerow(record)
```

---

## 부록: API 요약 표

| 메서드 | 엔드포인트 | 설명 | Rate Limit |
|--------|-----------|------|------------|
| GET | `/` | API 상태 | 60/min |
| GET | `/healthz` | 상세 헬스 체크 | 제외 |
| GET | `/records` | 레코드 목록 (lot_number, min/max_quantity 필터 추가) | 60/min |
| GET | `/records/{item_code}` | 특정 제품 레코드 | 60/min |
| GET | `/items` | 제품 목록 | 60/min |
| GET | `/summary/monthly_total` | 월별 총 생산량 | 60/min |
| GET | `/summary/by_item` | 기간별 제품별 생산량 | 60/min |
| GET | `/summary/monthly_by_item` | 월별 제품별 생산량 | 60/min |

### v1.0.2 새로운 기능

| 기능 | 설명 |
|------|------|
| Rate Limiting | IP 기반 요청 제한 (429 응답) |
| 새 필터 | `lot_number`, `min_quantity`, `max_quantity` |
| 입력 검증 | 날짜 범위, 문자열 길이 검증 |
| Request ID | 모든 응답에 추적용 `X-Request-ID` 포함 |

---

> **문서 버전:** 1.2
> **최종 업데이트:** 2026-10-05 (챗 API 폐지, 관리 조작 curl 레시피 추가)
> **문의:** 시스템 관리자
