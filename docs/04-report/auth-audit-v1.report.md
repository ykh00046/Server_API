# auth-audit-v1 Completion Report

> **Summary**: API-Key / Bearer 토큰 기반 **인증 미들웨어 + 접근 감사 로그**를
> opt-in(기본 OFF)으로 도입. 순수 인증 로직(`shared/auth.py`)과 감사 기록(`api/_audit.py`)을
> 분리하고 `api/main.py`에 미들웨어 1개를 추가해, 기존 공개 동작을 100% 보존하면서
> 보안 baseline(상수시간 비교·비밀값 마스킹·공개경로 SSOT)을 확보했다.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-02
> **Match Rate**: 100% (12/12 AC PASS)
> **Status**: Completed
> **Iterations**: 0 (1차 구현이 설계와 100% 일치 — Act/iterate 불필요)

---

## 1. 변경 요약

| 변경 | 파일 | 효과 |
|------|------|------|
| 순수 인증 로직 신규 | `shared/auth.py` (신규) | 자격증명 추출·검증·공개경로 판정, 프레임워크 비의존, 상수시간 비교 |
| 감사 로그 신규 | `api/_audit.py` (신규) | 전용 `audit` logger, grant/deny 구조화 1줄, principal 마스킹 |
| 인증 설정 | `shared/config.py` (수정) | `API_AUTH_ENABLED`(기본 false)·`API_KEYS`·`API_BEARER_TOKENS` |
| export | `shared/__init__.py` (수정) | auth 공개 심볼 7종 |
| 미들웨어 등록 | `api/main.py` (수정) | `auth_and_audit` 미들웨어 + 설정누락 startup 경고 |
| 설정 예시 | `.env.example` (수정) | opt-in 사용법 주석 |
| 테스트 신규 | `tests/test_auth.py`(23) + `tests/test_audit.py`(10) | 순수 로직 결정표 + 미들웨어/감사 통합 |

## 2. 핵심 설계 결정

- **opt-in / fail-safe 기본값**: `API_AUTH_ENABLED` 기본 false → 미설정 환경(dev/CI/기존 테스트)은 pass-through. 운영 활성화는 `.env` 한 줄. "기존 동작 유지" 요구를 구조적으로 보장.
- **순수 로직 ↔ 프레임워크 경계 분리**: `authenticate(headers, settings)`는 `Mapping`만 입력 → TestClient 없이 단위 테스트. 미들웨어는 얇은 어댑터.
- **단일 진실원천(SSOT)**: 공개경로는 `shared.auth.PUBLIC_PATHS` 하나로 관리.
- **shadowing 회피**([[feedback_default_shadowing]]): `load_auth_settings()`가 호출 시점에 config를 읽어 monkeypatch/런타임 변경이 즉시 반영.
- **보안**: `secrets.compare_digest` 상수시간 비교, 401 사유 미노출(감사 로그에만), principal 마스킹(`****1234`).
- **미들웨어 순서**(Starlette LIFO): request_id/rate-limit를 outermost로 유지 → 인증이 inner → 감사 로그가 `get_request_id()`를 안전히 참조.

## 3. 검증 결과 (QA)

- ✅ 신규 인증/감사 테스트: `pytest tests/test_auth.py tests/test_audit.py -q` → **33 passed**
- ✅ 전체 회귀(auth off 기본): `pytest -q` → **360 passed**, 회귀 0
- ✅ ruff 게이트(F,BLE001,I,UP,B904): **All checks passed** (0 errors)
- ✅ import smoke: `shared.auth`, `api._audit`, `api.main` OK
- ✅ 보안 계약: 원문 키 미로그 + 마스킹값 포함 동시 단언, auth off 감사 무소음

## 4. PDCA 메타데이터

- **Plan**: `docs/01-plan/features/auth-audit-v1.plan.md`
- **Design**: `docs/02-design/features/auth-audit-v1.design.md`
- **Analysis**: `docs/03-analysis/auth-audit-v1.analysis.md` (Match Rate 100%)
- **QA**: `docs/05-qa/auth-audit-v1.qa.md` (PASS)
- **Iteration**: 0회 — 1차 구현이 AC 12/12 충족, gap 0.

## 5. 설계 대비 의도된 강화 (차이 아님, 기록용)

| 항목 | 위치 | 비고 |
|---|---|---|
| CORS preflight pass-through | `main.py` `OPTIONS` 분기 | preflight는 자격증명 미동반 → 401 방지(긍정적) |
| 빈 Bearer 정규화 | `auth.py` `[7:].strip() or None` | `Bearer ` → None, 테스트 커버 |
| 401에 `X-Request-ID` 동봉 | `main.py` 401 응답 헤더 | 거부 응답도 추적 가능 |

## 6. 후속 작업 (Deferred / Non-Goals)

| 항목 | 비고 |
|------|------|
| `auth-rbac-v2` | per-route 스코프/역할 기반 인가 |
| `auth-token-issuer-v1` | JWT 발급·서명·만료·refresh |
| 키 DB 저장·회전, 해싱 | 현재는 env 평문 셋 + 상수시간 비교 |
| rate-limit 스킵 목록 정렬 | `add_request_id_and_rate_limit`의 스킵 리스트에 `/redoc` 추가 시 `PUBLIC_PATHS`와 완전 정렬(인증 동작엔 영향 없음) |
| principal 단위 rate limiting | 현 IP 기반 유지 |

## 7. 운영 활성화 절차

```
# .env
API_AUTH_ENABLED=true
API_KEYS=key1,key2            # 또는/그리고
API_BEARER_TOKENS=tokA,tokB
```
→ 재기동. 키 미설정 시 startup 경고 로그로 fail-closed(전 라우트 401) 가시화.
