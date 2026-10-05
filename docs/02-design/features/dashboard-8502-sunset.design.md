# dashboard-8502-sunset — Server_API 자체 Streamlit 대시보드 + Gemini 챗 API 폐지

- 상태: 구현 중 (2026-10-05)
- 브랜치: `feat/dashboard-8502-sunset`
- 출처: roadmap-2026h2 B-7 (v0.7에서 신설, 1순위 개발 후보) · Dashboard-Raw_material
  `docs/03-analysis/system-boundary-review.md` (2026-08-21) P1 "최대 효과" 백로그
- 운영자 결정(2026-10-05): ① 8502는 아무도 열어 보지 않는다 ② **UI 폐지 + Gemini 챗 API까지 제거**.
  webhook 관리·anomaly what-if·tombstone 복원은 API만 남긴다(curl 레시피 문서화).

## 배경 / 문제

시스템 경계 리뷰가 헌장을 "Server_API = 데이터 플랫폼(수집·보존·제공 + 데이터 이벤트 알림), 화면은
Dashboard-Raw_material 소유"로 고정했다. 2026-08-21 Dashboard `/data-hub`가 8502의 운영 콘솔 역할
(healthz·크롤러 stale·웹훅 큐·이상탐지 카드·문서 조회/Excel·자재/바인더 수동 실행)을 흡수했고,
생산실적 분석은 Dashboard `/production`이 서빙한다. 그 결과 8502(Streamlit, `dashboard/` 4.4k LOC +
`shared/ui/`)는 **동일 화면의 두 번째 사본**이며, Gemini 챗 API(`api/chat.py` 계열 1,152 LOC)는
**8502 UI가 유일한 소비처**다(Dashboard 챗은 자체 구현, Server_API `/chat`를 호출하지 않음 — grep 0).

유지 비용: streamlit 핀 1.58 동결(A-9), 대시보드 전용 테스트 ~100개, 사용자 창구 2개·LLM 창구 2개,
매니저의 Dashboard 패널·stop.bat 8502.

## 설계 — 제거 범위 (인벤토리는 2026-10-05 grep 실측)

### 1. UI 레이어 (Streamlit)

| 대상 | 처리 |
|---|---|
| `dashboard/**` (app.py, data.py, dataset_page.py, views/8, components/*) | 디렉터리 삭제 |
| `shared/ui/**` (theme.py, responsive.py — 소비처 dashboard뿐) | 디렉터리 삭제 |
| `shared/api_client.py` (auth_headers — 소비처 dashboard뿐) | 삭제. B-1 착수 시 클라이언트는 Dashboard `DataHubClient` |
| `.streamlit/config.toml` | 삭제 (git tracked) |
| `manager.py` | Dashboard 패널 제거: `_init_web_panel`, `start_web`/`stop_web`, `web_panel` 참조(`start_all`/`stop_all`/`on_close`/상태 뱃지 `web:{port}`/`_is_panel_running`), grid 열 재배치(`grid_columnconfigure(0, weight=2)  # Dashboard`), `DASHBOARD_PORT` import, `webbrowser` import가 그 용도뿐이면 함께 |
| `shared/config.py` / `shared/__init__.py` | `DASHBOARD_PORT`, `API_BASE_URL`(소비처 dashboard뿐) 제거 + `__all__` 정리 |
| `.env.example` | `DASHBOARD_PORT=8502`, `DASHBOARD_API_KEY=` + 설명 주석(40~45행) 제거 |
| `stop.bat` | 8502 제거(포트 루프 8000만), 메시지 갱신. `update.bat`/`manager.bat` 주석의 "Dashboard" 제거 |
| `pyproject.toml` | per-file-ignores의 `dashboard/...` 3줄 삭제, `[tool.coverage.run] source`에서 `"dashboard"` 제거, omit 목록의 `dashboard/*` 전부 삭제, 주석(79~104행) 정리 |
| `requirements.txt` | `streamlit`, `plotly`, `altair`, `streamlit-shadcn-ui`, `requests`, `openpyxl`, `pandas` 제거(비제거 코드 소비처 0 — 2026-10-05 실측). `httpx`·`cachetools`·`orjson`·`packaging`·`python-dotenv`·`Pillow`·`pystray`·`customtkinter`·`psutil`·`fastapi`·`uvicorn` 유지 |
| `constraints.txt` | streamlit 핀 제거(동결 사유 소멸) — 파일은 비워 두지 말고 주석만 남김 |
| 테스트 삭제 | `test_ai_table_parse`, `test_sse_parse`, `test_anomaly_view_helpers`, `test_dataset_page_display`, `test_kpi_cards`, `test_ui_theme`, `test_webhook_admin_ui`, `test_weekly_bucket`, `test_api_client_headers` |
| 테스트 수정 | `test_auth.py`: `from shared.api_client import auth_headers` 제거 + T13 `test_auth_headers_grants_access_to_protected_route` 삭제(주석 블록 162~190행 포함). 주석의 "dashboard helper ↔ server contract" 문구는 삭제 |

`dashboard/data.py`의 `WEEK_BUCKET_EXPR`/`_parse_production_dt`는 api 쪽에 사본이 없고 소비처도 dashboard뿐
→ 함께 삭제(test_weekly_bucket 삭제와 짝).

### 2. Gemini 챗 API 레이어

| 대상 | 처리 |
|---|---|
| `api/chat.py`, `api/_chat_stream.py`, `api/_gemini_client.py`, `api/_session_store.py` | 삭제 |
| `api/main.py` | `from . import chat` + `app.include_router(chat.router)` 제거(주석 "chat first to preserve include order" 포함). 미들웨어의 `/chat` 바이패스 블록(181~186행) 제거. 주기 정리에서 `chat_rate_limiter.cleanup()` 항과 한글 주석 제거. `from shared import (... chat_rate_limiter ...)` 정리 |
| `api/routers/system.py` | `_ai_health_cache`/`_ai_health_cache_lock`/`AI_HEALTH_CACHE_TTL` 삭제, `/healthz` 응답의 `"ai_api"` 블록 삭제, `GET /healthz/ai` 전체 삭제, `from .. import _session_store as _sstore` 삭제, 불필요해진 import(threading/time/os 중 다른 용도 없는 것) 정리 |
| `shared/rate_limiter.py` | `chat_rate_limiter` 인스턴스 삭제; `shared/__init__.py` export 삭제; `shared/config.py`의 `RATE_LIMIT_CHAT`, `CHAT_SESSION_*` 3개, `GEMINI_MODEL`/`GEMINI_FALLBACK_MODEL`/`GEMINI_FALLBACK_ENABLED` 삭제 + `__all__` 정리 |
| `shared/auth.py` | `PUBLIC_PATHS`에서 `"/healthz/ai"` 제거 |
| `.env.example` | `GEMINI_API_KEY`, `CHAT_SESSION_*` 3줄 + 관련 주석 제거 |
| `requirements.txt` | `google-genai` 제거 |
| 테스트 삭제 | `test_chat_fallback`, `test_chat_stream`, `test_session_store` |
| 테스트 수정 | `conftest.py` `_reset_rate_limiters`: `from api.chat import chat_rate_limiter` + 해당 clear 제거(api_rate_limiter만). `test_api_integration.py`: `from api import chat as chat_mod` 제거, `/chat/` 테스트(≈85~155행: 기본 응답·세션 이력·클라이언트 None·레이트리밋)와 `/healthz/ai` 호출(31행 부근) 삭제, 모듈 docstring의 "/chat/ endpoint" 문구 수정. `test_input_validation.py`: `ChatRequest` 3케이스 삭제. `test_misc_coverage.py`: `_gemini_client` import + 143행 이후 해당 클래스/함수 전부 삭제, docstring 정리. `test_sql_validation.py`: `_build_system_instruction` 테스트 1건 삭제. `test_notifications.py` 440·448행 경로 목록에서 `/healthz/ai`, `/chat/` 제거. `test_auth.py` 28·33행 목록에서 `/healthz/ai`, `/chat` 제거. `test_routers_db.py`: `test_healthz_ai_*` 3건 삭제(282~350행) |

`api/_http_helpers.py`(_normalize_date 등)는 챗 전용이 아님 — 유지.

**구현 중 확장(2026-10-05, 실측으로 드러난 챗 전용 잔재 — 같은 레이어로 처리):**

| 대상 | 근거 | 처리 |
|---|---|---|
| `api/_tool_dispatch.py`, `tests/test_tool_schemas.py`, `tools/check_models.py` | Gemini 툴 레지스트리·스키마 테스트(`google.genai` import)·모델 목록 CLI. 소비처 챗뿐 | 삭제 |
| `api/tools/` 패키지(_common/custom/items/summary, 864 LOC) + `tests/test_ai_tools_db.py`(26)·`tests/test_sql_validation.py`(전부 api.tools 대상) + `test_db_connection_lifecycle.py`의 `compare_periods` 케이스 + `conftest.py` 75행 모듈 목록 | Gemini function-calling 전용 툴. 프로덕션 소비처 0 | 삭제 |
| `shared/config.py` `STREAM_HEARTBEAT_SEC`/`STREAM_TIMEOUT_SEC`/`STREAM_BUFFER_FLUSH_MS` | 챗 SSE 전용, 소비처 0 | 삭제 |
| `shared/config.py` `_DEFAULT_CORS_ORIGINS`의 8502 origin 2개, `manager_theme.py` docstring, `설치방법.txt`, `requirements-smoke.txt`·`tools/smoke_api.sh`의 google-genai | grep 게이트 | 정리 |
| `.env.example` `MATERIALS_API_KEY=` | **유지(복원)** — 봇 `api_backup_config.py`가 `os.getenv('MATERIALS_API_KEY')`로 읽고, 매니저가 `shared.config`의 `load_dotenv(루트 .env)`로 환경을 채운 뒤 봇을 서브프로세스로 띄우므로 상속됨. 옛 주석("대시보드→API 호출")이 틀렸던 것 → 봇 백업 키로 주석 정정 |
| lock에서 `httptools`/`websockets`/`watchfiles`/`tzdata` 탈락 | `uvicorn`(extras 없음)·pandas 폐쇄 밖. 운용은 `--reload`·websocket 미사용 | 수용 |

### 3. 문서

| 문서 | 처리 |
|---|---|
| `docs/specs/ai_architecture.md` | `docs/archive/2026-10/dashboard-8502-sunset/`로 이동(삭제 아님 — 설계 이력) |
| `README.md` | 8502/Streamlit/Gemini/챗 섹션·포트 표·구조 트리(`dashboard/`, `shared/ui`)·환경변수 표 정리. 매니저 패널 설명에서 Dashboard 제거 |
| `docs/api_integration_guide.md`, `docs/specs/api_guide.md` | `/chat*`, `/healthz/ai` 항목 삭제, `/healthz` 응답 예시에서 `ai_api` 제거. **"관리 조작 curl 레시피"** 절 신설: webhook 등록/수정/회전/일괄재시도, anomaly what-if(`POST /anomaly/scan?emit=false` 또는 현행 시그니처 확인), 문서 삭제/`/tombstones`/`/{doc}/restore` |
| `docs/specs/operations_manual.md`, `docs/specs/system_architecture.md` | 8502 기동/중지 절차·구성도에서 Streamlit 제거, "화면은 Dashboard-Raw_material(8503)" 1줄 추가 |
| `docs/dataset-add-checklist.md` | 3점 체크리스트(datasets.py + 봇 config + 대시보드 views) → 2점 + "화면은 Dashboard-Raw_material `/data-hub`" |
| `docs/changelog_2026-01-23.md` | 손대지 않음(이력) |
| `docs/01-plan/features/roadmap-2026h2.plan.md` | 완료 시 B-7 ✅, M7 ✅, v0.9 (별도 커밋) |

### 4. 커버리지·CI

- `source = ["api", "shared"]`로 축소. 기준선 89%(2026-10-05, floor 88). 챗 레이어는 테스트 밀도가 높아
  제거 후 수치가 움직일 수 있음 → 구현 후 재측정, **floor는 실측치 −1pp 이하로만 조정**(올리지 않음).
  `.github/workflows/ci.yml` 66행 주석("+dashboard _parsing.py")도 갱신.
- lock 재생성: `pip uninstall`로 venv를 맞추지 말고 **fresh venv에 새 requirements를 설치해 `scripts/freeze_lock.py`**
  (폐쇄 필터가 streamlit 계열·google-genai·pandas 등을 자동 배제). 기존 venv는 그대로 둬도 무방.

## 운영 시맨틱

- 운용 PC: `update.bat` + 매니저 통째 재시작. 매니저 창에서 Dashboard 패널이 사라지고 API/Portal만 남는다.
  운용 `.env`의 `GEMINI_API_KEY`·`DASHBOARD_*`는 무해한 잔존 → 다음 방문 때 수동 삭제(절차 문서화).
- 외부 계약 변화: `GET /healthz` 응답에서 `ai_api` 키 소멸, `GET /healthz/ai`·`/chat*` 404.
  Dashboard-Raw_material는 `ai_api`를 읽지 않음(2026-10-05 grep 0) — 영향 없음.
- 제거되는 기능의 대체 경로: webhook CRUD → API 직접(curl 레시피), anomaly what-if → `/anomaly/scan`
  GET(emit 없음)·Dashboard 허브 카드, 문서 삭제/복원 → `DELETE`·`/restore` API, Gemini 챗 → Dashboard 챗봇.

## 검증 (DONE WHEN)

1. `grep -rnE "streamlit|from dashboard|import dashboard|shared\.ui|shared\.api_client|genai|_gemini_client|_chat_stream|_session_store|chat_rate_limiter|RATE_LIMIT_CHAT|DASHBOARD_PORT|API_BASE_URL|healthz/ai|8502" --include=*.py --include=*.toml --include=*.bat --include=*.txt --include=.env.example . | grep -v "\.venv\|webcloring-pdf\|docs/\|\.git/"` → **0건**.
2. `.venv\Scripts\python -m ruff check .` 그린, `pytest` 전부 그린(수집 에러 0, skip 0). 예상 테스트 수 ≈ 768 − (삭제 ~150).
3. `pytest --cov` TOTAL 실측 기록, floor 조정 규칙 준수.
4. 매니저 위젯 스모크(`ServerManager()` 생성 → update → 패널 메서드 → destroy, `_setup_tray` 무력화)에서 오류 0, `web_panel` 속성 부재.
5. uvicorn 실기동 `/healthz` 200 + 응답에 `ai_api` 없음, `/healthz/ai`·`/chat/stream` 404, `/openapi.json` 경로 목록에 `/chat`·`/healthz/ai` 없음.
6. fresh venv에 새 lock 설치 → 전체 테스트 그린, lock에 streamlit/plotly/altair/pandas/google-genai 부재.
7. 커밋은 레이어별 분리: ① design 문서 ② UI 레이어(refactor(dashboard)) ③ 챗 API 레이어(refactor(api)) ④ deps/pyproject/lock(chore) ⑤ 문서(docs) ⑥ 로드맵.
