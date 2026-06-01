# auth-audit-v1 — Plan

> **Cycle**: auth-audit-v1
> **PDCA Phase**: Plan
> **Date**: 2026-06-02
> **Project**: Production Data Hub API
> **Summary**: API-Key / Bearer 토큰 기반 인증 미들웨어 + 감사 로그를 **opt-in(기본 비활성)** 으로 도입해, 기존 동작을 100% 보존하면서 인증·접근 감사 레이어를 추가한다.

## 1. Background

현재 `api/main.py`의 모든 엔드포인트는 **인증 없이 공개**되어 있다. 보호 장치는 IP 기반 rate limiting(`shared/rate_limiter.py`)뿐이며, 누가 어떤 요청을 했는지 추적하는 **감사(audit) 기록도 없다**. 내부망 운영(dev server `192.168.200.107`, [[reference_server_network]])이라 해도, API-Key/Bearer 기반의 최소 인증과 접근 감사 로그는 보안 baseline으로 필요하다.

기존 코드에는 인증 관련 런타임 로직이 **전혀 없음**을 확인했다(`Authorization`/`X-API-Key`/`API_KEY` 매치는 전부 문서·README·Gemini API 키 용도). 즉 이번 사이클은 신규 레이어 추가이며 기존 라우터/로직 수정은 최소화한다.

### 기존 미들웨어 구조 (측정, 2026-06-02)

`api/main.py`에는 단일 HTTP 미들웨어 `add_request_id_and_rate_limit`가 있다:
1. `set_request_id()`로 요청 ID 발급 → `X-Request-ID` 응답 헤더
2. 공개 경로(`/`, `/healthz`, `/healthz/ai`, `/docs`, `/openapi.json`)는 rate limit 스킵
3. `/chat*`는 자체 limiter 사용 → 스킵
4. 그 외는 `api_rate_limiter.is_allowed()`로 429 처리

→ 인증 미들웨어는 이 흐름에 **request_id 발급 이후 / 라우트 진입 이전** 위치로 삽입해, 감사 로그가 request_id를 활용할 수 있게 한다(§ Design에서 순서 확정).

## 2. Goal

1. **인증 미들웨어** — `X-API-Key: <key>` 또는 `Authorization: Bearer <token>` 헤더를 검증. 둘 중 하나라도 유효하면 통과, 아니면 `401`.
2. **신규 모듈 분리**:
   - `shared/auth.py` — 순수 인증 로직(자격증명 추출·검증, 공개 경로 판정). 프레임워크 비의존(테스트 용이).
   - `api/_audit.py` — 감사 로그 기록(인증 성공/실패/공개접근, request_id·client_ip·path·method·principal 포함).
3. **미들웨어 등록** — `api/main.py`에 인증 미들웨어 1개 추가.
4. **공개 엔드포인트 예외** — health(`/`, `/healthz`, `/healthz/ai`)·문서(`/docs`, `/redoc`, `/openapi.json`)는 인증 제외(단일 진실원천으로 관리).
5. **기존 동작 100% 보존** — `API_AUTH_ENABLED` 기본 **false**. 미설정 환경(현 dev/CI/기존 테스트)에서는 미들웨어가 pass-through → 기존 pytest 전부 green 유지.
6. **회귀 0 + 신규 테스트** — 인증 on/off, API-Key/Bearer 성공·실패, 공개경로 우회, 감사로그 기록을 커버하는 신규 테스트 추가.

## 3. Non-Goals (defer)

- **사용자/세션 관리, 토큰 발급(JWT 서명·만료·refresh), OAuth2 flow** — 본 사이클은 정적 키/토큰 셋(env 주입) 검증까지. 동적 발급은 별도 사이클.
- **역할 기반 인가(RBAC)/스코프별 권한** — principal 식별까지만. per-route 권한 매트릭스는 후속(`auth-rbac-v2` 예고).
- **키 회전·해싱 저장소(DB)** — 키는 env 평문 셋 + 상수시간 비교(`secrets.compare_digest`). DB 저장/회전은 defer.
- **rate limiter를 principal 단위로 전환** — 현 IP 기반 유지.
- **`/chat` 자체 인증 분리** — 동일 미들웨어 정책 적용(공개 아님 → 인증 대상).

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Framework | FastAPI / Starlette 미들웨어 | ✅ 기존 사용 |
| Stdlib | `secrets`(상수시간 비교), `logging` | ✅ |
| 신규 외부 런타임 의존성 | — | **0** |
| 기존 스키마/DB 변경 | — | **0** |
| 공개 API 계약 변경 | 인증 활성 시에만 401 추가 (기본 off → 0) | opt-in |

## 5. Scope (대상)

| 구분 | 대상 |
|---|---|
| **신규 파일** | `shared/auth.py`, `api/_audit.py`, `tests/test_auth.py`, `tests/test_audit.py` |
| **수정 파일** | `api/main.py`(미들웨어 등록), `shared/config.py`(인증 설정), `shared/__init__.py`(export), `.env.example`(설정 예시) |
| **공개 경로(인증 제외)** | `/`, `/healthz`, `/healthz/ai`, `/docs`, `/redoc`, `/openapi.json` |
| **제외** | `webcloring-pdf/`, 동적 토큰 발급, RBAC, 키 DB 저장 |

## 6. Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-01 | `X-API-Key` 헤더 값이 설정된 키 셋에 포함되면 인증 성공 | High |
| FR-02 | `Authorization: Bearer <t>` 토큰이 설정된 토큰 셋에 포함되면 인증 성공 | High |
| FR-03 | 자격증명 누락/오류 시 `401` + `WWW-Authenticate` 헤더, JSON `{"detail": ...}` | High |
| FR-04 | 공개 경로는 자격증명 없이 통과 (단일 PUBLIC_PATHS 원천) | High |
| FR-05 | `API_AUTH_ENABLED=false`(기본)면 미들웨어 pass-through | High |
| FR-06 | 모든 인증 판정(grant/deny/public)을 감사 로그로 기록 (request_id·ip·method·path·principal·결과) | High |
| FR-07 | 키/토큰 비교는 상수시간(`secrets.compare_digest`)으로 timing attack 방지 | Medium |
| FR-08 | 인증 활성 + 키 미설정 시 startup 경고 로그(설정 누락 가시화) | Medium |

## 7. Non-Functional Requirements

| 범주 | 기준 | 측정 |
|------|------|------|
| 보안 | 상수시간 비교, 키 평문 미로그(마스킹), 공개경로 화이트리스트 방식 | 코드리뷰 + test |
| 성능 | 미들웨어 오버헤드: 경로 set 조회 O(1) + 셋 멤버십 O(1). 비활성 시 분기 1회 | 구조 검토 |
| 호환성 | 기존 pytest 100% green (auth off) | pytest |
| 관측성 | 감사 로그는 전용 logger(`audit`), 키 값 마스킹 | 로그 검사 |

## 8. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `shared/auth.py` 신규 — 자격증명 추출·검증·공개경로 판정 함수, 프레임워크 비의존 | 파일 |
| AC2 | `api/_audit.py` 신규 — 감사 기록 함수, 전용 logger, 키 마스킹 | 파일 |
| AC3 | `api/main.py`에 인증 미들웨어 등록, request_id 발급 이후 위치 | diff |
| AC4 | `API_AUTH_ENABLED=false`(기본): 보호 라우트 인증 없이 200 (기존 동작) | test |
| AC5 | auth on + 키 없음: 보호 라우트 401, `X-API-Key` 정답 200, 틀린 키 401 | test |
| AC6 | auth on + Bearer 정답 200, 틀린 토큰 401 | test |
| AC7 | auth on에서도 공개경로(`/healthz`, `/docs`, `/openapi.json`) 200 | test |
| AC8 | 인증 grant/deny/public 시 감사 로그 1건 기록(request_id·principal 포함) | test |
| AC9 | 기존 pytest 전체 회귀 green (auth off 기본) | pytest |
| AC10 | import smoke 통과(`shared.auth`, `api._audit`, `api.main`) | python -c |
| AC11 | ruff 게이트(F,BLE001,I,UP,B904) 신규 파일 0 errors | ruff |
| AC12 | gap-detector match rate ≥ 90% | Check |

## 9. Constraints / Risks

- **기본값 결정(가장 중요)**: auth를 기본 활성하면 키 미설정 환경에서 **모든 요청 401 → 기존 테스트·dev 전부 붕괴**. → `API_AUTH_ENABLED` **기본 false**(opt-in)로 "기존 동작 유지" 요구사항을 보장. 운영 활성화는 env 한 줄.
- **미들웨어 순서**: 인증을 request_id 발급보다 먼저 두면 감사 로그에 request_id 누락. → request_id/rate-limit 미들웨어를 outermost로 유지하고 인증을 inner로 등록(Starlette LIFO 특성, Design §에서 등록 순서 확정).
- **공개경로 중복 정의 위험**: 기존 rate-limit 스킵 목록과 인증 PUBLIC_PATHS가 어긋나면 혼란. → PUBLIC_PATHS는 `shared/auth.py` 단일 원천, 필요 시 main이 참조.
- **키 로그 유출**: 감사 로그에 키 평문 기록 시 2차 유출. → principal은 식별자/마스킹값만(`apikey:****abcd`), 원문 미기록.
- **소규모 diff**: 신규 2파일 + main 1곳 + config. 회귀 위험 낮음. 커밋은 [[feedback_commit_style]]에 따라 **(a) shared/auth 로직, (b) api/_audit, (c) main+config 등록, (d) tests** 계층 분리.
- **default-arg shadowing 주의**([[feedback_default_shadowing.md]]): config 상수를 함수 기본인자로 캡처하면 env 변경이 안 먹힘 → 런타임 조회 함수로 노출.

## 10. Out-of-band Notes

- **후속 사이클 예고**: `auth-rbac-v2`(per-route 스코프/역할), `auth-token-issuer-v1`(JWT 발급·만료), 키 DB 저장·회전.
- **운영 활성화 절차(문서화 예정)**: `.env`에 `API_AUTH_ENABLED=true` + `API_KEYS=...` 또는 `API_BEARER_TOKENS=...` → 재기동.
- **메모리 참조**: [[reference_server_network]], [[feedback_commit_style]], [[feedback_default_shadowing]], [[project_review_fixes_202604]]
- **SSE 계약 영향 없음**([[project_sse_contract]]): `/chat/stream`은 인증 대상이나 이벤트 순서/세션 규칙 불변.
