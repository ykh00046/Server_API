# coverage-blindspots-v1 — Gap Analysis

> **Cycle**: coverage-blindspots-v1
> **PDCA Phase**: Check
> **Date**: 2026-06-14
> **Design**: [[coverage-blindspots-v1.design]]
> **Match Rate**: **100%** (AC 8/8)

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | data_helpers/date_helpers 삭제 + import 잔재 0 | `shared/utils/` 디렉터리째 삭제. 16개 심볼 전수 grep — 정의부 외 참조 0 (삭제 전 확인) | ✅ |
| AC2 | measured coverage 상승(before/after) | **72% → 75%** (91 stmt 0% 파일 분모 제거) | ✅ |
| AC3 | `parse_markdown_table` 추출, UI는 호출만 | `_parsing.py` 신규, `_render_table_download`은 `df = parse_markdown_table(content); if df is None: return` + Excel 생성만 | ✅ |
| AC4 | SSE 파싱 st.* 비의존 분리 | `parse_sse_events(lines) -> Iterator[(name, data)]` 순수 함수, UI 루프는 분기/`st.*`만 | ✅ |
| AC5 | 신규 테스트 표 ≥6/SSE ≥5 green | 표 7 + SSE 6 = **13 passed** | ✅ |
| AC6 | 기존 363 + 신규 green, ruff, CI | **376 passed**(363+13), ruff All checks passed, CI(아래) | ✅ |
| AC7 | 리팩터 동작 보존 | characterization 테스트가 현재 동작 캡처(공백 제거 한계 포함). 추출 전후 로직 1:1, ai_section은 `json` import만 제거(파서로 이동) | ✅ |
| AC8 | match rate ≥ 90% | 100% | ✅ |

## Track별 결과

**A (죽은 코드 삭제)**: `shared/utils/data_helpers.py`+`date_helpers.py`+빈 `__init__` 삭제. measured 72%→75%. repo의 죽은 코드 삭제 패턴 일관.

**B (파서 추출+테스트)**: `dashboard/components/_parsing.py`(streamlit-free) 신규 — `parse_markdown_table`/`parse_sse_events`. 로직 무변경 이전, UI 함수는 호출만. 13 characterization 테스트가 importlib 격리 로드(test_webhook_admin_ui 선례)로 streamlit 런타임 없이 brittle 파싱을 고정.

## 측정/미측정 구분 (Report 핵심)

- "coverage 75%"는 **api+shared만** 측정한 값. dashboard/는 source에 없어 신규 파서 테스트(13건)는 coverage %에 안 잡힘 — 그래도 brittle 로직이 이제 회귀 가드를 가진다는 게 본질적 이득.
- pyproject `source`/`floor` **불변**(Plan Non-Goal 준수). dashboard source 확장 + floor 상향은 별도 사이클 판단.

## 권장 조치

없음 — **100% → Report.** 후속: `coverage-blindspots-v2`(watcher/kpi 순수 로직), coverage source 확장 + floor 상향 판단.
