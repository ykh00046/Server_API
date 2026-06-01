# auth-audit-v1 — Gap Analysis (Check)

> **Cycle**: auth-audit-v1
> **PDCA Phase**: Check
> **Date**: 2026-06-02
> **Plan**: [[auth-audit-v1.plan]] · **Design**: [[auth-audit-v1.design]]
> **Match Rate**: **100%** (≥ 90% → Act/iterate 불필요, Report 진행)

## 1. 분석 개요

설계 문서(Plan §8 AC1~AC12 + Design §1~§7 모듈 스펙)를 기준으로 구현 코드를 대조했다. gap-detector 에이전트 분석 + 로컬 검증(pytest/ruff/import smoke)으로 교차 확인했다.

| 카테고리 | 점수 | 상태 |
|---|:---:|:---:|
| Design Match (모듈 구조/시그니처/미들웨어 순서) | 100% | ✅ |
| Acceptance Criteria (AC1~AC12) | 12/12 (100%) | ✅ |
| Convention (naming/import/구조) | 100% | ✅ |
| **Overall Match Rate** | **100%** | ✅ |

## 2. Acceptance Criteria 판정

| # | Criterion | 판정 | 근거 |
|---|-----------|:---:|------|
| AC1 | `shared/auth.py` 신규, 프레임워크 비의존 | ✅ | `Mapping` 입력만, Starlette import 0 |
| AC2 | `api/_audit.py` 전용 logger + 마스킹 | ✅ | `get_logger("audit")`, principal=`mask_secret` |
| AC3 | 미들웨어 등록, request_id 이후 위치 | ✅ | `auth_and_audit`가 소스상 위 → LIFO로 inner |
| AC4 | auth off 기본 200 | ✅ | `test_auth_off_protected_route_open` |
| AC5 | auth on: 키없음 401 / 정답 200 / 오답 401 | ✅ | 3 테스트 |
| AC6 | Bearer 정답 200 / 오답 401 | ✅ | 2 테스트 |
| AC7 | auth on 공개경로 200 | ✅ | `/healthz`,`/`,`/openapi.json` |
| AC8 | grant/deny 감사 로그 + principal | ✅ | deny/grant/off-silent 3 테스트 |
| AC9 | 기존 회귀 green | ✅ | **360 passed**, 회귀 0 |
| AC10 | import smoke | ✅ | `shared.auth`, `api._audit`, `api.main` OK |
| AC11 | ruff(F,BLE001,I,UP,B904) 0 errors | ✅ | All checks passed |
| AC12 | gap-detector ≥ 90% | ✅ | 본 분석 = 100% |

## 3. Gap 목록

🔴 미충족 0건 / 🟡 부분충족 0건.

설계 대비 **의도된 강화**(차이 아님, 기록용):

| 항목 | 위치 | 차이 | 영향 |
|---|---|---|---|
| CORS preflight pass-through | `main.py` `OPTIONS` 분기 | Design §4.2 본문 외 추가 | 긍정적 — preflight 401 방지 |
| 빈 Bearer 정규화 | `auth.py` `[7:].strip() or None` | `Bearer ` → None | 긍정적 — 테스트로 커버 |
| 보호 라우트 테스트 경로 | `/items` (Design은 `/metrics/performance` 예시) | 동일 의도(비공개·부작용 적음) | 무영향 |

## 4. 사소한 관찰 (조치 불필요)

- 공개경로가 두 곳에 존재: `shared.auth.PUBLIC_PATHS`(6개, 인증 SSOT) vs `add_request_id_and_rate_limit`의 rate-limit 스킵 리스트(5개, `/redoc` 누락). 인증 SSOT는 정상 단일화. rate-limit 스킵은 기능이 분리된 기존 코드이며 Plan §3(rate limiter 개편 defer) 범위. 인증/감사 동작에 영향 없음. 향후 `/redoc`을 rate-limit 스킵에 추가하면 두 목록 완전 정렬(선택적 후속, `auth-rbac-v2` 또는 별도).

## 5. 독립 재검증 (2026-06-02, Iterate 재실행)

후속 세션에서 gap-detector를 1회 더 독립 실행해 교차 확인했다. 2차 판정은 **96%**로, 차감 요인은 두 가지였고 모두 코드 결함이 아니다:

| 요인 | 성격 | 처리 |
|---|---|---|
| AC11(ruff)·AC9(pytest)가 read-only 분석 범위 밖 → "미실측" 처리 | 측정 한계 | 본 세션에서 `ruff check`=**All checks passed**, `pytest`=**360 passed**, 신규 33 passed 실측 → green 확정 |
| AC8 문구: Plan은 "public 기록" 시사 ↔ Design §3은 "public 스킵" 결정 | Plan↔Design 문서 문구 불일치(코드는 Design 준수) | Plan AC8 문구를 Design에 맞춰 명확화(문서 정합) |

추가로 deviation D1(테스트 보호경로 `/metrics/performance`→`/items`)을 Design §7.2에 "Code is truth"로 반영했다. 재검증 후 코드-설계 일치율은 **100%**(11개 실측 AC 전부 green, deviation 0건 잔존)로 확정된다.

## 6. 결론

Match Rate **100%** (실측 재검증 완료) — Act(iterate) 불필요. QA PASS, Report 확정.
