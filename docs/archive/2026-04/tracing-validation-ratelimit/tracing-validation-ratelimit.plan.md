# Plan: Request Tracing + Input Validation + Rate Limiting

> PDCA Phase: **Plan**
> Feature: `tracing-validation-ratelimit`
> Created: 2026-02-13
> Status: Draft

---

## 1. Background & Motivation

### R1: Request Correlation (Request Tracing)
현재 Request ID는 미들웨어에서 생성하여 `X-Request-ID` 헤더로 반환하고 로그에 기록하고 있으나:
- Dashboard에서 API 호출 시 Request ID를 추적하지 않음
- 사용자가 에러 발생 시 Request ID를 알 수 없음
- AI Chat 응답에 Request ID가 포함되지 않아 디버깅 어려움

### V1: Input Validation (입력 검증 강화)
현재 API 입력 검증이 최소 수준:
- 날짜 형식만 YYYY-MM-DD 검증 (`_normalize_date`)
- `limit` 파라미터에 `ge=1, le=5000` 제약만 존재
- AI 채팅 `query` 필드에 길이 제한 없음
- `item_code`, `q` 파라미터에 길이/특수문자 제한 없음
- `date_from > date_to` 논리 검증 없음

### L1: Rate Limiting (요청 제한)
현재 모든 엔드포인트에 요청 제한이 없음:
- AI Chat 엔드포인트가 무제한 요청 가능 (Gemini API 쿼터 소진 위험)
- 집계 엔드포인트도 무제한 (캐시 미스 시 무거운 쿼리 반복 실행)
- 악의적 사용자가 서비스 가용성 저하시킬 수 있음

---

## 2. Goals

| ID | 목표 | 측정 기준 |
|:--:|------|----------|
| G1 | API 응답에 request_id 포함 | 모든 엔드포인트 응답에 request_id 존재 |
| G2 | Chat 응답에 request_id 포함 | ChatResponse에 request_id 필드 추가 |
| G3 | 입력 값 논리 검증 | date_from > date_to 시 400 에러 |
| G4 | AI 쿼리 길이 제한 | query 최대 2000자 제한 |
| G5 | AI 엔드포인트 Rate Limiting | IP당 분당 20회 제한 |
| G6 | 일반 API Rate Limiting | IP당 분당 60회 제한 |

---

## 3. Scope

### In Scope

| ID | 항목 | 파일 | 난이도 |
|:--:|------|------|:------:|
| R1 | ChatResponse에 request_id 추가 | `api/chat.py` | Low |
| R2 | X-Request-ID 헤더 로깅 개선 | `api/main.py` | Low |
| V1 | date_from > date_to 논리 검증 | `api/main.py` | Low |
| V2 | ChatRequest.query 길이 제한 | `api/chat.py` | Low |
| V3 | 문자열 파라미터 길이 제한 | `api/main.py` | Low |
| L1 | Rate Limiter 미들웨어 | `shared/rate_limiter.py` (신규) | Medium |
| L2 | AI 엔드포인트 Rate Limiting | `api/chat.py` | Medium |
| L3 | 일반 API Rate Limiting | `api/main.py` | Low |
| T1 | Rate Limiter + Validation 테스트 | `tests/test_rate_limiter.py` (신규) | Medium |

### Out of Scope

- 분산 Rate Limiting (Redis 기반 — 단일 서버 환경)
- 사용자 인증 기반 Rate Limiting (인증 시스템 미도입)
- Dashboard UI 변경 (API 레벨만)

---

## 4. Detailed Plan

### R1-R2. Request Tracing 강화

**ChatResponse 변경:**
```python
class ChatResponse(BaseModel):
    answer: str
    status: str = "success"
    tools_used: List[str] = []
    request_id: str = ""  # 추가
```

**미들웨어 개선:**
- 이미 `X-Request-ID` 헤더 반환 중 (유지)
- Chat 엔드포인트에서 request_id를 응답 본문에 포함

### V1-V3. Input Validation 강화

**V1: date_from > date_to 논리 검증:**
- `get_records()`, `get_monthly_total()`, `summary_by_item()` 등 날짜 파라미터 사용 엔드포인트
- `_normalize_date` 후 `date_from > date_to` 체크 → 400 에러

**V2: ChatRequest.query 길이 제한:**
```python
class ChatRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    session_id: str | None = None
```

**V3: 문자열 파라미터 길이 제한:**
- `item_code`: max 50자
- `q` (검색어): max 100자
- `lot_number`: max 50자

### L1-L3. Rate Limiting

**Rate Limiter 모듈 (`shared/rate_limiter.py`):**
- 인메모리 Sliding Window 방식
- IP 기반 요청 카운팅
- TTL 자동 정리 (lazy cleanup)

**설정값:**
- AI Chat: IP당 20 req/min
- 일반 API: IP당 60 req/min
- 헬스체크: Rate Limiting 제외

### T1. 테스트

**Rate Limiter 단위 테스트 (`tests/test_rate_limiter.py`):**
- 정상 요청 허용 테스트
- 제한 초과 시 차단 테스트
- 윈도우 만료 후 재허용 테스트
- 다른 IP 독립 카운팅 테스트

**Validation 테스트 (`tests/test_input_validation.py`):**
- date_from > date_to 검증 테스트
- query 길이 초과 검증 테스트

---

## 5. Modified Files Summary

| 파일 | 변경 유형 | 항목 |
|------|----------|------|
| `shared/rate_limiter.py` | 신규 생성 | L1: Rate Limiter 모듈 |
| `api/main.py` | Modified | R2, V1, V3, L3: 미들웨어 + 검증 + Rate Limiting |
| `api/chat.py` | Modified | R1, V2, L2: ChatResponse + 쿼리 길이 + Rate Limiting |
| `shared/config.py` | Modified | L1: Rate Limit 설정 상수 추가 |
| `tests/test_rate_limiter.py` | 신규 생성 | T1: Rate Limiter 테스트 |
| `tests/test_input_validation.py` | 신규 생성 | T1: Input Validation 테스트 |

---

## 6. Verification Plan

1. **R1 검증:** `/chat/` 응답 JSON에 `request_id` 필드 존재
2. **R2 검증:** 모든 응답 헤더에 `X-Request-ID` 존재 (이미 구현)
3. **V1 검증:** `date_from=2026-12-31&date_to=2026-01-01` → 400 에러
4. **V2 검증:** 2001자 query → 422 에러 (Pydantic 검증)
5. **V3 검증:** 51자 item_code → 422 에러
6. **L1 검증:** AI 엔드포인트 21회 연속 요청 → 429 에러
7. **L2 검증:** 일반 엔드포인트 61회 연속 요청 → 429 에러
8. **T1 검증:** `pytest tests/test_rate_limiter.py tests/test_input_validation.py` 전체 통과
