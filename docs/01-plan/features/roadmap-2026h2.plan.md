# roadmap-2026h2 Planning Document

> **Summary**: 2026-07 전면 검토(High 12·Medium 15 전량 수정) 이후의 유지보수 트랙, 개발 후보, 중장기 발전 방향을 하나의 우선순위 로드맵으로 정리한다.
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
| **Problem** | 기능 단위 PDCA는 잘 돌지만, 사이클 사이의 "다음에 무엇을 왜 하는가"가 세션 메모리와 리뷰 백로그에 흩어져 있다. 전면 검토로 부채가 소진된 지금이 방향을 문서로 고정할 적기다. |
| **Solution** | 유지보수(품질 유지)·개발(기능 추가)·발전(구조 진화) 3개 트랙으로 나누고, 각 항목에 근거·판정 기준·착수 조건을 달아 우선순위 큐로 관리한다. |
| **Function/UX Effect** | 다음 PDCA 사이클 착수 시 이 문서에서 항목을 꺼내 `/pdca plan {feature}`로 바로 진입한다. 완료 항목은 체크 후 Version History에 기록한다. |
| **Core Value** | 의사결정 이력의 단일 출처. "보류"도 근거와 함께 기록해 같은 논의를 반복하지 않는다. |

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 리뷰 부채 소진 직후, 산발적 백로그를 실행 가능한 로드맵으로 승격 |
| **WHO** | 운영자(단일), 개발 세션(Claude + bkit PDCA) |
| **RISK** | 로드맵이 실제 운영 필요와 괴리된 위시리스트가 되는 것. 항목별 "착수 조건"으로 방지 |
| **SUCCESS** | 각 사이클 시작 시 이 문서만 보고 다음 작업을 결정할 수 있다 |
| **SCOPE** | 우선순위·근거·판정 기준 정의까지. 개별 항목의 상세 설계는 각자의 plan/design 문서로 위임 |

## 1. Overview

### 1.1 Purpose

Server_API(FastAPI + SQLite + Streamlit + manager/봇) 프로젝트의 2026 하반기 유지보수·개발·발전 방향을 우선순위 큐로 고정한다.

### 1.2 Background — 현재 상태 (2026-07-07 기준)

- **품질**: 테스트 629개(수집 에러 0, skip 0, 실네트워크 0), 커버리지 floor 88(CI 전용), ruff 게이트 F/BLE001/I/UP/B/SIM/E501 + C901 3개 파일 잠금.
- **전면 검토 완료**: 6영역 병렬 검토 → High 12건 + Medium 15건 당일 수정·푸시(e5cc84f~da2cc29, 커밋 18개). Critical 0. 상세: `project_full_review_202607` 메모리.
- **서브시스템 성숙도**: webhook 알림(비동기 큐+backoff+리퍼+admin UI), 이상탐지 v1(규칙 기반), 자재/바인더 데이터셋 registry(대칭 작업 모델), AI 챗(SSE 스트리밍+폴백+멀티턴), auth-audit-v1(opt-in, 현재 비활성).
- **운영**: 서버+봇 단일 PC(192.168.200.107, 내부망), manager.vbs 트레이, 인증 비활성 open-access(의도된 opt-in).

### 1.3 Related Documents

- `docs/04-report/roadmap-consolidation-2026-02-26.report.md` (직전 로드맵 — anomaly v1으로 소진)
- `docs/01-plan/features/auth-audit-v1.plan.md` (T2의 토대)
- 메모리: `project_full_review_202607` (잔여 항목의 출처)

## 2. Scope

### 2.1 In Scope

- [x] 트랙 A — 유지보수: 검토 잔여물 + 품질 램프 + 의존성 추적
- [x] 트랙 B — 개발 후보: 기존 인프라 위에 얹는 기능 (우선순위·착수 조건 포함)
- [x] 트랙 C — 발전 방향: 구조적 진화 (판단 기준 포함, 착수는 조건부)
- [x] 분기별 재검토 절차

### 2.2 Out of Scope

- 개별 항목의 상세 설계(각자의 PDCA 사이클로)
- webcloring-pdf 봇 내부 로드맵(별도 저장소에서 관리, 결합점만 여기서 추적)
- 클라우드 이전/컨테이너화 — 단일 운영 PC + 내부망 전제가 유지되는 한 비대상

## 3. Requirements

### 3.1 트랙 A — 유지보수 (품질 유지, 상시)

| # | 항목 | 근거 | 규모 | 착수 조건 |
|---|------|------|------|----------|
| A-1 | ✅ 로컬 venv lock 재동기화 — 완료 2026-07-07 (pytest 9.1.0, ruff 0.15.17, 전체 게이트 그린) | pytest 9.0.3↔lock 9.1.0 드리프트. 9.1은 미등록 마커를 에러 처리 → 로컬 통과 ≠ CI 통과 | 5분 | ~~즉시~~ 완료 |
| A-2 | ✅ manager 로그 스트리밍 실동작 확인 — 운영자 확인 완료 2026-07-07 (이상 없음) | 0354317 Tk 마샬링은 GUI라 자동 테스트 불가 | 5분 | ~~운영 PC 업데이트 시~~ 완료 |
| A-3 | ✅ pytest-timeout 도입 여부 — **미도입 결정** 2026-07-07: 마커는 pyproject에 이미 등록·문서화("no-op unless installed"), 해당 테스트 hang은 자식 sleep(120s)으로 bounded. 단일 테스트를 위한 의존성 추가는 비용>이득 | `@pytest.mark.timeout(30)`이 no-op | 소 | ~~lock 갱신 편승~~ 결정 완료 |
| A-4 | ✅ test_session_store sleep→clock 주입 — 완료 2026-07-07 (`_session_store._clock` 시임 + FakeClock, sleep 전부 제거) | Windows time.time() 해상도(~15.6ms)보다 짧은 sleep(0.001) — 잠재 flaky | 소 | ~~여유 시~~ 완료 |
| A-5 | ✅ 품질 램프 R8: C901 전면 게이트 확대 — 완료 2026-07-16 (12c3e44: 위반 7건 헬퍼 추출로 해소, select에 C901 편입 + mccabe max-complexity=10) | 현재 3개 파일만 잠금. R3→R7 관례대로 "위반 0 파일부터 점진 잠금" | 중 | ~~분기 1회 램프 슬롯~~ 완료 |
| A-6 | Starlette/httpx2 마이그레이션 추적 | `StarletteDeprecationWarning: install httpx2` — 다음 starlette 메이저에서 강제될 것 | 중 | upstream GA 후 lock 갱신 사이클에서 |
| A-7 | chat↔stream 중복 로직 통합 (폴백 체인·툴콜 추출·상태코드 파싱) | 검토 M-5. **의도적 보류**: 리팩터 리스크 > 즉시 이득. 단, 폴백 정책을 다음에 수정할 때는 통합을 선행할 것 | 중 | 폴백/툴콜 로직에 기능 변경이 생길 때 |
| A-8 | ruff format 도입 | R7 때 blame 보존 사유로 보류. 재평가만 분기 1회 | — | 대규모 리네이밍/이동이 어차피 발생할 때 |

### 3.2 트랙 B — 개발 후보 (우선순위순)

| # | 항목 | 내용 | 근거 | 규모 |
|---|------|------|------|------|
| B-1 | **auth-enable-v2: 인증 실활성화 경로** | ① 대시보드 HTTP 클라이언트(webhook_admin, dataset_page, ai_section)에 API 키 헤더 일괄 지원(dataset_page `_headers()`는 이미 지원 — 나머지 정렬) ② 봇 ApiBackupManager 키 지원 확인 ③ 운영 .env에 키 발급 → `API_AUTH_ENABLED=true` 전환 리허설 | auth-audit-v1 토대는 완성·테스트 고정(d5b7ab8)됐으나 실제론 미사용. secret 노출 엔드포인트(webhook CRUD)가 내부망 신뢰에만 의존 중. **2026-07-07 운영 결정: 현상 유지** — 사내망 전체 신뢰 전제 수용(webhook 등록·/run 트리거 개방 리스크 인지 상태), 방화벽 IP 제한(옵션 ②)도 보류. 착수는 분기 재검토(10월) 때 재판단 — 전제가 깨지는 사건(사내망 사용자 증가, 보안 사고, 외부 노출 요구) 발생 시 즉시 승격 | 중 |
| B-2 | **anomaly-dashboard-v2** | 대시보드에 이상탐지 페이지: 최근 findings 타임라인, 규칙별 현황, 쿨다운 상태, 임계치 조정 미리보기(`POST /scan?emit=false` 재사용) | v1 plan의 명시적 후속. 탐지는 돌지만 관측 UI가 없어 webhook 수신 채널에만 의존 | 중 |
| B-3 | **notifications-deliveries-paging** | `list_deliveries`에 keyset 커서(`before_id`) — 최신 500건 이후 조회 불가 문제 | 검토 L-2. 대량 dead-letter 조사 시 필요. records.py 커서 패턴 재사용 | 소 |
| B-4 | **dataset 확장 대비 정리** | 신규 키워드 데이터셋 추가 리허설: datasets.py 한 줄 + 봇 config + 대시보드 views 파일의 3점 체크리스트 문서화, binder 전용 컬럼 헤더 확정(da2cc29의 `render(columns=)` 활용) | 멀티키워드 모델이 성장 축. 다음 데이터셋 추가 때 절차가 머리에만 있음 | 소 |
| B-5 | **materials-run 상태코드 세분화** | TriggerError를 사유별로 409(중복)/503(비활성)/500(설정오류) 분기 | 검토 M-6. 대시보드가 모든 실패를 "이미 실행 중"으로 오인 가능 | 소 |
| B-6 | **anomaly-rules-v2 (품목별 규칙)** | 품목별 임계치 오버라이드(설정 파일 기반, UI 없이 시작) | v1 Out of Scope 항목. B-2로 관측이 생긴 뒤 오탐 데이터를 보고 결정 | 중 |

### 3.3 트랙 C — 발전 방향 (구조 진화, 조건부)

| # | 방향 | 내용 | 착수 판단 기준 |
|---|------|------|---------------|
| C-1 | **관측성 통합** | webhook_metrics + anomaly + rate limiter + DB 유지보수 상태를 한 운영 헬스 페이지로. `/metrics` 게이지는 이미 존재 — 소비 UI만 부재 | 운영 장애를 "사후에 로그로" 알게 되는 일이 재발할 때 |
| C-2 | **RBAC/역할 분리** | auth-audit-v1 plan에 예고된 후속. 읽기(대시보드) vs 관리(webhook/실행 트리거) 권한 분리 | B-1 완료 + 사용자가 2인 이상 될 때. 단일 운영자인 동안은 과설계 |
| C-3 | **DB 성장 관리 자동화** | archive_cutoff.py(dry-run 수동)를 연 1회 정기 절차로: 실행 체크리스트 + notifications.db/materials.db 보존 정책 추가 | production DB 또는 deliveries 테이블이 성능에 보일 때(현재 무증상) |
| C-4 | **AI 레이어 확장** | 툴 추가(자재/바인더 데이터셋 질의, anomaly 조회), 응답 캐싱 검토. Gemini 모델 세대 교체 추적(폴백 GA 관례 유지) | 사용자 요청 기반. 툴 추가 시 `list[str] \| None` 시그니처 + FakeClient 스모크 관례 준수 |
| C-5 | **봇-서버 계약 강화** | webcloring-pdf ↔ Server_API 결합점(backup POST, run trigger, config 경로)의 계약 테스트. 현재 서브모듈 포인터 + 수동 확인에 의존 | 봇 쪽 대규모 변경(포털 개편 등)이 예정될 때 선행 |

### 3.4 Non-Functional Requirements

- 모든 트랙 공통: 기존 게이트(전체 테스트, ruff, C901 잠금 파일, 커버리지 floor 88) 통과가 완료 조건.
- 커밋은 논리 레이어별 분리(PDCA 관례), 커밋 메시지에 근거 문서/검토 ID 인용.
- 운영 PC 배포는 "update + 매니저 통째 재시작" 단일 절차 유지 — 이를 깨는 변경(신규 의존성, 스키마 마이그레이션)은 plan 문서에 배포 절차 섹션 필수.

## 4. Success Criteria

- [x] A-1~A-4 전량 소진 (2026-07-07) — **M1 완료**
- [~] B-1: 2026-07-07 보류 결정(현상 유지) — 10월 재검토에서 재판단
- [x] B-2 완료 (2026-07-08, Match Rate 96%, 운영 화면 확인) — anomaly-dashboard-v2
- [x] B-3~B-5 전량 소진 (2026-07-08) — M4 완료
- [ ] 분기 재검토 1회 수행: 이 문서의 우선순위 갱신 + 완료 항목 체크
- [ ] 새 PDCA 사이클이 이 문서를 참조해 착수된 비율 — 정성적으로 "다음 뭐 하지" 논의가 사라졌는가

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| B-1 인증 전환 중 봇/대시보드 무인증 클라이언트가 401로 조업 중단 | High | 전환 리허설: 키 배포 → 클라이언트 헤더 적용 → 마지막에 서버 활성화. 롤백은 .env 한 줄 |
| 로드맵이 stale — 실제 작업이 문서를 우회 | Medium | 분기 재검토를 A-트랙 상시 항목으로 고정, 세션 메모리에 문서 존재를 기록 |
| C-트랙 과설계 (단일 운영자 규모 초과) | Medium | 각 항목의 "착수 판단 기준" 충족 전 착수 금지 — 기준 자체를 문서에 명시함 |
| 봇(별도 repo) 변경이 서버 가정을 깨뜨림 | Medium | C-5를 봇 대규모 변경의 선행 조건으로 명시, 서브모듈 갱신 커밋에 결합점 언급 관례 유지 |

## 6. Milestones

| Milestone | Content | Target |
|-----------|---------|--------|
| M1 잔여 소진 | A-1~A-4 (venv 동기화, GUI 확인, pytest-timeout 결정, clock 주입) | 2026-07 중 |
| ~~M2 인증 실활성화~~ | B-1 — 2026-07-07 운영 결정으로 보류(현상 유지). 10월 재검토 안건 | ~~2026-08~~ 보류 |
| ✅ M3 이상탐지 관측 | B-2 anomaly-dashboard-v2 — **완료 2026-07-08** (계획 대비 1~2개월 조기) | ~~2026-08~09~~ |
| ✅ M4 소형 정리 묶음 | B-3(878396b keyset 페이징) + B-5(80ed3d9 상태코드 409/503/500) + B-4(0daf2a5 체크리스트) — **완료 2026-07-08** | ~~2026-Q3 내~~ |
| M5 품질 램프 | A-5 C901 R8 ✅(2026-07-16, 조기 완료) · A-6 의존성 추적 점검은 잔여 | ~~2026-Q4~~ A-6만 잔여 |
| 분기 재검토 | 이 문서 갱신 (완료 체크, 우선순위 재조정, C-트랙 착수 판단) | 10월 초 |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-07-07 | 최초 작성 — 전면 검토(full-review-202607) 소진 직후 잔여물 + 개발 후보 + 발전 방향 통합 |
| 0.2 | 2026-07-07 | M1 대부분 소진: A-1 venv 동기화, A-3 pytest-timeout 미도입 결정, A-4 clock 주입 완료. A-2만 운영 PC 업데이트 대기 |
| 0.3 | 2026-07-07 | M1 완료(A-2 운영 확인). **B-1 인증 활성화 보류 결정**(현상 유지, 리스크 인지 상태로 수용) — M2 취소, B-2가 차기 1순위로 승격 |
| 0.4 | 2026-07-08 | M3 완료: anomaly-dashboard-v2 (96%, 운영 확인). 다음 후보는 M4 소형 묶음(B-3 deliveries paging, B-5 상태코드, B-4 체크리스트) |
| 0.5 | 2026-07-08 | M4 완료(B-3/B-5/B-4). 잔여: M5 품질 램프(Q4), B-6·트랙 C는 조건 충족 대기, 10월 분기 재검토 |
| 0.6 | 2026-07-16 | A-5 C901 R8 완료(zcode 위임, 12c3e44). 동 사이클에서 대시보드 UI 통일(1b34123)·매니저 GUI 개선(49262b5, manager_theme.py 신설) — feature/ui-refactor-zcode 브랜치. 잔여: A-6, B-6, 트랙 C, 10월 재검토 |
