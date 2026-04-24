# docs-sync-v2 Planning Document

> **Summary**: 2026-04-24 재검토에서 발견된 문서화 lag 4건 반영 — manager-orphan-prevention-v1 등 최신 산출물이 spec 3종에 미반영
>
> **Project**: Server_API (Production Data Hub)
> **Version**: docs-sync-v2
> **Author**: interojo
> **Date**: 2026-04-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

2026-04-24 gap-detector 재검토 결과 spec 영역 가중 일치율 98.9% (이전 100% 대비 -1.1%p).
원인: `manager-orphan-prevention-v1` / `tool-schema-smoke-test` / `custom-query-bind-params-v1` 등 이번 세션 신규 산출물이 `system_architecture.md`, `operations_manual.md`, `_INDEX.md` 3종에 역반영 안 됨.
문서화 lag만 반영해 100% 회복.

### 1.2 Background (gap-detector 결과 요약)
- P1 `system_architecture.md §5.3`: 공통 모듈 표에 `shared/process_utils.py` 누락
- P1 `operations_manual.md`: Manager 고아 프로세스 방지 동작 (psutil / SIGINT / tray fallback) 소절 없음
- P2 `operations_manual.md §10`: 테스트 수 `133` → 현재 `224` 미갱신
- P2 `docs/archive/2026-04/_INDEX.md`: 7개 신규 사이클 요약 미반영 (최종 갱신 2026-04-21)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | 대상 | Effort |
|----|------|------|--------|
| V1 | `system_architecture.md §5.3` 공통 모듈 표에 `process_utils.py` 1줄 추가 | `docs/specs/system_architecture.md` | 2min |
| V2 | `operations_manual.md §2 Manager 실행 방법` 또는 §7 운영 이슈에 Manager 종료 동작 소절 추가 (psutil 기반 kill, SIGINT 핸들러, tray 실패 fallback) | `docs/specs/operations_manual.md` | 10min |
| V3 | `operations_manual.md §10` 테스트 수 `10.52s / 133 tests` → 현재 실측 기준으로 갱신 | `docs/specs/operations_manual.md` | 3min |
| V4 | `_INDEX.md`에 2026-04-22~24 7개 신규 사이클 요약 + 요약 표 갱신 | `docs/archive/2026-04/_INDEX.md` | 10min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| 7개 사이클의 `docs/archive/`로 실제 이동(archive 작업) | 별도 `/pdca archive` 흐름. 본 사이클은 index 갱신만 |
| api_guide.md 추가 변경 | 2026-04-23 docs-sync에서 100% 동기화됨, 변경 사항 없음 |
| ai_architecture.md §4.7 추가 변경 | custom-query-bind-params-v1 사이클에서 이미 반영됨 |
| 테스트 수치를 auto-reflect 스크립트화 | YAGNI, 수동 갱신 공수 낮음 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `system_architecture.md §5.3`에 `process_utils.py` 항목 존재 | grep |
| AC2 | `operations_manual.md`에 "고아 프로세스", "psutil", "SIGINT" 중 최소 한 단어 + tray fallback 설명 소절 존재 | grep |
| AC3 | `operations_manual.md §10` 테스트 수가 실측 (`python -m pytest tests/ -q --ignore=tests/test_smoke_e2e.py`)에서 나온 값과 일치 | bash 실측 |
| AC4 | `_INDEX.md`에 이번 세션 7개 사이클 이름 모두 등장 (critical-fixes, docs-sync, products-refactor, security-hardening-v3, dashboard-pages-refactor, custom-query-bind-params-v1, tool-schema-smoke-test, manager-orphan-prevention-v1) | grep |
| AC5 | gap-detector 재실행 시 spec 가중 일치율 ≥ 99% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| 테스트 수 갱신이 또 stale 될 가능성 | 갱신 시점(`측정일`) 명기, 실측 명령어 함께 기록 → 독자가 재실측 가능 |
| _INDEX.md 순서 뒤틀림 (기존은 번호/완료일 섞여 있음) | 기존 표기 관례를 따르되, 새로 추가되는 항목은 일자 역순으로 추가 (최신이 앞) |

---

## 5. Timeline

| Phase | Duration |
|-------|---------|
| Plan + Design | 0.1h |
| Act: V1 + V2 + V3 + V4 | 0.3h |
| Check: gap-detector | 0.1h |
| Report + commit | 0.1h |

총 예상: ~0.6h
