# R7-ruff-e501-ramp — Plan

> **Cycle**: R7-ruff-e501-ramp
> **PDCA Phase**: Plan
> **Date**: 2026-06-15
> **Project**: Production Data Hub
> **Summary**: ruff 게이트에 `E501`(line-too-long, 100) 추가. **`ruff format` 미도입**(사용자 결정 — 85파일 재포맷 회피, blame 보존). 99건 중 한글 프롬프트/UI·테스트 JSON 등 **문자열 지배 파일은 per-file-ignore**, 진짜 코드 라인(~48)만 수동 래핑. [[project_lint_ramp_r3_r4]] 후속(R6 다음).

## 1. Background (실측 2026-06-15)

- `ruff format`은 85/99 파일 재포맷 → 사용자 결정으로 **미도입**. E501만 수동 + 게이트.
- E501 99건 분류(ruff json + 한글 검출):
  - **KOR-str (per-file-ignore 대상, 30건/5파일)**: `api/chat.py`(10, Gemini 시스템 프롬프트), `dashboard/components/ai_section.py`(7, UI 텍스트), `dashboard/components/webhook_admin/views.py`(6), `portal_settings_dialog.py`(6), `dashboard/components/presets.py`(1) — 한글 문장 래핑은 가독성·의미 훼손.
  - **tests (19건/3파일)**: `test_webhook_admin_ui.py`(17, JSON 픽스처), `test_api_integration.py`(1), `test_chat_fallback.py`(1) — 이미 tests/** per-file-ignore 존재 → E501 추가.
  - **code/ascii (래핑 대상, ~48건/14파일)**: `api/tools/summary.py`(9), `api/routers/summary.py`(8), `api/tools/custom.py`(6), `dashboard/data.py`(5), `manager.py`(5), `api/tools/items.py`(3), `tools/db_watcher.py`(3), `api/routers/records.py`(2), `dashboard/components/charts.py`(2), `api/_chat_stream.py`(2, mixed), 그 외 1건씩(system.py, overview.py, shared/ui/theme.py, backup_db.py, watcher.py).
- 한글은 ruff가 East-Asian-width 2로 계산 → 짧아 보여도 E501.

## 2. Goal

1. **코드 라인 래핑**: code/ascii ~48건을 paren-continuation/문자열 분할로 100열 이내. docstring 문장은 분할, SQL/dict/시그니처는 괄호 줄바꿈. 동작 보존.
2. **문자열 지배 파일 per-file-ignore**: KOR-str 5파일 + tests/**에 E501 면제. 단 파일별 실inspection으로 "진짜 문자열 지배"인지 확인(코드 라인이 섞였으면 그 라인은 래핑하고 파일 ignore는 신중).
3. **게이트 확장**: `select`에 E501 추가. `[tool.ruff.lint]` line-length=100 이미 설정됨.
4. **회귀 0**: 376 green, CI green.

## 3. Non-Goals (defer)

- `ruff format` 도입 — 사용자 결정으로 제외(별도 결정 시 미래).
- C901(complexity) — R8.
- 한글 문자열 파일의 E501 실제 해소(래핑) — per-file-ignore로 면제(래핑이 의미 훼손).

## 4. Scope

| 구분 | 대상 |
|---|---|
| **래핑** | api/tools/summary.py, api/routers/summary.py, api/tools/custom.py, dashboard/data.py, manager.py, api/tools/items.py, tools/db_watcher.py, api/routers/records.py, dashboard/components/charts.py, api/_chat_stream.py, api/routers/system.py, dashboard/views/overview.py, shared/ui/theme.py, tools/backup_db.py, tools/watcher.py |
| **per-file-ignore E501** | api/chat.py, dashboard/components/ai_section.py, dashboard/components/webhook_admin/views.py, portal_settings_dialog.py, dashboard/components/presets.py, tests/** |
| **게이트** | pyproject.toml(select +E501, per-file-ignores 갱신) |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `ruff check . --select E501` 0 errors (래핑 + per-file-ignore 후) | ruff |
| AC2 | code/ascii 파일은 래핑으로 해소(noqa 최소), 문자열 지배 파일만 per-file-ignore | diff |
| AC3 | select에 E501 추가, line-length=100 | pyproject |
| AC4 | per-file-ignore 목록에 KOR-str 5파일 + tests/** E501 | pyproject |
| AC5 | 376 green + 전체 ruff 게이트 클린 + CI green | pytest/Actions |
| AC6 | 래핑이 동작/가독성 보존(특히 SQL·시그니처) | 376 green + 리뷰 |
| AC7 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **per-file-ignore 과다 면제 위험**: KOR-str 파일에 진짜 코드 E501이 섞이면 면제로 새 긴 코드가 안 잡힘. → 각 파일 inspection으로 확인, 코드 라인이 유의미하면 그 라인 래핑 후 파일 ignore 대신 noqa 검토.
- **SQL/f-string 래핑 시 의미 변화**: 문자열 분할(implicit concat) 시 공백 누락 주의(`"a" "b"` → `"ab"`). 줄 끝/시작 공백 보존.
- **docstring 래핑**: 문장 분할이 자연스러운 곳만, 억지 분할 금지.
- **mixed 파일(_chat_stream.py)**: 2건 중 코드는 래핑, 한글이면 판단.
- 커밋 분리([[feedback_commit_style]]): (a) 코드 래핑, (b) 게이트+per-file-ignore, (c) docs.

## 7. Out-of-band Notes

- 잔여: C901(R8). `ruff format`은 보류(사용자 결정).
- 메모리 참조: [[project_lint_ramp_r3_r4]](R3→R6 이력), [[feedback_commit_style]], [[feedback_powershell_text_mangling]]
