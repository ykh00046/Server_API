# R3-ble001-narrowing-followup Analysis Report

> **Analysis Type**: Gap Analysis / Code Quality / Runtime Verification
> **Project**: Server_API
> **Analyst**: Codex
> **Date**: 2026-06-07
> **Design Doc**: [R3-ble001-narrowing-followup.design.md](../02-design/features/R3-ble001-narrowing-followup.design.md)

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | Remove the most explicit R3 temporary BLE001 debt without expanding into unrelated API/UI broad-catch policy. |
| WHO | Maintainers running Manager UI, one-off tool scripts, and daemon watcher jobs. |
| RISK | Over-narrowing could let cleanup/UI/daemon failures escape and break shutdown or background loops. |
| SUCCESS | Targeted `noqa: BLE001` lines removed from the three selected files, lint gate green, targeted tests/import smoke pass. |
| SCOPE | `manager.py`, `tools/check_models.py`, `tools/watcher.py`, plus PDCA evidence documents. |

## Strategic Alignment Check

| Plan / Design Criteria | Status | Evidence |
|---|:---:|---|
| Target only R3 manager/tool follow-up broad catches | Met | Changes limited to `manager.py`, `tools/check_models.py`, `tools/watcher.py` |
| Replace temporary BLE001 suppressions with concrete exception tuples | Met | `rg -n "noqa: BLE001\|except Exception" manager.py tools/check_models.py tools/watcher.py` returned no matches |
| Preserve current lint gate | Met | `python -m ruff check . --select F,BLE001,I,UP,B904`: pass |
| Preserve regression behavior | Met | `python -m pytest`: 360 passed |
| Avoid public API/schema/CLI changes | Met | No route, schema, CLI argument, or config contract changes |

**Success Rate**: 5/5 criteria met.

## Gap Analysis

| Area | Expected | Actual | Status |
|---|---|---|:---:|
| Structural | 3 target files changed, PDCA docs created | Plan, Design, Analysis, QA, Report present | Match |
| Functional | Target boundaries still log/pass/continue on expected failures | Cleanup, stream, tray, SDK, daemon paths retain same handling action | Match |
| Contract | No external behavior changes beyond narrower swallowed exception set | No API/schema/command changes | Match |
| Runtime | Lint and tests pass | Ruff pass, 360 pytest pass | Match |

## Implementation Notes

- `manager.py`: best-effort shutdown, log streaming, widget teardown, one-shot reset scheduling, and tray setup now catch concrete UI/process exception families.
- `tools/check_models.py`: Gemini SDK listing failures now catch Google API-core errors plus common IO/runtime/value failures.
- `tools/watcher.py`: daemon cycle failures now catch filesystem, SQLite, JSON decode, runtime, and value failures.
- Remaining project-wide broad catches are intentionally outside this R3 follow-up scope and still documented by their own boundary comments.

## Verification Results

| Command | Result |
|---|---|
| `python -m ruff check . --select F,BLE001,I,UP,B904` | Pass, 0 errors |
| `python -m pytest tests\test_process_utils.py` | Pass, 2 passed |
| `python -c "import tools.watcher"` | Pass |
| `python -m pytest` | Pass, 360 passed, 54 warnings |
| `rg -n "noqa: BLE001\|except Exception" manager.py tools\check_models.py tools\watcher.py` | No matches |

## Verification Limitations

| Item | Reason | Impact |
|---|---|---|
| `manager` import smoke | `customtkinter` is not installed in the current shell environment | Covered by Ruff syntax/lint and full test suite; GUI runtime smoke not executed |
| `tools.check_models` import smoke | `google.generativeai` is not installed in the current shell environment | Covered by Ruff syntax/lint; script runtime requires dev dependency/API environment |

## Match Rate

| Axis | Score | Rationale |
|---|---:|---|
| Structural | 100% | Planned files and docs exist. |
| Functional | 96% | Target behavior preserved; GUI/SDK runtime smoke skipped due local missing dependencies. |
| Contract | 100% | No public contract changes. |
| Runtime | 95% | Ruff and full pytest pass; two dependency-specific import smokes skipped. |

**Overall Match Rate**: 97%.

## Iterate Result

One minor iteration was required: the first Ruff run found `I001` import ordering in `tools/check_models.py`. It was fixed with Ruff's import organizer and the gate then passed.

## Recommended Actions

- Keep broader API/chat/tool-result catch normalization for a separate policy review, because those boundaries intentionally convert errors for users or LLM tool contracts.
- If Manager UI runtime validation is needed later, install GUI dependencies in the test environment and add a lightweight import/startup smoke test.

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0 | 2026-06-07 | Check/Iterate analysis completed | Codex |
