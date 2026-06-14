# coverage-blindspots-v1 — Plan

> **Cycle**: coverage-blindspots-v1
> **PDCA Phase**: Plan
> **Date**: 2026-06-14
> **Project**: Production Data Hub
> **Summary**: 커버리지 사각지대 2종을 구분해 처리 — **(A)** measured 영역(api+shared)의 0% 파일 중 **죽은 코드는 삭제**(`shared/utils/*`), **(B)** unmeasured이지만 깨지기 쉬운 **live 순수 로직은 추출 후 단위 테스트**(AI 마크다운 표 파싱, SSE 이벤트 파싱).

## 1. Background — 사각지대는 한 종류가 아니다 (실측, 2026-06-14)

2026-06-10 검토의 "dashboard/manager/tools 1,100+줄 무검증" 지적을 실측해보니 **두 개의 서로 다른 문제**가 섞여 있었다:

### (A) measured 영역의 죽은 코드
coverage `source=["api","shared"]` 안에서 0%인 파일:
- `shared/utils/data_helpers.py`(55 stmt, 0%) — `format_large_number`/`to_korean_category`/`aggregate_*`/`resolve_display_unit` 등 순수 함수.
- `shared/utils/date_helpers.py`(36 stmt, 0%) — `get_*_range`/`calculate_change_percentage`/`parse_production_date`.

**실측: 둘 다 어디서도 import되지 않음** — dashboard/api/tools/manager 전수 grep 0건, `shared/__init__.py` 미export, `shared/utils/__init__.py` 빈 파일, 유일한 참조는 data_helpers 내부 상수뿐. → **죽은 코드**. 이들이 measured coverage를 ~71%로 끌어내린 주범(91 stmt가 분모에 0%로 기여).

> 처리 원칙: 0% 파일은 "테스트한다" 또는 "삭제한다" 둘 중 하나. 미사용 모듈을 테스트하면 커버리지만 부풀고 유지비가 는다. 이 repo의 일관된 패턴(create_index.py·responsive.py viewport chain·chat.py wrapper 삭제, [[project_review_fixes_202604_part2]])에 따라 **삭제**.

### (B) unmeasured 영역의 live 순수 로직
coverage source에 **dashboard/·tools/는 없음** → "71%"는 애초에 이들을 측정하지 않는다. 그중 **깨지기 쉬운(brittle) live 로직**:
- `dashboard/components/ai_section.py::_render_table_download` — 마크다운 표 텍스트 → DataFrame 파싱(공백 제거·구분선 필터·`**` 제거 등 휴리스틱 다수). AI 응답 포맷이 조금만 바뀌어도 조용히 깨짐. **순수 부분이 `st.download_button` 호출과 한 함수에 엉켜 있어 현재 테스트 불가.**
- `dashboard/components/ai_section.py::_stream_chat_tokens_once` — SSE `event:`/`data:` 라인 파싱 + JSON 디코드 + 이벤트 분기(token/tool_call/error/done). 파싱 로직이 httpx 스트림·`st.*`와 결합.
- (참고) `dashboard/components/kpi_cards.py::calculate_kpis`/`get_sparkline_*`는 이미 순수하나 dashboard라 unmeasured.

## 2. Goal

1. **A — 죽은 코드 삭제**: `shared/utils/data_helpers.py`, `shared/utils/date_helpers.py` 삭제. 빈 `shared/utils/__init__.py`는 잔존 여부 검토(다른 참조 없으면 디렉터리째 정리). measured coverage 자연 상승.
2. **B-1 — 마크다운 표 파서 추출+테스트**: `_render_table_download`의 파싱부를 순수 함수 `parse_markdown_table(content: str) -> pd.DataFrame | None`로 추출(`ai_section.py` 또는 신규 `dashboard/components/_table_parse.py`). UI 함수는 이 헬퍼를 호출만. 단위 테스트: 정상 표/표 없음/구분선만/공백·`**` 변형/빈 결과/멀티컬럼.
3. **B-2 — SSE 이벤트 파서 추출+테스트**: 라인 파싱을 `st.*` 비의존 순수 제너레이터/함수로 분리(이벤트 (name, data) 튜플 산출). 테스트: token 누적/tool_call/error 코드/done 메타/깨진 JSON 무시/멀티라인.
4. **회귀 0 + CI green**: 기존 363 테스트 + 신규 테스트 green. 리팩터는 동작 보존(추출만, 로직 변경 없음).

## 3. Non-Goals (defer)

- **coverage `source`에 dashboard/ 추가** — pyproject 불변 원칙([[project_ci_env_standardization]] AC8 정신) 유지. 이번엔 테스트 추가만, source 확장은 별도 판단.
- **watcher.py/manager.py 테스트** — DB·프로세스·tkinter 결합이라 추출 비용 큼. 별도 사이클(`coverage-blindspots-v2`).
- **kpi_cards 순수 함수 테스트** — 이미 순수하고 안정적(brittle 아님). 우선순위 낮음, 여력 시 보너스.
- **floor 상향** — 죽은 코드 삭제로 오른 수치를 새 floor로 고정하는 건 다음 사이클.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **삭제(A)** | `shared/utils/data_helpers.py`, `shared/utils/date_helpers.py` (+ 빈 `__init__`/디렉터리 정리 검토) |
| **수정(B)** | `dashboard/components/ai_section.py`(파싱부 추출, 호출부 교체) |
| **신규(B)** | 추출 헬퍼(파일 위치는 Design), `tests/test_ai_table_parse.py`, `tests/test_sse_parse.py` |
| **불변** | pyproject(source/floor), api/, shared/(utils 외), UI 렌더 동작 |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | data_helpers.py·date_helpers.py 삭제, 전 코드베이스 import 잔재 0 (삭제 전 재grep) | ls + grep |
| AC2 | measured coverage(api+shared)가 삭제 후 상승(실측 before/after 기록) | pytest --cov |
| AC3 | `parse_markdown_table` 순수 함수 추출, `_render_table_download`은 호출만 | diff |
| AC4 | SSE 이벤트 파싱이 `st.*` 비의존 순수 단위로 분리 | diff |
| AC5 | 신규 테스트: 표 파서 ≥6 케이스, SSE 파서 ≥5 케이스, 전부 green | pytest |
| AC6 | 기존 363 + 신규 green, ruff 클린, CI run green | pytest/Actions |
| AC7 | 리팩터 동작 보존 — 추출 전후 UI 함수 출력 동일(스모크) | 수동/스크린샷 선택 |
| AC8 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **삭제의 가역성**: data_helpers/date_helpers는 잘 작성된 순수 유틸이라 "미래 사용" 유혹이 있으나, YAGNI + git 복원 가능. 삭제 직전 한 번 더 전수 grep(동적 import·`getattr`·문자열 참조 포함)로 확정.
- **추출 시 동작 변화 위험**: 마크다운 파서의 휴리스틱(공백 제거 위치 등)을 **그대로** 옮긴다. 테스트는 현재 동작을 캡처(characterization test)부터 — "있어야 할 동작"이 아니라 "지금 하는 동작" 고정 후, 명백한 버그만 별도 표기.
- **dashboard import 시 streamlit 로드**: 테스트가 `ai_section`을 import하면 streamlit이 끌려옴. `test_webhook_admin_ui.py:19`의 선례(streamlit-free 서브모듈만 importlib 로드)대로, 파서를 **streamlit 비의존 별도 모듈**로 추출하면 테스트가 깔끔(이게 B의 부수 이점).
- 커밋 분리([[feedback_commit_style]]): (a) 죽은코드 삭제, (b) 파서 추출+테스트, (c) docs.

## 7. Out-of-band Notes

- 측정/미측정 구분이 이 사이클의 핵심 통찰 — "71% 커버리지"는 api+shared만이라는 점을 Report에 명시(오해 방지).
- 후속: `coverage-blindspots-v2`(watcher/kpi 순수 로직), coverage source 확장 + floor 상향 판단.
- 메모리 참조: [[project_ci_env_standardization]](floor 66, pyproject 불변), [[feedback_commit_style]], [[project_review_fixes_202604_part2]](죽은 코드 삭제 패턴)
