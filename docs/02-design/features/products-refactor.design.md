# products-refactor Design Document

> **Summary**: 함수 분해(R1/R2) + dead code 제거(R3/R4) 구현 설계
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-23
> **Status**: Design

---

## 1. Architecture Decisions

### AD-1: products.py 함수 추출 단위

페이지 스크립트(`dashboard/pages/products.py`)는 Streamlit이 매 rerun마다 top-to-bottom으로 실행되는 모듈.
함수 추출은 **순수 render 단위**로 분리하되, 모듈 top-level이 여전히 실행 entry point가 되도록 유지.

| 함수 | 인자 | 책임 |
|------|------|------|
| `_render_category_kpis(cat_summary, num_cats)` | DataFrame, int | Section 1 KPI 카드 렌더 |
| `_render_distribution_charts(df, cat_summary, categories_present, chart_template)` | 모두 인자로 | Section 2 Pie + Stacked bar |
| `_render_drilldown(df, categories_present, colors, chart_template)` | DataFrame, list, dict, str | Section 3 탭 + selectbox + 상세 (item detail에 `colors`/`chart_template` pass-through) |
| `_render_drilldown_item_detail(item_df, selected_code, colors, chart_template)` | DataFrame, str, dict, str | Section 3-내부, 단일 제품 상세 (KPI 4개 + 월별 추이 + 최근 배치) |
| `_render_trend_comparison(df, db_ver, chart_template)` | DataFrame, str, str | Section 4 Cross-product trend |

### AD-2: H5 탭 key 정책

**선택지**

| 옵션 | 안정성 | 가독성 | 결정 |
|------|--------|--------|------|
| A. `key=f"drill_select_{tab_idx}"` (현재) | 카테고리 변동 시 collision 가능 | 단순 | ✗ |
| B. `key=f"drill_select_{cat_or_all}"` (카테고리 코드 기반) | 안정 | 명확 | **✓** |
| C. UUID 기반 | 매 rerun 시 key 변경 → state 손실 | 나쁨 | ✗ |

**선택 근거**: B
- 카테고리 추가/제거 시에도 동일 카테고리는 동일 key 유지.
- 디버깅 시 어떤 탭의 selectbox인지 즉시 식별 가능.

### AD-3: responsive.py 정리 범위

**선택지**

| 옵션 | 결정 |
|------|------|
| A. broken `detect_viewport()`만 제거 | 의존 함수들이 dead로 남음 |
| B. dead chain 전체 제거 + 미사용 wrapper도 제거 | **✓** YAGNI 원칙, `apply_responsive_css()`만 유지 |
| C. `streamlit-js-eval`로 교체 | 신규 의존성, 현재 사용처 없음 |

**선택 근거**: B
- `apply_responsive_css()`가 모든 responsive 동작(media query)을 책임지므로 wrapper 함수들은 가치 없음.
- 미사용 코드는 향후 누군가 의심 없이 호출 시 broken 동작을 만날 위험.
- 필요 시 git history에서 복원 가능.

---

## 2. File-Level Changes

### 2.1 `shared/ui/responsive.py` (대폭 축소)

**유지**: `apply_responsive_css()` (line 68-141, dashboard/app.py:41에서 호출)

**제거**:
- `import streamlit.components.v1 as components` (line 14) — `detect_viewport`만 사용했음
- `from typing import List, Optional, Callable, Any` (모두 제거 함수에서만 사용)
- `def get_responsive_columns(count)` (line 18-36) — `st.columns(count)` 1줄 wrapper, 미사용
- `def get_optimal_columns(default)` (line 39-65) — viewport_width session state 의존(broken), 미사용
- `def touch_friendly_button(...)` (line 148-169) — `st.button(...)` wrapper, CSS는 글로벌, 미사용
- `def touch_friendly_slider(...)` (line 172-201) — `st.slider(...)` wrapper, 미사용
- `def responsive_grid(...)` (line 204-239) — `get_optimal_columns` + viewport_width 의존(broken), 미사용
- `def detect_viewport()` (line 242-269) — 본문 TODO 명시: postMessage가 session_state 갱신 안 함

결과: 약 170줄 → 약 80줄로 축소. 모듈 docstring도 정리.

### 2.2 `dashboard/pages/products.py` (구조 개편)

**상수**: `PRODUCT_CATEGORIES`, `_classify_item_code`, `_get_category_info` 유지.

**신규 함수**:
```python
def _render_category_kpis(cat_summary: pd.DataFrame, num_cats: int) -> None: ...
def _render_distribution_charts(df, cat_summary, categories_present, chart_template) -> None: ...
def _render_drilldown(df, categories_present) -> None: ...
def _render_drilldown_item_detail(item_df, selected_code, colors, chart_template) -> None: ...
def _render_trend_comparison(df, db_ver, chart_template) -> None: ...
```

**모듈 entry**:
```python
render_page_header("제품별 분석", "생산 관리 > 제품별 분석")
fs = get_filter_state()
col_main, col_ai = get_page_columns()

with col_main:
    df, _ = load_records(...)
    colors = get_colors()
    chart_template = colors.get("chart_template", "plotly_white")

    if df.empty:
        st.info("조회된 데이터가 없습니다. 사이드바 필터를 조정해 주세요.")
    else:
        df["category"] = df["item_code"].apply(_classify_item_code)
        cat_summary = (df.groupby("category").agg(...)...)
        categories_present = cat_summary["category"].tolist()

        st.markdown("#### 📊 카테고리별 현황")
        _render_category_kpis(cat_summary, len(categories_present))
        st.markdown('<div class="bkit-spacer-8"></div>', unsafe_allow_html=True)

        _render_distribution_charts(df, cat_summary, categories_present, chart_template)

        st.divider(); st.markdown("#### 🔍 제품 상세 드릴다운")
        _render_drilldown(df, categories_present)

        st.divider(); st.markdown("#### 📈 제품 추세 비교")
        _render_trend_comparison(df, db_ver, chart_template)

render_ai_column(col_ai)
```

**탭 key (R2)**:
```python
# Before:  key=f"drill_select_{tab_idx}"
# After:   key=f"drill_select_{selected_cat or 'all'}"
```
같은 컨텍스트에서 chart key도 `f"product_{selected_code}_trend"`는 안전(이미 코드 기반).

---

## 3. Test Plan

### 3.1 단위 검증

| Test | 명령 | 기대 |
|------|------|------|
| responsive.py import | `python -c "from shared.ui.responsive import apply_responsive_css; print('ok')"` | ok |
| products.py import (Streamlit 컨텍스트 외) | `python -c "import dashboard.pages.products"` | bare-mode 경고만, ImportError 없음 |
| dead code 잔존 검사 | `grep -RIn 'detect_viewport\|get_optimal_columns\|responsive_grid\|get_responsive_columns\|touch_friendly_' shared dashboard` | 0건 |
| products 함수 분해 검증 | `grep -E "^def _render_(category_kpis|distribution_charts|drilldown|drilldown_item_detail|trend_comparison)" dashboard/pages/products.py` | 5건 |
| H5 key 수정 | `grep "drill_select_" dashboard/pages/products.py` | `tab_idx` 표현 0건 |

### 3.2 수동 smoke

- 대시보드 실행 후 "제품별 분석" 페이지에서 모든 탭(AS/AC/AW/기타/전체) 전환 시 selectbox state 손실/충돌 없는지 확인.
- 차트 4종 모두 정상 렌더 (Pie, Stacked Bar, Monthly Bar, Trend Lines).

---

## 4. Rollback Strategy

각 commit 단위(`feedback_commit_style.md` 정책):

| Commit 단위 | Revert 영향 |
|-----------|-----------|
| Plan/Design 문서 | 기능 영향 없음 |
| R3+R4 (responsive.py) | wrapper 함수들 복구 (모두 미사용이므로 사용자 영향 없음) |
| R1+R2 (products.py) | 페이지 동작 원복. 함수 분해 전 절차적 코드로 복귀 |

---

## 5. Open Questions

- (해결됨) responsive 정리 범위 → AD-3에서 dead chain 전체 + 미사용 wrapper 제거로 결정.
- (해결됨) 함수 추출 단위 → AD-1에서 5개 함수로 결정 (drill-down은 외부/내부 2단으로).
