# R5-ruff-b904-ramp — QA

> **PDCA Phase**: QA (Zero-Script / 게이트·회귀 기반)
> **Date**: 2026-06-01
> **Design**: [[R5-ruff-b904-ramp.design]]

## QA 전략

B904는 런타임 동작을 바꾸지 않고 예외 `__cause__` 메타데이터만 명시화한다. 따라서 QA는 **(a) 정적 게이트 + (b) 기존 회귀 스위트**로 충분하며 별도 신규 테스트는 불필요(발생 예외 타입·status·detail이 불변이므로 기존 검증 테스트가 그대로 계약을 보증).

## 실행 결과

| # | 검사 | 명령 | 결과 |
|---|---|---|:---:|
| Q1 | 전체 게이트 | `ruff check . --select F,BLE001,I,UP,B904` | ✅ All checks passed (0 errors) |
| Q2 | B904 잔여 | `ruff check . --select B904` | ✅ All checks passed (0건) |
| Q3 | import smoke | `python -c "import api._http_helpers, api.routers.notifications, shared.validators"` | ✅ import OK |
| Q4 | 검증 경로 집중 | `pytest test_input_validation test_notifications test_sql_validation` | ✅ 71 passed |
| Q5 | 전체 회귀 | `pytest -q` | ✅ 324 passed, 0 failed, flaky 0 |

## 계약 불변 확인 (AC6)

- `_http_helpers.py`: `detail` 문자열 변경 없음 — `from e`만 추가. 400 status 불변.
- `notifications.py`: `detail=str(e)` 동일. create/update webhook 400 경로 테스트 green.
- `validators.py`: `from None`(date)·`from e`(path) — raise 메시지 텍스트 불변.
- → 사용자 대면 응답(HTTP body/status)은 **바이트 단위 동일**, 변경된 것은 트레이스백의 `__cause__` 표현뿐.

## 판정

**PASS** — 게이트 green, 회귀 324 passed, 계약 불변. 회귀·결함 0.
