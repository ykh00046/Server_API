# R3-ble001-narrowing-followup Planning Document

> **Summary**: Replace the temporary R3 BLE001 `noqa` boundaries in manager/tool scripts with concrete exception tuples.
>
> **Project**: Server_API
> **Author**: Codex
> **Date**: 2026-06-07
> **Status**: Final

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | R3 introduced a useful BLE001 gate, but several `manager.py` and tool-script boundaries still rely on temporary broad catches. |
| **Solution** | Narrow the R3 follow-up scope to `manager.py`, `tools/check_models.py`, and `tools/watcher.py`, replacing broad catches with concrete runtime, IO, GUI, SDK, and database exception families. |
| **Function/UX Effect** | Shutdown cleanup, log streaming, tray setup, SDK model listing, and watcher daemon loops keep their defensive behavior without hiding unrelated programming errors. |
| **Core Value** | The lint gate remains green while the codebase moves from documented exceptions toward actual exception contracts. |

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

### 1.1 Purpose

Continue the R3 lint-hardening cycle by replacing first-wave temporary broad exception handlers with explicit exception tuples.

### 1.2 Background

R3 completed `F`/`BLE001` enforcement and documented several broad catches with `# noqa: BLE001`. Its report called out a follow-up to replace those manager/tool-script `noqa` lines where specific exception families are practical.

### 1.3 Related Documents

- Plan: [R3-ruff-ble001-coverage.plan.md](R3-ruff-ble001-coverage.plan.md)
- Report: [R3-ruff-ble001-coverage.report.md](../../04-report/R3-ruff-ble001-coverage.report.md)

---

## 2. Scope

### 2.1 In Scope

- [x] Narrow `manager.py` cleanup, log streaming, one-shot reset, and tray setup broad catches.
- [x] Narrow `tools/check_models.py` external SDK listing failure handling.
- [x] Narrow `tools/watcher.py` daemon-cycle failure handling.
- [x] Preserve current command-line, GUI, and daemon behavior.
- [x] Update PDCA status and completion evidence.

### 2.2 Out of Scope

- API/chat/tool-boundary broad catches that intentionally normalize user-facing or LLM-facing errors.
- Dashboard UI broad catches outside R3's original manager/tool follow-up.
- Enforcing additional Ruff `B`, `SIM`, or `E501` rules.
- CI pipeline changes.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Replace selected `except Exception` handlers with concrete exception tuples. | High | Complete |
| FR-02 | Preserve best-effort cleanup and background-loop survival semantics. | High | Complete |
| FR-03 | Keep `python -m ruff check . --select F,BLE001,I,UP,B904` green. | High | Complete |
| FR-04 | Add reportable evidence for import smoke and targeted regression tests. | Medium | Complete |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Reliability | Cleanup/UI/daemon boundaries still absorb expected runtime failures. | Static review and targeted tests |
| Maintainability | Remaining broad catches are outside this scoped R3 follow-up. | `rg` evidence |
| Compatibility | No public API, schema, or command syntax changes. | Import smoke and tests |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [x] Target files no longer contain R3 temporary `noqa: BLE001` comments.
- [x] Concrete exception families are used with no behavior-changing side effects.
- [x] PDCA Plan, Design, Analysis, QA, and Report documents exist.

### 4.2 Quality Criteria

- [x] Ruff gate passes.
- [x] Targeted tests pass.
- [x] Import smoke passes for changed modules.

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Missing a real GUI/tray backend exception family | Medium | Medium | Include Tk/runtime/IO/value/attribute families used by UI and backend adapters. |
| External SDK raises provider-specific errors | Medium | Medium | Catch Google API-core exceptions plus runtime/IO/value errors. |
| Daemon loop stops on SQLite or filesystem failures | High | Low | Catch SQLite, OSError, JSON decode, runtime, and value failures around each cycle. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `manager.py` | GUI/process manager | Narrow best-effort cleanup and UI/tray exception boundaries. |
| `tools/check_models.py` | Developer script | Narrow Gemini model-listing failure boundary. |
| `tools/watcher.py` | Daemon script | Narrow cycle-level daemon safety boundary. |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `manager.py` | Start/stop services | Manual Manager UI execution | Expected cleanup/UI failures remain absorbed. |
| `tools/check_models.py` | List Gemini models | Manual developer command | Error message behavior preserved. |
| `tools/watcher.py` | DB maintenance daemon | CLI / scheduled task | Loop continues after expected IO/DB/runtime cycle failures. |

### 6.3 Verification

- [x] All consumers listed above verified by static review.
- [x] No API/auth/schema changes.
- [x] No lint rule expansion beyond current gate.

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Dynamic** | Python API, dashboard, scripts, local services | Yes |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Scope | All broad catches / R3 manager-tool follow-up | R3 manager-tool follow-up | Keeps blast radius aligned with R3 report. |
| Exception policy | Keep `noqa` / concrete tuples / helper abstraction | Concrete tuples | Removes lint debt without new abstraction. |
| Tests | Full suite only / targeted tests plus lint | Targeted plus lint | Sufficient for narrow script/GUI boundary edits. |

---

## 8. Convention Prerequisites

| Category | Current State | Applied Rule |
|----------|---------------|--------------|
| Error handling | Ruff BLE001 enforced with reasoned ignores where needed | Prefer concrete exception tuples where practical. |
| Tooling | Ruff/pytest configured in `pyproject.toml` | Reuse current gate. |

---

## 9. Next Steps

1. [x] Write design document.
2. [x] Implement concrete exception tuples.
3. [x] Run lint and targeted verification.
4. [x] Write analysis, QA, and report.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-07 | Initial final plan | Codex |
