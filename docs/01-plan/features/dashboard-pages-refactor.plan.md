# dashboard-pages-refactor Planning Document

> **Summary**: products.py 분해 패턴을 남은 3개 페이지(overview/batches/trends)에 확장 적용
>
> **Project**: Server_API (Production Data Hub)
> **Version**: dashboard-pages-refactor v1
> **Author**: interojo
> **Date**: 2026-04-24
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

`products-refactor` 사이클(2026-04-23)에서 확립한 **Streamlit hybrid 패턴**(top-level entry + `_render_*` 함수)을 대시보드의 남은 페이지 스크립트 3종에 적용하여 단일 책임 분리, 재사용성, 테스트 용이성을 통일.

### 1.2 Background

- `products-refactor` 사이클의 `dashboard/pages/products.py` (343줄, 5개 helper) 패턴이 검증됨 (일치율 100%, pytest 회귀 없음).
- 남은 페이지 파일 상태:
  - `overview.py` (139줄) — KPI + 2x2 chart grid, 섹션 3~4개 절차적
  - `batches.py` (86줄) — KPI + 상세 테이블 + export, 섹션 2~3개 절차적
  - `trends.py` (114줄) — aggregation selector + 트렌드 차트 + 요약 테이블, 섹션 2개 절차적
- 모두 섹션이 혼재되어 있어 변경 시 영향 범위 식별이 어렵다.

### 1.3 Related

- 선행 사이클: `products-refactor` (archived target, 100%)
- 메모리: `project_review_fixes_202604_part2.md` (Streamlit hybrid 패턴 — top-level + `_render_*` 권장)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Effort |
|----|------|--------|
| D1 | `overview.py` 분해 — `_render_kpi_section`, `_render_chart_row_1`, `_render_chart_row_2` (3 helpers) | 25min |
| D2 | `batches.py` 분해 — `_render_kpi_cards`, `_render_detail_table`, `_render_export_buttons` (3 helpers) | 15min |
| D3 | `trends.py` 분해 — `_render_trend_chart`, `_render_summary_table` (2 helpers) | 20min |
| D4 | 각 페이지의 top-level은 data load + colors/chart_template 세팅 + helper 호출만 하도록 슬림화 | 포함 |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| 페이지 간 공통 패턴 추출 (e.g. `_setup_colors_and_template()`) | DRY 유혹이지만 각 페이지의 세팅이 조금씩 달라 YAGNI. 필요 시 별도 사이클 |
| KPI 카드 → shadcn 컴포넌트 교체 | UX 개선 사이클 |
| 차트 기본값(height/margin) 하드코딩 제거 → 상수화 | 테마 통일 사이클 후보 |
| AI panel 통합 방식 변경 | 현재 `render_ai_column(col_ai)` 패턴 유지 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 |
|----|------|------|
| AC1 | `overview.py` top-level에 `_render_*` 호출 3개가 있고 각 호출은 1줄 | grep |
| AC2 | `batches.py` top-level에 `_render_*` 호출 3개가 있고 각 호출은 1줄 | grep |
| AC3 | `trends.py` top-level에 `_render_*` 호출 2개가 있고 각 호출은 1줄 | grep |
| AC4 | 추출된 helper는 모두 명시적 인자를 받음 (페이지 모듈 로컬 변수 implicit 캡처 없음) | code review |
| AC5 | `py_compile` 각 페이지 compile ok | bash |
| AC6 | `pytest tests/ -q` 회귀 없음 (163 passed 유지) | pytest |
| AC7 | gap-detector 재실행 시 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| Streamlit의 session_state/rerun 타이밍이 함수 추출로 달라질 가능성 | helper는 pure render (side effect=st 위젯만) 유지. state mutation은 top-level에서만 |
| 차트 config key (`get_chart_config("...")`) 중복 | 기존 key 그대로 유지, 테스트 회귀 방지 |
| overview.py의 recent summary table에서 `df.head(7)` 두 번 호출(line 123-124) — helper 추출 시 단일화 유혹 | scope 고정: 동작 동일하게 그대로 옮김. 중복 정리는 별도 사이클 |
| batches.py의 `display_detail`을 export 버튼에서 재사용 — helper 경계 결정 필요 | `_render_detail_table`이 `display_detail`을 반환하고 `_render_export_buttons(df, display_detail)`가 받는 구조 |

---

## 5. Timeline

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.3h | interojo |
| Act-1: overview.py (D1) | 0.4h | interojo |
| Act-2: batches.py (D2) | 0.3h | interojo |
| Act-3: trends.py (D3) | 0.3h | interojo |
| Check: compile + pytest + gap-detector | 0.3h | gap-detector |
| Report | 0.2h | report-generator |

총 예상: ~1.8h
