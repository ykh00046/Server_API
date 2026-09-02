# Server_API (Production Data Hub) 개선 플랜

> **상태: ✅ 완료 반영** (2026-07-15) — 본 플랜의 P0-1은 04 지시서로, 감사 3건은 05 지시서로 실행되어 `main`(9603290)에 병합·push 완료. P1/P2/F 항목은 §6 로드맵대로 후속 슬롯 대기.

> 분석일: 2026-07-12 · 분석 대상: `C:\X\Server_API` (webcloring-pdf submodule 포함)
> 근거: 실제 소스 코드, `README.md`, `docs/specs/*`, `docs/01-plan/features/roadmap-2026h2.plan.md`(v0.5, 2026-07-08), `docs/archive/2026-06/_INDEX.md`

---

## 1. 프로젝트 개요

### 1.1 목적

INTEROJO 사내 **생산 데이터 분석 및 AI 챗봇 시스템**. ERP가 갱신하는 SQLite 생산 DB를 읽어
대시보드 시각화·REST API·자연어(AI) 질의를 제공하고, 포털 자동화 봇(webcloring-pdf)이 수집한
자재요청/액상바인더출고 데이터를 수신·보관한다. 운영 환경은 **내부망 단일 PC(192.168.200.107)**,
운영자 1인.

### 1.2 기술 스택

| 계층 | 기술 | 근거 파일 |
|------|------|-----------|
| API 서버 | Python 3.12 + FastAPI + uvicorn (GZip, CORS, Rate Limit, SSE) | `api/main.py` |
| 대시보드 | Streamlit (st.navigation 멀티페이지, 네이티브 테마) | `dashboard/app.py`, `dashboard/views/` |
| DB | SQLite 5개 파일 — Live(`production_analysis.db`) + Archive(`archive_2025.db`) + `notifications.db` + `materials.db` + `anomaly.db` | `shared/config.py` |
| AI | Google Gemini (`google-genai` SDK, `gemini-2.5-flash` + `flash-lite` 폴백), 도구 7개 + Text-to-SQL | `api/chat.py`, `api/_gemini_client.py`, `api/_tool_dispatch.py` |
| 관리 GUI | CustomTkinter + pystray 트레이 (API·대시보드·봇 자식 프로세스 관리) | `manager.py` (803줄) |
| 포털 봇 | PySide6 + Selenium (별도 repo, git submodule) | `webcloring-pdf/` |
| CI | GitHub Actions — ruff 게이트 + pytest coverage floor 88 | `.github/workflows/ci.yml` |

### 1.3 규모

- 핵심 소스 약 **16,100줄** (`api/` + `dashboard/` + `shared/` + `tools/` + `scripts/` + `manager.py`, webcloring-pdf 제외)
- 테스트 **30여 파일 / 약 630 케이스** (2026-07-07 기준, `roadmap-2026h2.plan.md` §1.2)
- PDCA 문서 체계: `docs/01-plan` ~ `05-qa` + 월별 archive (28개 이상의 완료 사이클 기록)

---

## 2. 현재 상태 진단

### 2.1 강점

1. **품질 게이트가 실제로 작동한다.**
   - ruff 게이트 `F/BLE001/I/UP/B/SIM/E501` + C901(3개 파일 잠금)이 `pyproject.toml` SSOT로 CI에 걸려 있고,
     R3→R7 단계적 램프 이력이 문서화되어 있다 (`pyproject.toml` 주석, `docs/archive/2026-06/_INDEX.md`).
   - 커버리지 floor 88(CI 전용), `requirements.lock.txt` 핀 고정, flaky 원천 제거(RateLimiter `clock` 주입,
     `_session_store._clock` 시임 — `shared/rate_limiter.py`, `api/_session_store.py`).

2. **아키텍처 결정이 근거와 함께 기록되어 있다.**
   - 대시보드의 DB 직접 접근 vs API 경유 트레이드오프가 `docs/specs/system_architecture.md` §4에
     장애 격리/성능/단순성 근거로 명시. "왜 이 구조인가"를 재논의할 필요가 없다.
   - `dashboard/views/`가 `pages/`가 아닌 이유(Streamlit v1 라우팅 플래그 회피)까지
     코드 주석으로 남아 있다 (`dashboard/app.py` 상단 NOTE).

3. **보안 다층 방어가 설계되어 있다.**
   - SQLite 읽기 전용 URI(`mode=ro`, `shared/database.py:get_connection`) + SELECT-only 검증 +
     쿼리 타임아웃 + 파라미터 바인딩 강제(`api/tools/custom.py`) — Text-to-SQL 도구의 4중 방어.
   - opt-in 인증(`shared/auth.py` — 상수시간 비교, PUBLIC_PATHS SSOT) + 감사 로그(`api/_audit.py`),
     ATTACH 화이트리스트(`shared/_db_attach.py`), LIKE escape(`shared/validators.py`).

4. **확장 패턴이 준비되어 있다.**
   - 데이터셋 레지스트리(`api/materials/datasets.py`): 신규 키워드 데이터셋 추가 = Dataset 한 줄 +
     봇 config + 대시보드 view. 체크리스트도 문서화됨(`docs/dataset-add-checklist.md`).
   - webhook 알림(비동기 큐 + backoff worker, `api/notifications/worker.py`), 이상탐지 v1 규칙 엔진
     (`api/anomaly/detector.py`, `rules.py`)이 이벤트 발행 인프라로 재사용 가능.

5. **운영 자동화**: DB watcher(mtime 감지 → 인덱스 복구 → 24h ANALYZE, `tools/watcher.py`,
   `shared/db_maintenance.py:REQUIRED_INDEXES` 6종 SSOT), 자동 백업(`tools/backup_db.py`),
   `update.bat` 단일 배포 절차.

### 2.2 약점 · 기술 부채

| # | 항목 | 근거 | 리스크 |
|---|------|------|--------|
| W-1 | **인증 비활성 open-access 운영.** `API_AUTH_ENABLED=false`가 기본이고 운영에서도 미사용. webhook CRUD(`api/routers/notifications.py`)와 프로세스 기동 트리거(`POST /materials/run`, `api/materials/automation.py`)가 내부망 신뢰에만 의존 | `shared/config.py:148`, roadmap B-1 (2026-07-07 "현상 유지" 운영 결정, 10월 재검토) | 사내망 사용자 증가·외부 노출 시 즉시 High |
| W-2 | **chat ↔ stream 로직 중복.** 폴백 체인·툴콜 추출·상태코드 파싱이 `api/chat.py`(467줄)와 `api/_chat_stream.py`(346줄)에 이중 구현 | roadmap A-7 (검토 M-5, 의도적 보류) | 폴백 정책 수정 시 한쪽 누락 → 스트리밍/논스트리밍 동작 불일치 |
| W-3 | **쿼리 빌드 로직 이중화.** `dashboard/data.py`의 `load_records`/`load_monthly_summary` 등이 `api/routers/records.py`·`summary.py`와 같은 DBRouter 조합 패턴을 별도로 구현. 특히 `data.py`의 일/주/월 집계 3함수(204~312행)는 거의 동일 코드의 3벌 복사 | `dashboard/data.py`, `api/routers/records.py` | 필터·집계 규칙 변경 시 4곳 수정(이미 주 경계 불일치 버그를 한 번 겪음 — `data.py:296` 주석) |
| W-4 | **패키징 부재 — `sys.path.insert` 부트스트랩.** `pyproject.toml`에 `[project]` 섹션이 없어 pip 설치 불가. 진입점마다 경로 해킹 | `api/main.py:14`, `dashboard/app.py:20`, `manager.py:25` | import 순서 의존성, IDE/타입체커 혼란, 하위 호환 re-export 심(`api/main.py:39`, `api/chat.py:63~71`)의 잔존 원인 |
| W-5 | **대시보드 렌더 코드 무측정·무테스트.** coverage omit 화이트리스트로 `dashboard/views/*`, `charts.py`, `layout.py` 등 제외 — 순수 헬퍼(`_parsing.py`, `kpi_cards.py`)만 측정 | `pyproject.toml [tool.coverage.run] omit` | UI 회귀는 수동 확인(Playwright 실측은 사이클 단위 일회성)에 의존 |
| W-6 | **manager.py 803줄 단일 파일 GUI.** 프로세스 관리·트레이·로그 스트리밍·설정 다이얼로그가 한 파일. Tk 마샬링 등은 자동 테스트 불가(roadmap A-2가 수동 확인이었던 이유) | `manager.py` | 운영 필수 컴포넌트인데 회귀 검증 수단이 육안뿐 |
| W-7 | **DB 스키마 마이그레이션 체계 부재.** notifications/materials/anomaly 각 store가 `CREATE TABLE IF NOT EXISTS`로 자체 스키마 관리. 버전 개념 없음 | `api/materials/store.py`, `api/notifications/_store_connection.py`, `api/anomaly/store_findings.py` | 컬럼 추가/변경 시 ad-hoc ALTER — 데이터셋 확장 축과 충돌 가능 |
| W-8 | **연 단위 수동 절차 잔존.** `ARCHIVE_CUTOFF_YEAR = 2026` 하드코딩(`shared/config.py:36`) + `scripts/archive_cutoff.py` 수동 dry-run. 연초에 사람이 기억해야 함 | roadmap C-3 (착수 조건: 성능 증상 발현 시) | 2027-01 컷오버 누락 시 Live DB 비대 + 라우팅 경계 오류 |
| W-9 | **의존성 추적 항목.** Starlette가 `httpx2` 마이그레이션을 예고(DeprecationWarning) — 다음 메이저에서 강제 | roadmap A-6 | lock 갱신 사이클에서 대응 필요 |
| W-10 | **CI가 Windows 운영 환경을 검증하지 않음.** CI는 ubuntu-latest, 스모크는 Linux/WSL 전용(`tools/smoke_api.sh`). 운영은 Windows + bat + tkinter | `.github/workflows/ci.yml`, `README.md` §스모크 | GUI/프로세스 관리 계열 회귀는 운영 PC에서만 발견 |

**종합**: 2026-07 전면 검토(High 12 + Medium 15 전량 수정, Critical 0)와 자체 로드맵
(`roadmap-2026h2.plan.md`)이 이미 존재하는, **부채가 관리되고 있는** 코드베이스다.
따라서 본 플랜은 그 로드맵과 정합을 유지하면서(중복 재발명 금지), 로드맵이 다루지 않은
구조 항목(W-3, W-4, W-7, W-10)을 보강하는 방향으로 잡는다.

---

## 3. 개선 과제 (우선순위)

### P0 — 지금 하지 않으면 사고가 나는 것

| ID | 과제 | 이유 | 기대 효과 |
|----|------|------|-----------|
| P0-1 | **인증 활성화 리허설 완주 (auth-enable-v2)** — 대시보드 HTTP 클라이언트(`webhook_admin/api_client.py`, `ai_section.py`)에 `dataset_page._headers()` 패턴(이미 `MATERIALS_API_KEY`/`DASHBOARD_API_KEY` 지원, `dashboard/dataset_page.py:40~44`)을 일괄 적용 → 봇 `ApiBackupManager` 키 확인 → 운영 `.env` 키 발급 → `API_AUTH_ENABLED=true` 전환 | 서버 토대(`shared/auth.py` + 감사)는 완성·테스트 고정 상태인데 실사용 0. `POST /materials/run`은 **웹 요청으로 OS 프로세스를 기동**하는 엔드포인트고, webhook CRUD는 URL secret을 다룬다. "내부망 신뢰" 전제는 운영 결정으로 수용됐지만(2026-07-07), 클라이언트 측 준비만이라도 끝내두면 전환이 `.env` 한 줄이 된다 | 10월 재검토 시(또는 전제 붕괴 사건 시) 무중단 전환. 롤백도 `.env` 한 줄 |
| P0-2 | **백업 복구 훈련 + 무결성 검증 자동화** — `tools/backup_db.py`는 백업만 하고 복구 검증이 없음. 분기 1회 restore drill 절차 + 백업 파일 `PRAGMA integrity_check` 자동화를 `tools/backup_db.py`에 추가 | 5개 DB 파일이 단일 PC에 있고, materials/binder는 봇이 재수집 가능하지만 notifications/anomaly 이력은 유일본. "백업이 있다"와 "복구가 된다"는 다른 문제 | 디스크 장애 시 실제 복구 가능성 보장. 코드 변경 소(小) |

### P1 — 다음 기능 개발 전에 정리해야 하는 것

| ID | 과제 | 이유 | 기대 효과 |
|----|------|------|-----------|
| P1-1 | **chat/stream 공통 코어 추출** (`api/_chat_core.py`) — 로드맵 A-7의 "폴백 정책을 수정할 때 통합 선행" 조건을 명시적 선행 과제로 승격 | Gemini 모델 세대 교체(C-4)가 예정된 이상 폴백 체인 수정은 시간문제. 그때 이중 구현이 그대로면 두 배의 수정 + 불일치 리스크 | 스트리밍/논스트리밍 동작 단일화, 이후 AI 도구 추가 비용 절반 |
| P1-2 | **공용 쿼리 서비스 계층** (`shared/queries.py`) — `dashboard/data.py`와 `api/routers/`의 중복 쿼리 빌드를 순수 함수(SQL+params 반환)로 통합. DB 직접 접근 구조 자체는 유지(설계 원칙 존중) | W-3. 일/주/월 집계 3벌 복사가 대표 사례. "직접 접근 vs API 경유"를 건드리지 않고 로직 중복만 제거 가능 | 필터/집계 규칙의 SSOT 확보. 신규 대시보드 페이지·AI 도구가 같은 함수를 재사용 |
| P1-3 | **패키지화** — `pyproject.toml`에 `[project]` + `pip install -e .`, `sys.path.insert` 제거, re-export 심 정리(테스트 import 경로 함께 수정) | W-4. 지금은 파일 이동/모듈 추출 때마다 하위 호환 심이 늘어난다(`api/main.py:37~43` 주석이 그 증거) | 이후 모든 리팩터링 비용 감소, IDE/도구 지원 정상화 |
| P1-4 | **DB 스키마 버전 관리 도입** — 각 store에 `PRAGMA user_version` 기반 마이그레이션 러너(수십 줄이면 충분, Alembic 불요) | W-7. 데이터셋 확장(binder 전용 컬럼 등)이 성장 축인데 스키마 변경 수단이 없음 | 컬럼 추가가 "코드 + 마이그레이션 한 쌍"으로 안전해짐 |
| P1-5 | **아카이브 컷오버 자동 점검** — watcher 데몬에 "1월 1일 이후 `ARCHIVE_CUTOFF_YEAR` != 당해 연도면 경고 webhook 발행" 추가 | W-8. `scripts/archive_cutoff.py`(321줄, dry-run 지원)는 이미 있으니 실행을 잊지 않게 하는 장치만 부족 | 연초 수동 절차 누락 방지. 기존 emit_event 인프라 재사용 |

### P2 — 여유 슬롯에 하는 것 (기존 로드맵 정합)

| ID | 과제 | 근거 |
|----|------|------|
| P2-1 | C901 전면 게이트 확대 (R8) — 현재 `_chat_stream.py`, `tools/custom.py`, `routers/records.py` 3개 파일만 잠금(`ci.yml` Complexity gate) | roadmap A-5, 분기 1회 램프 슬롯 |
| P2-2 | Starlette/httpx2 마이그레이션 — upstream GA 후 lock 갱신 사이클에 편승 | roadmap A-6 |
| P2-3 | 대시보드 스모크를 CI에 — Playwright 콜드 딥링크 실측(nav-routing-fix-v1에서 1회 수행)을 최소 스크립트로 상시화. 실데이터 불필요(빈 fixture DB 재사용) | W-5, W-10 |
| P2-4 | manager.py 모듈 분해 — 프로세스 관리 코어(`_register_process` 등, 이미 순수)를 GUI에서 분리해 테스트 가능 범위 확대 | W-6 |
| P2-5 | ruff format 재평가 — 대규모 이동(P1-3)이 어차피 blame을 끊을 때 함께 | roadmap A-8의 착수 조건 충족 시점 |

---

## 4. 신규 기능 제안 (도메인 기반, 현실적 규모)

기존 로드맵 트랙 B/C와 겹치지 않거나, 이를 구체화하는 제안이다. 모두 "단일 운영 PC + 내부망 +
운영자 1인" 전제를 유지한다.

| # | 제안 | 내용 | 재사용하는 기존 인프라 |
|---|------|------|------------------------|
| F-1 | **운영 헬스 통합 페이지** (로드맵 C-1 구체화) | 대시보드 "운영" 그룹에 `views/health.py` 추가: `/metrics` 게이지(webhook 실패율·큐 깊이), watcher 상태(`database/.watcher_state.json`), 인덱스 존재 여부, 백업 최신성, anomaly 마지막 스캔 시각을 한 화면에 | `shared/metrics.py`, `api/routers/system.py`, anomaly state store — **소비 UI만 부재**한 상태 |
| F-2 | **정기 생산 리포트 자동 발행** | 주간/월간 생산 요약(총량·Top N·전기 대비·이상탐지 요약)을 Excel로 생성해 지정 폴더 저장 + webhook 알림. 스케줄은 watcher 데몬 루프에 편승 | `data.py` 집계 SQL(P1-2로 공용화 후), `to_excel_bytes`, `emit_event` |
| F-3 | **AI 도구 확장: 자재/바인더/이상탐지 질의** (로드맵 C-4 구체화) | "이번 주 자재요청 몇 건?", "최근 이상탐지 뭐 있었어?" — `materials.db`/`anomaly.db` 조회 도구 2~3개 추가. 도구 수 상한(7±2, `system_architecture.md` §6 토큰 효율 분석) 내에서 `execute_custom_query`와 균형 | `api/_tool_dispatch.py` 레지스트리, `api/tools/_common.py`, FakeClient 스모크 관례 |
| F-4 | **품목별 이상탐지 규칙 오버라이드** (로드맵 B-6) | 품목별 임계치(급감%·stale 일수)를 설정 파일(JSON)로 오버라이드. B-2(anomaly-dashboard-v2, 2026-07-08 완료)로 관측이 생겼으니 오탐 데이터 축적 후 착수 | `api/anomaly/rules.py`, `detector.py` |
| F-5 | **생산 목표 대비 실적 추적** | 월별 품목 생산 목표를 CSV/Excel 업로드 → 별도 테이블(`targets.db` 또는 materials.db 내) 저장 → overview KPI에 달성률 표시 + 미달 시 anomaly 규칙 연동 | 데이터셋 레지스트리 패턴, KPI 카드(`kpi_cards.py`), anomaly emit |

**비추천(과설계)**: 클라우드 이전, PostgreSQL 전환, 컨테이너화, RBAC(사용자 2인 이상 조건 미충족 —
로드맵 C-2 판단 기준 준수), React 프런트엔드 전환.

---

## 5. 코드 품질 개선 방향

1. **중복 제거 우선, 추상화 최소** — 이 코드베이스의 관례(레지스트리 한 줄 추가, SSOT 주석)를 따른다.
   P1-2(쿼리 서비스)도 클래스 계층이 아니라 "SQL+params를 돌려주는 순수 함수 모음"으로.
2. **테스트 가능한 코어 추출 패턴 유지** — `_parsing.py`, `kpi_cards.py` 추출 선례처럼,
   렌더/IO에서 순수 로직을 분리해 coverage omit 화이트리스트에서 하나씩 빼는 방식을 계속한다.
   신규 파일은 처음부터 측정 대상으로 작성.
3. **하위 호환 re-export 심 청산** — P1-3(패키지화)과 함께 테스트가 `api.main._normalize_date` 같은
   내부 경로 대신 정본 모듈(`api/_http_helpers.py`)을 직접 import하도록 정리.
4. **품질 램프 관례 유지** — "위반 0 파일부터 점진 잠금"(C901 R8), 분기 1회 슬롯. 새 게이트를
   한 번에 켜지 않는다.
5. **문서-코드 정합 소규모 수정**: `docs/specs/system_architecture.md` §2.2의 DB 파일명이
   `data/production.db`로 표기(실제는 `database/production_analysis.db`, `shared/config.py:28`) —
   docs-sync 사이클에서 교정.

---

## 6. 로드맵

기존 `roadmap-2026h2.plan.md`의 마일스톤(M5 품질 램프 Q4, 10월 분기 재검토)과 충돌하지 않도록 배치.

### 단기 (1개월, ~2026-08)

- [ ] P0-2 백업 무결성 검증 + 복구 훈련 1회 (소)
- [ ] P0-1 인증 클라이언트 준비 — 대시보드 HTTP 클라이언트 헤더 통일 + 봇 키 지원 확인 (전환 자체는 10월 재검토 결정 존중)
- [ ] P1-5 컷오버 자동 점검 (소, watcher 편승)
- [ ] F-1 운영 헬스 페이지 (중 — 기존 데이터 소스 조립)

### 중기 (3개월, ~2026-10)

- [ ] P1-2 공용 쿼리 서비스 계층 + `data.py` 집계 3벌 통합 (중)
- [ ] P1-1 chat/stream 공통 코어 추출 (중) — Gemini 모델 교체 이슈가 먼저 오면 순서 승격
- [ ] P1-4 스키마 버전 관리(user_version 러너) (소~중)
- [ ] F-3 AI 도구 확장 (자재/이상탐지 질의) (중)
- [ ] 10월 분기 재검토에서 P0-1 전환(auth ON) 재판단 — 리허설 완료 상태로 회부

### 장기 (6개월+, ~2027-01)

- [ ] P1-3 패키지화 + re-export 심 청산 + (조건 충족 시) ruff format (대 — blame 단절을 한 번에)
- [ ] P2-1 C901 R8 램프 (Q4 슬롯), P2-2 Starlette/httpx2 (upstream GA 시)
- [ ] P2-3 대시보드 CI 스모크, P2-4 manager 분해
- [ ] F-2 정기 리포트 / F-5 목표 대비 실적 (운영자 수요 확인 후 택1 착수)
- [ ] F-4 품목별 규칙 v2 (B-2 오탐 데이터 축적 후)
- [ ] **2027-01 아카이브 컷오버 실행**: `ARCHIVE_CUTOFF_YEAR` 2027 승격 + `scripts/archive_cutoff.py` 실행 (P1-5 경고가 트리거)

---

## 부록: 이 플랜과 기존 로드맵의 관계

| 본 문서 | roadmap-2026h2 | 관계 |
|---------|----------------|------|
| P0-1 | B-1 (보류) | 서버 전환은 보류 존중, **클라이언트 준비만 선행** 제안 |
| P1-1 | A-7 (조건부 보류) | 착수 조건("폴백 수정 시")이 C-4로 곧 충족된다고 보고 승격 |
| P2-1/P2-2/P2-5 | A-5/A-6/A-8 | 동일, 일정만 재확인 |
| F-1/F-3/F-4 | C-1/C-4/B-6 | 구체화 |
| P0-2, P1-2~P1-5, P2-3/P2-4, F-2, F-5 | (없음) | 본 분석의 신규 제안 |
