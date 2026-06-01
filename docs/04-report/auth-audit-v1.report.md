# auth-audit-v1 완료 보고서

> **요약**: API-Key / Bearer 토큰 기반 **인증 미들웨어 + 접근 감사 로그**를
> opt-in(기본 OFF)으로 도입. 순수 인증 로직(`shared/auth.py`)과 감사 기록(`api/_audit.py`)을
> 분리하고 `api/main.py`에 미들웨어 1개를 추가해, 기존 공개 동작을 100% 보존하면서
> 보안 baseline(상수시간 비교·비밀값 마스킹·공개경로 SSOT)을 확보했다.
>
> **프로젝트**: Server_API (Production Data Hub)
> **날짜**: 2026-06-02
> **설계 일치도**: 100% (12/12 AC 충족)
> **상태**: 완료
> **반복 회차**: 0회 (1차 구현이 설계와 100% 일치 — 추가 작업 불필요)

---

## 1. 변경 요약

| 변경 사항 | 파일 | 효과 |
|---------|------|------|
| 순수 인증 로직 신규 | `shared/auth.py` (신규) | 자격증명 추출·검증·공개경로 판정, 프레임워크 비의존, 상수시간 비교 |
| 감사 로그 신규 | `api/_audit.py` (신규) | 전용 `audit` logger, grant/deny 구조화 1줄, principal 마스킹 |
| 인증 설정 | `shared/config.py` (수정) | `API_AUTH_ENABLED`(기본 false)·`API_KEYS`·`API_BEARER_TOKENS` |
| export | `shared/__init__.py` (수정) | auth 공개 심볼 (AuthSettings, authenticate, load_auth_settings, mask_secret 등) |
| 미들웨어 등록 | `api/main.py` (수정) | `auth_and_audit` 미들웨어 + 설정누락 startup 경고 |
| 설정 예시 | `.env.example` (수정) | opt-in 사용법 주석 |
| 테스트 신규 | `tests/test_auth.py`(23) + `tests/test_audit.py`(10) | 순수 로직 결정표 + 미들웨어/감사 통합 |

---

## 2. 핵심 설계 결정

### 2.1 opt-in 정책 (fail-safe 기본값)
- `API_AUTH_ENABLED` 기본값 **false**
- 미설정 환경(dev/CI/기존 테스트)은 pass-through 유지 → "기존 동작 100% 보존" 보장
- 운영 활성화는 `.env` 한 줄

### 2.2 순수 로직 ↔ 프레임워크 경계 분리
- `authenticate(headers, settings)`는 `Mapping`만 입력 → TestClient 없이 단위 테스트 가능
- 미들웨어(`api/main.py`)는 얇은 어댑터만 담당

### 2.3 단일 진실원천(SSOT)
- 공개경로는 `shared.auth.PUBLIC_PATHS` 하나로 관리
- 중복 정의/불일치 위험 제거

### 2.4 shadowing 회피
- `load_auth_settings()`가 **호출 시점에** config를 읽음 → monkeypatch/런타임 변경이 즉시 반영
- 참고: [[feedback_default_shadowing]]

### 2.5 보안 기본사항
- `secrets.compare_digest` 상수시간 비교 → timing attack 방지
- 401 사유 미노출(감사 로그에만 기록)
- principal 마스킹(`apikey:****1234`, `bearer:****abcd`)

### 2.6 미들웨어 순서 (Starlette LIFO)
- request_id/rate-limit를 outermost로 유지
- 인증은 inner → 감사 로그가 `get_request_id()`를 안전히 참조
- 요청 흐름: request_id(outer) → rate-limit → auth(inner) → route

---

## 3. 검증 결과 (QA)

### 3.1 신규 테스트
```
pytest tests/test_auth.py tests/test_audit.py -q
→ 33 passed (순수 로직 23 + 미들웨어 통합 10)
```

### 3.2 회귀 테스트
```
pytest -q (auth off 기본값)
→ 360 passed, 회귀 0 (기존 동작 100% 보존 검증)
```

### 3.3 품질 게이트
```
ruff check (F,BLE001,I,UP,B904): All checks passed (0 errors)
import smoke: shared.auth, api._audit, api.main OK
```

### 3.4 보안 계약
- ✅ 원문 키 미로그 (test_audit_grant_logged_and_no_raw_secret)
- ✅ 마스킹값 포함 확인 (****1234 등)
- ✅ auth off 감사 무소음 (test_audit_off_produces_no_audit_log)

---

## 4. PDCA 메타데이터

| 단계 | 문서 | 상태 |
|------|------|------|
| Plan | `docs/01-plan/features/auth-audit-v1.plan.md` | ✅ 확정 |
| Design | `docs/02-design/features/auth-audit-v1.design.md` | ✅ 확정 |
| Do | 구현 완료 (shared/auth.py, api/_audit.py 등) | ✅ 완료 |
| Check | `docs/03-analysis/auth-audit-v1.analysis.md` (일치도 100%) | ✅ 완료 |
| Act | 본 보고서 | ✅ 완료 |

**반복 회차**: 0회 — 1차 구현이 AC 12/12 충족, gap 0.

---

## 5. 승인 기준(AC) 검증

| AC | 기준 | 상태 | 근거 |
|----|------|:---:|------|
| AC1 | `shared/auth.py` 신규 — 프레임워크 비의존 | ✅ | Starlette import 0 |
| AC2 | `api/_audit.py` 전용 logger + 마스킹 | ✅ | get_logger("audit"), mask_secret() |
| AC3 | 미들웨어 등록, request_id 이후 위치 | ✅ | LIFO 순서: auth_and_audit이 소스상 위 = inner |
| AC4 | auth off 기본 → 보호 라우트 자격증명 없이 200 | ✅ | test_auth_off_protected_route_open |
| AC5 | auth on + 키 없음 401 / 정답 200 / 틀린 키 401 | ✅ | 3개 테스트 |
| AC6 | Bearer 정답 200 / 오답 401 | ✅ | 2개 테스트 |
| AC7 | auth on도 공개경로 200 | ✅ | /healthz, /docs, /openapi.json 3건 |
| AC8 | grant/deny 감사 로그 + principal | ✅ | test_audit_grant_logged_and_no_raw_secret |
| AC9 | 기존 pytest 회귀 green | ✅ | 360 passed |
| AC10 | import smoke | ✅ | OK |
| AC11 | ruff(F,BLE001,I,UP,B904) 0 errors | ✅ | All checks passed |
| AC12 | gap-detector ≥ 90% | ✅ | 100% (분석.md 참조) |

---

## 6. 설계 대비 의도된 강화 (차이 아님, 기록용)

| 항목 | 위치 | 비고 |
|-----|------|------|
| CORS preflight pass-through | `main.py` `OPTIONS` 분기 | preflight는 자격증명 미동반 → 401 방지(긍정적 보완) |
| 빈 Bearer 정규화 | `auth.py` `[7:].strip() or None` | `Bearer ` 빈 값 → None으로 정규화, 테스트 커버 |
| 401에 X-Request-ID 동봉 | `main.py` 401 응답 헤더 | 거부 응답도 추적 가능(운영성 향상) |

---

## 7. 라이브 QA 검증 (수동 테스트)

| 시나리오 | 결과 | 확인 |
|---------|------|------|
| auth OFF (기본): GET `/metrics/performance` | 200 | 기존 동작 보존 |
| auth ON: 자격증명 없음 | 401 + WWW-Authenticate:Bearer | 표준 HTTP 응답 |
| auth ON: 틀린 `X-API-Key: wrong` | 401 | 검증 작동 |
| auth ON: 올바른 `X-API-Key: secret-key-1234` | 200 | 인증 성공 |
| auth ON: 올바른 `Authorization: Bearer bearer-tok-abcd` | 200 | Bearer 인증 성공 |
| auth ON: GET `/healthz` (공개경로) | 200 | 공개경로 제외 동작 |
| auth ON: OPTIONS preflight(CORS) | 200 | CORS 미보호(preflight 통과) |
| 감사 로그 (DENY) | `[AUDIT] DENY \| reason=missing_credentials` | 거부 기록 |
| 감사 로그 (GRANT) | `[AUDIT] GRANT \| principal=apikey:****1234` | 허용 기록 + 마스킹 |
| 감사 로그 (auth OFF) | (기록 없음) | 무소음(auth_disabled no-op) |
| startup 경고 | `[Auth] API_AUTH_ENABLED=true but no API_KEYS/API_BEARER_TOKENS set` | 설정 누락 감지 |

---

## 8. 완료된 작업 상세

### 8.1 신규 모듈

#### shared/auth.py (173줄)
- `PUBLIC_PATHS` SSOT (6개 공개 경로)
- `extract_credentials()` — X-API-Key / Authorization: Bearer 파싱
- `_matches_any()` — 상수시간 비교 (secrets.compare_digest)
- `authenticate()` — 인증 결정 로직
- `load_auth_settings()` — 런타임 config 조회
- `mask_secret()` — principal 마스킹

#### api/_audit.py (51줄)
- `audit_logger` 전용 logger
- `record_auth_event()` — 구조화된 감사 로그 기록
- auth_disabled 시 no-op (로그 노이즈 억제)

### 8.2 수정 파일

#### shared/config.py
- `API_AUTH_ENABLED` (기본: false)
- `API_KEYS` (env 리스트)
- `API_BEARER_TOKENS` (env 리스트)

#### api/main.py
- `auth_and_audit()` 미들웨어 추가
- request_id 미들웨어 보다 위(소스상) 배치 = inner
- startup 경고: API_AUTH_ENABLED=true + 키 미설정 시 경고

#### shared/__init__.py
- 공개 심볼 export

#### .env.example
- 3개 설정 예시 및 주석

### 8.3 테스트 신규

#### tests/test_auth.py (150줄, 23개 케이스)
- is_public_path: 2개
- extract_credentials: 6개
- mask_secret: 4개
- authenticate decision table: 11개

#### tests/test_audit.py (104줄, 10개 케이스)
- auth off (기본): 1개
- auth on (401): 3개
- auth on (200): 2개
- 공개경로: 1개
- 감사 로그: 2개
- auth off 무음: 1개

---

## 9. 학습 및 회고

### 9.1 잘된 점 (Keep)

1. **프레임워크 비의존 설계**
   - `shared/auth.py`의 순수 함수 설계로 TestClient 없이도 테스트 가능
   - 빠른 피드백 루프, 높은 테스트 커버리지 달성

2. **SSOT 원칙 적용**
   - 공개경로를 `PUBLIC_PATHS` 하나로 관리 → 불일치 위험 0

3. **opt-in 정책의 현명한 기본값**
   - `API_AUTH_ENABLED=false` → 빌드/배포/테스트 프로세스 변경 0
   - 기존 테스트 360개 전부 green 유지

4. **설계-구현 일치도 100% 달성**
   - Design 문서가 명확 → 구현이 일탈 없이 따름
   - gap-detector 100% → 재작업 0

5. **보안 기본사항 강화**
   - timing attack 방어 (상수시간 비교)
   - 민감정보 비로그 (마스킹)
   - 공개경로 화이트리스트

### 9.2 개선할 점 (Problem)

1. **공개경로 목록의 부분적 중복**
   - `shared.auth.PUBLIC_PATHS` (6개): "/", "/healthz", "/healthz/ai", "/docs", "/redoc", "/openapi.json"
   - `add_request_id_and_rate_limit`의 rate-limit 스킵 리스트 (5개): "/redoc" 누락
   - **영향**: 인증 기능엔 0 (auth가 /redoc을 공개경로로 취급), rate-limit 스킵 일관성만 미미
   - **개선 시기**: 향후 rate-limit 리팩토링 또는 별도 작업

2. **승인 기준 정의의 명확성**
   - AC를 처음부터 더 세분화했으면(예: "audit 로그에 request_id 필드 존재") 개발 중 체크리스트 활용도 더 높았을 것
   - **개선 방법**: Plan 초안에서 AC를 구현 전 더 구체화

### 9.3 다음 번에 시도할 점 (Try)

1. **PDCA 문서 순차성 엄격화**
   - Plan → Design → Do → Check → Act 각 단계 완료 시 공식 승인 게이트 도입
   - 이번엔 Design이 충분해서 구현이 매끄러웠으므로, 같은 패턴을 의식적으로 강화

2. **gap-detector 활용도 증대**
   - Do 단계 중간에 코드 스냅샷으로 조기 gap 확인
   - 이번 분석 결과 100% 일치 = 재작업 0이므로, 같은 결과를 다른 사이클에도 확대

3. **커밋 메시지에 AC 참조 추가**
   - 예: `feat(auth): shared/auth.py (fulfills AC1, AC2, AC3)`
   - 추적성 향상

4. **테스트-주도 개발(TDD) 검토**
   - 이번엔 설계 → 구현 → 테스트 순서
   - 복잡한 사이클에선 테스트를 먼저 작성하는 것도 고려

---

## 10. 미해결 / 연기 항목

🟢 **없음**. 모든 AC 충족, 설계 100% 구현.

**선택적 후속 (우선도 낮음)**:

| 항목 | 사유 | 처리 |
|------|------|------|
| rate-limit 스킵 리스트에 `/redoc` 추가 | `PUBLIC_PATHS`와 정렬 (비기능) | 향후 `auth-rbac-v2` 또는 별도 |
| startup 경고를 app 이벤트 핸들러로 이동 | 서버 기동 로그 가시성 증대 (미니) | 선택적 |

---

## 11. 후속 작업 (Deferred / Non-Goals)

| 항목 | 설명 | 예상 난도 |
|------|------|---------|
| `auth-rbac-v2` | per-route 스코프/역할 기반 인가 | High |
| `auth-token-issuer-v1` | JWT 발급·서명·만료·refresh | High |
| `auth-key-rotation-v1` | 키 DB 저장·해싱·만료·자동 교체 | Medium |
| `rate-limit-principal-v1` | principal 단위 rate limiting (IP → apikey) | Medium |
| rate-limit 스킵 정렬 | `add_request_id_and_rate_limit`의 스킵 리스트에 `/redoc` 추가 | Low |

---

## 12. 운영 활성화 절차

### 기본 (auth OFF — 현재)
```bash
# .env (생략 또는 기본값)
API_AUTH_ENABLED=false
API_KEYS=
API_BEARER_TOKENS=
```
→ 모든 엔드포인트 공개. 기존 동작 유지.

### 운영 (auth ON)
```bash
# .env
API_AUTH_ENABLED=true
API_KEYS=key1,key2,key3
API_BEARER_TOKENS=token-abc,token-xyz
```
→ 서버 재기동.

### 주의: 설정 누락
```
API_AUTH_ENABLED=true
API_KEYS=          # 미설정
API_BEARER_TOKENS= # 미설정
```
→ **startup 경고 발화**: `[Auth] API_AUTH_ENABLED=true but no API_KEYS/API_BEARER_TOKENS set — all protected routes will 401`
→ fail-closed: 모든 보호 라우트 401 (의도된 보안 동작, 설정 오류 감지)

---

## 13. Changelog

### v1.0.0 (2026-06-02)

**Added:**
- `shared/auth.py` — API-Key/Bearer 자격증명 검증 (PUBLIC_PATHS SSOT, extract_credentials, authenticate, mask_secret, load_auth_settings)
- `api/_audit.py` — 구조화된 감사 로그 (grant/deny 구분, principal 마스킹, auth_disabled no-op)
- `tests/test_auth.py` — 순수 인증 로직 단위 테스트 23개 (경로 판정, 자격증명 추출, 마스킹, 인증 결정표)
- `tests/test_audit.py` — 미들웨어 통합 테스트 10개 (401/200, 감사 로그, 비밀 마스킹, auth off 무음)
- `api/main.py` — `auth_and_audit` 미들웨어 (request_id 후 inner, OPTIONS/공개경로 pass-through, startup 경고)
- `shared/config.py` — 3개 인증 설정 상수 (`API_AUTH_ENABLED`, `API_KEYS`, `API_BEARER_TOKENS`) + startup 경고
- `.env.example` — opt-in 활성화 사용법 주석

**Changed:**
- `shared/__init__.py` — auth 심볼 export

**Fixed:**
- (없음 — 신규 기능)

---

## 14. 버전 이력

| 버전 | 날짜 | 변경사항 | 작성자 |
|------|------|---------|--------|
| 1.0 | 2026-06-02 | 완료 보고서 작성, AC 12/12 충족, gap-detector 100%, pytest 360 green | interojo |

---

End of Report.
