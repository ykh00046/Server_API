# R4-import-pyupgrade-ramp — Plan

> **Cycle**: R4-import-pyupgrade-ramp
> **PDCA Phase**: Plan
> **Date**: 2026-06-01
> **Predecessors**: [[R3-ruff-ble001-coverage]] 보고서에서 예고한 "R4: ruff ramp — I(import정렬) → UP(pyupgrade) → B904 → SIM 단계적 enforce"
> **Round**: R4 (lint ramp 1단계 — 자동수정 안전군)

## 1. Background

R3에서 ruff `F`/`BLE001`을 정적 게이트로 고정하고, 향후 ramp 후보 **360 findings(191 auto-fixable)** 를 baseline으로 기록했다. R4는 그 부채 중 **위험이 가장 낮고 자동수정이 안전한 두 규칙군** — `I`(import 정렬)와 `UP`(pyupgrade) — 을 게이트에 편입한다.

이 두 규칙군을 1순위로 고른 이유:

| 규칙군 | 성격 | 런타임 영향 | 자동수정 |
|---|---|---|---|
| `I001` unsorted-imports | import 순서/그룹화만 변경 | **없음** (실행 의미 동일) | safe |
| `UP006/045/007/037` | `List[x]`→`list[x]`, `Optional[x]`→`x \| None`, 따옴표 annotation 해제 | **없음** (py312 런타임, annotation 전용) | safe |
| `UP017` | `datetime.timezone.utc`→`datetime.UTC` | 동작 동일 | safe |
| `UP015/009/024` | redundant open mode, utf8 선언, OSError alias | 동작 동일 | safe |

즉 R4 diff는 **순수 기계적 변환**으로, 런타임 동작·API 계약·스키마에 영향이 0이다. 큰 diff이지만 검토 비용이 낮고 회귀 위험이 거의 없다.

### 측정된 현황 (2026-06-01, in-scope dirs, webcloring-pdf 제외)

명령: `python -m ruff check . --select I,UP --statistics`

| 규칙 | 건수 | 자동수정 | R4 방침 |
|---|---:|:---:|---|
| I001 unsorted-imports | 62 | `[*]` safe | **enforce + autofix** |
| UP006 non-pep585-annotation | 51 | `[*]` safe | **enforce + autofix** |
| UP045 non-pep604-annotation-optional | 30 | `[*]` safe | **enforce + autofix** |
| UP035 deprecated-import | 28 | `[-]` **unsafe** | ~~R5 연기~~ → **R4 포함** (Iterate 재결정, §8.1) |
| UP037 quoted-annotation | 12 | `[*]` safe | **enforce + autofix** |
| UP017 datetime-timezone-utc | 7 | `[*]` safe | **enforce + autofix** |
| UP007 non-pep604-annotation-union | 5 | `[*]` safe | **enforce + autofix** |
| UP015 redundant-open-modes | 3 | `[*]` safe | **enforce + autofix** |
| UP009 utf8-encoding-declaration | 2 | `[*]` safe | **enforce + autofix** |
| UP024 os-error-alias | 2 | `[*]` safe | **enforce + autofix** |

**합계**: 202 errors, **183 safe-fixable**. UP035(28)은 `--unsafe-fixes`를 요구하므로 R4 비범위(re-export·typing 호환 위험).

## 2. Goal

1. **게이트 확장** — `pyproject.toml`의 `[tool.ruff.lint] select`에 `I`, `UP` 추가 (`F`, `BLE001` 유지).
2. **safe autofix 일괄 적용** — `ruff check . --select I,UP --fix` (unsafe 미사용)로 183건 기계 변환.
3. ~~**UP035 한시 연기**~~ → **UP035 포함** (Iterate 재결정 §8.1): 연기 시 F401 파생 부채 발생 → `--unsafe-fixes`로 함께 적용.
4. **회귀 0** — pytest 기존 green(306 passed) 유지, import smoke 통과, F/BLE001 게이트 계속 green.
5. **잔여 baseline 갱신** — 적용 후 남은 ramp 후보(E501/SIM/B/UP035) 통계 재기록.

## 3. Non-Goals (defer)

- **`UP035` 실제 수정** — unsafe 분류분 포함, typing/collections.abc 재배치는 import 호환성 검토 필요 → **R5**.
- **`SIM`(105/102/108/117)·`B`(904/905/025/007)** — 일부는 로직/제어흐름 변경 동반 → **R5/R6** (B904 우선).
- **`E501` line-too-long** — 포매팅 정책 결정 필요(noqa vs 줄바꿈 vs formatter) → 별도.
- **`ruff format` 도입** — 코드 포매터 채택은 별도 결정.
- **CI/pre-commit 연결** — 게이트 명령만 유지, 외부 연결 별도.

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Tool | `ruff` (requirements-dev.txt) | ✅ R3에서 도입 |
| Tool | `pytest`, `pytest-cov` | ✅ |
| 신규 외부 런타임 의존성 | — | **0** |
| 런타임/스키마 변경 | — | **0** (annotation·import 순서 전용) |

## 5. Scope (대상)

| 구분 | 대상 |
|---|---|
| **게이트 적용(enforce)** | `api/`, `shared/`, `dashboard/`, `tools/`, `scripts/`, `manager.py`, `tests/` |
| **enforce 규칙(추가)** | `I`, `UP` (기존 `F`, `BLE001` 유지) |
| **한시 ignore** | `UP035` (R5 연기, 사유 주석) |
| **전체 제외(exclude)** | `webcloring-pdf/`, `.venv*`, `.smoke-venv*`, `dist/`, `build/`, `docs/`, `logs/`, `.pytest_tmp/` (R3와 동일) |

## 6. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `pyproject.toml` select에 `I`,`UP` 추가, ignore에 `UP035`+사유 주석 | 파일 검사 |
| AC2 | `ruff check . --select F,BLE001,I,UP` → **0 errors** | shell |
| AC3 | safe autofix가 183건 처리, 잔여는 UP035뿐임을 보고서에 기록 | shell + 보고서 |
| AC4 | import smoke 통과 (`api.tools.items`, `api.tools.summary`, `shared.validators`, `tools.db_watcher` 등) | python -c import |
| AC5 | 기존 pytest 회귀 green (R3 기준 306 passed, 알려진 flaky 제외) | pytest 실행 |
| AC6 | 런타임 동작/스키마/공개 API 변경 0 (diff가 import 순서·annotation에 국한) | diff 검토 |
| AC7 | 적용 후 ramp 후보(E501/SIM/B/UP035) 통계 재기록 | 보고서 |
| AC8 | gap-detector match rate ≥ 90% | Check phase |

## 7. Constraints / Risks

- **대형 diff**: ~66개 파일 변경 예상. 그러나 변환이 기계적이라 검토 단위가 작다. → 커밋을 **(a) 게이트 설정, (b) I001 import 정렬, (c) UP annotation 현대화** 3계층으로 분리해 리뷰 가능성 확보([[feedback_commit_style]]).
- **UP037 quoted-annotation 해제**: 따옴표 제거 시 전방참조(forward ref)가 깨질 수 있음 → autofix는 py312 `from __future__ import annotations` 또는 런타임 비평가 위치만 안전 변환. ruff safe-fix 신뢰하되 **import smoke + pytest로 실증**.
- **I001 그룹 재배치**: first-party 모듈 인식 오류 시 순환참조 노출 가능 → import smoke로 차단.
- **flaky full-suite**: tmpdir race / rate-limiter timing 알려진 flaky([[project_pytest_tmproot_strategy]]). cov-fail-under 미사용 유지.
- **UP035 게이트 green 트릭**: ignore로 통과시키는 것은 임시 부채 표식 — R5에서 제거 예정임을 보고서에 명시.

## 8. Out-of-band Notes

### 8.1 Iterate 재결정 — UP035 연기 → 포함 (2026-06-01)

Plan 최초 결정은 UP035(unsafe)를 R5로 연기하는 것이었다. 그러나 Do 단계에서 게이트(`F,BLE001,I,UP`)가 **47 errors = 28 F401 + 19 UP035** 로 깨졌다. 원인:

> UP035를 연기하면 `from typing import Dict/List` import가 남는데, UP006이 본문을 `dict/list`로 바꾸면서 그 typing import가 **unused(F401)** 가 된다. select에 `F`가 있으므로 게이트가 자기모순에 빠진다.

→ **UP035를 R4에 포함**하는 것이 게이트를 self-consistent하게 만드는 유일한 길. unsafe-fix이지만 변환(`typing.List`→`list` import 제거, `Callable`→`collections.abc`)이 py312 표준이고, **import smoke + 전체 pytest 306 passed** 로 안전성을 실증했다. (메모리 [[feedback_agent_verification]] 정신: 추정 대신 게이트·테스트로 검증 후 결정.)

- **연쇄 사이클 예고**:
  - R5: `B904`(raise from) enforce
  - R6: `SIM`(105/102/108/117) 가독성 정리
  - E501/`ruff format`: 포매팅 정책 결정 후 별도
  - CI: `ruff check . --select F,BLE001,I,UP` 게이트를 GitHub Actions에 연결(별도)
- **게이트 명령(확정)**: `python -m ruff check . --select F,BLE001,I,UP`
- **메모리 참조**: [[project_except_refactor_r2]], [[feedback_commit_style]]
