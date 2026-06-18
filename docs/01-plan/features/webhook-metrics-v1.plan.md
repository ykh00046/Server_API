# webhook-metrics-v1 Planning Document

> **Summary**: webhook 전송 큐의 운영 상태를 Prometheus 호환 메트릭으로 노출한다.
>
> **Project**: Production Data Hub
> **Version**: v10
> **Author**: Codex / bkit:pdca
> **Date**: 2026-06-19
> **Status**: Approved

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | webhook 비동기 전송은 재시도와 dead-letter를 지원하지만, 운영자가 장애와 적체를 자동 감지할 표준 메트릭이 없다. |
| **Solution** | 기존 notifications SQLite 상태를 읽기 전용 스냅샷으로 집계하고 `GET /metrics`에서 Prometheus text exposition 형식으로 제공한다. |
| **Function/UX Effect** | active/inactive webhook 수, 상태별 delivery 수, 24시간 성공·실패, 큐 최장 대기 시간과 전송 지연을 모니터링·알림 도구가 즉시 수집할 수 있다. |
| **Core Value** | webhook 장애를 사용자 신고 전에 발견하고 적체·실패 원인을 수치로 판단할 수 있는 운영 가시성을 확보한다. |

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 비동기 webhook의 실패·dead-letter·적체를 자동 감지할 표준 관측 지점이 없다. |
| **WHO** | Production Data Hub 운영자와 인프라 모니터링 담당자 |
| **RISK** | 잘못된 Prometheus 타입/고카디널리티 라벨 또는 집계 쿼리가 운영 부하를 만들 수 있다. |
| **SUCCESS** | `/metrics` 200 + Prometheus 형식, 핵심 6종 메트릭 정확성, 기존 전체 테스트·ruff 통과 |
| **SCOPE** | notifications read model, text renderer, FastAPI endpoint, 단위·통합 테스트와 운영 문서 |

## 1. Overview

### 1.1 Purpose

webhook 운영 상태를 외부 모니터링 시스템이 pull 방식으로 수집할 수 있게 한다.

### 1.2 Background

`webhook-async-dispatch-v2`와 `webhook-bulk-retry-v1`은 큐·재시도·dead-letter를 구현했고, `webhook-admin-ui-v1` 보고서는 다음 기능 후보로 `webhook-metrics-v1`을 명시했다. 저장소 분리보다 장애 감지 시간 단축과 운영 판단 지원이라는 직접 가치가 커 최우선으로 선정했다.

### 1.3 Related Documents

- `docs/04-report/webhook-admin-ui-v1.report.md`
- `docs/02-design/features/webhook-async-dispatch-v2.design.md`

## 2. Scope

### 2.1 In Scope

- [x] webhook 활성/비활성 수와 delivery 상태별 누적 행 수 집계
- [x] 최근 24시간 성공·실패 수와 평균/최대 전송 시간 집계
- [x] 처리 가능한 큐의 최장 대기 시간 집계
- [x] `GET /metrics` Prometheus 0.0.4 호환 text 응답
- [x] 고정된 저카디널리티 라벨과 deterministic 출력
- [x] 단위·API·회귀 테스트 및 문서화

### 2.2 Out of Scope

- Prometheus 서버/Grafana/Alertmanager 설치와 배포
- URL, webhook ID, event payload 등 고카디널리티·민감 라벨
- 프로세스 메모리/CPU, HTTP 전체 요청 메트릭
- DB 스키마 변경 및 background push exporter

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | active/inactive webhook 수를 gauge로 노출 | High | Approved |
| FR-02 | 알려진 모든 delivery status를 0 포함 gauge로 노출 | High | Approved |
| FR-03 | 최근 24시간 success/failure와 duration 평균·최대를 노출 | High | Approved |
| FR-04 | queued/retrying 중 최장 대기 시간을 음수 없이 노출 | High | Approved |
| FR-05 | `GET /metrics`가 UTF-8 Prometheus text로 응답 | High | Approved |
| FR-06 | HELP/TYPE과 escape·숫자 포맷이 결정적이어야 함 | Medium | Approved |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 로컬 fixture 100행에서 endpoint 200ms 미만 | pytest elapsed assertion |
| Security | URL/secret/payload/webhook_id 비노출, 기존 auth 정책 유지 | 응답 내용 테스트 |
| Compatibility | 새 의존성·DB migration 없음 | dependency diff 및 전체 테스트 |
| Quality | ruff 0건, 관련 테스트와 전체 suite 통과 | CI 명령 |

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: `/metrics`가 200과 올바른 content type을 반환한다.
- [ ] SC-2: webhook 상태와 모든 delivery 상태가 정확하며 빈 상태도 0으로 출력된다.
- [ ] SC-3: 24시간 window, duration, oldest queue age가 fixture 기대값과 일치한다.
- [ ] SC-4: 메트릭에 URL·secret·payload·webhook ID가 없다.
- [ ] SC-5: 관련/전체 pytest와 ruff가 통과한다.
- [ ] SC-6: Plan, Design, Analysis, QA, Report 문서가 완성된다.

### 4.2 Quality Criteria

- [ ] 외부 dependency 0
- [ ] DB write 0
- [ ] metric label cardinality가 고정 집합
- [ ] 기존 `/metrics/performance`, `/metrics/cache` 경로 회귀 없음

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| SQLite 집계 비용 | Medium | Low | 단일 연결·소수 GROUP BY, read-only, 고카디널리티 제거 |
| 시간대/음수 age | Medium | Medium | UTC ISO 파싱과 `max(0)` 적용, clock 주입 테스트 |
| counter 의미 오용 | High | Medium | DB 현재 상태는 모두 gauge로 모델링하고 이름/HELP에 snapshot 명시 |
| 민감정보 노출 | High | Low | 고정 라벨만 허용하고 content negative test 추가 |

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `api/notifications` | Read model | metrics snapshot·renderer 추가 |
| `api/routers/system.py` | API | `GET /metrics` 추가 |
| OpenAPI | Contract | 경로 1개 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| notifications DB | READ/WRITE | store, worker, admin API | 읽기 쿼리만 추가, breaking 없음 |
| `/metrics/*` | READ | 운영/테스트 | 기존 두 경로 유지 |
| auth middleware | READ | `api/main.py` | `/metrics`는 기존 정책대로 protected; auth disabled 기본값 유지 |

### 6.3 Verification

- [ ] 기존 notifications 테스트 전체 통과
- [ ] OpenAPI 기존 경로 집합 유지
- [ ] auth enabled에서 `/metrics` 401 검증

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 단일 파일 | |
| **Dynamic** | 기능 모듈 + FastAPI + SQLite | ✓ |
| Enterprise | 별도 telemetry service | |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Export format | JSON / Prometheus text | Prometheus text | 표준 scraper 호환 |
| Dependency | prometheus-client / 자체 renderer | 소형 자체 renderer | 새 의존성·global registry 불필요 |
| Metric model | counter / gauge snapshot | gauge | 재시도·정리로 감소 가능한 DB 현재 상태 |
| Endpoint auth | public / 기존 정책 | 기존 정책 | 운영 데이터의 불필요한 공개 방지 |
| Testing | live server / TestClient+fixture | TestClient+fixture | 결정적이고 빠른 검증 |

## 8. Convention Prerequisites

- Python 3.12, type hints, ruff 규칙을 적용한다.
- SQL은 parameter binding을 사용하고 renderer는 순수 함수로 유지한다.
- 환경 변수 추가 없음.

## 9. Next Steps

1. [x] Design 문서 작성 및 Option C 승인
2. [ ] 구현과 테스트
3. [ ] Check/Iterate/QA/Report

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-19 | 요구사항 확정 | Codex |
