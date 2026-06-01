# R5-ruff-b904-ramp — Plan

> **Cycle**: R5-ruff-b904-ramp
> **PDCA Phase**: Plan
> **Date**: 2026-06-01
> **Predecessors**: [[R4-import-pyupgrade-ramp]] §8.1에서 예고한 "R5: `B904`(raise from) enforce"
> **Round**: R5 (lint ramp 2단계 — 예외 체이닝 의미 보강)

## 1. Background

R4에서 ruff 게이트를 `F`/`BLE001`/`I`/`UP`로 확장하고 183+19건의 기계적 변환을 적용했다. R4 보고서는 잔여 ramp 후보로 `B`(flake8-bugbear)·`SIM`·`E501`을 남겼고, 그중 **`B904`(raise-without-from)를 R5 1순위**로 지정했다.

`B904`는 단순 포매팅이 아니라 **예외 인과관계(causal chain)를 코드에 명시**하게 하는 규칙이다. `except` 블록 안에서 `raise NewError(...)`만 하면 Python은 암묵적으로 원본을 `__context__`에 매단다(`During handling of the above exception, another exception occurred`). 명시적 `raise ... from err`(→ `__cause__`) 또는 `raise ... from None`(원인 억제)을 쓰면 **의도가 코드에 드러나고**, 트레이스백이 "이건 핸들링 중 버그"가 아니라 "이건 의도된 변환"임을 정확히 표현한다.

### 측정된 현황 (2026-06-01, in-scope dirs, webcloring-pdf 제외)

명령: `python -m ruff check . --select B904`

| 파일 | 라인 | except 변수 | 변환 방향 |
|---|---|---|---|
| `api/_http_helpers.py` | 31 | 없음 (`except ValueError:`) | `ValueError` → `HTTPException(400)` |
| `api/_http_helpers.py` | 44 | `as e` | `ValueError` → `HTTPException(400)` |
| `api/_http_helpers.py` | 52 | `as e` | `ValueError` → `HTTPException(400)` |
| `api/routers/notifications.py` | 70 | `as e` | `ValueError` → `HTTPException(400)` |
| `api/routers/notifications.py` | 98 | `as e` | `ValueError` → `HTTPException(400)` |
| `shared/validators.py` | 32 | 없음 (`except ValueError:`) | `ValueError` → `ValueError`(친절 메시지 재포장) |
| `shared/validators.py` | 164 | `as e` | `(OSError, RuntimeError)` → `ValueError` (메시지에 `{e}` 사용) |

**합계: 7건.** 모두 `tests/**` 밖(런타임 코드)이며, **전부 "검증 실패를 사용자 친화적 에러로 변환하는 경계"** 라는 공통 성격을 가진다. autofix 불가(`B904`는 `from` 대상을 사람이 골라야 하므로 ruff가 자동수정을 제공하지 않음) → **수동 변환 + 의미 검증 필수**.

> **Note**: 사용자가 언급한 "잔여 158건"은 R4 보고서의 전체 미적용 ramp 후보 총량(B/SIM/E501 등 합산)이며, 그중 **B904는 7건**이다. R5 범위는 B904 7건으로 한정한다(나머지는 R6+로 연기, §3).

## 2. Goal

1. **7건 수동 변환** — 각 raise에 의미에 맞는 `from err` / `from None`을 명시(정책은 Design §에서 확정).
2. **게이트 확장** — `pyproject.toml`의 `select`에 `B904` 추가 (`F`,`BLE001`,`I`,`UP` 유지). `B` 전체가 아니라 **`B904` 단일 규칙만** 편입(나머지 B는 R6).
3. **회귀 0** — pytest 기존 green 유지, import smoke 통과, 게이트 전체 0 errors.
4. **동작 보존** — 변환은 예외 **체이닝 메타데이터(`__cause__`)만** 바꾼다. 발생하는 예외 타입·status code·detail 메시지는 불변 → API 계약/테스트 영향 0.

## 3. Non-Goals (defer)

- **`B` 전체 enforce** — `B008`(FastAPI `Depends()` 기본인자), `B905`(zip strict), `B007`(unused loop var) 등은 별도 검토/수정 필요 → **R6**.
- **`SIM`(105/102/108/117)** — 가독성 정리, 제어흐름 변경 동반 → **R6/R7**.
- **`E501` line-too-long** — 포매팅 정책 결정 필요 → 별도.
- **`ruff format` 도입 / CI 연결** — 별도 결정(R4와 동일 보류).

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Tool | `ruff` | ✅ R3 도입 |
| Tool | `pytest` | ✅ |
| 신규 외부 런타임 의존성 | — | **0** |
| 런타임/스키마/공개 API 변경 | — | **0** (예외 `__cause__` 메타데이터만 변경) |

## 5. Scope (대상)

| 구분 | 대상 |
|---|---|
| **수정 파일** | `api/_http_helpers.py`, `api/routers/notifications.py`, `shared/validators.py` |
| **게이트 적용(enforce)** | `api/`, `shared/`, `dashboard/`, `tools/`, `scripts/`, `manager.py`, `tests/` (R4와 동일) |
| **enforce 규칙(추가)** | `B904` (기존 `F`,`BLE001`,`I`,`UP` 유지) |
| **전체 제외(exclude)** | `webcloring-pdf/`, `.venv*`, `.smoke-venv*`, `dist/`, `build/`, `docs/`, `logs/`, `.pytest_tmp/` (R3/R4 동일) |

## 6. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `pyproject.toml` select에 `B904` 추가, 의도 주석(B 단일 규칙 편입 사유) 기재 | 파일 검사 |
| AC2 | `python -m ruff check . --select F,BLE001,I,UP,B904` → **0 errors** | shell |
| AC3 | 7건 전부 `from err` 또는 `from None` 명시, 정책표(Design)와 1:1 일치 | diff + 보고서 |
| AC4 | import smoke 통과 (`api._http_helpers`, `api.routers.notifications`, `shared.validators`) | python -c import |
| AC5 | 기존 pytest 회귀 green (R4 기준, 알려진 flaky 제외) | pytest 실행 |
| AC6 | 발생 예외 타입·status·detail 불변 — 기존 검증 테스트(`test_input_validation`, `test_notifications`, `test_sql_validation`) green | pytest |
| AC7 | 적용 후 잔여 ramp 후보(B 나머지/SIM/E501) 통계 재기록 | 보고서 |
| AC8 | gap-detector match rate ≥ 90% | Check phase |

## 7. Constraints / Risks

- **`from None` 오용 위험**: 원인을 억제(`from None`)하면 디버깅 정보가 사라진다. → **순수 동일타입 재포장(원본이 노이즈)인 경우에만** `from None`, 그 외는 `from err`로 원인 보존(정책 Design §1).
- **`except`에 변수 없는 케이스**(`_http_helpers.py:31`, `validators.py:32`): `from err`를 쓰려면 `as exc` 추가 필요. 변수명은 기존 코드 관례(`e`)와 신규 도입 시 `exc` 중 **파일 내 일관성** 우선.
- **소규모 diff(3파일/7곳)**: 회귀 위험 낮음. 커밋은 [[feedback_commit_style]]에 따라 **(a) 코드 변환, (b) 게이트 설정** 2계층 분리.
- **테스트가 `__cause__`를 검사하지 않음**: 기존 테스트는 status/detail만 본다 → 변환이 테스트를 깨지 않음(오히려 안전). 단 message 텍스트 불변을 AC6로 확인.

## 8. Out-of-band Notes

- **연쇄 사이클 예고**:
  - R6: `B` 나머지(008/905/007 등) + `SIM` 가독성 정리
  - E501 / `ruff format`: 포매팅 정책 결정 후 별도
  - CI: `ruff check . --select F,BLE001,I,UP,B904` 게이트를 GitHub Actions에 연결(별도)
- **게이트 명령(확정 예정)**: `python -m ruff check . --select F,BLE001,I,UP,B904`
- **메모리 참조**: [[project_lint_ramp_r3_r4]], [[project_except_refactor_r2]], [[feedback_commit_style]]
