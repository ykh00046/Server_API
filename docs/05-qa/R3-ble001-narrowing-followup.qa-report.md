# QA Report: R3-ble001-narrowing-followup

> **Date**: 2026-06-07
> **Verdict**: QA_PASS
> **Pass Rate**: 100%
> **Critical Issues**: 0
> **Feature**: R3-ble001-narrowing-followup

## 1. Test Summary

| Level | Type | Status | Pass Rate | Failed |
|-------|------|:------:|:---------:|:------:|
| L1 | Static lint gate | PASS | 100% | 0 |
| L2 | Targeted regression | PASS | 100% | 0 |
| L3 | Full regression suite | PASS | 100% | 0 |
| L4 | Targeted broad-catch audit | PASS | 100% | 0 |

## 2. Executed Checks

| Command | Result |
|---|---|
| `python -m ruff check . --select F,BLE001,I,UP,B904` | All checks passed |
| `python -m pytest tests\test_process_utils.py` | 2 passed |
| `python -c "import tools.watcher"` | Passed |
| `python -m pytest` | 360 passed, 54 warnings |
| `rg -n "noqa: BLE001\|except Exception" manager.py tools\check_models.py tools\watcher.py` | No matches |

## 3. Failed Tests

None.

The first lint attempt found one import-order issue in `tools/check_models.py`; it was fixed before final QA and did not indicate a behavioral failure.

## 4. Critical Issues

None.

## 5. Metrics

| Metric | Value |
|---|---:|
| QA Pass Rate | 100% |
| Regression Tests | 360 passed |
| Static Gate Errors | 0 |
| Targeted BLE001 leftovers | 0 |
| Critical Runtime Errors | 0 |

## 6. Skipped / Environment-Limited Checks

| Check | Reason |
|---|---|
| `python -c "import manager"` | `customtkinter` is not installed in this shell environment. |
| `python -c "import tools.check_models"` | `google.generativeai` is not installed in this shell environment. |

## 7. Recommendations

- Add GUI/SDK smoke tests only after those optional dependencies are present in the normal dev/test environment.
- Keep remaining project-wide `noqa: BLE001` lines scoped to a separate API/tool-boundary review.

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-06-07 | QA report created |
