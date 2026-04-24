# tool-schema-smoke-test Completion Report

> **Summary**: PRODUCTION_TOOLS 7개의 Gemini schema를 offline smoke 검증하는 44개 pytest 추가 — 2026-04-24 `params: list` 회귀 재발 방지
>
> **Date**: 2026-04-24
> **Match Rate**: 100% (7/7 AC)
> **Status**: Completed

---

## 1. 변경 요약

| 파일 | 변경 |
|------|------|
| `tests/test_tool_schemas.py` (신규) | `_FakeClient` stub + `TestToolSchemaSmoke` parametrized class (6 checks × 7 tools) + 2 전역 invariant = **44 tests** |
| `docs/01-plan/features/tool-schema-smoke-test.plan.md` | Plan |
| `docs/02-design/features/tool-schema-smoke-test.design.md` | Design |
| `docs/03-analysis/tool-schema-smoke-test.analysis.md` | Analysis |
| `docs/04-report/tool-schema-smoke-test.report.md` | 본 보고서 |

## 2. 검증 결과

- ✅ `pytest tests/test_tool_schemas.py -v` → **44 passed in 0.15s**
- ✅ `pytest tests/ -q` → **222 passed** (178 기존 + 44 신규, 0 regression)
- ✅ Offline 작동: `_FakeClient.vertexai=False` stub으로 `GEMINI_API_KEY` 없이 실행 가능
- ✅ 핵심 가드: `test_no_array_without_items[execute_custom_query]`가 `params: list = None` drift 감지

## 3. PDCA 메타데이터

```yaml
cycle: tool-schema-smoke-test
phase: completed
match_rate: 100
plan: docs/01-plan/features/tool-schema-smoke-test.plan.md
design: docs/02-design/features/tool-schema-smoke-test.design.md
analysis: docs/03-analysis/tool-schema-smoke-test.analysis.md
report: docs/04-report/tool-schema-smoke-test.report.md
duration_h: 0.7
trigger: 2026-04-24 런타임 400 INVALID_ARGUMENT (custom-query-bind-params-v1 drift)
```

## 4. 효과

| Before | After |
|--------|-------|
| 도구 시그니처 drift는 `/chat/stream` 호출 순간에만 감지 (prod runtime) | `pytest tests/test_tool_schemas.py` 0.15s로 schema 생성 단계에서 선감지 |
| 새 도구 등록 시 수동으로 prod smoke 필요 | `PRODUCTION_TOOLS` 리스트 추가만으로 44 tests 자동 확장 |
| description 누락, TYPE_UNSPECIFIED 같은 부수 결함도 runtime까지 감춰짐 | CI 단계에서 즉시 fail |

## 5. Lessons Learned

- **회귀 방지 테스트는 문제가 드러난 직후 작성**: prod 에러를 고친 당일(같은 세션)에 smoke test를 추가하면 context 손실 없이 cause 범위를 명확히 가드 가능.
- **offline stub을 쓰면 CI/dev 환경 분산에도 안전**: 외부 API 의존성을 최소화 (SDK가 `.vertexai` 속성만 읽는다는 구체적 사실에 의존).
- **parametrize는 레지스트리 등록 실수 방지의 최선책**: 새 도구를 `PRODUCTION_TOOLS`에 추가하면 자동으로 6개 검증에 편입 — 명시 등록 누락 불가능.

## 6. 후속 후보

| 사이클 | 우선순위 | 근거 |
|--------|:-------:|------|
| `manager-orphan-prevention-v1` | Medium | manager 닫을 때 자식 프로세스 잔존 문제 (대기 중) |
| `response-schema-smoke-test` | Low | 현재 도구는 response schema 미사용, 도입 시 추가 |
| real Gemini round-trip e2e (opt-in) | Low | 네트워크/quota 필요, offline smoke로 대부분 커버 |
