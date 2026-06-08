# R3-ble001-narrowing-followup Design Document

> **Summary**: Narrow the R3 manager/tool BLE001 follow-up from temporary broad catches to explicit exception contracts.
>
> **Project**: Server_API
> **Author**: Codex
> **Date**: 2026-06-07
> **Status**: Final
> **Planning Doc**: [R3-ble001-narrowing-followup.plan.md](../../01-plan/features/R3-ble001-narrowing-followup.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Remove the most explicit R3 temporary BLE001 debt without expanding into unrelated API/UI broad-catch policy. |
| **WHO** | Maintainers running Manager UI, one-off tool scripts, and daemon watcher jobs. |
| **RISK** | Over-narrowing could let cleanup/UI/daemon failures escape and break shutdown or background loops. |
| **SUCCESS** | Targeted `noqa: BLE001` lines removed from the three selected files, lint gate green, targeted tests/import smoke pass. |
| **SCOPE** | `manager.py`, `tools/check_models.py`, `tools/watcher.py`, plus PDCA evidence documents. |

---

## 1. Overview

### 1.1 Design Goals

- Convert temporary broad catches into explicit exception tuples.
- Preserve defensive behavior at cleanup, GUI, SDK, and daemon boundaries.
- Avoid introducing helper abstractions for a small, localized follow-up.

### 1.2 Design Principles

- Keep the R3 follow-up narrow.
- Prefer concrete exception contracts over comments suppressing lint.
- Treat top-level user/LLM/API broad-catch policy as a separate future scope.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | Replace only `Exception` with coarse tuples | Add helper wrapper APIs around UI/daemon boundaries | Narrow each boundary with local exception tuples |
| **New Files** | 0 | 1-2 | 0 |
| **Modified Files** | 3 | 4-5 | 3 |
| **Complexity** | Low | Medium | Low |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | Medium | Low |
| **Risk** | Medium | Medium | Low |
| **Recommendation** | Useful if urgent | Too much for this follow-up | Selected |

**Selected**: Option C, pragmatic local tuples. It removes the targeted lint debt while keeping each boundary easy to inspect.

### 2.1 Component Diagram

```text
manager.py cleanup/UI/tray boundaries
  -> concrete IO/Tk/runtime/value/attribute exceptions

tools/check_models.py Gemini SDK boundary
  -> Google API-core exceptions + runtime/IO/value exceptions

tools/watcher.py daemon cycle boundary
  -> sqlite/json/IO/runtime/value exceptions
```

### 2.2 Data Flow

```text
Expected boundary failure -> local log/message/pass -> caller or daemon continues
Unexpected programming error -> not swallowed by these target handlers
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|------------|---------|
| `manager.py` | `tkinter`, `subprocess`, `pystray`, process utils | GUI/process safety boundary |
| `tools/check_models.py` | `google.generativeai`, `google.api_core.exceptions` | Gemini model-listing boundary |
| `tools/watcher.py` | `sqlite3`, `json`, filesystem utilities | Daemon-cycle safety boundary |

---

## 3. Data Model

No data model or schema changes.

---

## 4. API Specification

No API changes.

---

## 5. UI/UX Design

No visual UI changes. Manager UI behavior remains the same: cleanup and tray failures are best-effort and do not block usable UI paths.

---

## 6. Error Handling

| Location | Previous Boundary | New Boundary |
|----------|-------------------|--------------|
| `_cleanup_all_processes` | `Exception` | `OSError`, `RuntimeError`, `ValueError`, `subprocess.SubprocessError` |
| `_stream_output` read loop | `Exception` | `AttributeError`, `OSError`, `RuntimeError`, `tk.TclError`, `ValueError` |
| `_stream_output` outer/finally | `Exception` | `AttributeError`, `RuntimeError`, `tk.TclError`, `ValueError` |
| `_monitor` UI reset scheduling | `Exception` | `RuntimeError`, `tk.TclError` |
| `_setup_tray` | `Exception` | `AttributeError`, `OSError`, `RuntimeError`, `ValueError` |
| `tools/check_models.py` | `Exception` | `google_exceptions.GoogleAPIError`, `RetryError`, `OSError`, `RuntimeError`, `ValueError` |
| `tools/watcher.py` | `Exception` | `sqlite3.Error`, `OSError`, `json.JSONDecodeError`, `RuntimeError`, `ValueError` |

---

## 7. Security Considerations

- No new external input surface.
- Narrower exception handling reduces accidental swallowing of unexpected programming faults.
- No secret handling changes.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1 Static | Current Ruff gate | `python -m ruff check . --select F,BLE001,I,UP,B904` | Do/QA |
| L2 Import Smoke | Changed modules | `python -c "import ..."` | Do/QA |
| L3 Regression | Process/watcher related tests | `pytest tests/test_process_utils.py tests/test_watcher_maintenance.py` | Do/QA |

### 8.2 L1 Static Scenarios

| # | Command | Expected |
|---|---------|----------|
| 1 | `python -m ruff check . --select F,BLE001,I,UP,B904` | 0 errors |

### 8.3 L2 Import Scenarios

| # | Module | Expected |
|---|--------|----------|
| 1 | `manager` | Imports without syntax/runtime import errors |
| 2 | `tools.check_models` | Imports when environment permits dependency import; script behavior otherwise covered by lint |
| 3 | `tools.watcher` | Imports without syntax/runtime import errors |

### 8.4 L3 Regression Scenarios

| # | Test Target | Expected |
|---|-------------|----------|
| 1 | Process cleanup utilities | Existing process utility tests pass |
| 2 | Watcher maintenance | Existing watcher/db maintenance tests pass |

---

## 9. Clean Architecture

This feature stays in existing script/module boundaries and does not alter layer dependencies.

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|--------------------|
| Error handling | Concrete exception tuples instead of BLE001 suppressions where practical. |
| Imports | Ruff-managed import order. |
| Comments | No new explanatory comments unless needed for non-obvious behavior. |

---

## 11. Implementation Guide

### 11.1 File Structure

```text
manager.py
tools/check_models.py
tools/watcher.py
docs/03-analysis/R3-ble001-narrowing-followup.analysis.md
docs/05-qa/R3-ble001-narrowing-followup.qa-report.md
docs/04-report/R3-ble001-narrowing-followup.report.md
```

### 11.2 Implementation Order

1. [x] Update `manager.py` exception tuples.
2. [x] Update `tools/check_models.py` SDK exception tuple and import.
3. [x] Update `tools/watcher.py` daemon exception tuple and import.
4. [x] Run lint and targeted verification.
5. [x] Write Analysis, QA, and Report documents.

### 11.3 Session Guide

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Manager boundaries | `module-1` | Cleanup/log/tray exception narrowing | 1 |
| Tool boundaries | `module-2` | SDK and watcher exception narrowing | 1 |
| Verification/docs | `module-3` | Lint, tests, PDCA evidence | 1 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-07 | Initial final design | Codex |
