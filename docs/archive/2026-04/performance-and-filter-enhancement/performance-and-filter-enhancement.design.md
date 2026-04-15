# Design: Performance & Filter Enhancement

> PDCA Phase: **Design**
> Feature: `performance-and-filter-enhancement`
> Plan Reference: `docs/01-plan/features/performance-and-filter-enhancement.plan.md`
> Created: 2026-02-12
> Status: Draft

---

## 1. Implementation Order

```
S1 (Slow Query) → P1 (by_item 캐싱) → P2 (monthly_by_item 캐싱) → F1 (lot_number) → F2 (quantity)
```

S1을 먼저 구현하면 이후 P1/P2 캐시 효과를 로그로 바로 확인 가능합니다.

---

## 2. S1: Slow Query 임계값 경고

### 2.1 변경 파일

| 파일 | 변경 위치 | 유형 |
|------|----------|------|
| `shared/config.py` | 43행 뒤 (DB Connection 섹션) | 상수 추가 |
| `shared/logging_config.py` | 150-177행 (`__exit__` 메서드) | 로직 수정 |

### 2.2 `shared/config.py` 변경

43행 `DB_TIMEOUT = 10.0` 아래에 추가:

```python
SLOW_QUERY_THRESHOLD_MS = 500  # Log WARNING for queries exceeding this
```

### 2.3 `shared/logging_config.py` 변경

**import 추가** (22행 `.config` import에 추가):
```python
from .config import (
    LOGS_DIR,
    LOG_FILE,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    SLOW_QUERY_THRESHOLD_MS,  # ← 추가
)
```

**`__exit__` 메서드 변경** (174-177행):

현재:
```python
if exc_type is not None:
    self.logger.error(f"[Query Failed] {message} | error={exc_val}")
else:
    self.logger.info(f"[Query OK] {message}")
```

변경 후:
```python
if exc_type is not None:
    self.logger.error(f"[Query Failed] {message} | error={exc_val}")
elif duration_ms >= SLOW_QUERY_THRESHOLD_MS:
    self.logger.warning(f"[Slow Query] {message}")
else:
    self.logger.info(f"[Query OK] {message}")
```

### 2.4 로그 출력 예시

```
# 정상 (< 500ms)
2026-02-12 14:30:00 | INFO     | abc123 | [Query OK] sql_kind=records | db_targets=(...) | duration_ms=45.2 | row_count=150

# 느린 쿼리 (>= 500ms)
2026-02-12 14:30:01 | WARNING  | abc123 | [Slow Query] sql_kind=monthly_by_item | db_targets=(...) | duration_ms=1523.7 | row_count=3200
```

---

## 3. P1: `/summary/by_item` 캐싱

### 3.1 변경 파일

| 파일 | 변경 위치 | 유형 |
|------|----------|------|
| `api/main.py` | 523-567행 (`summary_by_item`) | 리팩터링 |

### 3.2 설계

기존 `_monthly_total_cached` 패턴(474-505행)을 따릅니다.

**현재 구조:**
```python
@app.get("/summary/by_item")
def summary_by_item(date_from, date_to, item_code, limit):
    # 직접 쿼리 로직 (캐시 없음)
```

**변경 후 구조:**
```python
@api_cache("summary_by_item")
def _summary_by_item_cached(
    date_from_n: str, date_to_n: str,
    item_code: str | None, limit: int
) -> dict:
    targets = DBRouter.pick_targets(date_from_n, date_to_n)
    where = ["production_date >= ?", "production_date < ?"]
    params: list[Any] = [date_from_n, date_to_n]

    if item_code:
        where.append("item_code = ?")
        params.append(item_code)

    where_clause = " AND ".join(where)

    with QueryLogger("summary_by_item", targets, logger) as ql:
        sql, _ = DBRouter.build_aggregation_sql(
            inner_select="item_code, MAX(item_name) AS item_name, SUM(good_quantity) AS total, COUNT(*) AS cnt",
            inner_where=where_clause,
            outer_select="item_code, MAX(item_name) AS item_name, SUM(total) AS total_production, SUM(cnt) AS batch_count",
            outer_group_by="item_code",
            targets=targets,
            outer_order_by="total_production DESC",
            limit=limit
        )
        query_params = DBRouter.build_query_params(params, targets)
        results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        ql.set_row_count(len(results))

    return {
        "data": results,
        "count": len(results),
        "date_range": {"from": date_from_n, "to": date_to_n}
    }


@app.get("/summary/by_item")
def summary_by_item(
    date_from: str = Query(..., description="YYYY-MM-DD (inclusive, required)"),
    date_to: str = Query(..., description="YYYY-MM-DD (inclusive, required)"),
    item_code: str | None = Query(default=None, description="Filter by specific item"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    date_from_n = _normalize_date(date_from)
    date_to_n = _normalize_date(date_to, add_days=1)
    return _summary_by_item_cached(date_from_n, date_to_n, item_code, limit)
```

**핵심 포인트:**
- `date_from`/`date_to` 정규화를 라우트 함수에서 수행 → 캐시 함수에는 정규화된 값 전달
- `@api_cache` 데코레이터가 `*args`를 해시하므로 파라미터 조합별 캐시 자동 분리
- date_range 응답에는 원본 날짜 대신 정규화된 `date_from_n`을 사용 (캐시 키 일관성)

---

## 4. P2: `/summary/monthly_by_item` 캐싱

### 4.1 변경 파일

| 파일 | 변경 위치 | 유형 |
|------|----------|------|
| `api/main.py` | 570-620행 (`monthly_by_item`) | 리팩터링 |

### 4.2 설계

P1과 동일한 패턴을 적용합니다.

**변경 후 구조:**
```python
@api_cache("monthly_by_item")
def _monthly_by_item_cached(
    year_month: str | None, item_code: str | None, limit: int
) -> list[dict]:
    # year_month → targets 계산
    if year_month:
        year, month = map(int, year_month.split("-"))
        if month == 12:
            next_month_first = f"{year + 1}-01-01"
        else:
            next_month_first = f"{year}-{month + 1:02d}-01"
        targets = DBRouter.pick_targets(f"{year_month}-01", next_month_first)
    else:
        targets = DBTargets(use_archive=True, use_live=True)

    where = []
    params: list[Any] = []

    if year_month:
        where.append("substr(production_date, 1, 7) = ?")
        params.append(year_month)
    if item_code:
        where.append("item_code = ?")
        params.append(item_code)

    where_clause = " AND ".join(where) if where else "1=1"

    with QueryLogger("monthly_by_item", targets, logger) as ql:
        sql, _ = DBRouter.build_aggregation_sql(
            inner_select="substr(production_date, 1, 7) AS year_month, item_code, MAX(item_name) AS item_name, SUM(good_quantity) AS total, COUNT(*) AS cnt, AVG(good_quantity) AS avg_val",
            inner_where=where_clause,
            outer_select="year_month, item_code, MAX(item_name) AS item_name, SUM(total) AS total_production, SUM(cnt) AS batch_count, AVG(avg_val) AS avg_batch_size",
            outer_group_by="year_month, item_code",
            targets=targets,
            outer_order_by="year_month DESC, total_production DESC",
            limit=limit
        )
        query_params = DBRouter.build_query_params(params, targets)
        results = DBRouter.query(sql, query_params, use_archive=targets.use_archive)
        ql.set_row_count(len(results))

    return results


@app.get("/summary/monthly_by_item")
def monthly_by_item(
    year_month: str | None = Query(default=None, description="e.g., 2026-01"),
    item_code: str | None = None,
    limit: int = Query(default=5000, ge=1, le=50000),
):
    return _monthly_by_item_cached(year_month, item_code, limit)
```

**핵심 포인트:**
- `year_month` → targets 변환 로직을 캐시 함수 안에 포함 (캐시 키가 `year_month` 문자열 기반)
- 원래 라우트 함수는 파라미터 전달만 수행

---

## 5. F1: `lot_number` 전용 필터

### 5.1 변경 파일

| 파일 | 변경 위치 | 유형 |
|------|----------|------|
| `api/main.py` | 284-293행 (함수 시그니처) + 309-320행 (WHERE 빌드) | 파라미터/로직 추가 |

### 5.2 설계

**함수 시그니처 변경 (284-293행):**

현재:
```python
def get_records(
    item_code: str | None = None,
    q: str | None = None,
    date_from: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0, description="Deprecated: Use cursor instead"),
    cursor: str | None = Query(default=None, description="v7: Cursor for pagination (base64 JSON)"),
):
```

변경 후:
```python
def get_records(
    item_code: str | None = None,
    q: str | None = None,
    lot_number: str | None = Query(default=None, description="Lot number prefix filter (e.g., LT2026)"),
    date_from: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(default=None, description="YYYY-MM-DD (inclusive)"),
    min_quantity: int | None = Query(default=None, ge=0, description="Minimum good_quantity"),
    max_quantity: int | None = Query(default=None, ge=0, description="Maximum good_quantity"),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0, description="Deprecated: Use cursor instead"),
    cursor: str | None = Query(default=None, description="v7: Cursor for pagination (base64 JSON)"),
):
```

**WHERE 빌드 추가 (320행 뒤, `if q:` 블록 다음):**

```python
if lot_number:
    where.append("lot_number LIKE ?")
    params.append(f"{lot_number}%")  # prefix match for index usage
```

### 5.3 동작 사양

| 요청 | WHERE 조건 | 설명 |
|------|-----------|------|
| `?lot_number=LT2026` | `lot_number LIKE 'LT2026%'` | LT2026으로 시작하는 로트 |
| `?lot_number=LT2026&item_code=BW0021` | `item_code = 'BW0021' AND lot_number LIKE 'LT2026%'` | 특정 제품 + 로트 조합 |
| `?q=LT2026` | `(item_code LIKE '%LT2026%' OR item_name LIKE '%LT2026%' OR lot_number LIKE '%LT2026%')` | 기존 범용 검색 (변경 없음) |

**`lot_number` vs `q` 차이점:**
- `lot_number`: prefix match (`LT2026%`) → 인덱스 활용 가능, lot_number만 검색
- `q`: middle match (`%LT2026%`) → full scan, 3개 컬럼 동시 검색

---

## 6. F2: `good_quantity` 범위 필터

### 6.1 변경 파일

| 파일 | 변경 위치 | 유형 |
|------|----------|------|
| `api/main.py` | 284-293행 (함수 시그니처) + WHERE 빌드 영역 | 파라미터/로직 추가 |

### 6.2 설계

**시그니처:** Section 5.2에서 `min_quantity`, `max_quantity` 이미 포함.

**WHERE 빌드 추가 (`lot_number` 블록 다음):**

```python
if min_quantity is not None:
    where.append("good_quantity >= ?")
    params.append(min_quantity)

if max_quantity is not None:
    where.append("good_quantity <= ?")
    params.append(max_quantity)
```

### 6.3 동작 사양

| 요청 | WHERE 조건 |
|------|-----------|
| `?min_quantity=100` | `good_quantity >= 100` |
| `?max_quantity=500` | `good_quantity <= 500` |
| `?min_quantity=100&max_quantity=500` | `good_quantity >= 100 AND good_quantity <= 500` |
| `?min_quantity=100&item_code=BW0021&date_from=2026-01-01` | `item_code = 'BW0021' AND production_date >= '2026-01-01' AND good_quantity >= 100` |

### 6.4 유효성 검증

- `min_quantity`, `max_quantity`에 `ge=0` 제약 (FastAPI Query 레벨)
- `min_quantity > max_quantity` 조합은 빈 결과를 반환 (에러 아님, SQL이 자연스럽게 처리)

---

## 7. 전체 변경 사양 요약

### 7.1 수정 파일

| 파일 | 항목 | 변경 내용 |
|------|------|----------|
| `shared/config.py` | S1 | `SLOW_QUERY_THRESHOLD_MS = 500` 상수 추가 (1줄) |
| `shared/logging_config.py` | S1 | import에 `SLOW_QUERY_THRESHOLD_MS` 추가 + `__exit__` 분기 추가 (~3줄) |
| `api/main.py` | P1 | `_summary_by_item_cached()` 추출 + `@api_cache` 적용 |
| `api/main.py` | P2 | `_monthly_by_item_cached()` 추출 + `@api_cache` 적용 |
| `api/main.py` | F1 | `get_records` 시그니처에 `lot_number` 추가 + WHERE 빌드 |
| `api/main.py` | F2 | `get_records` 시그니처에 `min_quantity`/`max_quantity` 추가 + WHERE 빌드 |

### 7.2 변경하지 않는 파일

| 파일 | 이유 |
|------|------|
| `shared/cache.py` | `_make_cache_key`가 `*args, **kwargs` 기반이므로 수정 불필요 |
| `shared/database.py` | `build_union_sql`이 WHERE 절 자동 전파하므로 수정 불필요 |
| `api/tools.py` | AI Tools는 `execute_custom_query`로 이미 모든 필터 가능 |

### 7.3 구현 순서

| 순서 | ID | 작업 | 의존성 |
|:----:|:--:|------|--------|
| 1 | S1 | Slow Query 경고 | 없음 |
| 2 | P1 | `/summary/by_item` 캐싱 | S1 (효과 확인용) |
| 3 | P2 | `/summary/monthly_by_item` 캐싱 | S1 (효과 확인용) |
| 4 | F1 | `lot_number` 필터 | 없음 |
| 5 | F2 | `min_quantity`/`max_quantity` 필터 | 없음 |

---

## 8. 검증 체크리스트

### S1 검증
- [ ] `SLOW_QUERY_THRESHOLD_MS` 상수가 `shared/config.py`에 존재
- [ ] `shared/logging_config.py`에서 import 확인
- [ ] `QueryLogger.__exit__`에서 500ms 이상 시 `[Slow Query]` WARNING 출력
- [ ] 500ms 미만 시 기존 `[Query OK]` INFO 출력 유지

### P1/P2 캐시 검증
- [ ] `_summary_by_item_cached` 함수에 `@api_cache("summary_by_item")` 적용
- [ ] `_monthly_by_item_cached` 함수에 `@api_cache("monthly_by_item")` 적용
- [ ] `/healthz` 응답의 `cache.size`가 호출 후 증가
- [ ] 동일 파라미터 2번째 호출이 캐시 적중 (응답 시간 < 10ms)

### F1 lot_number 검증
- [ ] `get_records` 시그니처에 `lot_number` 파라미터 존재
- [ ] `lot_number` → `lot_number LIKE '{value}%'` prefix match
- [ ] `lot_number`와 `item_code` AND 조합 동작
- [ ] `lot_number`와 `q`가 독립적으로 AND 결합

### F2 quantity 검증
- [ ] `get_records` 시그니처에 `min_quantity`, `max_quantity` 파라미터 존재
- [ ] `min_quantity` → `good_quantity >= ?`
- [ ] `max_quantity` → `good_quantity <= ?`
- [ ] 둘 다 지정 시 AND 결합 (범위 필터)
- [ ] `ge=0` 제약으로 음수 입력 시 422 에러
