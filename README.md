# Production Data Hub

생산 데이터 분석 및 AI 챗봇 시스템

## 주요 기능

- **Dashboard**: Streamlit 기반 데이터 시각화 (다크/라이트 모드, KPI 카드, 일/주/월별 집계)
- **API Server**: FastAPI REST API (GZip 압축, 캐싱, Rate Limiting, Cursor Pagination)
- **AI Chat**: Google Gemini 기반 자연어 쿼리 (멀티턴 대화, 7개 도구)
- **DB Watcher**: DB 변경 감지 → 인덱스 자동 복구 → 24시간마다 ANALYZE
- **Manager**: 통합 서버 관리 GUI (시스템 트레이 지원)

---

## 설치 (Windows)

### 1. 저장소 준비
```bash
git clone <repo-url>
cd Server_API
```

### 2. 가상환경 생성 및 활성화
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 3. 의존성 설치
```bash
pip install -U pip
pip install -r requirements.txt
```

### 4. 환경 변수 설정
`.env` 파일 생성:
```env
GEMINI_API_KEY=your_gemini_api_key_here
DASHBOARD_PORT=8502
API_PORT=8000
```

---

## 실행

### 방법 1: Manager GUI (권장)
```bash
python manager.py
```

### 방법 2: 개별 실행
```bash
# API 서버
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# Dashboard
python -m streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8502

# DB Watcher (단발 실행)
python tools/watcher.py

# DB Watcher (데몬 모드, 1시간 간격)
python tools/watcher.py --daemon --interval 3600
```

---

## 접속 정보

| 서비스 | URL | 설명 |
|--------|-----|------|
| Dashboard | http://localhost:8502 | 데이터 시각화 |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Health Check | http://localhost:8000/healthz | 서버 상태 |
| AI Health | http://localhost:8000/healthz/ai | AI API 상태 |

---

## API 엔드포인트

### Rate Limiting
| 엔드포인트 | 제한 | 응답 헤더 |
|-----------|------|----------|
| `POST /chat/` | 20 req/min | `Retry-After` |
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
| POST | `/chat/` | AI 자연어 쿼리 |
| GET | `/healthz` | 서버 상태 확인 |
| GET | `/healthz/ai` | AI API 상태 확인 |

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

### AI Chat

```bash
# 단발 질문
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"query": "이번 달 BW0021 총 생산량은?"}'

# 멀티턴 대화 (session_id로 맥락 유지)
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{"query": "그럼 저번 달이랑 비교하면?", "session_id": "my-session-01"}'
```

### AI 도구 (7개)

| 도구 | 트리거 예시 |
|------|-----------|
| `search_production_items` | "P물 제품 코드가 뭐야?" |
| `get_production_summary` | "BW0021 이번 달 생산량" |
| `get_monthly_trend` | "최근 6개월 월별 추이" |
| `get_top_items` | "올해 상위 5개 제품" |
| `compare_periods` | "이번 달 vs 저번 달 비교" |
| `get_item_history` | "BW0021 최근 10건 이력" |
| `execute_custom_query` | "로트번호 LT2026으로 시작하는 항목" |

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

### 인덱스
| 인덱스 | 컬럼 | 용도 |
|--------|------|------|
| `idx_production_date` | `production_date` | 날짜 범위 조회 |
| `idx_item_code` | `item_code` | 제품별 조회 |
| `idx_item_date` | `item_code, production_date` | 제품 + 날짜 복합 조회 |

---

## 프로젝트 구조

```
Server_API/
├── api/
│   ├── main.py              # FastAPI REST 엔드포인트
│   ├── chat.py              # AI Chat (멀티턴, 재시도, Rate Limit)
│   └── tools.py             # AI 도구 함수 7개
├── dashboard/
│   ├── app.py               # Streamlit 메인 대시보드
│   └── components/
│       ├── theme.py         # 다크/라이트 모드
│       ├── kpi_cards.py     # KPI 카드
│       ├── charts.py        # 차트
│       ├── presets.py       # 필터 프리셋
│       ├── ai_section.py    # AI Chat UI
│       └── ...
├── shared/
│   ├── config.py            # 설정 상수
│   ├── database.py          # DBRouter, DBTargets, Thread-local 연결
│   ├── cache.py             # TTLCache + db_mtime 무효화
│   ├── rate_limiter.py      # 슬라이딩 윈도우 Rate Limiter
│   ├── db_maintenance.py    # 인덱스 복구, ANALYZE, 안정화 대기
│   ├── validators.py        # 입력 검증
│   └── logging_config.py   # Slow Query 로깅
├── tools/
│   ├── watcher.py           # DB 변경 감시 + 인덱스 복구 + ANALYZE
│   └── backup_db.py         # DB 안전 백업 (mtime 안정화 후 실행)
├── tests/
│   ├── test_sql_validation.py   # SQL 인젝션 방지 (16개)
│   ├── test_rate_limiter.py     # Rate Limiter (16개)
│   ├── test_input_validation.py # 입력 검증 (19개)
│   ├── test_cache.py            # API 캐시 (16개)
│   └── test_db_router.py        # DB 라우팅 (36개)
├── database/                # DB 파일 및 백업
├── docs/                    # 문서
├── logs/                    # 로그 파일
├── manager.py               # 통합 관리 GUI
└── requirements.txt
```

---

## 테스트

```bash
pytest tests/ -v
```

### 스모크 검증

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

`requirements.txt` 전체 설치는 Streamlit/GUI 의존성까지 포함하므로, API 최소 검증만 필요할 때는 `requirements-smoke.txt` 경로를 우선 사용한다.

| 테스트 파일 | 케이스 수 | 설명 |
|-------------|:---------:|------|
| `test_sql_validation.py` | 16 | SQL 인젝션 방지 |
| `test_rate_limiter.py` | 16 | Rate Limiter |
| `test_input_validation.py` | 19 | 입력 검증 |
| `test_cache.py` | 16 | API 캐시 |
| `test_db_router.py` | 36 | DB 라우팅 |

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
- [v8 통합 로드맵(기존)](docs/plans/v8_consolidated_roadmap.md)
- [API 통합 가이드](docs/api_integration_guide.md)
- [운영 매뉴얼](docs/specs/operations_manual.md)
- [변경 로그](docs/04-report/changelog.md)
