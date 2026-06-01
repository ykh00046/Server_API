# R4-import-pyupgrade-ramp — Design

> **Cycle**: R4-import-pyupgrade-ramp
> **PDCA Phase**: Design
> **Date**: 2026-06-01
> **Plan**: [[R4-import-pyupgrade-ramp]] (../01-plan/features/R4-import-pyupgrade-ramp.plan.md)

## 1. Context Anchor

| Key | Value |
|-----|-------|
| WHY | R3가 기록한 lint 부채 360건 중 위험 0·자동수정 안전군(I/UP)을 게이트에 편입해 코드 현대화 부채를 회수한다. |
| WHO | Server_API 유지보수자, 이후 R5/R6 ramp 작업자, CI 연결 담당. |
| RISK | 대형 diff가 숨은 forward-ref/순환참조 회귀를 가릴 가능성, UP035 unsafe 변환 오적용. |
| SUCCESS | `ruff check . --select F,BLE001,I,UP` 0 errors, pytest 306 green, import smoke green, 런타임 변경 0. |
| SCOPE | `api/`, `shared/`, `dashboard/`, `tools/`, `scripts/`, `manager.py`, `tests/`; `webcloring-pdf/` 제외. |

## 2. 설정 변경 (pyproject.toml)

### 2.1 Before (R3)

```toml
[tool.ruff.lint]
select = ["F", "BLE001"]
```

### 2.2 After (R4 — 실제 적용본)

```toml
[tool.ruff.lint]
# UP035 포함: 연기 시 `from typing import Dict/List`가 남고 UP006이 본문을 바꿔
# 그 import가 F401(unused)이 된다. 게이트 self-consistency를 위해 포함하며,
# unsafe-fix는 --unsafe-fixes로 적용하고 import smoke + pytest로 실증한다.
select = ["F", "BLE001", "I", "UP"]
```

> **Iterate 재결정**: 최초 Design은 `ignore = ["UP035"]`로 연기였으나, Do에서 F401 파생 부채(28건)가 게이트를 깨 → UP035 포함으로 번복. 상세 [[R4-import-pyupgrade-ramp]] Plan §8.1.

per-file-ignores(tests BLE001)·exclude·target-version(py312)은 R3 설정을 그대로 유지한다.

## 3. 적용 전략 (Do)

3단계 순서로 적용하고, **각 단계 후 게이트·import·테스트를 재확인**한다.

| 단계 | 명령 | 검증 |
|---|---|---|
| D1 게이트 설정 | `pyproject.toml` select/ignore 편집 | `ruff check . --select F,BLE001,I,UP --statistics` (UP035만 잔여 예상) |
| D2 import 정렬 | `ruff check . --select I --fix` | import smoke |
| D3 annotation 현대화 | `ruff check . --select UP --fix` (safe) | import smoke |
| D3b UP035 (Iterate 추가) | `ruff check . --select UP035 --fix --unsafe-fixes` → `--select F,I,UP --fix`로 수렴 | import smoke + 게이트 0 |
| D4 회귀 | `pytest` | 306 passed |

> **unsafe 적용 범위 한정**: `--unsafe-fixes`는 **UP035에만** 명시적으로 사용한다(deprecated-import). 변환 후 import smoke + 전체 pytest로 의미 보존을 실증한다. autofix는 I→UP 순서로 따로 돌리면 import 변경이 새 I001/F401을 노출하므로, 마지막에 `--select F,I,UP --fix`로 **수렴**시킨다.

## 4. 안전성 설계 (왜 회귀 위험이 낮은가)

| 변환 | 의미 보존 근거 |
|---|---|
| I001 import 정렬 | 모듈 import는 부수효과 순서가 바뀔 수 있으나, ruff isort는 **블록 내 재정렬만** 하고 조건부/지연 import는 건드리지 않음. import smoke가 순환참조·순서 의존을 실증. |
| UP006 `List`→`list` | py312에서 `list[int]`은 런타임 subscriptable. annotation 평가 시점 동일. |
| UP045/007 `Optional[x]`/`Union`→`x \| None` | PEP 604, py312 런타임 지원. annotation 의미 동일. |
| UP037 따옴표 해제 | ruff는 런타임 평가되지 않는 위치(순수 annotation)만 safe로 해제. 평가 위치는 미변환. **import smoke로 실증**. |
| UP017 `timezone.utc`→`UTC` | `datetime.UTC is datetime.timezone.utc` (동일 객체). |
| UP015/009/024 | open mode 기본값/utf8 선언/OSError alias — 의미 동일. |

**핵심 안전장치**: import smoke(모듈 로드) + 전체 pytest. 기계 변환이 의미를 바꿨다면 둘 중 하나가 반드시 실패한다.

## 5. 검증 매트릭스 (QA에서 실행)

| # | 명령 | 기대 |
|---|---|---|
| V1 | `python -m ruff check . --select F,BLE001,I,UP` | All checks passed! (0 errors) |
| V2 | `python -m ruff check . --select UP035 --statistics` | UP035 잔여만 측정(연기 확인) |
| V3 | `python -c "import api.tools.items, api.tools.summary, shared.validators, tools.db_watcher, manager"` | 예외 없음 |
| V4 | `python -m pytest` | 306 passed (R3 동일), 회귀 0 |
| V5 | `git diff --stat` 검토 | 변경이 import/annotation에 국한, 로직 라인 변경 0 |

## 6. 커밋 분리 (feedback_commit_style)

| 커밋 | 범위 |
|---|---|
| C1 `chore(lint): enable ruff I,UP gate (defer UP035)` | pyproject.toml select/ignore |
| C2 `style(imports): apply ruff I001 import sorting` | I001 autofix diff |
| C3 `refactor(types): pyupgrade annotations to py312 (UP006/045/007/037/017...)` | UP autofix diff |
| C4 `docs(pdca): R4 Analysis + Report + QA` | docs |

> diff가 매우 크면 C2/C3는 디렉터리별로 더 쪼갤 수 있으나, 기계 변환이라 단일 커밋으로도 리뷰 부담이 낮다. 1차로 위 4분할 적용.

## 7. Rollback

각 단계가 독립 커밋이므로 문제 발생 시 해당 커밋만 `git revert`. autofix는 결정론적이라 재적용으로 재현 가능.

## 8. Out-of-scope (재확인)

UP035 실수정, SIM/B904, E501, `ruff format`, CI 연결 — 모두 R5+ 또는 별도. (Plan §3 참조)
