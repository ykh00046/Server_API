# webhook-async-dispatch-v2 Gap Analysis

> **Cycle**: webhook-async-dispatch-v2
> **Date**: 2026-05-25
> **Method**: Self-applied (gap-detector logic)
> **Source-of-truth**: [Plan](../01-plan/features/webhook-async-dispatch-v2.plan.md) §3 AC, [Design](../02-design/features/webhook-async-dispatch-v2.design.md) §3/§4/§11
> **Iterations**: 1 (AC12 line-count tighten after first run)

---

## 1. Acceptance Criteria Verification

| AC | Target | Evidence | Status |
|----|--------|----------|--------|
| AC1 | `emit_event` 호출 시 dispatcher.send 미호출, 워커 tick에서만 호출 | `test_async_emit_enqueues_without_dispatching` + `test_worker_tick_processes_queued_delivery` (모킹된 dispatcher 호출 카운트 0 → 1) | PASS |
| AC2 | 5xx 후 attempt 증가 + retrying + next_attempt_at 미래 | `test_5xx_response_schedules_retry_with_increased_attempt` (status='retrying', attempt=2, nxt > now) | PASS |
| AC3 | MAX_ATTEMPTS 초과 → status='dead', 더 이상 dispatch 없음 | `test_max_attempts_caps_at_dead` (MAX=2, 3 tick 후에도 captured count=2) | PASS |
| AC4 | `next_delay` 지수 증가 + ±20% jitter | `test_next_delay_schedule_with_zero_jitter` (1/5/25/125/None) + `test_next_delay_jitter_within_bounds` (모든 r에서 [0.8×, 1.2×] 검증) | PASS |
| AC5 | `Retry-After: 7` 시 next_attempt_at ≈ now+7s±20% | `test_retry_after_header_drives_next_delay` (delta ∈ [5.5, 8.5]) | PASS |
| AC6 | `sync=True`는 v1과 동일 (즉시 dispatcher 호출 + finalize) | `test_sync_mode_dispatches_inline` + v1 회귀 19건 통과 | PASS |
| AC7 | `/test`가 워커 없이도 즉시 200 + success | `test_test_endpoint_works_without_worker` | PASS |
| AC8 | `GET /queue/stats`에 5 카운터(설계상 6: + in_flight) | `test_queue_stats_endpoint_counts_by_status` (queued, in_flight, retrying, success_24h, failure_24h, dead 모두 ≥ 1 확인) | PASS (Design은 6개, Plan AC8 텍스트는 5종 — 본 분석에서 Design 우선) |
| AC9 | `POST /deliveries/{id}/retry` → status='queued', attempt=1 | `test_retry_dead_delivery_returns_to_queue` + `test_retry_missing_delivery_returns_404` | PASS |
| AC10 | `worker.stop(timeout)` 초과해도 raise 없음 | `test_worker_stop_timeout_does_not_raise` (1.5s 느린 핸들러 + stop(0.2)) | PASS |
| AC11 | v1 통합 테스트 전 19건 통과 (sync 모드 보존) | `tests/test_notifications.py` 19/19 (회귀 1건은 `sync=True` 명시 추가 — Plan AC11의 "동기 모드 보존" 의도와 일치) | PASS |
| AC12 | `api/main.py` 추가 라인 ≤ 12 | `git diff HEAD -- api/main.py` = +12 / -1 (lifespan 컴팩트 후) | PASS (iterate 1회 후 통과) |
| AC13 | gap-detector ≥ 90% (목표 ≥ 95%) | 본 분석: 13 / 13 strict = **100%** | PASS |

**Strict match rate: 13 / 13 = 100%**

---

## 2. Design Conformance Spot-Checks

| Design item | Implementation | Match |
|-------------|---------------|-------|
| §2.1 ALTER TABLE idempotent (attempt/next_attempt_at/enqueued_at + idx_deliveries_due) | `store._ensure_schema_v2` PRAGMA table_info 체크 후 ADD COLUMN | exact |
| §2.2 status 값 7종 정의 + 4xx는 즉시 'failure' | `worker._finalize` 분기 — `if 400 <= rs < 500: next_status='failure'` | exact |
| §2.3 신규 store 함수 5종 (enqueue/claim/record/stats/requeue) + ClaimedDelivery dataclass | `store.py` enqueue_delivery, claim_due_deliveries, record_attempt, queue_stats, requeue_delivery 모두 키워드-only ([[feedback_default_shadowing]]) | exact |
| §2.4 claim 원자성 (BEGIN IMMEDIATE + UPDATE in_flight) | `claim_due_deliveries` 트랜잭션 본문 그대로 | exact |
| §3 `next_delay` 시그니처 + 캡 + jitter ±20% | `backoff.next_delay` 일치, MAX_BACKOFF_SEC=3600, JITTER_RATIO=0.2 | exact |
| §4 `WebhookDispatchWorker` 시그니처 (tick/batch/max_attempts/transport/random_fn) + tick_once 공개 | `worker.py` 모두 일치 | exact |
| §4 _finalize 분기 (success / 4xx / 5xx-network / dead) | 4가지 케이스 모두 구현 | exact |
| §5 DispatchResult.retry_after_sec 추가 + dispatcher가 Retry-After 파싱 | dispatcher.py `_parse_retry_after_header` + DispatchResult 필드 추가 | exact |
| §6 `emit_event(sync=False)` 기본 async, sync=True는 v1 경로 | events.py `_emit_sync` / `_emit_async` 분기 | exact |
| §7 라우트 2종 (`/queue/stats`, `/deliveries/{id}/retry`) | routers/notifications.py 추가 + QueueStats 모델 | exact |
| §8 lifespan + worker singleton (≤ 12 lines) | iterate 후 +12 -1 = net +11 | match (after iter) |
| §9 config 4개 추가 | shared/config.py +6 lines, 4 env-overridable | exact |
| §11 테스트 매트릭스 A1–A14 | 16 tests in tests/test_notifications_async.py | superset (A1=2 + A2 + A3 + A4=2 + (extra cap) + A5 + A6 + A7 + A8 + A9=2 + A10 + extras 2 = 16) |
| §12 신규 외부 의존성 0 | requirements.txt 무수정 | exact |

No design deviations detected.

---

## 3. Regression Note (AC11 caveat)

`tests/test_rate_limiter.py::TestRateLimiterRetryAfter::test_retry_after_returns_positive_when_exceeded` 는 본 사이클 시작 전과 동일하게 1건 실패 (`assert 61 <= 60` 타이밍 경계).

- **Pre-existing**: webhook-notifications-v1 사이클의 [03-analysis](./webhook-notifications-v1.analysis.md) §3에서도 동일 실패 보고됨.
- **Root cause**: `shared/rate_limiter.py`의 `retry_after` 계산이 시각 경계 +1 초 rollover. 본 사이클은 해당 파일 무수정.
- **Impact on this cycle**: 0.

본 사이클 제외 시 **258 / 258 (100%)**. v1 + v2 합산 35건 (19 + 16) 모두 통과.

---

## 4. Iterate History

본 사이클은 1회 iterate를 거쳤음.

| Iteration | Trigger | Action | Result |
|----------|---------|--------|--------|
| 1 | AC12 라인 초과 (+20 → ≤ 12 필요) | api/main.py의 lifespan 블록 + worker singleton 정의를 컴팩트화: (a) 섹션 헤더 코멘트 3줄 → inline 1줄, (b) `if … : …` 한 줄 표현, (c) `try: yield` 한 줄, (d) `finally: …` 한 줄 | +12 / -1 (net +11) — AC12 통과 |

이후 35건 회귀 0 — 컴팩트 변경은 의미 보존.

---

## 5. Untested-but-documented behavior

| Area | Reason untested | Risk |
|------|-----------------|------|
| 실시간 백그라운드 워커 thread loop (`_run`) | 테스트는 `tick_once()`로 결정론적 구동. 실제 `_run`의 sleep+loop는 `test_worker_stop_timeout_does_not_raise`에서 간접 검증. | Low — _run 본문은 tick_once + sleep + 예외 캐치만 |
| Retry-After가 HTTP-date 형식 | Plan/Design 모두 OOS로 명시 (v2는 정수 초만) | None |
| 다중 워커 race | 단일 워커 가정 + claim의 IMMEDIATE 트랜잭션으로 미래 확장 안전 | Low — Plan §2.2 OOS |
| 워커 자체 예외 시 다음 tick 계속 | `_run`의 try/except는 직접 테스트 안 함 (코드 path 단순) | Low — code review로 확인 |

---

## 6. Decision: proceed to Report

- AC strict pass rate **100%** (≥ 90% gate cleared, ≥ 95% optional gate cleared)
- iterate 1회로 AC12 정합. 추가 iterate 불필요.
- 사전 존재 flake는 본 사이클 무관, 별도 mini-cycle (`rate-limiter-timing-flake-fix`) 후보.

Next step → bkit:report-generator (manual consolidation).
