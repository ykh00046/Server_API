# docs-sync Design Document

> **Summary**: 4개 spec 문서의 갱신 설계 (코드 ground truth 기준)
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-23
> **Status**: Design

---

## 1. 코드 Ground Truth 매핑

각 갱신 항목의 **단일 진실 출처(SoT)**를 코드에서 픽스.

### 1.1 AI 모듈 구조 (D1)

| 코드 위치 | 문서 반영 |
|----------|---------|
| `api/chat.py` (orchestrator only) | §2.2 Controller |
| `api/_session_store.py` | §2.2 Multi-turn Session Store |
| `api/_tool_dispatch.py` | §2.2 Tool Registry |
| `api/_chat_stream.py` | §2.2 SSE Stream Generator |
| `api/_gemini_client.py` | §2.2 GenAI Client Factory + `is_fallbackable()` |
| `api/tools.py` | §4 Tools (구현체) |
| `api/chat.py:106 _build_system_instruction()` | §3.1 동적 시스템 프롬프트 |

### 1.2 도구 7개 (D1)

`api/_tool_dispatch.py:20-28`의 `PRODUCTION_TOOLS` 리스트가 SoT:

1. `search_production_items` (`tools.py:54`)
2. `get_production_summary` (`tools.py:140`)
3. `get_monthly_trend` (`tools.py:221`)
4. `get_top_items` (`tools.py:290`)
5. `compare_periods` (`tools.py:352`)
6. `get_item_history` (`tools.py:452`)
7. `execute_custom_query` (`tools.py:524`)

### 1.3 모델명 (D1)
- Primary: `gemini-2.5-flash` (현재 `shared/config.py:53`)
- Fallback: `gemini-2.5-flash-lite` (Cycle 1에서 정정)
- Fallback 트리거: 429/503 (HTTP) — `_gemini_client.py:53 FALLBACK_STATUS_CODES`

### 1.4 Multi-turn 세션 정책 (D1)
- `shared/config.py:85-87`:
  - TTL 1800s, MAX_PER_IP 20, MAX_TOTAL 1000
- `api/_session_store.py`: SESSION_MAX_TURNS 등

### 1.5 미문서화 엔드포인트 (D2)
- `api/main.py:220 GET /metrics/performance` → rolling-window 통계
- `api/main.py:226 GET /metrics/cache` → cache + perf 스냅샷
- `api/chat.py:363 POST /chat/stream` → SSE (이벤트 계약: meta → tool_call* → token+ → done|error)

### 1.6 응답 필드 보강 (D2)
- `/records` 응답 (`api/main.py:538-543`): `data`, `next_cursor`, `has_more`, `count` (현재 doc은 `has_more` 누락)
- `/chat/` 응답 (`api/chat.py:357-360`): `answer`, `tools_used`, `request_id`, **`model_used`** (현재 doc 누락)

### 1.7 /cache/clear 결정 (D3)

**선택지**

| 옵션 | 장점 | 단점 | 결정 |
|------|------|------|------|
| A. POST /cache/clear 신규 구현 | 즉시 무효화 가능 | 익명 호출 시 캐시 박싱 공격 가능, 인증 필요 → 복잡도↑ | ✗ |
| B. 문서에서 제거 + 서버 재시작 안내 | 단순, 안전 | 5분 무효화 대기 | **✓** |

**선택 근거**: B
- 5분 TTL이라 자연 만료가 빠름.
- /metrics/cache로 현재 상태 모니터링 가능.
- 강제 무효화가 정말 필요하면 manager.py 또는 systemctl restart api 한 줄.

### 1.8 Dashboard 포트 (D4)

`shared/config.py:40` `DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 8502))` → 8502가 SoT.
`system_architecture.md` §2.1, §3 다이어그램, §5.1 streamlit 명령 모두 8502로 통일.

---

## 2. File-by-File Changes

### 2.1 `docs/specs/ai_architecture.md` (전면 개정)

- §2.1 모델: `gemini-2.0-flash` → `gemini-2.5-flash` + fallback `gemini-2.5-flash-lite`
- §2.2 핵심 컴포넌트: 4개 내부 모듈 분리 명시
- §3.1 시스템 프롬프트: `SYSTEM_INSTRUCTION` 상수 → `_build_system_instruction()` 동적 함수로 교체 설명
- §4 도구 명세: 5개 → 7개 (search/summary/monthly_trend/top_items/compare_periods/item_history/execute_custom_query)
- §5.x 신규: Multi-turn 세션 정책, Fallback 정책, SSE 스트리밍 개요
- §6 유지보수: 모델명 위치(`shared/config.py`)로 정정

### 2.2 `docs/specs/api_guide.md` (보강)

- §2 헬스체크 뒤에 §2.x **Metrics** 추가 (`/metrics/performance`, `/metrics/cache`)
- §3 `/records` 응답 예시에 `has_more` 필드 추가
- §6 `/chat/`에 `model_used` 응답 필드 추가
- §6 뒤에 §6.x **`POST /chat/stream` (SSE)** 섹션 추가 — 이벤트 계약 + curl 예제

### 2.3 `docs/specs/operations_manual.md` (소폭 수정)

- §7.4 캐시 초기화 안내: `POST /cache/clear` → "서버 재시작 또는 5분 TTL 대기" + `/metrics/cache`로 모니터링 안내

### 2.4 `docs/specs/system_architecture.md` (소폭 수정)

- §2.1 Dashboard 포트 8501 → 8502
- §3 다이어그램 :8501 → :8502
- §5.1 streamlit 명령 `--server.port 8501` → `--server.port 8502`
- §6 도구표(현재 5개) → 7개로 보강 (`compare_periods`, `get_item_history` 추가)
- §7 변경 이력에 1.6 항목 추가: "v8 진화 반영 (도구 7개, 모듈 분리, 포트 통일)"

---

## 3. 검증

- `grep -RIn "gemini-2.0-flash\|SYSTEM_INSTRUCTION\b\|POST /cache/clear" docs/specs` → 0건
- `grep -RIn "compare_periods\|get_item_history\|/metrics/performance\|/chat/stream\|model_used\|has_more\|8502" docs/specs` → 각 1건+ 존재
- gap-detector 재실행 시 docs 영역 ≥ 95%
