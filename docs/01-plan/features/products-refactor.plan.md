# products-refactor Planning Document

> **Summary**: 종합 검토에서 도출된 High 이슈 — products.py 함수 분해(H4) + responsive.py dead code 정리(H7) + 탭 key 충돌(H5) 수정
>
> **Project**: Server_API (Production Data Hub)
> **Version**: products-refactor v1
> **Author**: interojo
> **Date**: 2026-04-23
> **Status**: Plan

---

## 1. Overview

### 1.1 Purpose

종합 검토에서 도출된 High 이슈 중 코드 위생/유지보수성 직결 항목을 묶어 한 사이클로 처리.

### 1.2 Background

- **H4 products.py**: `dashboard/pages/products.py`(330줄)이 단일 모듈에 4개 섹션을 절차적으로 모아 둠 — 함수 단위 분해 필요. uncommitted diff에서 +336줄 추가된 상태.
- **H5 탭 key collision**: `key=f"drill_select_{tab_idx}"` — 카테고리 동적 변경 시 키가 다른 카테고리에 매핑될 위험.
- **H7 responsive.py dead code**: `detect_viewport()`는 본문 TODO대로 동작하지 않음 (postMessage가 streamlit session_state로 전파 안 됨). 이를 의존하는 `get_optimal_columns`, `responsive_grid` 모두 dead. 추가로 `get_responsive_columns`, `touch_friendly_button`, `touch_friendly_slider`도 외부 사용 0건 — `apply_responsive_css()`만 `dashboard/app.py:41`에서 사용.

### 1.3 Related
- 종합 검토 (대화, 2026-04-23)
- 메모리: `feedback_commit_style.md` (logical layer 단위 commit)

---

## 2. Scope

### 2.1 In Scope

| ID | Item | Priority | Source | Effort |
|----|------|----------|--------|--------|
| R1 | `dashboard/pages/products.py` 4개 섹션 → `_render_*` 함수 추출 | High | H4 | 30min |
| R2 | drill-down selectbox key를 `tab_idx` → category code 기반으로 변경 | Medium | H5 | 5min |
| R3 | `shared/ui/responsive.py` dead code 제거 — `detect_viewport`, `get_optimal_columns`, `responsive_grid`, `get_responsive_columns`, `touch_friendly_button`, `touch_friendly_slider`. `apply_responsive_css()`만 유지 | Medium | H7 | 15min |
| R4 | `streamlit.components.v1` import 제거 (detect_viewport 의존이 사라지므로) | Low | 부산물 | 2min |

### 2.2 Out of Scope

| Item | Reason |
|------|--------|
| `streamlit-js-eval` 도입으로 진짜 viewport 감지 | 현재 사용처 없음 (YAGNI). 필요 시 별도 사이클 |
| products.py 추가 UX 개선 (스켈레톤, 로딩 상태) | 별도 사이클 |
| 다른 페이지(`overview.py`, `batches.py`, `trends.py`)의 동일 패턴 분해 | 본 사이클 트리거된 H4가 products.py로 한정. 후속 사이클 후보 |

---

## 3. Acceptance Criteria

| AC | 내용 | 검증 방법 |
|----|------|----------|
| AC1 | `dashboard/pages/products.py`의 4개 섹션이 모두 `_render_*` 함수(또는 동등) 호출 1줄로 표현 | grep |
| AC2 | 추출된 함수는 명시적 인자(state-only) — 페이지 모듈의 로컬 변수 implicit 캡처 금지 | code review |
| AC3 | drill-down selectbox key가 카테고리 코드(또는 "all")를 포함 | grep `key=f"drill_select_` |
| AC4 | `shared/ui/responsive.py`에 `detect_viewport`, `get_optimal_columns`, `responsive_grid`, `get_responsive_columns`, `touch_friendly_button`, `touch_friendly_slider` 잔존 0건 | grep |
| AC5 | `shared/ui/responsive.py`에서 `import streamlit.components.v1` 제거 | grep |
| AC6 | `dashboard/app.py`의 `apply_responsive_css()` 호출 정상 — import 회귀 없음 | python -c import |
| AC7 | gap-detector 재실행 시 본 사이클 일치율 ≥ 95% | bkit:gap-detector |

---

## 4. Risks

| Risk | Mitigation |
|------|-----------|
| products.py 함수 분해 시 동작 차이(특히 chart key 변경) | render 함수의 chart_config key는 기존과 동일 유지. 함수 인자로 명시 전달 |
| responsive.py 함수 제거가 다른 미발견 import를 깨뜨림 | grep으로 모든 reference 사전 확인 (이미 완료: `apply_responsive_css`만 외부 사용) |
| Streamlit 페이지의 모듈-수준 코드 vs 함수 호출 차이 | products.py는 페이지 스크립트라 모듈 top-level 실행이 정상. 함수 호출도 그 안에서 일어나도록 유지 |

---

## 5. Timeline

| Phase | Duration | Owner |
|-------|---------|-------|
| Plan + Design | 0.4h | interojo |
| Act-1: R3+R4 (responsive.py 정리) | 0.3h | interojo |
| Act-2: R1+R2 (products.py 분해 + key fix) | 0.5h | interojo |
| Check: gap-detector + smoke import | 0.2h | gap-detector |
| Report | 0.2h | report-generator |

총 예상: ~1.6h
