# anomaly-detection-v1 Planning Document

> **Summary**: 생산 데이터를 주기적으로 스캔해 급감·급증·장시간 미생산을 규칙 기반으로 탐지하고, 기존 webhook `emit_event`로 능동 알림을 발행한다.
>
> **Project**: Production Data Hub
> **Version**: v10
> **Author**: Claude / bkit:pdca
> **Date**: 2026-06-19
> **Status**: Approved

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 시스템은 모두 수동 조회(pull)다. 운영자가 대시보드/AI 챗으로 직접 묻지 않으면 생산 급감·장시간 미생산 같은 이상 징후를 늦게 발견한다. |
| **Solution** | `production_records`를 읽기 전용으로 주기 스캔하고, 후행(trailing) 평균 대비 임계치 규칙으로 이상을 판정해 기존 webhook 인프라(`emit_event`)로 push 알림을 발행한다. |
| **Function/UX Effect** | 생산량 급감/급증, 활성 품목의 장시간 미생산을 사람이 묻기 전에 webhook 구독 채널(Slack/사내 시스템)로 자동 통지한다. |
| **Core Value** | 관측을 pull→push로 전환해 문제 발견 시간(MTTD)을 단축한다. 전달/재시도/관리 UI는 검증된 webhook 서브시스템을 그대로 재사용하므로 신규 코드는 "탐지 규칙 + 스케줄러"로 최소화된다. |

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 이상 징후를 자동 감지할 능동 관측 지점이 없다. |
| **WHO** | Production Data Hub 운영자, 생산관리 담당자 |
| **RISK** | 잘못된 임계치/기준선으로 인한 오탐(false positive) 폭주, 알림 스팸, 읽기 쿼리의 운영 DB 부하. |
| **SUCCESS** | 3종 규칙 정확 판정, 쿨다운 기반 알림 dedup, 읽기 전용·idempotent 스캔, `emit_event` 재사용, 전체 테스트·ruff 통과. |
| **SCOPE** | 탐지 규칙(순수 함수) + 오케스트레이터 + 스캔 상태/쿨다운 + 스케줄 러너 + 온디맨드 조회 API + 설정 + 테스트·문서. |

## 1. Overview

### 1.1 Purpose

생산 데이터의 이상 징후를 규칙 기반으로 자동 탐지하고, 기존 webhook 채널로 능동 알림을 발행한다.

### 1.2 Background

`webhook-notifications-v1` ~ `webhook-async-dispatch-v2`로 비동기 전송·재시도·dead-letter·관리 UI를 갖춘 webhook 서브시스템이 완성되어, 도메인 코드는 `emit_event(type, payload)` 한 줄로 알림을 발행할 수 있다(`api/notifications/events.py`). 그러나 발행 트리거는 현재 `production.record.created` 수준에 머물러 있고, "이상 징후"를 판정하는 소비자가 없다. 본 기능은 그 소비자(탐지기)를 추가해 webhook 인프라의 가치를 실현한다.

`tools/watcher.py`는 이미 단발/데몬 주기 실행 + 상태파일(`.watcher_state.json`) 패턴을 검증했다. 동일 패턴을 차용해 별도 스케줄 러너를 둔다.

### 1.3 Related Documents

- `docs/04-report/webhook-async-dispatch-v2.report.md`
- `docs/04-report/webhook-admin-ui-v1.report.md`
- `docs/04-report/roadmap-consolidation-2026-02-26.report.md` (1순위 후보로 본 기능 선정)

## 2. Scope

### 2.1 In Scope

- [x] **규칙 1 — 생산량 급감**: 직전 완료일 총 양품 수량이 후행 N일 평균 대비 `DROP_PCT` 이상 하락
- [x] **규칙 2 — 생산량 급증**: 동일 비교에서 `SPIKE_PCT` 이상 상승
- [x] **규칙 3 — 장시간 미생산**: 기준 기간 내 생산 이력이 있던 활성 품목이 `STALE_DAYS` 이상 미생산
- [x] 순수 함수 탐지 규칙(I/O 분리, 단위 테스트 용이)
- [x] 오케스트레이터: 읽기 전용 쿼리 → 기준선 산출 → 규칙 적용 → dedup → `emit_event`
- [x] 쿨다운(`COOLDOWN_SEC`) 기반 알림 dedup 상태파일
- [x] 스케줄 러너 `tools/anomaly_watch.py` (단발/`--daemon`)
- [x] 온디맨드 조회 API `GET /anomaly/scan` (기본 dry-run, 발행 안 함) + `GET /anomaly/rules`
- [x] `shared/config.py` 환경변수 노브, 단위·API·회귀 테스트, 운영 문서

### 2.2 Out of Scope

- 통계/머신러닝 기반 이상탐지(계절성, STL, 회귀 등) — v2 후보
- 품목별 개별 임계치 커스터마이즈 UI / 임계치 DB 저장
- Slack/Email 등 채널 통합(이미 webhook 구독으로 위임)
- production_records 스키마 변경, 쓰기 작업
- 대시보드 시각화(별도 후속 `anomaly-dashboard-v2`)

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-1 | 직전 완료일 수량 vs 후행 N일 평균으로 급감/급증 판정 | High | Planned |
| FR-2 | 활성 품목의 마지막 생산일 기준 장시간 미생산 판정 | High | Planned |
| FR-3 | 각 이상에 대해 종류/심각도/키/메시지/근거를 담은 Finding 생성 | High | Planned |
| FR-4 | 신규(쿨다운 외) Finding만 `emit_event`로 비동기 발행 | High | Planned |
| FR-5 | `GET /anomaly/scan`로 발행 없이 현재 Finding 미리보기 | Medium | Planned |
| FR-6 | `GET /anomaly/rules`로 활성 임계치/설정 노출 | Low | Planned |
| FR-7 | 스케줄 러너 단발/데몬 실행 | High | Planned |

### 3.2 Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | 스캔은 read-only 연결만 사용 (`get_connection(read_only=True)`) | 운영 DB 무변경 |
| NFR-2 | 스캔 idempotent + 알림 dedup(쿨다운) | 동일 이상 반복 발행 0 |
| NFR-3 | 탐지기 예외가 러너/API를 죽이지 않음 | graceful degrade |
| NFR-4 | `emit_event`는 절대 예외 전파 안 함(기존 계약 유지) | fire-and-forget |
| NFR-5 | 기능 OFF 스위치(`ANOMALY_ENABLED`) | 기본 ON, 즉시 비활성 가능 |

## 4. Success Criteria

- 3종 규칙이 합성 데이터에서 정확히 판정/미판정 (경계값 포함)
- 동일 이상 반복 스캔 시 쿨다운 내 재발행 없음
- `GET /anomaly/scan` 200 + Finding 목록(발행 부작용 없음)
- 신규 코드 커버리지가 프로젝트 floor(88%) 유지/상회
- 전체 pytest + ruff 게이트 통과

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| 오탐 폭주 | 운영자 알림 피로 | 후행 평균 기준선 + `MIN_BASELINE_QTY` 바닥값 + 쿨다운 dedup |
| 알림 스팸 | 신뢰도 저하 | 이상 키별 쿨다운 상태파일 |
| 부분일(당일 미마감) 데이터로 급감 오판 | 거짓 급감 | "직전 완료일" 사용(당일 제외) |
| 신규/단발 품목을 stale로 오판 | 노이즈 | 기준 기간 내 생산 이력 있는 품목만 stale 후보 |
| 읽기 쿼리 부하 | 운영 지연 | 일 단위 집계 + 기존 인덱스(idx_production_date 등) 활용 |

## 6. Milestones

| Phase | Deliverable |
|-------|-------------|
| Design | 모듈 구조, Finding 모델, 규칙 시그니처, API 스펙 확정 |
| Do | `api/anomaly/` 구현 + 러너 + 라우터 + config + 테스트 |
| Check | gap-detector 분석, Match Rate ≥ 90% |
| Act | 잔여 갭 보정 |
| QA | pytest + ruff + 스캔 스모크 |
| Report | 완료 보고서 |

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-19 | Claude / bkit:pdca | 최초 작성 |
