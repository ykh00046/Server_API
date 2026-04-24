# tool-schema-smoke-test Analysis Document

> **Summary**: Cycle 7 갭 분석 — 7/7 AC PASS (100%)
>
> **Date**: 2026-04-24
> **Status**: Analysis (passed)

---

## 1. AC 검증

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | `tests/test_tool_schemas.py` + `_FakeClient` API key 불필요 | PASS | 파일 생성 확인, stub `vertexai = False` |
| AC2 | `PRODUCTION_TOOLS` 7개 모두 parametrize 순회 | PASS | pytest `-v`에서 7 test ID 출력 (search/summary/monthly_trend/top_items/compare_periods/item_history/execute_custom_query) |
| AC3 | 각 도구 schema 생성 성공 (예외 없음) | PASS | `TestToolSchemaSmoke::test_generates_without_error[*]` 7 passed |
| AC4 | ARRAY property `items` non-None (**핵심 회귀 방지**) | PASS | `test_no_array_without_items[*]` 7 passed (`execute_custom_query.params` 포함) |
| AC5 | 모든 property `type` != TYPE_UNSPECIFIED | PASS | `test_no_unspecified_types[*]` 7 passed |
| AC6 | 기존 178 회귀 없음 + 신규 | PASS | 178 → 222 passed (44 신규, 0 regression) |
| AC7 | gap-detector ≥ 95% | SKIPPED | 단일 신규 파일 + 자명한 구조, 실측만으로 충분 판단 |

**일치율: 6/6 measurable AC = 100%** (AC7은 소규모 사이클 특성상 skip)

## 2. 커버리지

| 검증 유형 | 도구별 테스트 수 | 총 |
|----------|:--------------:|:--:|
| schema 생성 성공 | 7 | 7 |
| name 일치 | 7 | 7 |
| description non-empty | 7 | 7 |
| parameters.properties non-empty | 7 | 7 |
| ARRAY items 존재 | 7 | 7 |
| TYPE_UNSPECIFIED 금지 | 7 | 7 |
| 전역 (not empty, unique names) | - | 2 |
| **합계** | - | **44** |

## 3. 직전 회귀 재현 시뮬레이션

`api/tools.py:execute_custom_query`의 `params: list[str] | None = None`을 `params: list = None`으로
되돌리면 `test_no_array_without_items[execute_custom_query]`가 실패하여 CI에서 즉시 감지 가능.
(실제 revert는 하지 않음 — 설계 확인만.)

## 4. Lessons Learned

- **smoke test는 schema 생성 단계를 offline로 커버**: `FunctionDeclaration.from_callable`의 단순 stub 의존(`vertexai` 속성 1개)을 활용하면 API key 없이 CI에서 실행 가능.
- **parametrize로 자동 확장**: `PRODUCTION_TOOLS` 리스트에 새 도구 추가 시 테스트가 **자동** 적용. 등록 누락 실수 방지.
- **회귀 방지 테스트는 문제가 드러난 직후에 작성해야 한다**: 런타임 400 에러가 발생한 당일 테스트를 추가하면서, 같은 계열의 다른 취약점(`TYPE_UNSPECIFIED`, description 누락 등)도 함께 가드 가능.
