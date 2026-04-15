---
template: analysis
feature: tracing-validation-ratelimit
date: 2026-04-14
phase: check
match_rate: 97
iteration: 1
---

## Iteration 1 (2026-04-14)

**Match Rate: 88% → 97%** (G1 + G2 closed)

| Gap | Status | Resolution |
|---|---|---|
| G1 | ✅ Closed | `api/chat.py:95` `ChatRequest.query` 에 `min_length=1` 추가 + `test_chat_query_empty_blocked` 케이스 추가 |
| G2 | ✅ Closed | `get_records.lot_number` `max_length=50`; `monthly_by_item.year_month` `max_length=7` + `pattern=r"^\d{4}-\d{2}$"` |
| G3/G4/G5 | 🟢 Superseded | doc-only, 설계 문서 업데이트는 report 단계에서 주석 처리 |

Tests: **134 passed** (133 → +1, 0 regression).

# tracing-validation-ratelimit — Gap Analysis

> **Plan**: [tracing-validation-ratelimit.plan.md](../01-plan/features/tracing-validation-ratelimit.plan.md)
> **Design**: [tracing-validation-ratelimit.design.md](../02-design/features/tracing-validation-ratelimit.design.md)
> **Date**: 2026-04-14
> **Phase**: Check
> **Iteration**: 0

---

## 1. Summary

| Metric | Value |
|---|---|
| **Match Rate** | **88%** |
| Threshold (auto-completion) | 90% |
| Decision | Report (2개 minor drift 선택적 fix) — 대부분 후속 사이클(security-and-test-improvement / security-followup-observability) 에서 이미 해소 |
| Regression | `pytest tests/ -q` → **133 passed** |

| Category | Score |
|---|---|
| L1 Rate Limiter module (§2 / §8 L1) | 100% 기능, 2 naming drift |
| V1 Date-range validation (§3.2 / §8 V1) | 100% |
| V2 ChatRequest field constraints (§3.3 / §8 V2) | 67% (`min_length=1` 누락) |
| V3 Query-param `max_length` (§3.4 / §8 V3) | 67% (6 중 4) |
| R1 ChatResponse `request_id` (§4 / §8 R1) | 100% |
| L2 Chat rate limiting (§5.2 / §8 L2) | 100% |
| L3 Middleware rate limiting (§5.3 / §8 L3) | 100% |
| T1 Tests (§6 / §8 T1) | 100% (design 초과) |

Note: Design §7.2 가 이미 `shared/logging_config.py` 를 "기존 인프라, 변경 불요"로 명시 — R1 미들웨어측 request_id 는 사전 제공 인프라로 gap 대상 외.

---

## 2. Matched Items

- **L1 RateLimiter 모듈** — `shared/rate_limiter.py` 가 sliding-window `RateLimiter` 를 구현. `is_allowed()`, `remaining()`, `retry_after()`, `cleanup()`, `get_stats()` 제공. `threading.RLock` + `deque` 로 O(1) 슬라이딩 윈도우 — 설계 스니펫(list 기반, non-thread-safe) 보다 **강화된** 구현.
- **L1 config 상수** — `shared/config.py` 에 `RATE_LIMIT_CHAT=20`, `RATE_LIMIT_API=60`, `RATE_LIMIT_WINDOW=60`. `shared/__init__.py` 에서 재노출.
- **L1 인스턴스** — `chat_rate_limiter` (20/min), `api_rate_limiter` (60/min) 모듈 레벨 인스턴스.
- **V1 `_validate_date_range`** — `api/main.py:159` (shared pure validator 래핑). `get_records` (L403), `monthly_total` (L646), `summary_by_item` (L707) 에서 호출. 불일치 시 `HTTPException(400)`.
- **V2 ChatRequest.query max_length** — `api/chat.py:95` `Field(..., max_length=2000, …)`.
- **V2 ChatRequest.session_id max_length** — `api/chat.py:96` `Field(default=None, max_length=100, …)`.
- **V3 `get_records` item_code / q** — `max_length=50` / `max_length=100` (L378–379).
- **V3 `list_items.q`** — `max_length=100` (L585).
- **V3 `summary_by_item.item_code`** — `max_length=50` (L694).
- **V3 `monthly_by_item.item_code`** — `max_length=50` (L761).
- **R1 ChatResponse.request_id** — `api/chat.py:103`, default `""`.
- **R1 success/error 응답** — `chat_with_data` 의 success (L334) / error (L306) 양쪽 모두 `request_id=request_id` 포함.
- **L2 chat_with_data signature** — `async def chat_with_data(request: ChatRequest, http_request: Request)` (L277); `client_ip = http_request.client.host` (L281).
- **L2 enforcement** — `_enforce_rate_limit()` (L204–219) 이 `chat_rate_limiter.is_allowed` 체크, `HTTPException(429)` 과 구조화된 `detail={"code":"RATE_LIMITED","message":…}` + `Retry-After` 헤더. *(security-and-test-improvement Act-1 에서 code wrapper 추가 — 설계 초과)*
- **L3 middleware** — `api/main.py:81–131` `add_request_id_and_rate_limit` 가 request-id 설정 + `api_rate_limiter` 통합. `/`, `/healthz`, `/healthz/ai`, `/docs`, `/openapi.json`, `/chat*` 제외. `JSONResponse(429)` + `Retry-After` / `X-RateLimit-Limit` / `X-RateLimit-Remaining`. 100 요청마다 cleanup.
- **L3 X-Request-ID 헤더** — success / 429 모든 분기에서 설정.
- **T1 `tests/test_rate_limiter.py`** — 7 클래스 ≈ **14** 케이스 — 설계의 8 케이스 초과.
- **T1 `tests/test_input_validation.py`** — 4 클래스 ≈ **19** 케이스 — 설계의 7 케이스 초과.
- **T1 suite green** — `pytest tests/ -q` → 133 passed.

---

## 3. Gap List

| # | Severity | Area | Gap |
|---|---|---|---|
| G1 | 🟢 Low | §3.3 V2 / §8 V2 | `ChatRequest.query` 에 `min_length=1` 미적용. 설계 체크리스트는 `Field(..., min_length=1, max_length=2000)` 요구. 현재 빈 문자열 `""` 허용. 대응 테스트 `test_chat_query_empty_blocked` 도 부재. |
| G2 | 🟢 Low | §3.4 V3 / §8 V3 | V3 체크리스트 2 항목 미적용: (a) `get_records.lot_number` (`api/main.py:380`, 제약 없음); (b) `monthly_by_item.year_month` (`api/main.py:760`, `max_length=7` 없음). 나머지 4 V3 파라미터는 정상. |
| G3 | 🟢 Info / Naming | §2.2 / §8 L1 | 설계 스니펫은 `chat_limiter` / `api_limiter`, 실제 구현은 `chat_rate_limiter` / `api_rate_limiter`. 기능 동일, doc 철자 문제로 처리. |
| G4 | 🟢 Info / Superseded | §2.2 (RateLimiter 내부) | 설계 스니펫은 plain `list` + 단일 스레드. 실제 구현은 `deque` + `RLock` + `get_stats()`. `security-and-test-improvement` 사이클의 의도적 개선 — **superseded**. |
| G5 | 🟢 Info / Superseded | §5.3 (분리 미들웨어) | 설계는 `add_request_id` 뒤에 별도 `rate_limit_middleware`. 구현은 단일 `add_request_id_and_rate_limit` 로 통합. 기능 동등, 1-pass 로 더 효율적 — **superseded**. |

---

## 4. Recommendations

1. **(G1, ≤5 LOC)** `api/chat.py:95` 에 `min_length=1` 추가 + `tests/test_input_validation.py` 에 `test_chat_query_empty_blocked` 1건 추가.
2. **(G2, ≤4 LOC)** `get_records.lot_number` 에 `max_length=50`, `monthly_by_item.year_month` 에 `max_length=7` 추가. 선택: `year_month` 에 `pattern=r"^\d{4}-\d{2}$"`.
3. **(G3, doc)** 설계 §2.2/§7.1 의 인스턴스명을 실제 이름으로 업데이트.
4. **(G4/G5, doc)** 설계 §2.2/§5.3 에 "Implementation Notes: security-and-test-improvement 사이클에서 deque+thread-safe + merged middleware 로 상향됨" 주석 추가. 참조: `docs/archive/2026-04/security-and-test-improvement/`.
5. **Iteration 불필요**. G1+G2 는 <10 LOC 의 trivial metadata + 1 테스트 — report 단계의 tidy-up 커밋으로 흡수 가능.

---

## 5. Decision

- 엄격 카운트 Match Rate **88% < 90%** 이나 모든 잔여 gap 이 (a) 한 줄짜리 metadata fix (G1, G2) 또는 (b) 후속 사이클의 *superseding improvement* (G3, G4, G5).
- **권장: `/pdca iterate` 1회** (G1+G2 를 5분 내 마감, Match Rate ~97% 로 상승) → `/pdca report` → archive. 또는 drift 를 보고서의 "Known drift" 로 기록하고 바로 report.
- 설계 문서는 병행 업데이트해 G3/G4/G5 를 resolved/superseded 로 명시.

---

## 6. Inspected Files

- `docs/02-design/features/tracing-validation-ratelimit.design.md`
- `shared/rate_limiter.py` (full)
- `shared/config.py:68–70` (rate-limit 상수)
- `shared/__init__.py` (재노출)
- `shared/logging_config.py` (request_id ContextVar — 기존 인프라)
- `shared/validators.py` (date_range / length validators)
- `api/main.py:38–131` (middleware), `:159–174` (validator wrappers), `:376–769` (endpoints w/ Query constraints)
- `api/chat.py:39` (limiter import), `:94–103` (models), `:204–233` (helpers), `:276–336` (orchestrator)
- `tests/test_rate_limiter.py` (14 cases / 7 classes)
- `tests/test_input_validation.py` (19 cases / 4 classes)
- `docs/archive/2026-04/security-and-test-improvement/security-and-test-improvement.analysis.md`
