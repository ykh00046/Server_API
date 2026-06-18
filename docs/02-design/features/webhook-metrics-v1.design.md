# webhook-metrics-v1 Design Document

> **Summary**: notifications DB snapshot을 Prometheus text로 변환하는 독립 read model과 API endpoint 설계
>
> **Project**: Production Data Hub
> **Version**: v10
> **Author**: Codex / bkit:pdca
> **Date**: 2026-06-19
> **Status**: Approved
> **Planning Doc**: [webhook-metrics-v1.plan.md](../../01-plan/features/webhook-metrics-v1.plan.md)

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 비동기 webhook의 실패·dead-letter·적체를 자동 감지할 표준 관측 지점이 없다. |
| **WHO** | Production Data Hub 운영자와 인프라 모니터링 담당자 |
| **RISK** | 잘못된 Prometheus 타입/고카디널리티 라벨 또는 집계 쿼리가 운영 부하를 만들 수 있다. |
| **SUCCESS** | `/metrics` 200 + Prometheus 형식, 핵심 6종 메트릭 정확성, 기존 전체 테스트·ruff 통과 |
| **SCOPE** | notifications read model, text renderer, FastAPI endpoint, 단위·통합 테스트와 운영 문서 |

## 1. Overview

### 1.1 Design Goals

- DB 상태를 변경하지 않는 결정적 스냅샷
- Prometheus scraper가 별도 adapter 없이 수집 가능한 표준 응답
- metric/label 이름과 cardinality 고정
- 쿼리와 표현 계층 분리로 단위 테스트 용이성 확보

### 1.2 Design Principles

- 현재 상태는 counter가 아니라 gauge로 표현한다.
- 민감/고카디널리티 데이터는 label로 내보내지 않는다.
- endpoint는 얇게 유지하고 집계·렌더링은 notifications 모듈이 소유한다.

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| Approach | system router에 SQL·문자열 직접 작성 | collector/registry/adapter 다계층 | metrics read model + 얇은 router |
| New Files | 1 test | 4+ | 1 source + 1 test |
| Modified Files | 1 | 2 | 1 |
| Complexity | Low | High | Medium |
| Maintainability | Low | High | High |
| Effort | Low | High | Medium |
| Risk | 결합도 높음 | 과설계 | 낮음 |
| Recommendation | 단기 hotfix | 대규모 telemetry | **선택** |

**Selected**: Option C — 쿼리·도메인 포맷을 한 모듈에 응집하면서 별도 framework/registry는 도입하지 않는다.

### 2.1 Component Diagram

```text
Prometheus scraper
       |
       v
GET /metrics (system router)
       |
       v
notifications.metrics.render_prometheus()
       |
       +-- collect_snapshot(now) -- read-only SQL --> notifications.db
```

### 2.2 Data Flow

요청 → auth/rate-limit → snapshot 집계 → 고정 metric sample 생성 → text/plain 응답

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| system router | notifications.metrics | 응답 생성 |
| metrics read model | `_store_connection._get_conn` | 동일 DB 연결·스키마 보장 |
| renderer | Python stdlib | deterministic text 생성 |

## 3. Data Model

DB migration은 없다. read model `WebhookMetricsSnapshot`은 다음 필드를 가진다.

```python
@dataclass(frozen=True)
class WebhookMetricsSnapshot:
    webhooks: dict[str, int]          # active, inactive
    deliveries: dict[str, int]       # fixed status set
    deliveries_24h: dict[str, int]   # success, failure
    duration_avg_ms_24h: float
    duration_max_ms_24h: int
    oldest_queue_age_seconds: float
```

고정 delivery 상태: `pending`, `queued`, `in_flight`, `retrying`, `success`, `failure`, `dead`, `skipped`.

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/metrics` | Prometheus text exposition | 기존 API auth 정책 적용 |

### 4.2 Detailed Specification

응답은 `text/plain; version=0.0.4; charset=utf-8`이며 아래 family를 포함한다.

| Metric | Labels | Type | Meaning |
|--------|--------|------|---------|
| `production_data_hub_webhooks` | `state` | gauge | active/inactive 설정 수 |
| `production_data_hub_webhook_deliveries` | `status` | gauge | 상태별 현재/누적 DB 행 수 |
| `production_data_hub_webhook_deliveries_24h` | `outcome` | gauge | 24시간 success/failure 수 |
| `production_data_hub_webhook_delivery_duration_avg_ms_24h` | 없음 | gauge | 24시간 완료 전송 평균 시간 |
| `production_data_hub_webhook_delivery_duration_max_ms_24h` | 없음 | gauge | 24시간 완료 전송 최대 시간 |
| `production_data_hub_webhook_oldest_queue_age_seconds` | 없음 | gauge | queued/retrying 최장 대기 시간 |

## 5. UI/UX Design

UI 변경 없음. 소비자는 Prometheus/Grafana/운영 자동화다.

## 6. Error Handling

| Case | Handling |
|------|----------|
| 빈 DB | 모든 고정 label을 0으로 출력 |
| 잘못된/naive timestamp | UTC로 간주; 파싱 불가 시 age 0 |
| 미래 timestamp | age를 0으로 clamp |
| SQLite 오류 | FastAPI 500 + 기존 로깅 경로; 허위 0으로 은폐하지 않음 |

## 7. Security Considerations

- URL, secret, payload, webhook ID, event type을 출력하지 않는다.
- `/metrics`를 `PUBLIC_PATHS`에 추가하지 않아 auth enabled 환경에서 인증을 요구한다.
- SQL은 사용자 입력이 없고 읽기 전용이다.

## 8. Test Plan

### 8.1 Test Scope

| Level | Target | Tool | Phase |
|------|--------|------|-------|
| L1 | snapshot/renderer 순수·DB 단위 테스트 | pytest | Do |
| L2 | `/metrics` contract/auth/OpenAPI | FastAPI TestClient | Do/QA |
| L3 | 기존 notifications 및 전체 API 회귀 | pytest 전체 suite | QA |
| L4 | Prometheus parser 연동 | 설치 없음으로 scope out | - |
| L5 | DB → API text data flow | fixture + TestClient | QA |

### 8.2 L1/L2 Scenarios

| # | Scenario | Expected |
|---|----------|----------|
| T1 | 빈 DB | 고정 상태가 전부 0 |
| T2 | active/inactive + 각 delivery 상태 seed | label별 정확한 수 |
| T3 | 24h 안/밖 완료 delivery | window 집계 정확 |
| T4 | 과거/future queue timestamp | 양수 age / 0 clamp |
| T5 | endpoint 호출 | 200, content type, HELP/TYPE 포함 |
| T6 | 민감 문자열 seed | 응답에 미포함 |
| T7 | auth enabled 무자격 호출 | 401 |
| T8 | OpenAPI | 기존 경로 + `/metrics` 유지 |

## 9. Clean Architecture

| Component | Layer | Location |
|-----------|-------|----------|
| metrics endpoint | Presentation | `api/routers/system.py` |
| snapshot/renderer | Application/read model | `api/notifications/metrics.py` |
| SQLite connection | Infrastructure | `api/notifications/_store_connection.py` |

Dependency direction은 router → metrics → connection 단방향이다.

## 10. Coding Convention Reference

- snake_case 함수/변수, PascalCase dataclass, UPPER_SNAKE_CASE 상수
- stdlib → FastAPI → shared/api 내부 순 import
- renderer는 trailing newline을 보장하고 정수/유한 float만 출력
- Design Ref와 Plan SC 주석은 핵심 경계에만 추가

## 11. Implementation Guide

### 11.1 File Structure

```text
api/notifications/metrics.py      # NEW: snapshot + renderer
api/routers/system.py             # MOD: GET /metrics
tests/test_webhook_metrics.py     # NEW: L1/L2/L5 tests
README.md                         # MOD: endpoint 문서
```

### 11.2 Implementation Order

1. [ ] immutable snapshot model과 UTC age helper
2. [ ] read-only aggregate query
3. [ ] deterministic Prometheus renderer
4. [ ] FastAPI plain-text endpoint
5. [ ] 단위·contract·auth·회귀 테스트
6. [ ] README endpoint 추가

### 11.3 Session Guide

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Metrics core | `module-1` | snapshot + renderer | 2 |
| API and QA | `module-2` | endpoint + tests + docs | 2 |

이번 사이클은 작고 결합된 변경이므로 한 세션에서 전체 scope를 구현한다.

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-19 | Option C 상세 설계 승인 | Codex |
