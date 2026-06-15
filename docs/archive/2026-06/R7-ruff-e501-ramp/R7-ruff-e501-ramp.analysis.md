# R7-ruff-e501-ramp — Gap Analysis

> **Cycle**: R7-ruff-e501-ramp
> **PDCA Phase**: Check
> **Date**: 2026-06-15
> **Plan**: [[R7-ruff-e501-ramp.plan]]
> **Match Rate**: **100%** (AC 7/7)

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | `ruff check . --select E501` 0 errors | 전체 게이트 All checks passed | ✅ |
| AC2 | code/ascii 래핑 해소(noqa 최소), 문자열 지배 파일만 per-file-ignore | ~45건 래핑(noqa 0), KOR-str 5파일+tests per-file-ignore | ✅ |
| AC3 | select에 E501, line-length 100 | `select=[...,"E501"]` | ✅ |
| AC4 | per-file-ignore: KOR-str 5파일 + tests/** E501 | api/chat.py, ai_section, webhook_admin/views, presets, portal_settings_dialog, tests/** | ✅ |
| AC5 | 376 green + 전체 게이트 + CI | 376 passed, ruff clean, CI(아래) | ✅ |
| AC6 | 래핑 동작/가독성 보존(SQL·시그니처) | SQL paren+concat 공백 보존, 376 green이 동작 보존 입증 | ✅ |
| AC7 | match rate ≥ 90% | 100% | ✅ |

## 처리 내역 (99건)

| 분류 | 건수 | 처리 |
|------|---:|------|
| code/ascii 래핑 | ~45 | 15파일: SQL 문자열 paren+concat, logger f-string 분할, Query/def 시그니처·dict·list 줄바꿈, CSS 셀렉터 개행 |
| KOR-str per-file-ignore | 30 | api/chat.py(프롬프트), ai_section/webhook_admin views/presets/portal_settings(한글 UI) |
| tests per-file-ignore | 19 | test_webhook_admin_ui/api_integration/chat_fallback(JSON 픽스처) |
| mixed(_chat_stream) | 2 | 코드 래핑으로 해소(한글 포함 라인도 100열 이내, noqa 0) |

## 설계 정합

- `ruff format` 미도입(85파일 재포맷 회피, blame 보존 — 사용자 결정) 준수.
- 문자열 지배 vs code/ascii 분류(ruff json + 한글 검출)대로 처리. code/ascii는 전부 래핑(noqa 0건), 한글/JSON 문자열 파일만 면제.
- SQL 문자열 concat 시 공백 보존 검증: 376 green(쿼리 실행 테스트 포함)이 SQL 의미 불변 입증.

## 부수 관찰

- ruff E501은 한글/이모지를 East-Asian-width 2로 계산 → "짧아 보이는" 한글 라인도 위반. 이 때문에 한글 UI/프롬프트 파일은 래핑보다 per-file-ignore가 합리적(래핑해도 width로 다시 걸리거나 의미 훼손).

## 권장 조치

없음 — **100% → Report.** 후속 R8: C901(complexity baseline). `ruff format`은 보류(사용자 결정).
