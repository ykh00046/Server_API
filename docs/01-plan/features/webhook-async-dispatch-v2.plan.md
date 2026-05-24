# webhook-async-dispatch-v2 Planning Document

> **Summary**: `webhook-notifications-v1`(2026-05-24, 100%)에서 도입된 동기 1회-시도 webhook 발송을 **비동기 워커 큐 + exponential backoff 재시도**로 확장한다. 호출자(`emit_event`)는 즉시 반환되며, 백그라운드 워커가 영속화된 큐(SQLite `webhook_deliveries` 테이블 재사용)에서 작업을 소비·재시도한다.
>
> **Project**: Server_API (Production Data Hub)
> **Version**: webhook-async-dispatch v2
> **Author**: interojo (Claude assisted)
> **Date**: 2026-05-25
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

`emit_event`가 외부 HTTP 호출(평균 100ms~수초)을 동기로 기다리는 현 구조는, 도메인 hook(예: ERP intake에서 production.record.created 자동 emit)을 도입하면 그대로 사용자 응답 지연에 노출된다. 백그라운드 발송 + 재시도를 도입해 (a) 호출자 즉시 반환, (b) 일시적 외부 장애(5xx, 네트워크) 자동 복구를 가능케 한다.

### 1.2 Background

- v1 dispatcher는 이미 "절대 raise 안 함" 규약이라 큐 도입 시 단순 재호출만 추가하면 됨.
- `webhook_deliveries` 테이블이 이미 한 발송의 결과를 한 row로 표현 — `attempt` 컬럼만 추가하면 시도 이력을 그대로 행으로 표현 가능.
- v1의 `transport` seam을 그대로 사용하면 워커 테스트도 외부망 0건.
- 메모리: [[feedback_timeout_daemon_gc]] — daemon thread + GC 위임 패턴이 엄격한 종료 처리보다 실용적. [[feedback_commit_style]] — 레이어별 분할 커밋. [[feedback_default_shadowing]] — wrapper 기본 인자 주의.

### 1.3 Related

- 선행 사이클: `webhook-notifications-v1` (2026-05-24, 100%)
- 비-목표: 다중 프로세스 워커, 다른 머신으로의 워커 분리, Redis/Celery 도입

---

## 2. Scope

### 2.1 In Scope

#### A. Store 스키마 확장 (`api/notifications/store.py`)

| ID | 변경 |
|----|------|
| S1 | `webhook_deliveries` 컬럼 추가: `attempt INTEGER NOT NULL DEFAULT 1`, `next_attempt_at TEXT` (nullable), `enqueued_at TEXT` (nullable) |
| S2 | `status` 값 확장: 기존 `pending`/`success`/`failure`/`skipped` + 신규 `queued`/`retrying`/`dead`. 라우터 응답 모델은 그대로(`DeliveryPublic.status: str`) — 추가 상태도 동일 필드로 노출 |
| S3 | 마이그레이션: lazy `_ensure_schema`에서 `PRAGMA table_info` 체크 후 `ALTER TABLE ... ADD COLUMN`. 단일 DB 파일, 단일 schema_version 시드 행 없음 — 컬럼 존재로 판단 |
| S4 | 신규 함수: `enqueue_delivery(webhook_id, event_type, payload) -> int` (status='queued', attempt=1, next_attempt_at=now), `claim_due_deliveries(now, limit) -> list[WebhookRecord+delivery]` (status in queued/retrying AND next_attempt_at ≤ now), `record_attempt(delivery_id, outcome, attempt, retry_after_sec | None) -> None` |

#### B. Backoff 정책 (`api/notifications/backoff.py` 신규)

| ID | 항목 |
|----|------|
| B1 | `def next_delay(attempt: int) -> float` — exponential backoff. 1→1s, 2→5s, 3→25s, 4→125s, 5→625s, ≥6→dead |
| B2 | 최대 attempt 환경변수: `WEBHOOK_MAX_ATTEMPTS` (기본 5). 초과 시 status='dead' |
| B3 | jitter: ±20% uniform 분포 추가 (thundering herd 회피) |
| B4 | 외부 응답이 `Retry-After` 헤더를 주면 그 값 우선 (정수 초 또는 HTTP-date). 단 60분 상한 |

#### C. Worker (`api/notifications/worker.py` 신규)

| ID | 항목 |
|----|------|
| W1 | 단일 daemon thread. `class WebhookDispatchWorker`. `start()` / `stop(timeout=2)` / `is_alive()` |
| W2 | tick 주기: `WEBHOOK_WORKER_TICK_SEC` (기본 0.5s). tick마다 `claim_due_deliveries(now, limit=WEBHOOK_WORKER_BATCH)` 호출 |
| W3 | 각 due delivery에 대해 dispatcher.send → 성공 시 finalize(success), 실패+attempt<MAX 시 attempt 증가 + next_attempt_at 재설정 + status='retrying', 실패+attempt≥MAX 시 status='dead' |
| W4 | `stop()` 시 `_shutdown` Event 세트 후 thread.join(timeout). join 실패 시에도 raise 안 함 ([[feedback_timeout_daemon_gc]] 적용) |
| W5 | 워커 자체 예외는 logger.exception으로만 남기고 다음 tick 계속 (워커 자살 금지) |

#### D. emit_event 동작 변경 (`api/notifications/events.py`)

| ID | 항목 |
|----|------|
| E1 | 기본 모드: 호출자는 enqueue만 하고 즉시 반환. 반환은 `list[DeliveryPublic]` (status='queued', response_status=None) |
| E2 | 동기 모드 옵션: `emit_event(..., sync=True)` — v1과 동일 동작 (테스트/`/test` 엔드포인트용) |
| E3 | `/test` 엔드포인트는 sync=True 유지 — 사용자가 "지금 보내봐"라고 명시한 거니까 |
| E4 | dispatcher.send 직접 호출 코드 경로는 사실상 v1 sync 경로뿐 (호환 보존) |

#### E. App 라이프사이클 (`api/main.py`)

| ID | 항목 |
|----|------|
| L1 | FastAPI `lifespan` 컨텍스트 매니저 추가. 시작 시 worker.start(), 종료 시 worker.stop() |
| L2 | 신규 라우트/엔드포인트 0건 — 내부 인프라만 |
| L3 | 추가 라인 ≤ 12 (lifespan 함수 정의 + FastAPI(lifespan=...) 인자) |

#### F. 신규 라우트 (UI 최소화)

| ID | Method/Path | 설명 |
|----|------------|------|
| R1 | `GET /notifications/queue/stats` | `{queued: n, retrying: n, success_24h: n, failure_24h: n, dead: n}` 운영 가시성 |
| R2 | `POST /notifications/deliveries/{id}/retry` | dead/failure 상태 1건을 큐로 복귀 (`status='queued'`, attempt 리셋) — 수동 복구용 |

> 라우트 2개는 운영 필수 표면적. v1의 8개 + 2개 = 10개. 라우트 추가는 최소화.

#### G. 설정 (`shared/config.py`)

| ID | 항목 |
|----|------|
| C1 | `WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", 5))` |
| C2 | `WEBHOOK_WORKER_TICK_SEC = float(os.getenv("WEBHOOK_WORKER_TICK_SEC", 0.5))` |
| C3 | `WEBHOOK_WORKER_BATCH = int(os.getenv("WEBHOOK_WORKER_BATCH", 16))` |
| C4 | `WEBHOOK_WORKER_ENABLED = os.getenv("WEBHOOK_WORKER_ENABLED", "1") not in {"0","false","False"}` (테스트 환경에서 자동 시작 비활성화 옵션) |

#### H. 회귀 방어

| ID | 항목 |
|----|------|
| RG1 | v1 통합 테스트(`tests/test_notifications.py`) 전 19건 그대로 통과 — 동기 모드(`sync=True`) 보존 |
| RG2 | OpenAPI 기존 path 그대로 + 신규 path 2건만 추가 |
| RG3 | `api/main.py` 추가 라인 ≤ 12 |
| RG4 | pytest 전체 baseline (241 + 신규 v2 tests, 사전 존재 flake 제외) 통과 |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| 다중 프로세스 워커 (multi-worker) | SQLite 단일 writer 가정 — 단일 process 단일 worker. 멀티 instance는 별도 사이클 (DB는 already WAL이라 추후 확장 가능) |
| 워커 메트릭을 Prometheus로 export | metrics export 자체가 별도 사이클(메모리 §2의 #4 후보) |
| 자동 housekeeping (오래된 success delivery 삭제) | 별도 사이클(`webhook-housekeeping-v1`) |
| 도메인 이벤트 자동 emit hook (records POST → emit) | 본 사이클은 인프라만. emit 트리거 추가는 `webhook-domain-emit-v1` |
| dead-letter UI / dashboard 패널 | dashboard 통합은 별도 사이클 |
| webhook 우선순위 큐 | MVP는 FIFO + due time |

### 2.3 Naming Decisions

- 워커 모듈: `api/notifications/worker.py` (단일 워커 클래스만 보유, 복수형 워커는 후속)
- 상태값: `queued` (최초 enqueue) → `retrying` (1회 이상 실패, 재시도 대기) → `success`/`failure` (단발성 종결, attempt=MAX 이전)/`dead` (MAX 초과). `pending`은 v1의 동기 모드에서만 사용되며 v2에서는 `queued`로 단계적 대체. `skipped`는 그대로.
- 신규 헤더 명세 변경 없음 — dispatcher 그대로.

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `emit_event(event_type, payload)` 호출 시 dispatcher.send가 **호출 시점에는** 실행되지 않고, 워커가 다음 tick에 실행 | pytest (worker stop, emit, dispatcher.send 호출 0 확인 후 worker tick 1회 → 호출 1) |
| AC2 | 외부 500 응답 발송에 대해 워커가 자동 재시도하며 attempt 컬럼이 증가 | pytest (fail_transport, 워커 tick N회, delivery.attempt 증가 확인) |
| AC3 | `WEBHOOK_MAX_ATTEMPTS` 초과 시 status='dead'로 종결되고 더 이상 시도 안 함 | pytest (MAX=2 설정, 3 tick 후에도 dispatcher 호출 ≤ MAX) |
| AC4 | `next_delay(attempt)`가 지수 증가하고 jitter ±20% 안에 들어옴 | pytest (수치 직접 검증, 100회 반복으로 분포 체크) |
| AC5 | 외부 응답의 `Retry-After: 7` 헤더가 있으면 다음 next_attempt_at이 지금+7s±20%에 근접 | pytest (mock transport가 Retry-After 헤더 응답, store row 검증) |
| AC6 | `emit_event(..., sync=True)`는 v1과 동일하게 즉시 dispatcher.send 호출 + finalize | pytest (sync 경로 회귀) |
| AC7 | `/test` 엔드포인트는 worker 미시작 상태에서도 즉시 dispatcher 호출 + 응답 (sync 경로 사용) | pytest (worker.stop() 상태에서 /test 200 + delivery success) |
| AC8 | `GET /notifications/queue/stats`가 queued/retrying/success_24h/failure_24h/dead 5개 카운터 반환 | pytest (각 status row 삽입 후 응답 검증) |
| AC9 | `POST /notifications/deliveries/{id}/retry`가 status='dead'를 'queued'로 복귀, attempt 리셋 | pytest |
| AC10 | 워커 stop(timeout=2)가 2초 안에 join, 실패해도 raise 안 함 | pytest (slow handler 주입, stop 호출 후 alive=False 또는 daemon GC 위임 로그) |
| AC11 | v1 통합 테스트 19건 전부 통과 (모드 분기 후) | pytest (기존 `tests/test_notifications.py` zero 수정) |
| AC12 | `api/main.py` 추가 라인 ≤ 12 | git diff wc |
| AC13 | gap-detector ≥ 90% (목표 ≥ 95%) | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| 워커 스레드가 SQLite에 동시 write 경쟁 | store는 이미 thread-local conn + WAL. 쓰기는 한 트랜잭션. busy_timeout=10s로 충돌 자동 wait |
| `claim_due_deliveries`와 워커 처리 사이 race (다른 컨텍스트가 같은 row 잡는 일) | 단일 워커 + 단일 프로세스 가정. claim 시 status를 'in_flight'로 우선 토글 후 dispatcher 호출 → finalize → status 갱신. 실패 시 status='retrying' 복귀 |
| 테스트 환경에서 워커가 자동 시작되어 테스트 격리 깨짐 | `WEBHOOK_WORKER_ENABLED=0` env or fixture에서 worker.stop() 호출. conftest에서 자동 비활성화 환경변수 set |
| daemon thread가 join 못해 process shutdown 지연 | daemon=True + join timeout 짧게 + GC 위임 ([[feedback_timeout_daemon_gc]]) |
| `lifespan` 도입이 기존 `@app.on_event("startup")` 또는 다른 훅과 충돌 | 현재 main.py는 lifespan/on_event 미사용. 깨끗하게 lifespan만 추가 (`api/main.py` 점검 후 진행) |
| 스키마 마이그레이션 실패 (이미 DB가 있는 경우) | `PRAGMA table_info` 결과로 column 존재 확인 후 idempotent `ADD COLUMN`. 실패 시 logger.warning + 계속 |
| jitter 난수가 테스트를 flaky하게 함 | `next_delay`가 `random_fn` 매개변수를 받도록 설계 (DI). 테스트는 `random_fn=lambda: 0.0` 주입 |
| Retry-After 헤더가 거대한 값(예: 86400)일 때 워커가 그만큼 정지 | 60분 cap 강제 |
| store에서 wrapper 기본 인자 가림 | enqueue_delivery 등 신규 함수는 키워드-only 매개변수 사용 ([[feedback_default_shadowing]]) |

---

## 5. Timeline (estimate)

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.6h | claude |
| Act-1: store 스키마 + 신규 함수 + 마이그레이션 | 0.4h | claude |
| Act-2: backoff.py | 0.2h | claude |
| Act-3: worker.py | 0.4h | claude |
| Act-4: events.py sync 분기 + main.py lifespan | 0.2h | claude |
| Act-5: queue/stats + retry 라우트 | 0.2h | claude |
| Act-6: config 4개 추가 | 0.1h | claude |
| QA: tests/test_notifications_async.py + 전체 회귀 | 0.6h | claude |
| Analyze: gap-detector self | 0.2h | claude |
| Iterate (if needed) | 0–0.5h | claude |
| Report + commit | 0.3h | claude |

총 예상: ~3.2h

---

## 6. Open Questions (Design 단계 결정)

| Q | 후보 | 권장 |
|---|------|------|
| Q1 | claim 시 row를 'in_flight'로 토글 vs 그냥 마지막에 status 업데이트 | 'in_flight' 토글 (단일 워커지만 멀티-worker 확장 대비 깨끗) |
| Q2 | 워커 1 tick에서 일괄 처리 vs 1건씩 | 일괄 (batch=16), 단 각 건마다 finalize 즉시 commit |
| Q3 | sync 모드를 emit_event 시그니처 옵션 vs 별도 함수 | 옵션 (`sync=False` 기본) — call site가 적고 명시적 |
| Q4 | Retry-After 파싱 | 정수 초만 지원 (HTTP-date는 v2 OOS) |
| Q5 | dead 상태에서 retry 라우트 동작 | attempt를 1로 리셋, next_attempt_at = now, status='queued' |
