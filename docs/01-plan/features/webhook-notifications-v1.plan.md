# webhook-notifications-v1 Planning Document

> **Summary**: 외부 시스템(Slack/Teams/사내 메신저/사용자 정의 서비스)이 Server_API의 도메인 이벤트(생산 레코드 적재, 임계 초과 등)를 수신할 수 있도록 Webhook 등록·발송·이력 관리 기능을 신규로 추가한다. 본 사이클은 **신규 기능 추가(non-refactor)** 이며, 기존 라우트/도구/저장소에는 변경을 주지 않는다.
>
> **Project**: Server_API (Production Data Hub)
> **Version**: webhook-notifications v1 (MVP)
> **Author**: interojo (Claude assisted)
> **Date**: 2026-05-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

생산 데이터에 의미 있는 변화가 생길 때, 외부 서비스가 **풀(poll) 없이 푸시로 통보**받을 수 있는 표준 채널을 제공한다. 사이클 종료 시점에는 (a) HTTP Webhook을 안전하게 등록·발송하는 인프라와 (b) 도메인 이벤트를 내부에서 emit할 수 있는 헬퍼만 도입한다. 실제 도메인 이벤트(예: 신규 레코드 적재 시 자동 emit)는 후속 사이클로 분리한다.

### 1.2 Background

- 직전 사이클(`api-router-split`, 2026-05-22, 98%)에서 라우터 분해 패턴이 정착됨 → 신규 라우터를 `api/routers/notifications.py`로 일관되게 추가할 수 있음.
- `httpx`, `pydantic`, `sqlite3` 등 발송·검증·저장에 필요한 의존성이 이미 `requirements.txt`에 존재. **신규 외부 의존성 0**.
- 기존 도메인 로직과 격리하기 위해 별도 SQLite DB(`database/notifications.db`)를 사용. `DBRouter`(production/archive 라우팅)는 건드리지 않음.
- 보안 메모리 영향: [[project_review_fixes_202604]]의 패턴(env 기반 설정, 입력 검증), [[feedback_default_shadowing]]의 함정(라우터 wrapper 기본 인자) 준수.

### 1.3 Related

- 선행 사이클: `api-router-split` (2026-05-22, 98%) — 라우터 패턴 확립
- 메모리:
  - `feedback_commit_style.md` — phase별 logical layer 분할 커밋
  - `feedback_default_shadowing.md` — wrapper 기본 인자 주의
  - `project_sse_contract.md` — 본 사이클은 SSE 무관(별도 채널)
- 비-목표: `api/chat.py`, `dashboard/*`, `webcloring-pdf/*` 무수정

---

## 2. Scope

### 2.1 In Scope

#### A. 신규 라우터 (`api/routers/notifications.py`)

| ID | Method/Path | 설명 |
|----|------------|------|
| R1 | `POST /notifications/webhooks` | Webhook 등록 (url, event_types[], description, active). 응답 1회 한정으로 `secret` 평문 노출 |
| R2 | `GET /notifications/webhooks` | 활성/전체 목록 (secret 미노출) |
| R3 | `GET /notifications/webhooks/{id}` | 단건 조회 (secret 미노출) |
| R4 | `PATCH /notifications/webhooks/{id}` | active 토글, description 수정, event_types 갱신, secret 회전(rotate=true) |
| R5 | `DELETE /notifications/webhooks/{id}` | 삭제 (관련 deliveries는 cascade 보존 정책: 90일 후 housekeeping은 후속 사이클) |
| R6 | `POST /notifications/webhooks/{id}/test` | `webhook.test` 이벤트 즉시 발송 + delivery 1건 기록 |
| R7 | `GET /notifications/webhooks/{id}/deliveries` | 발송 이력 페이지네이션 (limit, status 필터) |
| R8 | `GET /notifications/events` | 알려진 이벤트 타입 목록 (등록 가능 타입을 클라이언트가 발견할 수 있게) |

#### B. 신규 모듈 (`api/notifications/` 패키지)

| ID | 모듈 | 책임 |
|----|------|------|
| M1 | `api/notifications/__init__.py` | 공개 API re-export (`emit_event`, `register_event_type`, `KNOWN_EVENT_TYPES`) |
| M2 | `api/notifications/schemas.py` | Pydantic 모델: `WebhookCreate`, `WebhookUpdate`, `WebhookPublic`, `WebhookCreated`, `DeliveryPublic`, `EventTypeInfo` |
| M3 | `api/notifications/store.py` | SQLite repository (CRUD + delivery 기록). 모든 SQL은 bind parameter 사용 |
| M4 | `api/notifications/dispatcher.py` | HMAC-SHA256 서명 + httpx 동기 POST + 결과 캡처 |
| M5 | `api/notifications/events.py` | `emit_event(event_type, payload)` — 활성 webhook 매칭 → dispatcher 호출 → store에 delivery 기록. 본 사이클은 동기 발송만 |

#### C. 설정 / 인프라

| ID | 항목 |
|----|------|
| C1 | `shared/config.py`에 `NOTIFICATIONS_DB_FILE`, `WEBHOOK_TIMEOUT_SEC`, `WEBHOOK_USER_AGENT`, `WEBHOOK_MAX_PAYLOAD_BYTES` 추가 |
| C2 | `api/main.py`에 `from .routers import notifications`, `app.include_router(notifications.router)` 추가 (alphabetical 또는 등록 순서 유지) |
| C3 | `database/notifications.db` 첫 호출 시 lazy init (스키마 생성). 별도 마이그레이션 도구 도입 안 함 — DB 단일 파일, 테이블 2개 |
| C4 | rate-limiter는 기존 미들웨어 그대로 적용 (notifications 경로는 별도 예외 없음). 헬스 체크 경로 변경 없음 |

#### D. 보안

| ID | 항목 |
|----|------|
| S1 | URL 화이트 스킴(`http`, `https`)만 허용, 길이 ≤ 2048. SSRF 차단을 위한 host 차단 목록은 본 사이클 범위 외(로컬 dev → 자유 발송 허용). 환경 변수 `WEBHOOK_BLOCKED_HOSTS`(콤마 구분) 옵션만 추가 |
| S2 | `secret`는 등록/회전 시점에만 평문 응답. 저장은 평문(서명 계산에 필요). DB 파일 권한은 OS 기본 |
| S3 | 서명 헤더 명세: `X-Webhook-Signature: sha256=<hex>`, `X-Webhook-Event: <event_type>`, `X-Webhook-Delivery: <delivery_id>`, `X-Webhook-Timestamp: <unix>` |
| S4 | 응답 본문은 발송 측이 처음 1KB만 저장(이력 비대화 방지) |

#### E. 회귀 방어

| ID | 항목 |
|----|------|
| RG1 | 기존 라우터/도구/`/openapi.json`의 기존 path 그대로 유지 (신규 path만 추가) |
| RG2 | `tests/` 기존 224건 통과 유지 |
| RG3 | `api/main.py` 추가 라인 ≤ 5 (`include_router` 1줄 + import 1줄 + 빈줄) |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| 비동기 큐(Celery/RQ) 기반 발송 | MVP는 동기 — 운영 트래픽 패턴 확보 후 별도 사이클 |
| 자동 재시도(exponential backoff) | 본 사이클은 1회 시도 + delivery 기록만. 재시도 워커는 후속 |
| 도메인 이벤트 자동 emit (production_records 적재 시) | 통합 지점이 ERP 파일 처리 경로에 있어 별도 사이클 필요. 본 사이클은 `emit_event` 헬퍼만 제공 |
| 화이트리스트 기반 SSRF 방어 | 운영 토폴로지 확정 후 별도 보안 사이클 |
| 대시보드 UI | API만 제공. dashboard 통합은 후속 |
| 인증(API key/JWT) | 현재 API 전체에 인증 없음 — 별도 보안 사이클 범위 |
| 90일 자동 housekeeping | 본 사이클은 수동 DELETE만 |

### 2.3 Naming Decisions

- 패키지명: `api/notifications/` (단수형 `notification`보다 도메인이 모듈 묶음을 의미하므로 복수형).
- DB 파일: `database/notifications.db` (production_analysis.db / archive_2025.db와 같은 위치, 같은 명명 컨벤션).
- 이벤트 타입 명명: `<domain>.<entity>.<action>` 패턴 (`webhook.test`, `production.record.created`, `production.threshold.exceeded`). 점 구분 + 소문자 + 단수 entity.

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `POST /notifications/webhooks` 200 응답에 `id`, `secret`(평문)이 포함되고, 이후 `GET`은 `secret` 키를 응답하지 않음 | pytest |
| AC2 | 발송 시 요청 헤더에 `X-Webhook-Signature: sha256=<hex>` 가 포함되고, `payload`의 HMAC-SHA256(secret, body)과 일치 | pytest (서명 재계산 비교) |
| AC3 | `POST /notifications/webhooks/{id}/test` 호출 후 `GET /notifications/webhooks/{id}/deliveries` 가 1건 이상 반환 (`status`, `response_status`, `response_body`, `attempted_at` 포함) | pytest |
| AC4 | `event_types`에 등록되지 않은 이벤트 emit 시 해당 webhook은 호출되지 않음 | pytest (mock dispatcher가 호출되지 않음 확인) |
| AC5 | `active=false` 인 webhook은 emit 시 호출되지 않음 | pytest |
| AC6 | URL 검증: scheme이 http/https 가 아닐 때 `POST /notifications/webhooks` 400 반환 | pytest |
| AC7 | `PATCH /notifications/webhooks/{id}` 에 `rotate_secret=true` 전달 시 새 secret 평문이 응답에 포함되고 이전 secret로 만든 서명은 검증 실패 | pytest |
| AC8 | `GET /notifications/events` 가 최소 `webhook.test`, `production.record.created`, `production.threshold.exceeded` 3종을 반환 | pytest |
| AC9 | `/openapi.json` 의 기존 path 집합이 분리 전 baseline과 동일 (신규 `/notifications/*` 만 추가) | pytest |
| AC10 | `pytest tests/ -q` 회귀 없음 (기존 통과 수 ≥ 직전 사이클의 baseline 224) | pytest |
| AC11 | `api/main.py` net 추가 라인 ≤ 5 | wc -l / diff |
| AC12 | gap-detector 본 사이클 일치율 ≥ 90% (목표 ≥ 95%) | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| 동기 발송이 API 응답 시간을 늘림 (`/test` 엔드포인트) | timeout 기본 5초 + httpx에 명시 timeout. `/test`는 어차피 명시적 호출이라 응답 지연 수용 가능. 도메인 emit은 본 사이클에서 자동 트리거하지 않음 → 응답 지연 위험 없음 |
| SSRF — 사용자가 등록한 URL이 내부망(`http://localhost`, `http://192.168.*`) 호출 | dev 환경 dogfooding을 위해 본 사이클은 차단 안 함. `WEBHOOK_BLOCKED_HOSTS` env 변수로 운영에서 차단 가능하도록 훅만 제공 |
| `notifications.db` 파일이 conftest 실행마다 누적 | 테스트는 `tmp_path` + monkeypatch로 임시 DB 사용. autouse fixture로 모듈 캐시된 conn 초기화 |
| HMAC secret 평문 저장 → DB 유출 시 위조 가능 | DB 파일 자체가 신뢰 경계 내부. 키 관리(KMS)는 별도 사이클. 사용자가 우려 시 `rotate_secret`으로 즉시 회전 가능 |
| 응답 본문이 거대(>10MB)일 때 메모리 폭발 | httpx에 `read` 시 본문 1KB만 슬라이스 후 저장. dispatcher가 이 책임 가짐 |
| 라우터 등록 순서 변경으로 OpenAPI 경로 정렬 흔들림 | 기존 등록 순서(chat → system → records → summary)는 유지하고 notifications를 마지막에 추가. AC9가 path **집합** 동등성을 검증하므로 정렬 변경은 무관 |
| `_http_helpers._validate_length` 시그니처 재사용 시 wrapper의 기본 인자가 inner를 가린다 ([[feedback_default_shadowing]]) | 본 사이클의 notifications 모듈은 자체 validator(`_validate_webhook_url`)를 노출하고, 기본 인자 없이 명시적 키워드만 사용 |
| 발송이 외부망에 의존 → 테스트에서 실네트워크 호출 발생 우려 | dispatcher의 `_post` 호출을 monkeypatch로 가짜 응답으로 대체. 통합 테스트는 fake transport만 사용 |

---

## 5. Timeline (estimate)

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.5h | claude |
| Act-1: `notifications/` 모듈 4종(schemas, store, dispatcher, events) | 0.8h | claude |
| Act-2: `api/routers/notifications.py` 8개 엔드포인트 | 0.6h | claude |
| Act-3: `shared/config.py` + `api/main.py` 등록 | 0.1h | claude |
| QA: `tests/test_notifications.py` 작성 + 전체 회귀 | 0.6h | claude |
| Analyze: gap-detector (수동) | 0.2h | claude |
| Report | 0.2h | claude |

총 예상: ~3h

---

## 6. Open Questions (Design 단계에서 결정)

| Q | 후보 | 권장 |
|---|------|------|
| Q1 | event_types 컬럼 — JSON 문자열 vs 별도 join 테이블 | JSON (MVP, 행 수 적음) |
| Q2 | delivery status 값 | `pending`/`success`/`failure`/`skipped` 4종 |
| Q3 | secret 길이 | 32바이트 URL-safe (`secrets.token_urlsafe(32)`) |
| Q4 | 타임스탬프 형식 | ISO-8601 UTC (`datetime.now(UTC).isoformat()`) 일관성 |
| Q5 | rate-limit | 기존 API rate-limit(60/min) 그대로. `/test`도 동일 |
