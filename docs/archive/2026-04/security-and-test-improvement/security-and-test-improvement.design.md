---
template: design
version: 1.2
feature: security-and-test-improvement
date: 2026-04-14
author: interojo
project: Production Data Hub (Server_API)
version_project: v8
---

# 보안·테스트 개선 Design Document

> **Summary**: Top 5 이슈(.env 분리, API 통합 테스트, Chat 세션 IP 제한, Custom Query 안전장치, 대형 함수 리팩토링)에 대한 구현 설계.
>
> **Project**: Production Data Hub
> **Version**: v8
> **Author**: interojo
> **Date**: 2026-04-14
> **Status**: Draft
> **Planning Doc**: [security-and-test-improvement.plan.md](../../01-plan/features/security-and-test-improvement.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 (Schema) | N/A (변경 없음) | N/A |
| Phase 2 (Convention) | N/A | N/A |
| Phase 4 (API Spec) | `README.md` 내 엔드포인트 표 참조 | ✅ |

---

## 1. Overview

### 1.1 Design Goals

1. **비밀정보 저장소 노출 0** — 키 유출 시 즉시 회전 가능한 구조.
2. **API 회귀 안전망** — FastAPI `TestClient` 기반 in-process 통합 테스트.
3. **Chat 세션 DoS 차단** — IP당 동시 세션 상한 + TTL sliding expiry.
4. **Custom Query 주입 면적 제로** — ATTACH 경로를 화이트리스트로 강제, 문자열 이스케이프 의존 제거.
5. **복잡도 감소** — `chat_with_data()`, `execute_custom_query()` 를 단일 책임 helper로 분리.

### 1.2 Design Principles

- **최소 침습**: 기존 공개 API (엔드포인트/응답 스키마) 변경 금지.
- **테스트 퍼스트**: S2·S3·S4는 실패 테스트를 먼저 작성한 뒤 수정.
- **명시적 설정**: 새 동작은 환경변수로 조정 가능, 기본값은 현행과 호환.
- **Fail fast on boot**: 필수 설정이 누락되면 AI만 비활성 + 경고 로그 1회.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────┐  HTTP  ┌──────────────────────────┐
│   Client     │───────▶│  FastAPI (api/main.py)   │
│ (Dash/curl)  │        │  ─ rate_limiter          │
└──────────────┘        │  ─ cache (mtime)         │
                        │  ─ /records /summary     │
                        │  ─ /chat ────────┐       │
                        └──────────┬───────┼───────┘
                                   │       │
                    ┌──────────────▼──┐  ┌─▼──────────────────┐
                    │ shared/database │  │ api/chat.py        │
                    │ DBRouter        │  │  ─ SessionStore    │
                    │ (Live/Archive)  │  │  ─ GeminiClient    │
                    └─────────┬───────┘  │  ─ ToolDispatcher  │
                              │          └─┬──────────────────┘
                    ┌─────────▼────────┐   │
                    │ sqlite Live/Arch │◀──┘ (via api/tools.py)
                    └──────────────────┘
```

### 2.2 Data Flow (Chat)

```
POST /chat/
  → rate_limiter (20/min/ip)
  → SessionStore.get(session_id, ip)          # S3: IP 바인딩
  → GeminiClient.generate_with_tools(...)     # S5: helper 분리
      ↳ ToolDispatcher.run(tool_name, args)   # tools.py
          ↳ execute_custom_query
               → validate_db_path (pathlib)   # S4
               → ATTACH via whitelist lookup   # S4
               → run_with_timeout(CUSTOM_QUERY_TIMEOUT_SEC)  # S4
  → SessionStore.save(...)
  → ChatResponse
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `SessionStore` | `cachetools.TTLCache` | 세션 TTL/용량 관리 |
| `GeminiClient` (new shim) | `google.generativeai` | 단일 모델 호출 경계, 테스트 monkeypatch 지점 |
| `ToolDispatcher` (new) | `api/tools.py` | Gemini tool_calls → Python fn 매핑 |
| `validate_db_path` | `pathlib`, 설정 `ARCHIVE_DB_WHITELIST` | 경로 주입 차단 |
| 통합 테스트 | `fastapi.testclient.TestClient` | in-process API 호출 |

---

## 3. Data Model

신규 DB 스키마 없음. 인메모리 모델만 정의한다.

### 3.1 Session Entity (in-memory)

```python
# api/chat.py (리팩토링 후)
@dataclass
class ChatSession:
    session_id: str
    owner_ip: str              # S3: IP 바인딩
    history: list              # Gemini Content 리스트
    created_at: float
    last_access: float         # sliding expiry 기준
```

### 3.2 SessionStore 인터페이스

```python
class SessionStore:
    def __init__(self, ttl_sec: int, max_per_ip: int, max_total: int): ...
    def get(self, session_id: str | None, ip: str) -> list: ...
    def save(self, session_id: str, ip: str, history: list) -> None: ...
    def purge_expired(self) -> int: ...
    def stats(self) -> dict: ...      # 테스트·헬스체크용
```

- 내부 저장: `cachetools.TTLCache(maxsize=max_total, ttl=ttl_sec)` + `defaultdict[ip, set[session_id]]`.
- `save()` 시 동일 IP의 세션 수가 `max_per_ip` 초과면 **가장 오래된 세션 evict**.
- `get()`: 다른 IP가 같은 `session_id`를 요청하면 **새 세션처럼 취급**(history 빈 리스트 반환) + warning 로그.

### 3.3 Archive Whitelist

```python
# shared/config.py (신규 상수)
ARCHIVE_DB_WHITELIST: tuple[Path, ...] = (
    DB_DIR / "archive_2025.db",
    # 연도별 추가
)
```

환경변수 `ARCHIVE_DB_WHITELIST`(세미콜론 구분)로 override 가능. 파일이 실제 존재하지 않으면 boot 시 warning.

---

## 4. API Specification

### 4.1 Endpoint 변경

공개 엔드포인트 **추가/제거 없음**. 응답 필드 변경도 없음.

| Method | Path | 변경 사항 |
|--------|------|---------|
| POST | `/chat/` | 내부 구현만 변경 (SessionStore/Dispatcher) |
| GET | `/healthz/ai` | `session_count`, `session_ttl_sec` 필드 추가 (선택) |

### 4.2 `/healthz/ai` (확장안)

```json
{
  "status": "ok",
  "gemini_api_key_configured": true,
  "model": "gemini-2.0-flash-exp",
  "sessions": {
    "count": 7,
    "ttl_sec": 1800,
    "max_per_ip": 20
  }
}
```

### 4.3 설정 로딩 규약 (FR-01)

- `shared/config.py`에서 `GEMINI_API_KEY`가 없거나 빈 문자열이면:
  - 시작 시 `logger.warning("GEMINI_API_KEY missing — AI chat disabled")` **1회** 출력
  - `/chat/` 엔드포인트는 `503 AI_DISABLED` 반환 (기존과 동일)
- `.env.example` 신설, `.env`는 `.gitignore` 확인(없으면 추가).

---

## 5. UI/UX Design

해당 없음 (내부 개선).

---

## 6. Error Handling

### 6.1 신규/변경 에러 매핑

| Code | 상황 | 처리 |
|------|------|------|
| 503 `AI_DISABLED` | `GEMINI_API_KEY` 미설정 | 기존 동작 유지 |
| 429 `RATE_LIMITED` | 기존 rate limiter | 변경 없음 |
| 429 `SESSION_LIMIT_EXCEEDED` | IP당 세션 한도 초과 (신규) | `Retry-After` 헤더 없이 메시지로 안내 |
| 400 `INVALID_ARCHIVE_PATH` | custom query에서 화이트리스트 외 DB 참조 | 명확한 메시지 |
| 408 `QUERY_TIMEOUT` | custom query 타임아웃 (기본 10초) | 기존 메시지 문구 업데이트 |

### 6.2 에러 응답 포맷

기존 FastAPI HTTPException 형식 유지:

```json
{"detail": {"code": "SESSION_LIMIT_EXCEEDED", "message": "IP당 최대 세션 수 초과"}}
```

---

## 7. Security Considerations

- [x] 입력 검증: 기존 `validators.py` 유지 + `validate_db_path()` `pathlib.Path.resolve()` 기반 재작성
- [x] 비밀정보: `.env.example` + `.gitignore` 검증 (FR-01)
- [x] SQL 주입 방지: custom query 키워드 블랙리스트 + **ATTACH 화이트리스트**로 2중 방어 (FR-04)
- [x] Rate limiting: 기존 유지 + 세션 수 제한 추가 (FR-03)
- [x] Path traversal 차단: `Path.resolve()` 가 `database/` 하위인지 검증
- [ ] HTTPS: 본 Plan 범위 밖 (운영 매뉴얼 참조)

### 7.1 Custom Query ATTACH 강화 (S4 상세)

```python
# api/tools.py (신규 helper)
def _resolve_archive_db(requested: Path | None) -> Path:
    if requested is None:
        raise ValueError("archive not requested")
    resolved = Path(requested).resolve()
    if resolved not in (p.resolve() for p in ARCHIVE_DB_WHITELIST):
        raise ValueError(f"archive db not in whitelist: {resolved}")
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved

def _attach_archive(conn: sqlite3.Connection, path: Path) -> None:
    # URI 모드: 경로를 파일 URI로 안전하게 전달
    uri = f"file:{path.as_posix()}?mode=ro"
    conn.execute("ATTACH DATABASE ? AS archive", (uri,))
```

> 주의: sqlite의 `ATTACH DATABASE`는 표준 파라미터 바인딩을 허용하지 않는 일부 버전이 있으므로,
> **화이트리스트로 경로 집합을 한정**한 뒤 f-string 사용이 허용되는 fallback을 둔다.

```python
def _attach_archive(conn, path: Path) -> None:
    try:
        conn.execute("ATTACH DATABASE ? AS archive", (f"file:{path.as_posix()}?mode=ro",))
    except sqlite3.OperationalError:
        # fallback: path가 화이트리스트라 주입 위험 없음
        conn.execute(f"ATTACH DATABASE 'file:{path.as_posix()}?mode=ro' AS archive")
```

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `SessionStore` TTL/IP 제한 | pytest |
| Unit | `_resolve_archive_db`, `validate_db_path` | pytest |
| Integration | `/records`, `/summary/*`, `/healthz*`, `/chat/` | `fastapi.testclient.TestClient` |
| Integration | Chat with Gemini (mock) | `monkeypatch` + fake client |
| Regression | 기존 103 케이스 (`test_sql_validation`, `test_cache`, `test_db_router`, `test_rate_limiter`, `test_input_validation`) | pytest |

### 8.2 Key Test Cases

**신규 파일 `tests/test_api_integration.py`**
- [ ] `GET /healthz` → 200, `status=="ok"`
- [ ] `GET /healthz/ai` → 200, AI 키 미설정 시 `status=="disabled"`
- [ ] `GET /records?date_from=...&date_to=...&limit=10` → `count<=10`, `has_more`/`next_cursor` 필드 존재
- [ ] `GET /records?cursor=<invalid>` → 400 error shape
- [ ] `GET /records/BW0021` → 200, 정상 응답 구조
- [ ] `GET /items` → 200
- [ ] `GET /summary/monthly_total?year=2026` → 정렬된 월별 행
- [ ] `GET /summary/by_item?date_from=...&date_to=...` → 품목별 집계
- [ ] `POST /chat/` (Gemini fake, 단일 턴) → `reply` 문자열 반환
- [ ] `POST /chat/` (멀티턴, 같은 session_id) → history 유지
- [ ] `POST /chat/` 21회 호출 → 21번째 429
- [ ] Bad date format → 400

**신규 파일 `tests/test_session_store.py`**
- [ ] TTL 만료 후 `get()` → 빈 history
- [ ] 같은 IP 세션이 max_per_ip 초과 시 오래된 것부터 evict
- [ ] 다른 IP가 같은 session_id 요청 시 격리 (history 공유되지 않음)
- [ ] 10,000회 반복 save/get 후 `len(store)` 이 max_total 이하

**`tests/test_sql_validation.py` 추가 케이스**
- [ ] `ARCHIVE_DB_WHITELIST` 외 경로로 custom query → 에러
- [ ] 경로에 단일 따옴표/NUL/상대경로(`..`) 포함 → 거부

**성능·메모리 스모크 (수동)**
- [ ] 부하 스크립트로 1만 채팅 요청 → RSS 증가 < 50MB
- [ ] `pytest tests/test_api_integration.py -q` 실행 시간 < 30초

---

## 9. Clean Architecture

### 9.1 현 프로젝트 레이어 (Dynamic 수준)

| Layer | 위치 | 책임 |
|-------|------|------|
| Presentation | `dashboard/`, `api/*.py`의 라우터 | HTTP I/O, Streamlit UI |
| Application | `api/chat.py` 내 orchestration, `api/tools.py` | Gemini 호출, 도구 디스패치 |
| Domain | `shared/validators.py`, 설정 상수 | 순수 검증·타입 |
| Infrastructure | `shared/database.py`, `shared/cache.py`, `shared/rate_limiter.py` | DB/캐시/레이트리미팅 |

### 9.2 본 개선의 레이어 배치

| Component | Layer | Location |
|-----------|-------|----------|
| `SessionStore` | Application | `api/chat.py` (또는 `api/_session_store.py` 분리) |
| `GeminiClient` shim | Infrastructure | `api/_gemini_client.py` (신규) |
| `ToolDispatcher` | Application | `api/_tool_dispatch.py` (신규) |
| `_resolve_archive_db` | Domain (순수 함수) | `shared/validators.py` |
| integration tests | Test | `tests/test_api_integration.py`, `tests/test_session_store.py` |

---

## 10. Coding Convention Reference

### 10.1 본 프로젝트 컨벤션(실측)

- Python 3.11+, snake_case 함수, PascalCase 클래스
- 파일명: `snake_case.py`
- 모듈 private helper: `_leading_underscore`
- 타입 힌트: `Optional`, `Dict` 혼용 허용 (일관성만 유지, 본 Plan 범위 밖)
- 로거: `logger = logging.getLogger("production_api")` 재사용

### 10.2 환경 변수 네이밍

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `GEMINI_API_KEY` | (없음) | Gemini 인증 |
| `CHAT_SESSION_TTL_SEC` | `1800` | 세션 sliding TTL |
| `CHAT_SESSION_MAX_PER_IP` | `20` | IP당 최대 세션 |
| `CHAT_SESSION_MAX_TOTAL` | `1000` | 전역 최대 세션 |
| `CUSTOM_QUERY_TIMEOUT_SEC` | `10` | sqlite 실행 타임아웃 |
| `ARCHIVE_DB_WHITELIST` | `database/archive_2025.db` | 세미콜론 구분 목록 |

### 10.3 Feature별 적용

| Item | 규약 |
|------|------|
| Helper 분리 위치 | `api/_session_store.py`, `api/_tool_dispatch.py`, `api/_gemini_client.py` |
| 테스트 파일 | `tests/test_<area>.py` |
| 에러 코드 문자열 | `UPPER_SNAKE_CASE` |
| 설정 로드 | `shared/config.py`에서 `os.getenv` 일원화 |

---

## 11. Implementation Guide

### 11.1 파일 변경 맵

```
api/
├── chat.py                 # SessionStore 사용하도록 축소 (~150 LOC)
├── _session_store.py       # NEW: SessionStore 클래스
├── _gemini_client.py       # NEW: Gemini 호출 wrapper (테스트 주입점)
├── _tool_dispatch.py       # NEW: tool_calls → tools.py 함수 매핑
├── tools.py                # execute_custom_query 분리 + 화이트리스트
└── main.py                 # 변경 최소 (healthz/ai 필드 추가만)
shared/
├── config.py               # 신규 env 변수, ARCHIVE_DB_WHITELIST
└── validators.py           # validate_db_path 재작성
tests/
├── test_api_integration.py # NEW
├── test_session_store.py   # NEW
└── test_sql_validation.py  # + 경로 케이스
docs/
├── specs/operations_manual.md   # .env.example 안내
└── 04-report/changelog.md       # 1줄 기록
.env.example                    # NEW
.gitignore                      # .env 확인
```

### 11.2 구현 순서 (S1 → S4 → S3 → S5 → S2)

1. [ ] **S1**: `.env.example`, `.gitignore` 확인, `shared/config.py` 정리 (fail-soft 규약)
2. [ ] **S4**: `validators.validate_db_path` 재작성 + `ARCHIVE_DB_WHITELIST` + `_resolve_archive_db` + `CUSTOM_QUERY_TIMEOUT_SEC` 적용
3. [ ] **S3**: `api/_session_store.py` 생성, `chat.py`에서 전역 dict 제거, IP 바인딩·TTL sliding expiry 적용
4. [ ] **S5**: `api/_gemini_client.py` + `api/_tool_dispatch.py` 추출, `chat_with_data()` 를 orchestrator로 축소
5. [ ] **S2**: `tests/test_api_integration.py`, `tests/test_session_store.py` 작성 (Gemini mock monkeypatch)
6. [ ] 회귀: `pytest tests/ -v`
7. [ ] 문서: `operations_manual.md`, `changelog.md` 업데이트
8. [ ] `/pdca analyze security-and-test-improvement`

### 11.3 Gemini Mock 예시

```python
# tests/test_api_integration.py
class FakeChat:
    def __init__(self, history=None): self.history = history or []
    def send_message(self, parts):
        class R: text = "mocked reply"; candidates = []
        return R()

class FakeModel:
    def start_chat(self, history=None): return FakeChat(history)

def test_chat_single_turn(monkeypatch, client):
    monkeypatch.setattr("api._gemini_client.get_model", lambda: FakeModel())
    r = client.post("/chat/", json={"query": "hi"})
    assert r.status_code == 200
    assert "reply" in r.json()
```

### 11.4 리스크 체크포인트

- `chat_with_data` 분리 후 **multi-turn 히스토리 회귀**: S3 테스트가 먼저 있어야 안전.
- `_attach_archive`의 파라미터 바인딩은 SQLite 버전 의존 → fallback 경로를 반드시 테스트.
- `TestClient`가 앱 start-up hook을 실행하므로, `GEMINI_API_KEY` 미설정 경로도 부팅 가능해야 함(FR-01).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-14 | 초기 드래프트 (Plan v0.1 기반) | interojo |
