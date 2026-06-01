# auth-audit-v1 — QA

> **PDCA Phase**: QA (Zero-Script / 게이트·회귀 + 신규 계약 테스트)
> **Date**: 2026-06-02
> **Design**: [[auth-audit-v1.design]] · **Analysis**: [[auth-audit-v1.analysis]]

## QA 전략

인증/감사는 (a) **순수 로직**(`shared/auth.py`)과 (b) **미들웨어 통합 동작**(`api/main.py`)으로 나뉜다.
- 순수 로직은 TestClient 없이 결정표를 직접 검증(`tests/test_auth.py`).
- 미들웨어는 실제 FastAPI 앱을 TestClient로 구동, `monkeypatch`로 auth on/off를 토글해 401/200 계약과 감사 로그(caplog)를 검증(`tests/test_audit.py`).
- opt-in(기본 OFF)이므로 **기존 회귀 스위트 전체가 "auth off" 경로의 계약**을 그대로 보증한다.

## 실행 결과

| # | 검사 | 명령 | 결과 |
|---|---|---|:---:|
| Q1 | 신규 인증/감사 테스트 | `pytest tests/test_auth.py tests/test_audit.py -q` | ✅ **33 passed** |
| Q2 | 전체 회귀 (auth off 기본) | `pytest -q` | ✅ **360 passed**, 0 failed, flaky 0 |
| Q3 | ruff 게이트 (신규/수정 파일) | `ruff check … --select F,BLE001,I,UP,B904` | ✅ All checks passed (0 errors) |
| Q4 | import smoke | `python -c "import shared.auth, api._audit, api.main; …"` | ✅ import OK |

## 보안 계약 확인 (FR-03/06/07, NFR 관측성)

- **401 응답 계약**: 자격증명 누락/오류 시 `401` + `WWW-Authenticate: Bearer` + `{"detail":"Unauthorized"}`. 사유(missing vs invalid)는 응답에 노출하지 않고 감사 로그에만 기록 — 정보 누출 차단.
  - `test_auth_on_missing_credentials_401`, `test_auth_on_wrong_api_key_401`, `test_auth_on_wrong_bearer_401`.
- **상수시간 비교**: `_matches_any`가 early-return 없이 모든 후보를 `secrets.compare_digest`로 평가 — timing 누출 차단(구조 검토).
- **비밀값 비로그**: 감사 로그의 principal은 `mask_secret`(끝 4자만). `test_audit_grant_logged_and_no_raw_secret`이 **원문 키 미포함 + 마스킹값(`****1234`) 포함**을 동시 단언.
- **opt-in 무소음**: auth off일 때 감사 로거 완전 침묵 — `test_audit_off_produces_no_audit_log`(`caplog`에 audit 레코드 0건).

## 호환성 확인 (AC4/AC9 — 기존 동작 100% 보존)

- 기본 설정(`API_AUTH_ENABLED=false`)에서 보호 라우트(`/items`)는 자격증명 없이 200 — `test_auth_off_protected_route_open`.
- 전체 360 테스트 green → 미들웨어가 비활성 단일 분기 pass-through임을 회귀로 입증. 공개 API 계약 변경 0.

## 공개경로 우회 확인 (FR-04/AC7)

- auth on에서도 `/healthz`, `/`, `/openapi.json`은 자격증명 없이 200 — `test_auth_on_public_paths_open`(parametrize). `PUBLIC_PATHS` 단일 원천으로 판정.

## 런타임 감사 로그 증거 (auth ON 스모크, 2026-06-02)

`API_AUTH_ENABLED=true` + 키/토큰 주입 후 TestClient로 실제 요청을 보내 감사 로거 출력을 육안 확인했다. 모든 라인에 `rid`(request_id)가 채워지고, 비밀값은 마스킹(`****` + 끝 4자)만 노출된다.

```
[AUDIT] DENY  | rid=4292472f ip=testclient GET /items | principal=-               method=-       reason=missing_credentials status=401
[AUDIT] DENY  | rid=a407fdd1 ip=testclient GET /items | principal=-               method=-       reason=invalid_credentials status=401
[AUDIT] GRANT | rid=6caba59b ip=testclient GET /items | principal=apikey:****1234 method=api_key reason=-                  status=200
[AUDIT] GRANT | rid=cdfdc7d6 ip=testclient GET /items | principal=bearer:****abcd method=bearer  reason=-                  status=200
# GET /healthz (public) → 200, 감사 로그 없음 (의도)
# 401 응답: WWW-Authenticate=Bearer, body={"detail":"Unauthorized"}
```

- 원문 키 `secret-key-1234` / 토큰 `bearer-tok-abcd`는 로그 어디에도 등장하지 않음 (마스킹 `****1234` / `****abcd`만).
- missing vs invalid 사유는 감사 로그에만 구분 기록, 응답 body는 일반화된 `Unauthorized`.
- 공개경로(`/healthz`)는 인증 스킵 → 감사 로그 무발생(노이즈 억제 설계 §3 부합).

## 판정

**PASS** — 신규 33 + 회귀 360 green, ruff 0 errors, import smoke OK. 보안/호환/공개경로 계약 모두 충족, 런타임 감사 로그 증거 확보, 회귀·결함 0.
