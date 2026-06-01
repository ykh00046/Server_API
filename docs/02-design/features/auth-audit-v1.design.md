# auth-audit-v1 — Design

> **Cycle**: auth-audit-v1
> **PDCA Phase**: Design
> **Date**: 2026-06-02
> **Plan**: [[auth-audit-v1.plan]]

## 0. 설계 원칙

1. **순수 로직과 프레임워크 경계 분리** — 자격증명 검증은 `shared/auth.py`에서 `Request` 비의존 함수로 구현(헤더 dict만 입력). 미들웨어(`api/main.py`)는 얇은 어댑터. → 단위 테스트가 TestClient 없이도 가능.
2. **opt-in 보안** — `API_AUTH_ENABLED` 기본 `False`. 비활성 시 미들웨어는 단일 분기 후 즉시 통과. 기존 동작 100% 보존.
3. **단일 진실원천(SSOT)** — 공개 경로 집합은 `shared/auth.py`의 `PUBLIC_PATHS` 하나로 관리.
4. **상수시간 비교** — 키/토큰은 `secrets.compare_digest`로 비교(timing attack 방지). 셋 멤버십이 아니라 후보 순회 비교(짧은 셋이므로 비용 무시 가능).
5. **민감정보 비로그** — 감사 로그의 principal은 마스킹 식별자(`apikey:****1a2b`)만. 원문 키/토큰은 절대 기록하지 않음.

## 1. 모듈 구조

```
shared/auth.py        ← 순수 인증 로직 (신규)
  ├─ AuthSettings      : env 스냅샷 (enabled, api_keys, bearer_tokens)
  ├─ AuthResult        : 판정 결과 (authenticated, principal, method, reason)
  ├─ load_auth_settings()        : config에서 런타임 조회 (shadowing 회피)
  ├─ is_public_path(path)        : PUBLIC_PATHS 판정
  ├─ extract_credentials(headers): X-API-Key / Authorization 파싱
  └─ authenticate(headers, settings) -> AuthResult

api/_audit.py         ← 감사 로그 (신규)
  ├─ logger = get_logger("audit")
  ├─ _mask(secret)               : 끝 4자만 노출 마스킹
  └─ record_auth_event(...)      : grant/deny/public 구조화 로그 1줄

api/main.py           ← 미들웨어 등록 (수정)
  └─ @app.middleware("http") auth_and_audit  (request_id 미들웨어 inner)

shared/config.py      ← 설정 상수 (수정)
shared/__init__.py    ← export (수정)
```

## 2. `shared/auth.py` 상세

### 2.1 데이터 구조

```python
@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    api_keys: frozenset[str]
    bearer_tokens: frozenset[str]

@dataclass(frozen=True)
class AuthResult:
    authenticated: bool
    principal: str | None   # 마스킹된 식별자 (e.g. "apikey:****1a2b")
    method: str | None      # "api_key" | "bearer" | None
    reason: str | None      # 실패 사유 (감사/디버그용; 응답엔 노출 안 함)
```

### 2.2 공개 경로 (SSOT)

```python
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/", "/healthz", "/healthz/ai",
    "/docs", "/redoc", "/openapi.json",
})

def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS
```

> 정확 일치(set membership)로 시작. `/docs`가 서빙하는 하위 정적 자산(`/docs/oauth2-redirect` 등)은 FastAPI 기본 docs UI가 inline asset을 쓰므로 추가 경로 불필요. 필요 시 prefix 확장은 후속.

### 2.3 자격증명 추출 (헤더 dict 입력 — 프레임워크 비의존)

```python
def extract_credentials(headers: Mapping[str, str]) -> tuple[str | None, str | None]:
    """(api_key, bearer_token) 반환. 헤더 키는 대소문자 무시 조회."""
    api_key = _get(headers, "x-api-key")
    api_key = api_key.strip() if api_key else None   # 공백 정규화
    bearer = None
    authz = _get(headers, "authorization")
    if authz and authz.lower().startswith("bearer "):
        bearer = authz[7:].strip() or None           # "Bearer " 뒤 공백뿐이면 None
    return api_key, bearer
```

- Starlette `request.headers`는 대소문자 무시 `Mapping`이지만, 순수 함수가 일반 dict도 받도록 `_get`은 lower-case 비교로 방어.
- **입력 정규화(구현 반영)**: `X-API-Key`는 `.strip()`, `Bearer ` 뒤가 공백뿐이면 `None`으로 정규화해 빈 자격증명이 `missing_credentials`로 일관 처리되게 한다(`test_extract_empty_bearer` 커버).

### 2.4 검증 (상수시간)

```python
def _matches_any(candidate: str, allowed: frozenset[str]) -> bool:
    # compare_digest를 모든 항목에 대해 평가 (early-return로 인한 timing leak 회피)
    matched = False
    for a in allowed:
        if secrets.compare_digest(candidate, a):
            matched = True
    return matched

def authenticate(headers, settings: AuthSettings) -> AuthResult:
    if not settings.enabled:
        return AuthResult(True, None, None, "auth_disabled")
    api_key, bearer = extract_credentials(headers)
    if api_key and _matches_any(api_key, settings.api_keys):
        return AuthResult(True, f"apikey:{_mask(api_key)}", "api_key", None)
    if bearer and _matches_any(bearer, settings.bearer_tokens):
        return AuthResult(True, f"bearer:{_mask(bearer)}", "bearer", None)
    if api_key or bearer:
        return AuthResult(False, None, None, "invalid_credentials")
    return AuthResult(False, None, None, "missing_credentials")
```

> `enabled=True`인데 `api_keys`/`bearer_tokens`가 모두 비어 있으면 어떤 자격증명도 매치 못 함 → 전부 401. 이 위험은 startup 경고(FR-08)로 가시화하되, 정책상 "활성화했으면 키를 넣어야 한다"가 맞으므로 fail-closed 유지.

### 2.5 런타임 설정 조회 (shadowing 회피)

[[feedback_default_shadowing]]: config 상수를 함수 기본인자로 캡처하지 않고, **호출 시점에** config를 읽는다.

```python
def load_auth_settings() -> AuthSettings:
    from shared import config
    return AuthSettings(
        enabled=config.API_AUTH_ENABLED,
        api_keys=frozenset(config.API_KEYS),
        bearer_tokens=frozenset(config.API_BEARER_TOKENS),
    )
```

→ 테스트에서 `monkeypatch.setattr(config, "API_AUTH_ENABLED", True)` 후 `load_auth_settings()` 호출이면 즉시 반영.

## 3. `api/_audit.py` 상세

```python
audit_logger = get_logger("audit")

def _mask(secret: str) -> str:
    if not secret:
        return "****"
    return "****" + secret[-4:] if len(secret) > 4 else "****"

def record_auth_event(*, request_id, client_ip, method, path,
                      result: AuthResult, status_code: int) -> None:
    outcome = "GRANT" if result.authenticated else "DENY"
    if result.reason == "auth_disabled":
        return  # 비활성 시 감사 노이즈 억제 (기존 동작 보존)
    audit_logger.info(
        "[AUDIT] %s | rid=%s ip=%s %s %s | principal=%s method=%s reason=%s status=%s",
        outcome, request_id, client_ip, method, path,
        result.principal or "-", result.method or "-",
        result.reason or "-", status_code,
    )
```

- `_mask`는 `auth.py`와 `_audit.py` 양쪽에서 필요 → **`shared/auth.py`에 `mask_secret()` 정의하고 `_audit.py`가 import**(중복 제거, SSOT).
- 공개경로 접근도 감사할지: 기본은 **인증 판정이 일어난 요청만** 기록(공개경로는 인증 스킵이므로 audit 스킵 → 로그 노이즈/성능 보호). 공개경로 audit는 후속 옵션.

## 4. `api/main.py` 미들웨어 등록

### 4.1 순서 (Starlette LIFO)

Starlette는 **나중에 등록된 미들웨어가 outermost**(요청 시 먼저 실행). 감사 로그가 `request_id`를 쓰려면 request_id가 먼저 set돼야 하므로:

- **기존 `add_request_id_and_rate_limit`를 outermost로 유지** → 소스에서 **나중에**(아래) 등록되어야 함.
- **신규 `auth_and_audit`는 inner** → 소스에서 **먼저**(위) 등록.

요청 실행 순서: `request_id+ratelimit (outer)` → `auth_and_audit (inner)` → route.
즉 **request_id 발급 → rate limit → 인증 → 라우트**. 감사 로그는 request_id를 안전하게 참조한다.

구현: 신규 미들웨어 함수를 기존 데코레이터 **위쪽**(소스상 먼저)에 배치.

### 4.2 미들웨어 본문

```python
@app.middleware("http")
async def auth_and_audit(request, call_next):
    settings = load_auth_settings()
    # OPTIONS(CORS preflight)는 자격증명을 싣지 않으므로 통과시켜 CORS가
    # 깨지지 않게 한다. disabled/공개경로도 pass-through.
    if (not settings.enabled
            or request.method == "OPTIONS"
            or is_public_path(request.url.path)):
        return await call_next(request)

    result = authenticate(request.headers, settings)
    request_id = get_request_id()           # logging_config에서 현재 rid 조회
    client_ip = request.client.host if request.client else "unknown"

    if not result.authenticated:
        record_auth_event(request_id=request_id, client_ip=client_ip,
                          method=request.method, path=request.url.path,
                          result=result, status_code=401)
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={"WWW-Authenticate": "Bearer", "X-Request-ID": request_id or ""},
        )

    record_auth_event(request_id=request_id, client_ip=client_ip,
                      method=request.method, path=request.url.path,
                      result=result, status_code=200)
    return await call_next(request)
```

- `get_request_id()` — `shared/logging_config.py`에 조회 함수가 있으면 사용, 없으면 추가(context var 조회). **확인 후 결정**(없으면 `request.headers`엔 아직 X-Request-ID 없으므로 contextvar 조회 함수 신설).
- 401 detail은 일반화된 `"Unauthorized"`(사유 미노출 — `missing` vs `invalid` 구분은 감사 로그에만).

### 4.3 register 위치

기존 파일 line 86 `@app.middleware("http") add_request_id_and_rate_limit` **위에** `auth_and_audit`를 정의 → import 추가(`shared.auth`, `._audit`).

## 5. `shared/config.py` 추가

```python
# ==========================================================
# API Authentication (auth-audit-v1)  — opt-in, default OFF
# ==========================================================
API_AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "false").lower() in {"1","true","yes","on"}
API_KEYS: list[str] = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
API_BEARER_TOKENS: list[str] = [t.strip() for t in os.getenv("API_BEARER_TOKENS", "").split(",") if t.strip()]
```

startup 경고(FR-08)는 `api/main.py` 모듈 로드 시:
```python
if API_AUTH_ENABLED and not (API_KEYS or API_BEARER_TOKENS):
    logger.warning("[Auth] API_AUTH_ENABLED=true but no API_KEYS/API_BEARER_TOKENS set — all protected routes will 401")
```

## 6. `.env.example` 추가

```
# API Authentication (auth-audit-v1) — opt-in. Default OFF preserves open access.
API_AUTH_ENABLED=false
# Comma-separated. Used only when API_AUTH_ENABLED=true.
API_KEYS=
API_BEARER_TOKENS=
```

## 7. 테스트 설계

### 7.1 `tests/test_auth.py` (순수 로직 — 빠름)

| 케이스 | 기대 |
|---|---|
| `is_public_path("/healthz")` | True |
| `is_public_path("/records")` | False |
| `extract_credentials({"x-api-key":"k"})` | ("k", None) |
| `extract_credentials({"authorization":"Bearer t"})` | (None, "t") |
| `extract_credentials({"authorization":"Basic xx"})` | (None, None) |
| `authenticate(enabled=False)` | authenticated=True, reason=auth_disabled |
| 올바른 api_key | authenticated=True, method=api_key, principal 마스킹 |
| 틀린 api_key | authenticated=False, reason=invalid_credentials |
| 자격증명 없음(enabled) | authenticated=False, reason=missing_credentials |
| `mask_secret("abcd1234")` | `****1234` |

### 7.2 `tests/test_audit.py` + 미들웨어 통합 (TestClient + monkeypatch)

> **구현 정합(2026-06-02)**: 보호 라우트(`PROTECTED_PATH`)는 부작용 없는 read-only 라우트면 동등하다. 구현은 `/metrics/performance` 대신 **`/items`**(`api/routers/records.py:248`, GET, 캐시 조회, query 파라미터 모두 optional)를 사용한다. `is_public_path("/items") is False`로 비공개임이 보장된다.

| 케이스 | 기대 |
|---|---|
| auth OFF(기본): GET `/items` | 200 (기존 동작) |
| auth ON, 자격증명 없음: GET `/items` | 401 + `WWW-Authenticate` |
| auth ON, 올바른 `X-API-Key` | 200 |
| auth ON, 틀린 `X-API-Key` | 401 |
| auth ON, 올바른 `Authorization: Bearer` | 200 |
| auth ON, 공개경로 `/healthz` 자격증명 없이 | 200 |
| auth ON, deny 시 audit 로그 `[AUDIT] DENY` (caplog) | 기록됨 |
| auth ON, grant 시 audit 로그 `[AUDIT] GRANT` + principal 마스킹 | 기록됨, 원문 키 미포함 |

> auth ON은 `monkeypatch.setattr(shared.config, "API_AUTH_ENABLED", True)` + `API_KEYS`/`API_BEARER_TOKENS` 패치로 구성. `load_auth_settings()`가 런타임 조회이므로 즉시 반영(§2.5). 보호 라우트는 인증 외 부작용이 적은 `/metrics/performance` 선택.

## 8. 구현 순서 (Do 단계 체크리스트)

1. [ ] `shared/config.py` — 인증 설정 3개 추가
2. [ ] `shared/auth.py` — 신규 (데이터구조 + 함수)
3. [ ] `shared/__init__.py` — `load_auth_settings`, `is_public_path`, `authenticate`, `mask_secret` export
4. [ ] `api/_audit.py` — 신규
5. [ ] `shared/logging_config.py` — `get_request_id()` 존재 확인, 없으면 추가
6. [ ] `api/main.py` — `auth_and_audit` 미들웨어 + startup 경고 + import
7. [ ] `.env.example` — 설정 예시
8. [ ] `tests/test_auth.py`, `tests/test_audit.py`
9. [ ] ruff + 전체 pytest 회귀 확인

## 9. 커밋 계층 ([[feedback_commit_style]])

| 커밋 | 범위 |
|---|---|
| (a) `feat(auth): shared/auth.py 인증 로직 + config` | shared/auth.py, config.py, __init__.py |
| (b) `feat(audit): api/_audit.py 감사 로그` | api/_audit.py |
| (c) `feat(auth): main.py 미들웨어 등록` | api/main.py, logging_config(필요시), .env.example |
| (d) `test(auth): 인증/감사 테스트` | tests/test_auth.py, tests/test_audit.py |
| (e) `docs(pdca)` | plan/design/analysis/report |

## 10. 위험 재확인

- **기존 미들웨어 수정 최소화**: `add_request_id_and_rate_limit` 본문 불변, 신규 함수만 추가 → 회귀 표면 최소.
- **request_id 조회**: contextvar 기반. 미들웨어 체인에서 outer가 set한 값을 inner가 읽음 → 동일 요청 컨텍스트라 보장. (§5 Do에서 logging_config 확인)
- **fail-closed**: enabled+키없음 = 전부 401. 의도된 안전 동작, 경고로 가시화.
