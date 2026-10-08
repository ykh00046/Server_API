# roadmap-2026h2 Planning Document

> **Summary**: 2026-07 전면 검토(High 12·Medium 15 전량 수정) 이후의 유지보수 트랙, 개발 후보, 중장기 발전 방향을 하나의 우선순위 로드맵으로 정리한다.
>
> **Project**: Production Data Hub
> **Version**: v11
> **Author**: Claude / bkit:pdca
> **Date**: 2026-07-07 (분기 재검토 2026-10-05)
> **Status**: Active

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

### 1.2a 분기 재검토 — 현재 상태 (2026-10-05 기준)

- **품질**: 테스트 768개(+139), ruff 전 게이트 그린(C901 전역 mccabe≤10 포함). 경고 1건 = `StarletteDeprecationWarning: install httpx2`(A-6).
- **7/16 이후 변경(커밋 26개)**: materials tombstone v1(5015334)·백업 쓰기 최적화(4aa9fe8)·읽기 트래픽 rate limit 분리(58c22b7)·대시보드 2026-08 UI 검토 HIGH/MED/LOW 전량(eb01f92)·매니저 수집 작업 UI + 작업별 일시정지(d14ea08, manager-collector-ui-v1)·**봇 attendance collector 편입(d33e8ae, 9/22)** — 부서공개함 근태허가원 → BRM(IRMS) `/api/public/attendance-approvals`로 직접 POST. Server_API 계약면은 불변, 매니저 편집 모달은 materials/binder만 알아 해당 작업은 읽기 전용 표시.
- **의존성 드리프트**: lock 마지막 갱신 2026-06-19(3.5개월). 주요 격차 — fastapi 0.137→0.142, starlette 1.3.1→1.7.0, streamlit 1.58→1.65, google-genai 2.8→2.28, selenium 4.44→4.50, uvicorn 0.49→0.54, ruff 0.15→0.16. **httpx2 2.13.1 GA** → A-6 착수 조건 충족.
- **외부 지형 변화(Dashboard-Raw_material 측)**: 2026-08-21 시스템 경계 리뷰(`C:\X\Dashboard-Raw_material\docs/03-analysis/system-boundary-review.md`)가 헌장 확정 — **Server_API = 데이터 플랫폼(수집·보존·제공 + 데이터 이벤트 알림)**. 같은 날 Dashboard `/data-hub`가 Server_API 운영 콘솔(healthz·크롤러 stale 판정·웹훅 큐·이상탐지 카드·문서 조회/Excel·자재/바인더 수동 실행)을 흡수(d6d19cc→844092f, 운용 실측 완료). 리뷰의 1순위 백로그 = **Server_API 8502 Streamlit 대시보드 sunset(P1)**.
- **운영 사고 1건(2026-08-24, Dashboard 측 기록)**: 확인 목적 POST가 크롤러 2개를 동시 기동(Selenium 포털 세션 공유). 교훈은 Dashboard 쪽 "운용 서버에는 GET만" 규칙으로 흡수, 교차 데이터셋 동시 실행 차단은 Dashboard 프록시 계층이 수행. **Server_API의 가드(`automation.py` `_trigger_lock` + runs 테이블 `running` 검사)는 데이터셋 단위라 자재+바인더 동시 기동을 막지 못함** — 두 크롤러가 Selenium 포털 세션을 공유하므로 서버측 전역 가드가 정답(B-9 신설).

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
| A-6 | ✅ **Starlette/httpx2 마이그레이션 — 완료 2026-10-05** | starlette 1.x `testclient`는 `import httpx2 as httpx`를 먼저 시도하고 없을 때만 `httpx`로 폴백하며 경고. 앱 코드(notifications dispatcher·dashboard 클라이언트, MockTransport 주입)는 httpx 0.28 그대로 두고 **dev 의존성에 httpx2만 추가** — 두 패키지는 공존. 경고 0 확인 | ~~중~~ 소 | ~~A-9와 같은 사이클에서 즉시~~ 완료 |
| A-9 | ✅ **lock 분기 갱신 — 완료 2026-10-05** (fastapi 0.142.2·starlette 1.7.0·uvicorn 0.54·google-genai 2.28·pandas 3.0.6·numpy 2.5.3·plotly 7.1·altair 6.3·customtkinter 6.0·ruff 0.16.10·pytest 9.1.1) | 검증: 768 tests·ruff 그린, 매니저 위젯 스모크(ctk 6.0, 라이트/다크 토글), uvicorn+streamlit 실기동 healthz 200, **fresh venv에 lock 설치 후 전체 테스트**. ⚠️ `pip freeze`가 venv의 포털 전용 의존성(selenium 등)을 섞어 넣는 문제 발견 → `scripts/freeze_lock.py`(requirements 폐쇄 필터)+`constraints.txt`(streamlit==1.58.0 동결) 신설, README §3 갱신. ⚠️ customtkinter 6.0 동작 변화(버튼 release 시 발화·엔트리 포커스 해제·드롭다운 재클릭 닫힘)는 운용 PC 매니저에서 육안 확인 필요 | 소~중 | ~~즉시~~ 완료. 다음 갱신 2027-01 재검토 때 |
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
| B-6 | **anomaly-rules-v2 (품목별 규칙)** | 품목별 임계치 오버라이드(설정 파일 기반, UI 없이 시작) | v1 Out of Scope 항목. B-2로 관측이 생긴 뒤 오탐 데이터를 보고 결정. 2026-10 재검토: 오탐 신고 0건 → 계속 대기 | 중 |
| B-7 | ✅ **dashboard-8502-sunset — 완료 2026-10-05** (설계 `docs/02-design/features/dashboard-8502-sunset.design.md`). 운영자 결정: 8502 미사용 → UI + Gemini 챗 API + 툴 패키지까지 제거. 커밋 6개(f6baa7b UI·5c28aaf 챗·f719b36 툴·15e288d deps·b1080fa 문서). 코드 −10.6k줄, 테스트 768→486, lock 83→37핀, cov 93%, openapi 39경로. 잔여 운영: update.bat+매니저 재시작, 운용 .env 잔존 키 수동 삭제(operations_manual §9) | 원안 범위: `dashboard/` 3,478 LOC + manager 런처(`manager.py` streamlit run) + `stop.bat` 8502 + streamlit 의존성. 전제: Dashboard `/data-hub`가 상태·문서 조회·수동 실행을 이미 서빙, `/production`이 생산실적 분석을 서빙. **8502만 가진 기능 4종의 거취를 먼저 결정**: ① webhook CRUD admin(Dashboard는 파괴적 조작을 의도적으로 제외 → manager GUI 또는 CLI로 이관 후보) ② anomaly findings·what-if 페이지 ③ 문서 삭제/tombstone 복원 UI ④ Gemini 챗(Dashboard 챗으로 일원화 후보). 1단계 = 운용 PC 8502 실사용 여부 확인(접속 로그/운영자 확인) | Dashboard 경계 리뷰 P1(최대 효과). 헌장상 "화면"은 Dashboard 소유. 사용자 창구 2개·LLM 창구 2개 유지 비용 제거. Dashboard 측 Streamlit sunset 플레이북(2026-05) 재사용 | 중~대 |
| B-8 | ✅ **manager collector-type 확장 — 2026-10-08 축소 종결** | 동기였던 근태허가원 수집기를 봇에서 제거(IRMS 자체 수집으로 고아화)하면서 "신규 type 전용 모달"의 필요가 사라짐. 남긴 것: `resolve_badge`가 모달이 모르는 type을 `{문서함}·{type}[·평일]`로 일반 표시하고 저장 시 보존(테스트 2건 일반화). 다음 collector가 생기면 그때 모달 확장 재판단 | ~~매니저 작업 모달이 materials/binder 패턴만 인식 → attendance 같은 신규 collector는 읽기 전용 배지로만 표시(d33e8ae). 패턴 레지스트리를 봇 collectors 스키마에서 파생하도록 일반화~~ | 봇 collector 추가가 실제로 발생(9/22). 다음 collector 추가 때 또 "spec 보호" 땜질이 필요 | 소 |
| B-9 | ✅ **run 트리거 전역 동시 실행 가드 — 완료 2026-10-05** (`docs/02-design/features/run-trigger-global-guard-v1.design.md`). `runs.active_automation_dataset()`/`reap_stale_running_all()`로 교체, 409 메시지에 실행 중인 데이터셋 명시, 되돌려 실패 확인한 테스트 2건. 매니저 Run Now는 봇 직접 spawn이라 범위 밖(봇 측 락 부재는 C-5 과제) | ~~`automation.py` 가드를 데이터셋 단위 → 프로세스 전역(모든 runs 테이블 중 하나라도 `running`이면 409)으로 승격~~ | 2026-08-24 사고: 자재+바인더 동시 기동(포털 세션 공유). 현재는 Dashboard 프록시만 막고 있어 `/run` 직접 POST 경로는 무방비(매니저 Run Now가 같은 경로를 타는지는 착수 시 확인) | 소 |

### 3.3 트랙 C — 발전 방향 (구조 진화, 조건부)

| # | 방향 | 내용 | 착수 판단 기준 |
|---|------|------|---------------|
| C-1 | **관측성 통합** — ✅ 2026-10 재검토: **Dashboard `/data-hub`가 소비 UI 역할을 대신 충족**(healthz·크롤러 데이터셋별 stale·웹훅 큐·이상탐지 카드). Server_API 안에 별도 헬스 페이지를 만들지 않는다(B-7과 일관). 잔여는 `/metrics` 게이지 중 허브가 안 보여주는 것(rate limiter·DB 유지보수)의 노출 여부뿐 | ~~webhook_metrics + anomaly + rate limiter + DB 유지보수 상태를 한 운영 헬스 페이지로~~ | 허브에서 못 본 장애를 사후 로그로 알게 될 때 → Dashboard 허브 카드 추가로 대응 |
| C-2 | **RBAC/역할 분리** | auth-audit-v1 plan에 예고된 후속. 읽기(대시보드) vs 관리(webhook/실행 트리거) 권한 분리 | B-1 완료 + 사용자가 2인 이상 될 때. 단일 운영자인 동안은 과설계 |
| C-3 | **DB 성장 관리 자동화** | archive_cutoff.py(dry-run 수동)를 연 1회 정기 절차로: 실행 체크리스트 + notifications.db/materials.db 보존 정책 추가 | production DB 또는 deliveries 테이블이 성능에 보일 때(현재 무증상) |
| C-4 | **AI 레이어 확장** | 툴 추가(자재/바인더 데이터셋 질의, anomaly 조회), 응답 캐싱 검토. Gemini 모델 세대 교체 추적(폴백 GA 관례 유지) | 사용자 요청 기반. 툴 추가 시 `list[str] \| None` 시그니처 + FakeClient 스모크 관례 준수 |
| C-5 | **봇-서버 계약 강화** | webcloring-pdf ↔ Server_API 결합점(backup POST, run trigger, config 경로)의 계약 테스트. 현재 서브모듈 포인터 + 수동 확인에 의존. 2026-10 재검토: 봇에 attendance collector가 추가됐으나 목적지가 BRM이라 Server_API 계약면은 불변 → 조건 미충족 유지. Dashboard 경계 리뷰 P6도 같은 항목을 지목(consumer-driven contract, L24 4-layer 경험 공유) | 봇 쪽 대규모 변경(포털 개편 등)이 예정될 때 선행. **B-7 sunset으로 봇 config GUI가 매니저 단독이 되면 결합점이 1곳 줄어 착수 비용↓** |

### 3.4 Non-Functional Requirements

- 모든 트랙 공통: 기존 게이트(전체 테스트, ruff, C901 잠금 파일, 커버리지 floor 88) 통과가 완료 조건.
- 커밋은 논리 레이어별 분리(PDCA 관례), 커밋 메시지에 근거 문서/검토 ID 인용.
- 운영 PC 배포는 "update + 매니저 통째 재시작" 단일 절차 유지 — 이를 깨는 변경(신규 의존성, 스키마 마이그레이션)은 plan 문서에 배포 절차 섹션 필수.

## 4. Success Criteria

- [x] A-1~A-4 전량 소진 (2026-07-07) — **M1 완료**
- [~] B-1: 2026-07-07 보류 결정(현상 유지) — **2026-10-05 재판단: 현상 유지 연장(권고, 운영자 확인 대기)**. 승격 트리거(사용자 증가·보안 사고·외부 노출 요구) 중 발생한 것 없음. 단, Dashboard 허브가 서버측 프록시로 `/run`을 호출하는 새 쓰기 경로가 생겼으므로 B-1 착수 시 클라이언트 목록에 Dashboard `DataHubClient`를 추가해야 함. 다음 재판단 2027-01
- [x] B-2 완료 (2026-07-08, Match Rate 96%, 운영 화면 확인) — anomaly-dashboard-v2
- [x] B-3~B-5 전량 소진 (2026-07-08) — M4 완료
- [x] 분기 재검토 1회 수행 (2026-10-05): 완료 체크·A-6 승격·A-9/B-7/B-8/B-9 신설·C-1 외부 충족 판정
- [x] 새 PDCA 사이클이 이 문서를 참조해 착수된 비율 — 7/16 이후 사이클 4개(tombstone·backup opt·manager-collector-ui·attendance) 중 로드맵 유래 0, 전부 운영 신고/봇 변경 유래. **"다음 뭐 하지" 논의는 사라졌으나 로드맵은 사후 기록 역할** — 허용 가능(운영 이슈 우선 원칙), 분기 재검토에서 흡수하는 것으로 충분

### 4.1 2026-10 재검토 이후 착수 순서 (권고)

1. ✅ **A-6 + A-9 (lock 갱신 + httpx2)** — 완료 2026-10-05(v0.8). streamlit 핀은 B-7 결정 전까지 1.58 동결.
2. ✅ **B-7 dashboard-8502-sunset** — 완료 2026-10-05(v0.9). 운영자 결정: 미사용 → UI+챗 API+툴 전부 제거, 관리 조작은 curl 레시피(api_integration_guide §6).
3. ✅ **B-9 (전역 동시 실행 가드)** — 완료 2026-10-05(v0.10).
4. B-8 → C-5 순. B-6·C-2~C-4는 조건 대기 유지.

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
| ✅ 분기 재검토 | 이 문서 갱신 (완료 체크, 우선순위 재조정, C-트랙 착수 판단) — **수행 2026-10-05 (v0.7)** | ~~10월 초~~ |
| ✅ M6 의존성 갱신 | A-6 httpx2 + A-9 lock 분기 갱신 (streamlit 핀 동결) — **완료 2026-10-05**, 운용 PC 반영은 update.bat + 매니저 재시작(ctk 6.0 육안 확인 동반) | ~~2026-10~~ |
| ✅ M7 8502 sunset | B-7 — **완료 2026-10-05** (실사용 0 확인 → 설계 → UI·챗 API·툴 패키지 제거, 레이어별 커밋 6개). 운용 PC 반영은 update.bat + 매니저 재시작 | ~~2026-Q4~~ |
| ✅ M8 소형 묶음 2 | B-9 전역 가드(2026-10-05) + B-8(2026-10-08 축소 종결 — 근태 수집기 제거로 동기 소멸, 배지 일반화만) | ~~2026-Q4~~ |
| 분기 재검토 2 | B-1 인증 재판단(2027-01), C-트랙 조건 점검 | 2027-01 초 |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-07-07 | 최초 작성 — 전면 검토(full-review-202607) 소진 직후 잔여물 + 개발 후보 + 발전 방향 통합 |
| 0.2 | 2026-07-07 | M1 대부분 소진: A-1 venv 동기화, A-3 pytest-timeout 미도입 결정, A-4 clock 주입 완료. A-2만 운영 PC 업데이트 대기 |
| 0.3 | 2026-07-07 | M1 완료(A-2 운영 확인). **B-1 인증 활성화 보류 결정**(현상 유지, 리스크 인지 상태로 수용) — M2 취소, B-2가 차기 1순위로 승격 |
| 0.4 | 2026-07-08 | M3 완료: anomaly-dashboard-v2 (96%, 운영 확인). 다음 후보는 M4 소형 묶음(B-3 deliveries paging, B-5 상태코드, B-4 체크리스트) |
| 0.5 | 2026-07-08 | M4 완료(B-3/B-5/B-4). 잔여: M5 품질 램프(Q4), B-6·트랙 C는 조건 충족 대기, 10월 분기 재검토 |
| 0.6 | 2026-07-16 | A-5 C901 R8 완료(zcode 위임, 12c3e44). 동 사이클에서 대시보드 UI 통일(1b34123)·매니저 GUI 개선(49262b5, manager_theme.py 신설) — feature/ui-refactor-zcode 브랜치. 잔여: A-6, B-6, 트랙 C, 10월 재검토 |
| 0.7 | 2026-10-05 | **10월 분기 재검토**. 현황 갱신(테스트 768, 7/16 이후 커밋 26개 — tombstone·backup opt·UI 검토·manager-collector-ui·attendance collector). A-6 착수 조건 충족(httpx2 GA)·A-9 lock 갱신 신설. Dashboard 경계 리뷰(8/21) 반영: B-7 8502 sunset 신설(1순위 개발 후보), C-1은 Dashboard 허브로 외부 충족 판정. 8/24 동시 기동 사고 → B-9 전역 가드 신설. B-8 collector-type 일반화 신설. B-1 현상 유지 연장 권고(2027-01 재판단). 착수 순서 §4.1 |
| 0.8 | 2026-10-05 | **M6 완료(A-6 httpx2 + A-9 lock 갱신)**, chore/deps-2026-10. 4중 검증(768 tests·매니저 ctk 6.0 위젯 스모크·uvicorn/streamlit 실기동·fresh venv lock 설치). lock 생성 절차를 `scripts/freeze_lock.py` + `constraints.txt`로 고정(포털 의존성 혼입 차단, streamlit 1.58 동결). 다음 = B-7 1단계(운영자 결정) · B-9 |
| 0.9 | 2026-10-05 | **M7 완료(B-7 dashboard-8502-sunset)**, feat/dashboard-8502-sunset. 운영자 결정(8502 미사용)으로 UI+Gemini 챗 API+툴 패키지 제거: 코드 −10.6k줄, 테스트 768→486, lock 83→37핀, cov 93%, 의존성에서 streamlit·plotly·altair·pandas·google-genai 소멸. 구현 중 발견: `pip freeze` 포털 의존성 혼입(A-9에서 해결), MATERIALS_API_KEY는 봇 키라 유지. 다음 = B-9 전역 동시 실행 가드 → B-8 |
| 0.10 | 2026-10-05 | **B-9 완료**(run-trigger-global-guard-v1): 가드를 데이터셋 단위→전역으로, 409 메시지에 실행 중 데이터셋 명시, 고아 running 전 테이블 정리. 488 tests·cov 93%. operations_manual 비활성 코드 409→503 오기 정정. 다음 = B-8 collector-type 일반화(M8 잔여) |
| 0.11 | 2026-10-08 | 봇 서브모듈 bump(9bda704 → 봇 fa42536): **목록 행 지문 스킵 + 완료일 60일 고정 창**(IRMS 수집기 비교에서 역이식, PDF·브라우저 유지). 봇 테스트 285. 결합점 불변(backup POST·run 트리거). 운용 첫 실행은 60일치 1회 전수 열람. 비교 결과·근태 작업 거취(제거 권고, 결정 대기)는 메모리 `project_irms_collector_comparison` |
