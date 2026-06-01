# R3-ruff-ble001-coverage Analysis Report

> **Analysis Type**: Gap Analysis / Code Quality / Runtime Verification
> **Project**: Server_API
> **Analyst**: Codex
> **Date**: 2026-05-28
> **Design Doc**: [R3-ruff-ble001-coverage.design.md](../02-design/features/R3-ruff-ble001-coverage.design.md)

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | R2 이후 새 `except Exception` 회귀와 pyflakes 계열 실제 오류를 정적 게이트로 차단한다. |
| WHO | Server_API 유지보수자와 이후 lint/CI ramp 작업자. |
| RISK | 대량 스타일 정리로 diff가 커지는 것, 테스트 flaky가 lint 도입을 가리는 것. |
| SUCCESS | `ruff check . --select F,BLE001` 0 errors, pytest green, coverage baseline 기록. |
| SCOPE | `api/`, `shared/`, `dashboard/`, `tools/`, `scripts/`, `manager.py`, `tests/`; `webcloring-pdf/` 제외. |

## Strategic Alignment Check

| Plan / Design Criteria | Status | Evidence |
|---|:---:|---|
| Ruff 설정 추가 및 F/BLE001 선택 | Met | `pyproject.toml`에 `[tool.ruff]`, `[tool.ruff.lint]`, tests per-file ignore 존재 |
| F821 미import 제거 | Met | `python -m ruff check . --select F,BLE001` 통과 및 import smoke 통과 |
| F401/F541/F841/F811 정리 | Met | `ruff --fix` + 수동 정리 후 F 게이트 0 |
| BLE001 8건 처리 | Met | UI/daemon/top-level 보호 catch에 `# noqa: BLE001` 사유 코멘트 추가 |
| coverage 설정 및 baseline | Met | `python -m pytest --cov --cov-report=term-missing`: TOTAL 70% |
| dev 의존성 명시 | Met | `requirements-dev.txt` 추가 |
| pytest 회귀 0 | Met | `python -m pytest`: 306 passed, 47 warnings |
| ramp 후보 규칙 baseline 기록 | Met | E501/I/UP/SIM/B 통계 기록 |

**Success Rate**: 8/8 criteria met.

## Gap Analysis

| Area | Expected | Actual | Status |
|---|---|---|:---:|
| Ruff gate | F/BLE001 0 errors | `All checks passed!` | Match |
| Runtime tests | Full pytest green | 306 passed | Match |
| Coverage | Baseline only, no fail-under | 70% total, no fail-under added | Match |
| Future lint ramp | Non-enforced debt measured | 360 findings measured | Match |

## Implementation Notes

- `manager.py`, `tools/check_models.py`, `tools/watcher.py`: broad catch는 장기 실행 UI/daemon 또는 외부 SDK 보호 경계로 유지하고, 각 라인에 BLE001 사유를 명시했다.
- `tools/watcher.py`: 로컬 `get_file_state` 재정의는 제거하고 `shared.db_maintenance.get_file_state`를 사용하게 했다.
- `shared/rate_limiter.py`: 전체 pytest 중 드러난 경계값 버그를 함께 수정했다. `retry_after()`가 60초 윈도우에서 61을 반환하지 않도록 `ceil` 결과를 window 범위로 clamp했다.
- `requirements-dev.txt`: `ruff`, `pytest`, `pytest-cov`를 dev tooling으로 분리 명시했다.

## Verification Results

| Command | Result |
|---|---|
| `python -m ruff check . --select F,BLE001` | Pass, 0 errors |
| `python -c "import api.tools.items, api.tools.summary, shared.validators, tools.db_watcher"` | Pass |
| `python -m pytest` | Pass, 306 passed, 47 warnings |
| `python -m pytest --cov --cov-report=term-missing` | Pass, 306 passed, TOTAL 70% |

## Coverage Baseline

| Metric | Value |
|---|---:|
| Statements | 2672 |
| Missing | 742 |
| Branches | 584 |
| Partial Branches | 98 |
| Total Coverage | 70% |

Lowest covered in-scope modules:

| File | Coverage |
|---|---:|
| `shared/db_maintenance.py` | 0% |
| `shared/path_setup.py` | 0% |
| `shared/ui/responsive.py` | 0% |
| `shared/ui/theme.py` | 0% |
| `shared/utils/data_helpers.py` | 0% |
| `shared/utils/date_helpers.py` | 0% |
| `api/tools/summary.py` | 12% |
| `api/tools/items.py` | 20% |

Recommended optional CI floor: start at `--cov-fail-under=70` only after CI environment stability is confirmed.

## Future Ruff Ramp Baseline

Command: `python -m ruff check . --select E501,I,UP,SIM,B --statistics`

| Rule | Count |
|---|---:|
| E501 | 110 |
| I001 | 62 |
| UP006 | 51 |
| UP045 | 30 |
| UP035 | 28 |
| SIM105 | 17 |
| UP037 | 12 |
| B904 | 7 |
| SIM117 | 7 |
| UP017 | 7 |
| UP007 | 5 |
| SIM102 | 4 |
| B017 | 3 |
| B905 | 3 |
| SIM108 | 3 |
| UP015 | 3 |
| B025 | 2 |
| UP009 | 2 |
| UP024 | 2 |
| B007 | 1 |
| SIM300 | 1 |

Total: 360 findings, 191 auto-fixable.

## Match Rate

| Axis | Score | Rationale |
|---|---:|---|
| Structural | 100% | Planned config, requirements, and touched files exist. |
| Functional | 100% | F/BLE001 gate blocks target regressions and tests pass. |
| Contract | 100% | No API contract changes; import smoke passes. |
| Runtime | 100% | Full pytest and coverage run pass. |

**Overall Match Rate**: 100%.

## Recommended Actions

- R4에서 I001/UP/SIM/B904를 단계별로 별도 PR 단위로 ramp한다.
- coverage floor는 현재 baseline 70%를 기준으로 CI에서만 opt-in 적용한다.
- R2-2에서 `manager.py`의 `# noqa: BLE001` 보호 catch를 가능한 구체 예외로 좁히는 후속 정리를 진행한다.

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0 | 2026-05-28 | R3 Check/Iterate analysis completed | Codex |
