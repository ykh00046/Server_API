# anomaly-dashboard-v2 Planning Document

> **Summary**: 규칙 기반 이상탐지(anomaly-detection-v1)의 관측 UI를 대시보드에 추가한다 — 현재 findings 현황, 발행 이력 타임라인, 쿨다운 상태, 임계치 조정 미리보기.
>
> **Project**: Production Data Hub
> **Version**: v11
> **Author**: Claude / bkit:pdca
> **Date**: 2026-07-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 이상탐지 v1은 탐지·발행은 하지만 관측 UI가 없다. 운영자는 webhook 수신 채널에 도착한 알림만 보고, "지금 무엇이 이상인가 / 최근 한 달간 무엇이 발행됐나 / 왜 이건 알림이 안 왔나(쿨다운?)"를 확인할 곳이 없다. |
| **Solution** | 대시보드에 "이상탐지" 페이지를 추가하고, 필요한 최소 API(발행 이력 저장·조회, 쿨다운 노출)를 anomaly 서브시스템에 보강한다. 스캔 미리보기는 기존 `GET /anomaly/scan`을 그대로 재사용한다. |
| **Function/UX Effect** | ① 현재 스캔 결과를 규칙별로 즉시 확인 ② 최근 30일 발행 이력 타임라인 ③ 쿨다운 중인 키와 남은 시간 표시("왜 안 왔나"에 답) ④ 임계치를 바꿔보는 what-if 미리보기(발행 없음). |
| **Core Value** | push 알림(v1)에 pull 관측을 더해 이상탐지 루프를 닫는다. 오탐 데이터가 쌓이면 B-6(품목별 규칙)의 근거가 된다. |

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 탐지는 돌지만 관측 UI가 없어 webhook 수신 채널에만 의존 (roadmap-2026h2 B-2, v1 plan의 명시적 후속) |
| **WHO** | Production Data Hub 운영자 |
| **RISK** | 이력 저장이 스캔 경로에 부하/실패 지점을 추가하는 것. what-if가 실수로 발행을 유발하는 것 |
| **SUCCESS** | 최근 30일 findings를 대시보드에서 확인 가능(roadmap 성공 기준), 발행 실패·재시도 의미론 불변, 전체 게이트 그린 |
| **SCOPE** | 이력 영속화 + 조회 API + 쿨다운 노출 + 대시보드 페이지. 규칙/임계치 변경 기능은 미리보기(read-only)까지만 |

## 1. Overview

### 1.1 Purpose

이상탐지 findings의 발행 이력을 영속화하고, 대시보드에서 현황·이력·쿨다운·what-if를 한 페이지로 관측한다.

### 1.2 Background

- v1(anomaly-detection-v1)은 `GET /anomaly/scan`(미리보기) / `POST /anomaly/scan`(발행) / `GET /anomaly/rules`(임계치)를 제공하고, 쿨다운 상태는 `.anomaly_state.json`(원자적 저장, full-review-202607에서 보강)에만 있다.
- **발행 이력이 어디에도 남지 않는다**: 쿨다운 dict(key→ts)는 `prune`이 7×COOLDOWN(기본 7일)에서 잘라내고 메시지·심각도를 담지 않는다. webhook_deliveries는 구독 webhook이 있을 때만, 전달 단위로 남는다. → "최근 30일 타임라인"은 신규 영속화가 필요하다.
- 대시보드는 dataset_page/webhook admin에서 확립된 패턴(httpx 클라이언트 + `WebhookAdminError`식 에러 정규화 + views/ 페이지 등록)을 재사용한다.

### 1.3 Related Documents

- `docs/01-plan/features/anomaly-detection-v1.plan.md` (Out of Scope에 대시보드 시각화 → 본 기능)
- `docs/01-plan/features/roadmap-2026h2.plan.md` (B-2, M3)
- `docs/01-plan/features/webhook-admin-ui-v1.plan.md` (대시보드 admin 페이지 패턴 선례)

## 2. Scope

### 2.1 In Scope

- [ ] **F1 발행 이력 영속화**: `_emit_new`에서 성공 발행된 finding을 append-only로 기록 (kind, severity, key, message, details JSON, emitted_at). 저장소는 SQLite `anomaly.db` 신규 파일 (production/notifications/materials와 동일한 파일 분리 관례)
- [ ] **F2 이력 조회 API**: `GET /anomaly/findings?days=30&kind=&severity=&limit=` — emitted_at 내림차순, keyset 불필요(30일 규모 작음, limit 상한 500)
- [ ] **F3 쿨다운 노출**: `GET /anomaly/state` — 쿨다운 중인 key 목록 + 남은 시간(sec) + last_scan_ts (state 파일 read-only 변환)
- [ ] **F4 대시보드 페이지** `dashboard/views/anomaly.py`: ① 현재 스캔(GET /scan) 규칙별 카드 ② 30일 이력 타임라인(일별 count 바 + 테이블) ③ 쿨다운 현황 ④ what-if: 임계치 입력 → 클라이언트 측 재판정 미리보기(아래 F5)
- [ ] **F5 what-if 미리보기**: 임계치 파라미터를 받는 `GET /anomaly/scan?drop_pct=&spike_pct=&stale_days=` 확장 (emit 불가 경로에만 허용 — POST에는 미적용)
- [ ] **F6 이력 보존 정책**: `ANOMALY_FINDINGS_RETENTION_DAYS`(기본 90) 초과분을 스캔 시 lazy 삭제
- [ ] 테스트(이력 저장/조회/보존, what-if 파라미터, 페이지 스모크 가능 범위) + 문서

### 2.2 Out of Scope

- 품목별 임계치 오버라이드 저장/UI — B-6 (이 페이지가 만든 오탐 데이터로 착수 판단)
- 임계치의 서버 측 영구 변경 (what-if는 조회 전용, .env가 여전히 SSOT)
- 알림 채널 관리 (webhook admin 페이지가 담당)
- 통계/ML 탐지, anomaly_watch 데몬 변경 (F1 훅킹 외 무변경)
- 과거(도입 이전) 이력 소급 — 도입 시점부터 쌓인다

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | 성공 발행된 finding만 이력에 기록된다 (emit 실패분 제외 — detector의 성공분-마킹 의미론과 일치) | Must |
| FR-2 | `GET /anomaly/findings`는 days/kind/severity 필터와 limit(≤500)을 지원한다 | Must |
| FR-3 | `GET /anomaly/state`는 쿨다운 key별 남은 시간과 마지막 스캔 시각을 반환한다 | Must |
| FR-4 | 대시보드 페이지는 API 다운 시 크래시 없이 에러를 표시한다 (dataset_page 계약) | Must |
| FR-5 | what-if 파라미터는 GET(미리보기)에서만 동작하고 emit·상태 변경이 절대 없다 | Must |
| FR-6 | 이력 기록 실패가 발행 자체를 실패시키지 않는다 (로그만, fire-and-forget) | Must |
| FR-7 | 90일(설정 가능) 초과 이력은 자동 정리된다 | Should |
| FR-8 | 타임라인은 일별 발행 건수 + severity 구분을 시각화한다 | Should |

### 3.2 Non-Functional Requirements

- 이력 기록은 스캔 경로에 O(발행 건수) 쓰기만 추가 (스캔 자체는 여전히 read-only 쿼리)
- anomaly.db는 WAL + busy_timeout, thread-local 커넥션 — notifications `_store_connection` 패턴 복제(또는 경량 공용화)
- 페이지는 `st.cache_data(ttl)` 로 스캔 결과를 짧게(60s) 캐시해 rerun 폭주 시 API 부하 방지
- unsafe_allow_html 신규 사용 0 (현행 2곳 유지)
- 기존 게이트: 전체 테스트, ruff, C901 잠금, 커버리지 floor 88

## 4. Success Criteria

- [ ] 대시보드에서 최근 30일 발행 이력 확인 가능 (roadmap-2026h2 성공 기준 충족)
- [ ] 쿨다운 중인 finding의 "다음 발행 가능 시각"이 UI에 보인다
- [ ] what-if로 임계치를 바꿔도 서버 상태·발행에 어떤 변화도 없다 (테스트로 고정)
- [ ] emit 실패 시 이력 미기록·발행 재시도 의미론(b1421f5) 불변 (기존 테스트 유지)
- [ ] 전체 테스트 + ruff + C901 그린

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| 이력 쓰기 실패가 스캔/발행을 중단 | High | FR-6: try/except + 로그, 발행 경로와 독립 (detector의 기존 예외 계층 관례) |
| what-if 파라미터가 POST 경로에 흘러 emit 판정을 왜곡 | Medium | F5를 GET 전용으로 구현, POST는 서명 무변경. 테스트로 고정 |
| anomaly.db 신규 파일이 tmp 테스트 격리를 깨뜨림 | Medium | conftest live_db 패턴 준수: config 경유 경로 + reset_for_tests 훅 제공 |
| 타임라인이 빈 상태(도입 직후)라 페이지가 빈약 | Low | 현재 스캔 카드가 1차 콘텐츠, 이력은 "누적 시작" 안내 문구 |
| 스캔 캐시(60s)로 최신성 혼동 | Low | "마지막 스캔 시각" 명시 + 수동 새로고침 버튼 (관례) |

## 6. Milestones

| Milestone | Content |
|-----------|---------|
| M1 | Design: anomaly.db 스키마, API 3종(F2/F3/F5) 계약, 페이지 레이아웃 |
| M2 | Do: 서버 측 (F1 영속화 → F2/F3 조회 → F5 what-if → F6 보존) |
| M3 | Do: 대시보드 페이지 (F4) + app 네비 등록 |
| M4 | Check: gap 분석 → 90%+ → Report |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-07-07 | 최초 작성 — roadmap-2026h2 B-2 착수 (M2 보류로 차기 1순위 승격분) |
