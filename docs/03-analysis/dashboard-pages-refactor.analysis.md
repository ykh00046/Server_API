# dashboard-pages-refactor Analysis Document

> **Summary**: Cycle 5 갭 분석 — 7/7 AC PASS (일치율 100%)
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-24
> **Status**: Analysis (passed)

---

## 1. AC 검증 결과

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | `overview.py` top-level에 `_render_*` 3회(각 1줄) | PASS | overview.py:152-154 |
| AC2 | `batches.py` 3회 + detail→export display_detail 재사용 | PASS | batches.py:105-107, 57 |
| AC3 | `trends.py` 2회 + empty-state 분기는 top-level | PASS | trends.py:127-131 |
| AC4 | helper 명시적 인자만 사용 (implicit capture 없음) | PASS | 모든 helper 시그니처 검증 |
| AC5 | py_compile 3/3 성공 | PASS | 실측 ok |
| AC6 | pytest 회귀 없음 | PASS | 163 passed (변동 0) |
| AC7 | AD-1 Hybrid 패턴(top-level + `_render_*`) 준수 | PASS | 8개 helper 모두 일관 |

**일치율: 7/7 = 100%**

## 2. 변경 메트릭

| 파일 | Before | After | 변화 | Helper 수 |
|------|:------:|:-----:|:----:|:--------:|
| overview.py | 139줄 | 158줄 | +19 | 3 |
| batches.py | 86줄 | 117줄 | +31 | 3 |
| trends.py | 114줄 | 136줄 | +22 | 2 |
| **합계** | 339줄 | 411줄 | +72 | **8** |

> 줄 수 증가는 섹션 주석 블록 + 각 helper의 docstring + 타입 힌트 추가 때문. 실제 **로직은 동일하게 유지**, 순수 구조 개선.

## 3. 전체 대시보드 일관성

| Page | Helper 수 | 패턴 준수 |
|------|:--------:|:-------:|
| overview.py | 3 | ✓ |
| batches.py | 3 | ✓ |
| trends.py | 2 | ✓ |
| products.py (선행 사이클) | 5 | ✓ |
| **대시보드 전체** | **13** | **100%** |

대시보드의 모든 페이지가 동일한 Streamlit hybrid 패턴을 따름.

## 4. Iteration 필요 여부

불필요 (100%).

## 5. Lessons Learned

- **페이지 크기가 달라도 동일 패턴 적용 가능**: 86줄(batches)부터 343줄(products)까지 모두 같은 hybrid 구조. 페이지 크기는 helper 수만 달라질 뿐, 패턴 자체는 불변 → 확장 시 인지 부담 최소.
- **return value로 재사용성 표현**: `_render_detail_table(df) -> pd.DataFrame` 처럼 helper가 render 외에 가공된 데이터를 반환하면, 후속 helper가 동일 가공을 재실행하지 않음 (batches.py가 우수 사례).
- **Empty-state는 helper 밖에서 처리하면 helper가 pure하게 남음**: trends.py에서 `if len(summary_df) == 0: st.info(...)` 분기를 top-level에 두고, helper는 "데이터가 있다"는 전제만 받음. helper 책임 축소.
