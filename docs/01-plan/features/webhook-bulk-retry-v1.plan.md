# webhook-bulk-retry-v1 Planning Document

> **Summary**: `webhook-async-dispatch-v2`(2026-05-25)에서 도입된 단건 재시도(`POST /notifications/deliveries/{id}/retry`)를 **터미널 실패 상태(dead/failure) 일괄 재시도**로 확장한다. 외부 시스템 장애 후 수십~수백 건이 dead-letter로 쌓인 상황에서, 1건씩 클릭하는 대신 한 번의 호출로 전부 재큐잉한다.
>
> **Project**: Server_API (Production Data Hub)
> **Version**: webhook-bulk-retry v1
> **Author**: interojo (Claude assisted)
> **Date**: 2026-05-28
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

현재 dead-letter 복구 표면은 단건 `POST /notifications/deliveries/{id}/retry` 하나뿐이다. 외부 수신 시스템(Slack/Teams/사내 메신저)이 30분~수시간 장애를 겪으면 `WEBHOOK_MAX_ATTEMPTS`(기본 5)를 소진한 delivery가 `dead`로 다수 적재된다. 운영자는 각 건을 일일이 재시도해야 하며, admin UI는 webhook당 최근 10개 버튼만 노출한다(`views.render_deliveries_section`). **장애 복구 시 대량 재처리 경로가 없다.**

`requeue_delivery`(단건 mutation)와 `queue_stats`의 `dead` 카운터가 이미 존재하므로, batch 버전은 동일 primitive의 자연 확장이며 저위험이다.

### 1.2 Background

- `deliveries_repo.requeue_delivery(delivery_id)` — 단건을 `status='queued', attempt=1, next_attempt_at=now`로 리셋, response 필드 NULL화. 이미 구현됨.
- 터미널 실패 DB 상태는 정확히 2개: `dead`(5xx/네트워크 재시도 소진), `failure`(4xx 영구 실패 또는 v1 sync 단발 실패). `worker._finalize` + `dispatcher.send` 기준 확정.
- 재큐잉된 row는 워커 `claim_due_deliveries`가 즉시 집어가므로(다음 tick) 별도 트리거 불필요.
- admin UI 큐 상태 섹션(`render_queue_stats_section`)이 `dead` 카운트를 이미 카드로 표시 → 그 옆에 "전체 재시도" 버튼이 자연스러운 자리.
- 메모리: [[feedback_default_shadowing]](신규 store 함수 키워드-only), [[feedback_commit_style]](레이어별 분할 커밋), [[project-notifications-module-layout]](deliveries_repo에 구현 + store facade re-export), [[project-webhook-subsystem]](상태 전이 규약).

### 1.3 Related

- 선행 사이클: `webhook-async-dispatch-v2`(2026-05-25, 100%), `webhook-admin-ui-v1`(2026-05-25, 98%)
- 비-목표: 자동 housekeeping, dead row 영구 삭제, 우선순위 큐, 다중 워커

---

## 2. Scope

### 2.1 In Scope

#### A. Store 레이어 (`api/notifications/deliveries_repo.py` + `store.py` facade)

| ID | 변경 |
|----|------|
| S1 | `RETRYABLE_TERMINAL_STATUSES = ("dead", "failure")` 상수 — 일괄 재시도 허용 상태의 단일 진실원 |
| S2 | `list_retryable_delivery_ids(*, statuses, webhook_id=None, limit) -> list[int]` — 읽기 전용. 조건 매칭 id 목록(capped, id ASC). dry_run 및 사전 카운트용 |
| S3 | `requeue_deliveries(*, statuses, webhook_id=None, limit) -> list[int]` — 단일 트랜잭션(BEGIN IMMEDIATE)에서 매칭 id를 SELECT → `UPDATE ... WHERE id IN (...)`로 일괄 큐 복귀. 재큐잉된 id 목록 반환 |
| S4 | 두 함수 모두 store.py facade에서 re-export. statuses는 `RETRYABLE_TERMINAL_STATUSES`와 교집합만 적용(방어). limit는 1..5000 clamp |

#### B. 라우트 (`api/routers/notifications.py`)

| ID | Method/Path | 설명 |
|----|------------|------|
| R1 | `POST /notifications/deliveries/bulk-retry` | body `BulkRetryRequest` → 매칭 터미널 실패 delivery 일괄 재큐잉. 응답 `BulkRetryResult` |

- 경로 세그먼트: `deliveries/bulk-retry`(1 세그먼트) vs 기존 `deliveries/{delivery_id}/retry`(2 세그먼트) → 충돌 없음. 가독성 위해 단건 라우트보다 위에 등록.

#### C. 스키마 (router 모듈 내, `QueueStats` 선례 따름)

| ID | 모델 |
|----|------|
| M1 | `BulkRetryRequest`: `statuses: list[str] = ["dead"]`, `webhook_id: int \| None = None`, `limit: int = 500 (ge=1, le=5000)`, `dry_run: bool = False` |
| M2 | `BulkRetryResult`: `requeued: int`, `ids: list[int]`, `dry_run: bool`, `statuses: list[str]`, `webhook_id: int \| None` |
| M3 | status 검증: 요청 `statuses`가 `{"dead","failure"}` 부분집합이 아니면 400. 빈 리스트도 400(재시도 대상 미지정) |

#### D. Admin UI (`dashboard/components/webhook_admin/`)

| ID | 변경 |
|----|------|
| U1 | `api_client.bulk_retry_dead(*, statuses=None, webhook_id=None, limit=500, dry_run=False) -> dict` — POST 래퍼 |
| U2 | `views.render_queue_stats_section`에 dead 카운트 > 0일 때 "💀 dead 전체 재시도" 버튼. 클릭 시 dry_run 없이 호출 → toast로 결과(requeued N건) 표시 후 rerun |

#### E. 테스트

| ID | 항목 |
|----|------|
| T1 | `tests/test_notifications_bulk_retry.py` 신규 — store + 라우트 통합 (httpx 0건, isolated_db fixture 재사용) |
| T2 | `tests/test_webhook_admin_ui.py`에 `bulk_retry_dead` api_client 케이스 추가(MockTransport) + views 소스 와이어링 검사 |

#### F. 회귀 방어

| ID | 항목 |
|----|------|
| RG1 | 기존 단건 retry 라우트/테스트 무변경 통과 |
| RG2 | OpenAPI 기존 path 유지 + 신규 path 1건만 추가 |
| RG3 | pytest 전체 baseline 통과(신규 제외 0 회귀) |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| dead row 영구 삭제 / housekeeping | `webhook-housekeeping-v1` 별도 |
| UI `is_retryable_status`의 `failed` vs 실제 `failure` 불일치 수정 | 기존 동작/테스트 변경 — 본 사이클 범위 밖, 리포트에 기록 |
| 재큐잉 대상 미리보기 테이블 UI | dry_run API는 제공하되 UI 프리뷰 패널은 후속 |
| webhook_id별 선택적 일괄 재시도 UI | API는 `webhook_id` 파라미터 지원, UI는 전역 dead 버튼만 |
| 비동기/스트리밍 재시도 진행률 | 동기 일괄 UPDATE로 충분(수천 건 단위) |

### 2.3 Naming Decisions

- 라우트: `bulk-retry`(동사구, 단건 `retry`와 구분). 
- store 함수: `requeue_deliveries`(복수형, 단건 `requeue_delivery`와 대칭).
- 허용 상태 상수: `RETRYABLE_TERMINAL_STATUSES` — `dead`+`failure`만. `queued/in_flight/retrying/success`는 일괄 재시도 금지(double-dispatch/재발송 위험).

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `POST /deliveries/bulk-retry`(기본 body)가 모든 `dead` delivery를 `queued`로 복귀, `requeued`=건수, `ids` 일치 | pytest |
| AC2 | `statuses=["dead","failure"]` 시 dead+failure 둘 다 재큐잉, 그 외 상태(queued/success/retrying) 미변경 | pytest |
| AC3 | `dry_run=true` 시 DB 무변경 + 재큐잉 대상 `ids`만 반환(`requeued`=len(ids), `dry_run`=true) | pytest |
| AC4 | `webhook_id` 지정 시 해당 webhook의 터미널 실패만 재큐잉(타 webhook dead 미변경) | pytest |
| AC5 | `statuses`에 허용 외 값(예: `success`, `queued`) 포함 시 400 | pytest |
| AC6 | `statuses=[]`(빈 리스트) 시 400 | pytest |
| AC7 | 대상 0건일 때 200 + `requeued`=0, `ids`=[] (에러 아님) | pytest |
| AC8 | `limit` 초과분은 id ASC 순 상한까지만 재큐잉, le=5000 초과 요청은 422 | pytest |
| AC9 | 재큐잉된 row를 워커 `tick_once()`가 즉시 집어 dispatch(성공 transport) → status='success' | pytest (end-to-end) |
| AC10 | 재큐잉 시 단건과 동일하게 attempt=1, next_attempt_at=now, response_status/body/error NULL | pytest (raw row 검증) |
| AC11 | OpenAPI에 `/notifications/deliveries/bulk-retry` 추가, 기존 path 유지 | pytest |
| AC12 | `api_client.bulk_retry_dead`가 올바른 path/method/body로 POST + 응답 반환 | pytest (MockTransport) |
| AC13 | `views.render_queue_stats_section` 소스에 bulk-retry 버튼 와이어링 존재(모듈 레벨 api 호출 0 유지) | pytest (소스 검사) |
| AC14 | gap-detector ≥ 90%(목표 ≥ 95%) | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| SELECT-then-UPDATE 사이 새 dead row 유입 race | 단일 트랜잭션 `BEGIN IMMEDIATE`로 SELECT한 id만 UPDATE — 그 사이 유입분은 다음 호출에서 처리. 반환 ids = 실제 변경분으로 정확 |
| `IN (...)` 파라미터 폭주(수천 건) | `limit` le=5000 상한 + id 리스트 바인딩. 5000개 IN은 SQLite 안전 범위 |
| 허용 외 상태 일괄 변경으로 in_flight double-dispatch | `RETRYABLE_TERMINAL_STATUSES` 교집합 강제(store) + 라우트 400 검증(이중 방어) |
| webhook이 비활성(active=0)인데 재큐잉 → 워커가 claim 안 함 | 의도된 동작: claim_due는 active=1만 집음. dead만 쌓이지 재발송 안 됨. 운영자가 webhook 재활성화하면 자동 처리. 문서화 |
| 단건 retry 라우트와 경로 충돌 | 세그먼트 수 상이(1 vs 2). bulk 라우트를 위에 등록해 명시적 우선 |
| 빈 statuses/잘못된 입력으로 전체 의도치 않은 재시도 | 빈 리스트 400, 기본값 `["dead"]` 보수적. 와일드카드/전체 옵션 미제공 |
| keyword-only 누락으로 wrapper 기본 인자 가림 | 신규 함수 전부 `*` 키워드-only ([[feedback_default_shadowing]]) |

---

## 5. Timeline (estimate)

| Phase | Duration |
|-------|---------|
| Plan + Design | 0.4h |
| Do-1: store 2 함수 + facade | 0.3h |
| Do-2: 라우트 + 스키마 + 검증 | 0.2h |
| Do-3: api_client + views 버튼 | 0.2h |
| QA: 테스트 + 전체 회귀 + 라이브 스모크 | 0.5h |
| Analyze: gap-detector | 0.2h |
| Iterate (필요 시) | 0–0.3h |
| Report + 분할 커밋 + 메모리 | 0.3h |

총 예상: ~2.4h

---

## 6. Open Questions (Design 단계 결정)

| Q | 후보 | 권장 |
|---|------|------|
| Q1 | 기본 statuses | `["dead"]` (dead-letter 본래 의미, 보수적) |
| Q2 | dry_run 위치 | request body 필드 (단일 모델, 단순) |
| Q3 | 스키마 위치 | router 모듈 내 (`QueueStats` 선례) |
| Q4 | 반환에 ids 포함 여부 | 포함 (감사/검증 용이, limit 상한으로 폭주 없음) |
| Q5 | UI 버튼에 confirm 단계 | st.button 1클릭 즉시 실행 + 결과 toast (Streamlit 모달 부재, dead는 어차피 실패분이라 재시도 안전) |
