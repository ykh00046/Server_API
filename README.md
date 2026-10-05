# Production Data Hub

![CI](https://github.com/ykh00046/Server_API/actions/workflows/ci.yml/badge.svg)

생산 데이터 분석 API 서버

## 주요 기능

- **API Server**: FastAPI REST API (GZip 압축, 캐싱, Rate Limiting, Cursor Pagination)
- **DB Watcher**: DB 변경 감지 → 인덱스 자동 복구 → 24시간마다 ANALYZE
- **Manager**: 통합 서버 관리 GUI (시스템 트레이 지원)

> 화면(현황·문서 조회/Excel·수동 실행·챗봇)은 별도 프로젝트 **Dashboard-Raw_material**(8503, `/data-hub`)이 서빙한다.
> Server_API 자체 Streamlit 대시보드(8502)와 Gemini 챗 API는 2026-10 폐지됨(dashboard-8502-sunset).

---

## 설치 (Windows)

### 1. 저장소 준비
```bash
git clone <repo-url>
cd Server_API
```

> `webcloring-pdf/`(INTEROJO 포털 자동화)는 별도 submodule이다. 함께 받으려면
> `git clone --recurse-submodules <repo-url>` 또는 클론 후
> `git submodule update --init`. 분리 절차/현황은 [SEPARATION.md](SEPARATION.md) 참조.
> (메인 API는 submodule 없이도 동작한다.)

### 2. 가상환경 생성 및 활성화

정본 인터프리터는 **Python 3.12** (ruff `target-version`과 일치):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
```

### 3. 의존성 설치

재현 가능한 설치(권장 — CI와 동일한 핀 고정 버전):

```powershell
pip install -U pip
pip install -r requirements.lock.txt
```

최신 버전으로 의존성을 올릴 때(top-level 선언 기준 설치 후 lock 재생성):

```powershell
pip install -U --upgrade-strategy eager -r requirements.txt -r requirements-dev.txt -c constraints.txt
python scripts/freeze_lock.py > requirements.lock.txt
# requirements*.txt 와 lock 을 같은 커밋으로
```

- `constraints.txt`는 의도적으로 묶어 두는 핀을 담는다(2026-10 UI 폐지로 현재 활성 핀 없음). 로드맵 A-9 참조.
- `scripts/freeze_lock.py`는 `pip freeze`를 requirements 폐쇄(closure)로 걸러 준다. 같은 venv에
  `webcloring-pdf/requirements.txt`(selenium 등 포털 전용)를 설치해 둔 경우 맨 `pip freeze`는 그것까지
  lock에 섞어 넣으므로 쓰지 않는다.

### 4. 환경 변수 설정
`.env` 파일 생성(전체 항목은 `.env.example` 참조):
```env
API_PORT=8000

# 자재 백업 수동 실행(materials-run-v1) — `POST /materials/run` (Dashboard-Raw_material 수동 실행).
# 기본 false(웹에서 봇 프로세스 기동은 opt-in). true일 때만 동작.
MATERIALS_RUN_ENABLED=false
# (선택) 봇 디렉토리/파이썬 경로 — 미설정 시 repo의 webcloring-pdf + 현재 파이썬.
# MATERIALS_BOT_DIR=
# MATERIALS_BOT_PYTHON=
```

---

## 실행

### 방법 1: 매니저 (운용 PC 권장)

트레이 통합 관리 GUI. API·포털(봇)을 한 곳에서 제어. **더블클릭만으로** 기동:

| 스크립트 | 동작 |
|---|---|
| `manager.bat` | 매니저 실행(트레이). API·포털을 자식으로 관리. (콘솔 없음) |
| `stop.bat` | API(8000) 포트 점유 프로세스 종료 |
| `update.bat` | 이 레포 프로세스 정지 → `git pull` + 서브모듈 + deps. 끝나면 `manager.bat`로 실행 |
| `install.bat` | (최초 1회) 의존성 설치 |

- 접속: API 문서 http://localhost:8000/docs. 화면(자재요청/액상바인더출고 조회)은 Dashboard-Raw_material `/data-hub`.
- **포털 봇 설정·검색 프로필(시간대별 멀티 키워드)·수동 실행**은 매니저 **⚙️ Settings** / **Portal 패널**에서. (봇 단독 GUI는 제거됨 — CLI는 `main.py --schedule`/`--auto`)
- 자재·바인더 데이터는 봇이 종료 시 `POST /materials/backup`·`/binder/backup`으로 전송(문서번호 upsert). 목록·실행 이력·Excel 다운로드는 Dashboard-Raw_material `/data-hub`에서. 상세는 [운영 매뉴얼 §11](docs/specs/operations_manual.md).

### 방법 2: 개별 실행 (수동/디버그)
```bash
# API 서버
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# DB Watcher (단발 실행 / 데몬 모드 1시간 간격)
python tools/watcher.py --daemon --interval 3600
```

---

## 접속 정보

| 서비스 | URL | 설명 |
|--------|-----|------|
| API Docs | http://localhost:8000/docs | Swagger UI |
| Health Check | http://localhost:8000/healthz | 서버 상태 |

---

## API 엔드포인트

### Rate Limiting
| 엔드포인트 | 제한 | 응답 헤더 |
|-----------|------|----------|
| 기타 | 60 req/min | `X-RateLimit-Remaining` |

### REST API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/records` | 생산 레코드 조회 (Cursor Pagination 지원) |
| GET | `/records/{item_code}` | 특정 품목 레코드 조회 |
| GET | `/items` | 제품 목록 |
| GET | `/summary/monthly_total` | 월별 총생산량 집계 |
| GET | `/summary/by_item` | 제품별 집계 |
| GET | `/summary/monthly_by_item` | 제품별 월별 집계 |
| POST | `/materials/backup` | 자재요청 백업 수신 (문서번호 upsert, webcloring-pdf 봇 → 서버) |
| GET | `/materials` | 자재요청 목록 (문서번호 날짜 기준, 요청부서·날짜 필터) |
| GET | `/materials/{doc_number}` | 자재요청 단건 조회 |
| POST | `/materials/run` | 봇 자동화 수동 실행 (opt-in, `MATERIALS_RUN_ENABLED`) |
| GET | `/materials/runs` | 백업/실행 이력 |
| GET | `/healthz` | 서버 상태 확인 |
| GET | `/metrics` | Prometheus 호환 webhook 운영 메트릭 (인증 활성화 시 보호) |

### 주요 쿼리 파라미터 (`/records`)

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `date_from` | YYYY-MM-DD | 시작일 (포함) |
| `date_to` | YYYY-MM-DD | 종료일 (포함) |
| `item_code` | string | 제품 코드 |
| `q` | string | 제품 코드/이름/로트 검색 (부분 일치) |
| `lot_number` | string | 로트 번호 (prefix 매칭) |
| `min_quantity` | int | 최소 생산량 |
| `max_quantity` | int | 최대 생산량 |
| `limit` | int | 반환 건수 (기본 1000, 최대 5000) |
| `cursor` | string | Cursor Pagination 토큰 |
| `offset` | int | 오프셋 기반 페이지네이션 (하위 호환용, 비권장) |

`GET /records` 응답에는 `next_cursor`, `has_more`, `count`가 포함된다. 대량 조회는 `offset`보다 `cursor` 기반 페이지네이션을 권장한다.

---

## 데이터베이스 구조

```
database/
├── production_analysis.db   # Live DB (당해 연도)
├── archive_2025.db          # Archive DB (전년도 이하)
└── backups/                 # 자동 백업 (Live 최근 30개, Archive 최근 12개)
```

### Archive / Live 자동 라우팅
- 쿼리 기간에 따라 `DBRouter`가 Archive / Live / 양쪽 자동 선택
- ERP가 DB 파일을 갱신해도 mtime 기반 캐시 자동 무효화

### 인덱스 (정본: `shared/db_maintenance.REQUIRED_INDEXES`, 6종)
| 인덱스 | 컬럼 | 용도 |
|--------|------|------|
| `idx_production_date` | `production_date` | 날짜 범위 조회 |
| `idx_item_code` | `item_code` | 제품별 조회 |
| `idx_production_date_item` | `production_date, item_code` | 날짜+제품 복합 |
| `idx_lot_number` | `lot_number` | 로트번호 검색 |
| `idx_agg_covering` | `item_code, production_date, good_quantity` | 집계 커버링 |
| `idx_date_qty` | `production_date, good_quantity` | 날짜순 수량 조회 |

> 인덱스 생성: `python tools/create_indexes.py` (DB watcher가 변경 감지 시 자동 복구).

---

## 프로젝트 구조

```
Server_API/
├── api/
│   ├── main.py              # FastAPI 앱 조립 (미들웨어: auth+audit, request_id+rate_limit, CORS, GZip)
│   ├── _audit.py            # 접근 감사 로그
│   ├── routers/             # records / summary / system / notifications / materials / anomaly
│   ├── tools/               # 조회 도구 함수 (items / summary / custom)
│   ├── notifications/       # Webhook 비동기 디스패치 (큐+backoff worker)
│   └── materials/           # 자재요청 수신 (store/runs/automation, materials.db, 문서번호 upsert)
├── shared/
│   ├── config.py            # 설정 상수 (.env override)
│   ├── auth.py              # opt-in 인증 (API-Key/Bearer, 상수시간 비교, PUBLIC_PATHS SSOT)
│   ├── database.py          # DBRouter, DBTargets, Thread-local 연결
│   ├── cache.py             # TTLCache + db_mtime 무효화
│   ├── rate_limiter.py      # 슬라이딩 윈도우 Rate Limiter (clock 주입 가능)
│   ├── db_maintenance.py    # REQUIRED_INDEXES(6종) 복구, ANALYZE, 안정화 대기
│   ├── process_utils.py     # kill_process_tree (manager 프로세스 관리)
│   ├── validators.py        # 입력 검증
│   └── logging_config.py    # Slow Query 로깅, request_id
├── tools/
│   ├── watcher.py           # DB 변경 감시 + 인덱스 복구 + ANALYZE (standalone)
│   ├── db_watcher.py        # manager 내장 워처 스레드
│   ├── create_indexes.py    # 인덱스 생성 (REQUIRED_INDEXES SSOT 참조)
│   └── backup_db.py         # DB 안전 백업 (mtime 안정화 후 실행)
├── tests/                   # 30개 파일, 517 테스트
├── webcloring-pdf/          # ⮑ git submodule (INTEROJO 포털 자동화, 별도 repo)
├── database/                # DB 파일 및 백업 (gitignore)
├── docs/                    # PDCA 문서 (01-plan ~ 04-report, archive)
├── manager.py               # 통합 관리 GUI (CustomTkinter + 트레이)
├── pyproject.toml           # ruff/pytest/coverage 설정 (SSOT)
├── requirements.txt         # top-level 의존성 선언
└── requirements.lock.txt    # 핀 고정 lock (CI·재현 설치용)
```

---

## 테스트

```bash
pytest tests/ -v        # 30개 파일, 517 테스트
```

### CI (GitHub Actions)

`main` push / PR 시 `.github/workflows/ci.yml`이 자동 실행된다:

| Job | 내용 |
|-----|------|
| `lint` | `ruff check .` — 게이트 규칙(F/BLE001/I/UP/B/SIM/E501)은 `pyproject.toml`이 SSOT |
| `test` | `pytest --cov --cov-fail-under=88` — coverage floor는 CI 전용(로컬 pytest는 floor 없음) |

- 측정 범위: `api` + `shared`. 구현 후 실측치는 CI 로그 참조.
- 의존성은 `requirements.lock.txt`로 설치된다(재현성). 의존성 변경 시 §3의 lock 재생성 절차를 따른다.
- 게이트 램프 이력(R3→R7)은 `docs/archive/2026-06/` 참조.

### 스모크 검증 (선택, Linux/WSL 전용)

Linux/WSL 기준 재현 가능한 최소 검증 경로:

```bash
tools/smoke_api.sh
```

의존성이 없는 환경이면 스모크 전용 가상환경을 만들고 최소 패키지를 설치한 뒤 실행:

```bash
SMOKE_INSTALL=1 tools/smoke_api.sh
```

선택적으로 로컬 헬스 엔드포인트까지 확인:

```bash
SMOKE_INSTALL=1 SMOKE_RUN_HEALTH=1 tools/smoke_api.sh
```

`requirements.txt` 전체 설치는 GUI(매니저) 의존성까지 포함하므로, API 최소 검증만 필요할 때는 `requirements-smoke.txt` 경로를 우선 사용한다.

> 테스트는 30개 파일/517 케이스로 SQL 안전성·Rate Limiter·입력 검증·캐시·DB 라우팅·인증/감사·webhook·조회 도구(DB 백엔드)·집계 라우터·DB 유지보수(인덱스/ANALYZE/VACUUM)·자재 백업(upsert·문서번호 날짜·실행 트리거) 등을 커버한다. (전체 목록은 `tests/` 참조)

---

## DB 백업

```bash
# 수동 백업 (Live + Archive)
python tools/backup_db.py

# Live만 백업
python tools/backup_db.py --live

# 오래된 백업 정리만
python tools/backup_db.py --cleanup
```

---

## 버전 이력

| 버전 | 날짜 | 변경사항 |
|------|------|----------|
| v11 | 2026-10 | 자체 Streamlit 대시보드(8502)·Gemini 챗 API(`/chat*`, `/healthz/ai`) 폐지 — 화면은 Dashboard-Raw_material(8503)로 일원화, 관리 조작은 API curl 레시피([API 통합 가이드](docs/api_integration_guide.md)) |
| v10 | 2026-06 | 자재 백업 Google Sheets → Server_API 전환(`/materials`, 문서번호 upsert), 대시보드 "자재요청" 페이지(엑셀 레이아웃 리스트 + CSV/Excel 다운로드 + 실행 상태/이력 + "지금 실행" 트리거, opt-in), 커버리지 측정 확장(floor 88) |
| v9 | 2026-06 | CI 파이프라인(GitHub Actions) + py3.12 정본 venv + lock 고정, 대시보드 블루/슬레이트 네이티브 테마, 콜드 딥링크 라우팅 픽스, flaky 제거(RateLimiter clock 주입), 커버리지 측정 확장(floor 72), ruff 게이트 B/SIM/E501 램프, webcloring-pdf submodule 분리 |
| v8 | 2026-02-26 | AI 도구 2개 추가 (compare_periods, get_item_history), DB ANALYZE 자동화 |
| v7 | 2026-01-23 | 성능 개선 (GZip, ORJSONResponse, TTLCache, Cursor Pagination, Thread-local 연결) |
| v6 | 2026-01-23 | 개선 로드맵 (Rate Limit, 멀티턴, 재시도, DBRouter 통합, 백업 자동화) |
| v5 | 2026-01 | 코드 리팩토링 (shared 모듈화) |
| v4 | 2026-01 | AI Chat (Gemini Tool Calling) |
| v3 | 2026-01 | 자동화 (Watcher, Backup) |
| v2 | 2026-01 | DB 최적화 (Archive/Live 분리) |
| v1 | 2026-01 | 초기 릴리즈 |

---

## 문서

- [Server API 인수 계획 (archive)](docs/archive/2026-04/server-api-intake/server-api-intake.plan.md)
- [문서 정합성 및 스모크 (archive)](docs/archive/2026-04/server-api-consistency-and-smoke/)
- [WSL 스모크 검증 리포트](docs/04-report/server-api-smoke-2026-03-31.report.md)
- [2026-04 PDCA 아카이브 인덱스](docs/archive/2026-04/_INDEX.md)
- [v8 통합 로드맵(레거시 아카이브)](docs/archive/legacy/plans/v8_consolidated_roadmap.md)
- [API 통합 가이드](docs/api_integration_guide.md)
- [운영 매뉴얼](docs/specs/operations_manual.md)
- [변경 로그](docs/04-report/changelog.md)
- [webcloring-pdf 분리 절차서](SEPARATION.md) — submodule 운영/롤백
- [2026-06 PDCA 아카이브 인덱스](docs/archive/2026-06/_INDEX.md) — 이번 사이클(11건) 기록
