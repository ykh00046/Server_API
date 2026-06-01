# R4-import-pyupgrade-ramp Analysis Report

> **Analysis Type**: Gap Analysis / Lint Ramp / Runtime Verification
> **Project**: Server_API
> **Date**: 2026-06-01
> **Design Doc**: [R4-import-pyupgrade-ramp.design.md](../02-design/features/R4-import-pyupgrade-ramp.design.md)

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | R3가 기록한 lint 부채 360건 중 위험 0·자동수정 안전군(I/UP)을 게이트에 편입해 코드 현대화 부채를 회수. |
| WHO | Server_API 유지보수자, R5/R6 ramp 작업자, CI 연결 담당. |
| RISK | 대형 diff가 forward-ref/순환참조 회귀를 가릴 위험, UP035 unsafe 변환 오적용. |
| SUCCESS | `ruff check . --select F,BLE001,I,UP` 0 errors, pytest 306 green, import smoke green, 런타임 변경 0. |
| SCOPE | `api/`, `shared/`, `dashboard/`, `tools/`, `scripts/`, `manager.py`, `tests/`; `webcloring-pdf/` 제외. |

## Strategic Alignment Check

| Plan / Design Criteria | Status | Evidence |
|---|:---:|---|
| select에 I, UP 추가 | Met | `pyproject.toml [tool.ruff.lint] select=["F","BLE001","I","UP"]` |
| I001 import 정렬 적용 | Met | 62건 autofix, 잔여 0 |
| UP safe autofix 적용 | Met | 121건 autofix |
| UP035 처리 | Met | Iterate 재결정으로 R4 포함, `--unsafe-fixes` 19건 적용 |
| 파생 F401 해소 | Met | UP035 미처리 시 발생한 28건 → UP035 포함으로 해소 |
| 게이트 green | Met | `All checks passed!` |
| import smoke | Met | `SMOKE OK` |
| pytest 회귀 0 | Met | 306 passed (재실행) |
| 잔여 baseline 재기록 | Met | E501/SIM/B 158건 기록 |

**Success Rate**: 9/9 criteria met.

## Gap Analysis

| Area | Expected | Actual | Status |
|---|---|---|:---:|
| Ruff gate | F/BLE001/I/UP 0 errors | `All checks passed!` | Match |
| Runtime tests | Full pytest green | 306 passed | Match |
| Import integrity | smoke green | SMOKE OK | Match |
| Diff scope | import/annotation only | 67 files, 로직 변경 0 | Match |
| UP035 decision | 연기 예정 | **포함으로 번복** (F401 파생 부채 차단) | Intentional deviation (문서화) |

## Implementation Notes

- **UP035 결정 번복**: Plan/Design 초안은 UP035(unsafe)를 R5로 연기했으나, Do 단계에서 게이트가 `28 F401 + 19 UP035 = 47 errors`로 깨졌다. UP035를 연기하면 `from typing import Dict/List`가 남고 UP006이 본문을 `dict/list`로 바꿔 그 import가 unused(F401)가 되는 자기모순. → UP035를 R4에 포함하고 `--unsafe-fixes`로 적용, import smoke + pytest로 안전성 실증. (Plan §8.1에 정직하게 기록)
- **autofix 비수렴 처리**: `--select I --fix` → `--select UP --fix`를 따로 돌리면 UP가 import를 바꿔 새 I001/F401을 노출한다. 마지막에 `--select F,I,UP --fix`로 수렴시켰다.
- **flaky 식별**: full-suite 1차에서 `test_requeued_delivery_is_dispatched_by_worker` 1건 실패 → 단독 5/5 passed, full-suite 재실행 306 passed로 worker 백그라운드 레이스(R4 무관) 확정.

## Verification Results

| Command | Result |
|---|---|
| `python -m ruff check . --select F,BLE001,I,UP` | Pass, 0 errors |
| `python -m ruff check . --select UP035` | Pass, 0 errors (포함됨) |
| `python -c "import api.tools.items, api.tools.summary, shared.validators, tools.db_watcher"` | Pass |
| `python -m pytest -q` | Pass, 306 passed, 47 warnings |

## Lint Debt Progression

| 시점 | 측정 명령 | 총 findings |
|---|---|---:|
| R3 baseline | `--select E501,I,UP,SIM,B` | 360 |
| R4 회수 | `--select I,UP` | **202 (I001 62 + UP 140)** |
| R4 잔여 | `--select E501,SIM,B` | 158 |

R4가 부채의 **56%(202/360)** 를 회수했다.

## Match Rate

| Axis | Score | Rationale |
|---|---:|---|
| Structural | 100% | select 확장, 적용 파일·설정 모두 존재. |
| Functional | 100% | I/UP/UP035 게이트 0, F401 파생 부채 해소. |
| Contract | 100% | 런타임/스키마/공개 API 변경 0, import smoke green. |
| Runtime | 100% | 전체 pytest 306 passed, flaky는 R4 무관 확정. |

**Overall Match Rate**: 100%.

## Recommended Actions

- R5: `B904`(raise-without-from, 7건) enforce — 예외 체이닝 품질, 일부 수동.
- R6: `SIM`(105/117/102/108/300, 32건) 가독성 정리.
- E501(110): `ruff format` 채택 여부 결정 후 일괄.
- CI: `ruff check . --select F,BLE001,I,UP` + `pytest`를 GitHub Actions 게이트로 연결.
- notifications worker 테스트 레이스 안정화(flaky 제거) 별도 후보.

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0 | 2026-06-01 | R4 Check/Iterate analysis completed | Claude |
