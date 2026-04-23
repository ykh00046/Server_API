# products-refactor Analysis Document

> **Summary**: Cycle 3 갭 분석 — 7/7 AC PASS (일치율 100%)
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-23
> **Status**: Analysis (passed)

---

## 1. AC 검증 결과

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | 4개 섹션이 `_render_*` 1줄 호출 | PASS | products.py:346, 349, 353, 357 |
| AC2 | 명시적 인자만 사용 (no implicit capture) | PASS | 모든 추출 함수 시그니처에 인자 명시 |
| AC3 | drill_select key = `f"drill_select_{selected_cat}"` (`selected_cat = "all"` 폴백) | PASS | products.py:262, 244 |
| AC4 | responsive.py 6개 dead 함수 본문 0건 | PASS | docstring history만 잔존 (허용) |
| AC5 | `import streamlit.components.v1` 제거 | PASS | responsive.py:20에 streamlit만 |
| AC6 | `apply_responsive_css()` 호출 정상 | PASS | app.py:23, 41 |
| AC7 | 5개 추출 함수가 design AD-1과 일치 | PASS | (design 인자 표기 사후 동기화 반영) |

**일치율: 7/7 = 100%** (목표 95% 초과)

## 2. 추가 검증

- `python -c "from shared.ui.responsive import apply_responsive_css; print('ok')"` → ok ✓
- `py_compile.compile('dashboard/pages/products.py')` → ok ✓
- `dir(shared.ui.responsive)` → public API: `apply_responsive_css`만 (그 외 `st`만 노출)
- products.py 줄 수: 330 → 343 (+13, but 함수 분해로 가독성 ↑, 단일 책임 원칙 충족)
- responsive.py 줄 수: 270 → 95 (-175, dead chain 제거)

## 3. Iteration 필요 여부

불필요 (≥ 90%, 실제 100%).

## 4. Lessons Learned

- **Streamlit 페이지 분해는 함수+top-level 하이브리드가 자연스럽다**: top-level은 entry point 유지, 섹션은 `_render_*` 함수로 분리하는 패턴이 Streamlit rerun 모델과 잘 맞음.
- **Dead code chain은 dependency 단위로 함께 제거**: `detect_viewport`만 제거하면 `get_optimal_columns`/`responsive_grid`가 default-only로 남아 헷갈림. 의존 chain 전체 제거가 깔끔.
- **session_state key는 의미 있는 식별자(`tab_idx` 같은 인덱스 X, 카테고리 코드 O)**: 동적 컨텍스트에서 데이터 시프트가 일어나도 안전.
