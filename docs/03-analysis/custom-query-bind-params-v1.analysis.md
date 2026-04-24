# custom-query-bind-params-v1 Analysis Document

> **Summary**: Cycle 6 갭 분석 — 9/9 AC PASS (일치율 100%)
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-04-24
> **Status**: Analysis (passed)

---

## 1. AC 검증 결과

| AC | 항목 | 결과 | 근거 |
|----|------|:----:|------|
| AC1 | 시그니처 + docstring | PASS | `api/tools.py:549-582` |
| AC2 | `params=None/[]` backward compat | PASS | 기존 17 테스트 무수정 pass |
| AC3 | `conn.execute(sql_clean, bound_params)` 바인딩 | PASS | `api/tools.py:684` |
| AC4 | list 아닌 타입 → `INVALID_PARAMS` | PASS | `_validate_custom_query_params` + 2 tests |
| AC5 | non-str 원소 → `INVALID_PARAMS` | PASS | `_validate_custom_query_params` + 2 tests |
| AC6 | system prompt `?` + `params` 포함 | PASS | `api/chat.py:130-140` + `TestSystemPromptBindGuide` |
| AC7 | `ai_architecture.md §4.7` 갱신 | PASS | params 설명 + 예시 2건 |
| AC8 | `api_guide.md §6` 갱신 | PASS | Parameters 표 + 바인딩 섹션 + 예시 2건 |
| AC9 | pytest 회귀 무손상 | PASS | 178 passed (163 + 15) |

**일치율: 9/9 = 100%**

## 2. 초과 달성 항목

- Plan 단계 신규 테스트 7개 예상 → 실제 **15개** (`TestValidateCustomQueryParams` 7 + `TestCustomQueryParams` 7 + `TestSystemPromptBindGuide` 1)
- Helper 이름 `_validate_params` → `_validate_custom_query_params`로 더 명시적 naming

## 3. 변경 메트릭

| 파일 | 변경 |
|------|------|
| `api/tools.py` | +40줄 (helper + params arg + validation + bind) |
| `api/chat.py` | +13줄 (rule 9 expansion) |
| `docs/specs/ai_architecture.md` | +20줄 (params binding subsection + 예시) |
| `docs/specs/api_guide.md` | +35줄 (Parameters 표 + 바인딩 가이드 + 예시) |
| `tests/test_sql_validation.py` | +100줄 (15 신규 테스트) |

## 4. Iteration 필요 여부

불필요 (100%).

## 5. Lessons Learned

- **Gradual adoption via backward compat**: `params=None` 기본값으로 기존 코드 경로 그대로 유지. 이로써 AI가 점진적으로 새 패턴을 학습하도록 허용, 일회성 전환 위험 제거.
- **str-only 정책이 schema 단순성 확보**: `list[str | int | float]` union 대신 `list[str]`로 고정하여 Gemini tool schema 안정. SQLite dynamic typing에 numeric cast 위임 — trade-off는 prompt에서 `"1000"` 문자열 사용 가이드로 해소.
- **System prompt + spec + test 3층 동기화**: 도구 시그니처 변경은 (1) 런타임 검증, (2) AI 학습 가이드, (3) 문서, (4) 테스트 — 4개 지점 모두 동기화해야 완전. 이번 사이클은 cycle 2(docs-sync)의 교훈을 반영해 모두 AC에 포함.
