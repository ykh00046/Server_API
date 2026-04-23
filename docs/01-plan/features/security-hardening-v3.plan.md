# security-hardening-v3 Planning Document

> **Summary**: 종합 검토 잔여 보안 cleanup — ATTACH SQL 패턴 통일(C3) + offset deprecation 가시성(H1)
>
> **Project**: Server_API (Production Data Hub)
> **Version**: security-hardening-v3
> **Author**: interojo
> **Date**: 2026-04-23
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

2026-04-23 종합 검토에서 후속 사이클로 분리한 보안 cleanup 항목 중 작은 변경 2건을 처리.
현재 두 항목 모두 런타임 보호가 적용되어 있어(whitelist / int 캐스팅) 실제 위험은 낮지만,
패턴 일관성과 운영 가시성을 위해 정리.

### 1.2 Background

#### C3: ATTACH SQL 패턴 불일치
- `shared/database.py:255-265` (`DBRouter.get_connection`):
  - `validate_db_path()` (regex 검증) → `path.replace("'", "''")` escape → string interpolation으로 ATTACH
- `api/tools.py:629-645` (`execute_custom_query`):
  - `resolve_archive_db()` (whitelist 검증) → URI form (`file:...?mode=ro`) → bind parameter 시도 → OperationalError 시 string fallback

두 패턴이 다르고, 후자(tools.py)가 더 강한 검증(whitelist) + bind parameter 우선이라 우월.
동일 helper로 추출해 DRY + 일관성 확보.

#### H1: OFFSET 가시성
- `api/main.py:521-523`: `sql += f" OFFSET {int(offset)}"` — `int()` 캐스팅으로 SQL 인젝션은 차단되지만 deprecated 표기.
- 현재 cursor pagination이 권장. offset 사용은 점진적 제거 대상이지만 실제 사용 시점 추적 가시성 부족.

### 1.3 Out of Scope

| Item | Reason |
|------|--------|
| H2 `execute_custom_query` bind parameter 도입 | 도구 시그니처 변경 + AI 학습 영향 + spec 동기화로 별도 사이클 (`custom-query-bind-params-v1` 후보) |
| `/healthz/ai`에서 fallback 모델 ping | observability-v3 사이클 |
| ATTACH 모드 ro 강제 (tools.py URI는 ro, database.py는 default) | 본 사이클에서 함께 통일됨 (helper 안에서 `mode=ro` 일관 적용) |

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Source | Effort |
|----|------|--------|--------|
| S1 | `shared/database.py`에 `_attach_archive_safe(conn, archive_path, whitelist)` helper 추출 — `resolve_archive_db` + URI form + bind-then-string fallback 패턴 | C3 | 20min |
| S2 | `DBRouter.get_connection()`이 helper를 호출하도록 변경 (기존 string interpolation 제거) | C3 | 10min |
| S3 | `api/tools.py:execute_custom_query`도 동일 helper 사용 (코드 중복 제거) | C3 | 10min |
| S4 | `api/main.py`에서 `offset > 0` 사용 시 `logger.warning(f"[Deprecated] /records called with offset={offset} ip={ip} — use cursor pagination")` | H1 | 10min |
| S5 | 단위 테스트: `tests/test_db_attach.py` (helper의 whitelist 거부 / bind fallback 동작 검증) | 신규 | 20min |

### 2.2 Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `shared/database.py`에 `_attach_archive_safe()` (또는 동등 helper) 정의 존재 | grep |
| AC2 | `DBRouter.get_connection()`에서 ATTACH 직접 string interpolation 제거 (`f"ATTACH DATABASE '{...}'"`) | grep 0건 |
| AC3 | `api/tools.py:execute_custom_query`도 helper 호출 (코드 중복 제거) | grep |
| AC4 | helper는 ① `resolve_archive_db()` 호출 ② URI form `file:...?mode=ro` 사용 ③ bind parameter 우선 시도 | code review |
| AC5 | `api/main.py` legacy offset 경로에 `logger.warning` 호출 (메시지에 `Deprecated`, `cursor` 키워드) | grep |
| AC6 | `pytest tests/test_db_attach.py` 통과 (whitelist 거부 / bind 성공 시나리오) | pytest |
| AC7 | 기존 회귀 없음: `pytest tests/` 전체 통과 | pytest |
| AC8 | gap-detector 재실행 시 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 3. Risks

| Risk | Mitigation |
|------|-----------|
| `DBRouter.get_connection`이 매우 빈번하게 호출됨 — `resolve_archive_db()`의 whitelist resolve가 매번 disk I/O | helper 내부에서 resolved Path를 모듈 레벨 cache (frozen tuple `ARCHIVE_DB_WHITELIST` 활용) |
| 기존 `validate_db_path()` 호출이 사라져 누군가 그것에 의존하던 다른 코드가 깨질 수 있음 | grep로 기타 사용처 확인 (있으면 본 사이클 out-of-scope, 별도 deprecation) |
| `mode=ro` URI form으로 강제하면 read-write가 필요한 archive 시나리오가 깨질 수 있음 | 현재 archive는 항상 ro 사용 (DBRouter도 ro 모드 사용). 회귀 가능성 없음 |
| `logger.warning`이 너무 자주 발생해 로그 spam | offset 자체가 deprecated이므로 외부 클라이언트 마이그레이션 유도 신호. 적절 |

---

## 4. Timeline

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.4h | interojo |
| Act-1: S1+S2+S3 (helper + 두 호출 지점) | 0.5h | interojo |
| Act-2: S4 (offset warning) | 0.2h | interojo |
| Act-3: S5 (test) | 0.3h | interojo |
| Check: gap-detector + pytest | 0.2h | gap-detector |
| Report | 0.2h | report-generator |

총 예상: ~1.8h
