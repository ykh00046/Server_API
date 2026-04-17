# dashboard-sidebar-redesign Gap Analysis

> **Feature**: dashboard-sidebar-redesign
> **Plan**: `docs/01-plan/features/dashboard-sidebar-redesign.plan.md`
> **Date**: 2026-04-17
> **Overall Match Rate**: 96%
> **Status**: PASS (>= 90%)

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Scope Item Match (S1-S10) | 95% | PASS |
| Functional Requirement Match (FR-01~FR-08) | 100% | PASS |
| Architecture Compliance | 100% | PASS |
| **Overall** | **96%** | **PASS** |

---

## Scope Item Verification (S1-S10)

| ID | Scope Item | Status | Evidence |
|----|-----------|--------|----------|
| S1 | Data layer separation (`data.py`) | MATCH | `dashboard/data.py` 331줄, `load_records`, `load_monthly_summary` 등 6개 `@st.cache_data` 함수 |
| S2 | `st.navigation` + `st.Page` multipage | MATCH | `app.py:59-70` — 4페이지 등록, `st.navigation(pages)`, `nav.run()` |
| S3 | Sidebar filters + session_state 공유 | MATCH | `app.py:75-123` — date, keyword, multiselect, slider → `st.session_state["_filters"]` |
| S4 | AI panel toggle (7:3 columns) | MATCH | `layout.py:42-44` — `st.columns([7, 3])` open, `st.container()` closed |
| S5 | AI compact panel | MATCH | `ai_section.py:365-513` — compact header, quick chips, 400px chat, excel download |
| S6 | Common layout (`layout.py`) | MATCH | `render_page_header`, `get_page_columns`, `render_ai_column`, `init_ai_panel_state` |
| S7 | Pink/sky chart colors | MATCH | `#ec4899` / `#0ea5e9` — overview, trends, charts.py 전반 적용 |
| S8 | `st.segmented_control` 집계 단위 | MATCH | `trends.py:36-41`, `products.py:77-82` |
| S9 | X축 category 타입 강제 | **PARTIAL** | `overview.py:98`, `trends.py:88`에 적용됨. `charts.py:create_trend_lines()`에는 미적용 |
| S10 | 부동소수점 정수 포맷팅 | MATCH | `charts.py:51` — `f"{x:,.0f}"`, `trends.py:109` — `.round(1)` |

**Scope Match: 9.5 / 10 (95%)**

---

## Functional Requirement Verification (FR-01~FR-08)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| FR-01 | `st.navigation` 4페이지 라우팅 | MATCH | overview, trends, batches, products |
| FR-02 | 사이드바 필터 (날짜, 키워드, 제품, 레코드 수) | MATCH | `app.py:97-114` |
| FR-03 | `session_state["_filters"]` 전페이지 공유 | MATCH | `app.py:117-123`, 4개 페이지 모두 읽기 확인 |
| FR-04 | AI 패널 토글 (기본 닫힘, 7:3) | MATCH | `layout.py:16` default False, `layout.py:43` columns |
| FR-05 | AI compact: quick chips + chat + excel | MATCH | `ai_section.py:357-513` |
| FR-06 | `data.py` 캐시 데이터 로딩 | MATCH | 6개 `@st.cache_data` TTL 60~300s |
| FR-07 | 핑크/스카이 차트 색상 | MATCH | overview, trends, charts.py 전반 |
| FR-08 | segmented_control 집계 단위 | MATCH | trends.py, products.py |

**FR Match: 8 / 8 (100%)**

---

## Gaps Found

### G-01: `create_trend_lines()` xaxis_type 미적용 (S9 partial)

- **위치**: `dashboard/components/charts.py:223` (`fig.update_layout()`)
- **내용**: `overview.py`, `trends.py`에는 `xaxis_type="category"` 적용됨. 하지만 `charts.py:create_trend_lines()`에는 미적용 — `products.py` 제품 비교 추세 차트에서 Plotly가 날짜형 문자열을 자동 파싱할 수 있음.
- **영향도**: Low — period 문자열이 날짜 형태인 경우에만 발생
- **해결**: `charts.py:223` `fig.update_layout()`에 `xaxis_type="category"` 추가

### G-02: `data.py:get_filter_state()` dead code

- **위치**: `dashboard/data.py:321-330`
- **내용**: 개별 `_filter_*` 세션 키를 읽는 함수이나, 실제로는 `_filters` dict로 통합됨. 어떤 페이지에서도 호출되지 않음.
- **영향도**: None — 기능 영향 없음
- **해결**: 삭제 또는 `_filters` dict 기반으로 리팩터링

---

## Added Features (Plan 외 구현)

| Item | Location | Description |
|------|----------|-------------|
| 제품 추세 비교 | `products.py:63-94` | 멀티셀렉트 + create_trend_lines |
| CSV 내보내기 | `batches.py:64-71` | Excel 외 CSV 다운로드 버튼 추가 |
| 프리셋 매니저 | `app.py:126-134` | 필터 프리셋 저장/로드 (기존 기능 유지) |

---

## Architecture Compliance

| Check | Status |
|-------|--------|
| Entrypoint 분리 (app.py = nav + sidebar only) | PASS |
| Data layer 격리 (data.py) | PASS |
| Page-per-file 구조 (4 files) | PASS |
| Component 재사용 (layout, charts) | PASS |
| Import 방향 (pages → components, data) | PASS |
| `__init__.py` exports 완전성 | PASS |

**Architecture Score: 100%**

---

## Conclusion

Match Rate **96%** — Plan과 구현이 잘 정렬됨. S9 xaxis_type 1건만 partial이며, 나머지 모든 항목 완전 일치. 90% 임계값 초과로 completion report 진행 가능.

**Next**: `/pdca report dashboard-sidebar-redesign`
