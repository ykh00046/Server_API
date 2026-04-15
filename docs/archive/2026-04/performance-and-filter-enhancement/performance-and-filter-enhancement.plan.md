# Plan: Performance & Filter Enhancement

> PDCA Phase: **Plan**
> Feature: `performance-and-filter-enhancement`
> Created: 2026-02-12
> Status: Draft

---

## 1. Background & Motivation

이전 PDCA 사이클(4-critical-issues-fix, 97%)에서 보안/안정성 이슈를 해결한 후,
코드 분석에서 **성능 병목**과 **필터 제한**이 다음 개선 대상으로 식별되었습니다.

### 현재 문제점

**성능:**
- `/summary/by_item`, `/summary/monthly_by_item` 엔드포인트가 **캐싱 미적용** 상태
  - 매 요청마다 전체 테이블 집계 → CPU/IO 부하 높음
  - `_list_items_cached`, `_monthly_total_cached`만 캐싱됨
- Slow Query 감지 메커니즘 없음 (v7 계획 section 2.5에 명시되었으나 미구현)
  - `QueryLogger`가 `duration_ms`를 로깅하지만 임계값 경고 없음

**필터:**
- `lot_number` 전용 필터 파라미터 없음 — 현재 `q` LIKE 검색에 섞여 있음
  - `q=LT2026` → item_code, item_name, lot_number 모두 검색 → 불필요한 매칭
- `good_quantity` 범위 필터 없음
  - 소량 생산/대량 생산 배치 구분 불가 (품질 분석 한계)

---

## 2. Goals

| ID | 목표 | 측정 기준 |
|:--:|------|----------|
| G1 | 집계 엔드포인트 응답 시간 50%+ 단축 | 캐시 적중 시 <10ms 응답 |
| G2 | 500ms 초과 쿼리 자동 감지 | Slow Query 로그 WARNING 레벨 출력 |
| G3 | lot_number 직접 필터링 가능 | `/records?lot_number=LT2026%` 지원 |
| G4 | 수량 범위 기반 배치 조회 가능 | `/records?min_quantity=100&max_quantity=500` 지원 |

---

## 3. Scope

### In Scope

| ID | 항목 | 파일 | 난이도 |
|:--:|------|------|:------:|
| P1 | `/summary/by_item` 캐싱 | `api/main.py` | Low |
| P2 | `/summary/monthly_by_item` 캐싱 | `api/main.py` | Low |
| S1 | Slow Query 임계값 경고 (500ms) | `shared/logging_config.py` | Low |
| F1 | `lot_number` 전용 필터 파라미터 | `api/main.py` | Medium |
| F2 | `min_quantity` / `max_quantity` 범위 필터 | `api/main.py` | Medium |

### Out of Scope

- DB 스키마 변경 (shift, line_no 등 ERP 연동 필요 항목)
- Dashboard Lazy Loading (별도 PDCA로 분리)
- Dashboard → API 마이그레이션 (별도 PDCA로 분리)
- DB ANALYZE 스케줄링 (운영 도구 영역)

---

## 4. Detailed Plan

### P1. `/summary/by_item` 캐싱 추가

**현재 상태:** `api/main.py:523-567` — `summary_by_item()` 직접 쿼리, 캐시 없음

**변경 내용:**
1. `_summary_by_item_cached()` 내부 함수 생성
2. `@api_cache("summary_by_item")` 데코레이터 적용
3. 기존 `_list_items_cached` / `_monthly_total_cached` 패턴과 동일하게 구현

**참조 패턴:** `_monthly_total_cached()` (main.py:474-505)

---

### P2. `/summary/monthly_by_item` 캐싱 추가

**현재 상태:** `api/main.py:570-620` — `monthly_by_item()` 직접 쿼리, 캐시 없음

**변경 내용:**
1. `_monthly_by_item_cached()` 내부 함수 생성
2. `@api_cache("monthly_by_item")` 데코레이터 적용

---

### S1. Slow Query 임계값 경고

**현재 상태:** `shared/logging_config.py:150-177` — `QueryLogger.__exit__()` 에서 `duration_ms` 로깅하지만 임계값 분기 없음

**변경 내용:**
1. `shared/config.py`에 `SLOW_QUERY_THRESHOLD_MS = 500` 상수 추가
2. `QueryLogger.__exit__()`에서 `duration_ms >= SLOW_QUERY_THRESHOLD_MS` 시 WARNING 레벨로 로깅
3. 정상 쿼리는 기존 INFO 레벨 유지

**변경 파일:**
- `shared/config.py`: 상수 추가 (1줄)
- `shared/logging_config.py`: `__exit__()` 메서드 내 분기 추가 (~5줄)

---

### F1. `lot_number` 전용 필터 파라미터

**현재 상태:** `api/main.py:284-401` — `/records` 엔드포인트에 `lot_number` 파라미터 없음
- 현재 `q` 파라미터로 `item_code LIKE ? OR item_name LIKE ? OR lot_number LIKE ?` 검색 (319행)

**변경 내용:**
1. `/records` 엔드포인트에 `lot_number: str | None = None` 파라미터 추가
2. WHERE 절에 `lot_number LIKE ?` 조건 추가 (LIKE 패턴: `{lot_number}%` — prefix 매칭)
3. 기존 `q` 검색과 독립적으로 동작 (AND 결합)

**구현 예:**
```python
if lot_number:
    where.append("lot_number LIKE ?")
    params.append(f"{lot_number}%")  # prefix match
```

**AI Tools 연동:** `api/tools.py`의 `execute_custom_query`는 이미 lot_number 직접 쿼리 가능하므로 변경 불필요.

---

### F2. `good_quantity` 범위 필터

**현재 상태:** `/records` 엔드포인트에 수량 기반 필터 없음

**변경 내용:**
1. `/records` 엔드포인트에 파라미터 추가:
   - `min_quantity: int | None = None` — 최소 생산량
   - `max_quantity: int | None = None` — 최대 생산량
2. WHERE 절에 범위 조건 추가

**구현 예:**
```python
if min_quantity is not None:
    where.append("good_quantity >= ?")
    params.append(min_quantity)
if max_quantity is not None:
    where.append("good_quantity <= ?")
    params.append(max_quantity)
```

**사용 사례:**
- `/records?min_quantity=1000` → 대량 생산 배치만 조회
- `/records?max_quantity=50` → 소량/불량 의심 배치 탐지
- `/records?min_quantity=100&max_quantity=500&item_code=BW0021` → 특정 제품의 중간 규모 배치

---

## 5. Modified Files Summary

| 파일 | 변경 유형 | 항목 |
|------|----------|------|
| `api/main.py` | Modified | P1, P2: 캐시 함수 추가 / F1, F2: 필터 파라미터 추가 |
| `shared/logging_config.py` | Modified | S1: Slow Query 경고 분기 |
| `shared/config.py` | Modified | S1: `SLOW_QUERY_THRESHOLD_MS` 상수 |

---

## 6. Risk & Mitigation

| 리스크 | 영향 | 완화 방안 |
|--------|------|----------|
| 캐시 키에 새 파라미터 미포함 | 잘못된 캐시 응답 | `_make_cache_key`가 `*args, **kwargs`를 모두 포함하므로 자동 처리됨 |
| lot_number LIKE 검색 성능 | prefix match(`LT%`)는 인덱스 활용 가능, 중간 매칭(`%LT%`)은 full scan | prefix match로 제한 (`lot_number%`) |
| quantity 필터가 UNION 쿼리에 전파 | Archive/Live 모두 적용 필요 | WHERE 절에 추가되므로 `build_union_sql`이 자동 전파 |

---

## 7. Verification Plan

1. **P1/P2 캐시 검증:**
   - 동일 파라미터로 2회 호출 → 2번째 응답 시간 < 10ms
   - `/healthz`의 cache.size 증가 확인
   - DB 파일 변경 후 캐시 무효화 확인

2. **S1 Slow Query 검증:**
   - `execute_custom_query`로 의도적 느린 쿼리 실행
   - 로그에서 `[Slow Query]` WARNING 메시지 확인

3. **F1 lot_number 필터:**
   - `/records?lot_number=LT2026` → lot_number가 `LT2026%`인 레코드만 반환
   - `/records?lot_number=LT2026&item_code=BW0021` → AND 조합 동작 확인

4. **F2 quantity 필터:**
   - `/records?min_quantity=100` → good_quantity >= 100인 레코드만
   - `/records?min_quantity=100&max_quantity=500` → 범위 내 레코드만
   - Archive + Live 양쪽에서 정상 필터링 확인
