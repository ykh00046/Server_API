# R6-ruff-bugbear-sim-ramp — Plan

> **Cycle**: R6-ruff-bugbear-sim-ramp
> **PDCA Phase**: Plan
> **Date**: 2026-06-15
> **Project**: Production Data Hub
> **Summary**: ruff 게이트를 `B`(bugbear 전체) + `SIM`(simplify)로 확장하는 R6 램프. 위반 41건 해소 — src의 B는 전부 수정, tests의 B017(broad raises)은 per-file-ignore, SIM은 autofix + 수동 판단. [[project_lint_ramp_r3_r4]] 후속(R3→R5에 이어).

## 1. Background (실측 2026-06-15)

현재 게이트: `select = ["F", "BLE001", "I", "UP", "B904"]`. R6 후보 `B,SIM` 위반 **41건**:

| 규칙 | 수 | 위치 | 처리 |
|------|---:|------|------|
| SIM105 (suppressible-exception) | 17 | src/tests/tools/manager 분산 | `contextlib.suppress`로 전환(타당한 곳) 또는 케이스별 판단 |
| SIM117 (multiple-with) | 7 | dashboard/components 등 | autofix |
| SIM102 (collapsible-if) | 4 | 분산 | 수동(가독성 판단) |
| SIM108 (if-else→ternary) | 3 | 분산 | 수동(가독성 판단) |
| SIM300 (yoda) | 1 | — | autofix |
| B017 (assert-raises-Exception) | 3 | **tests/test_input_validation.py** | **per-file-ignore**(broad raises 관용) |
| B905 (zip-without-strict) | 3 | dashboard/app.py·views.py·products.py | 수정(`strict=...` 명시) |
| B025 (duplicate-try) | 2 | shared/db_maintenance.py(x2) | 수정 |
| B007 (unused-loop-var) | 1 | shared/rate_limiter.py | 수정(`_` 처리) |

자동수정 가능: 8건(SIM117x7 + SIM300x1). 나머지는 수동.

## 2. Goal

1. **src의 B 위반 전부 수정**: B905(zip strict 명시), B025(중복 except 블록 정리), B007(미사용 루프 변수 `_`).
2. **tests B017 per-file-ignore**: `tests/**`에 B017 추가(이미 F401/BLE001 면제 중). `pytest.raises(Exception)`는 "예외 발생 여부"만 보는 의도적 광범위 검증.
3. **SIM 처리**: autofix(SIM117/300) 적용 + 수동(SIM105는 `contextlib.suppress`가 명확히 나은 곳만, SIM102/108은 가독성 향상 시만). 억지 변환 금지 — 불명확하면 해당 라인 `# noqa: SIMxxx` + 사유 대신 케이스별 보존 판단.
4. **게이트 확장**: 위반 0 달성 후 `select`에 `B`, `SIM` 추가.
5. **회귀 0**: 376 green, CI green.

## 3. Non-Goals (defer)

- E501(line-too-long, 110건) — 별도 R7(`ruff format` 도입과 묶음).
- C901(complexity) — 별도(baseline 임계값 방식).
- B008(FastAPI Depends 기본인자) 등 의도적 패턴 — 발생 시 noqa 또는 per-file 처리, 게이트 확장이 깨면 재검토.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **수정(src B)** | `dashboard/app.py`, `dashboard/components/webhook_admin/views.py`, `dashboard/views/products.py`, `shared/db_maintenance.py`, `shared/rate_limiter.py` |
| **수정(SIM)** | dashboard/components, tools/backup_db.py, tools/create_indexes.py, manager.py, api/notifications, api/routers, shared/_db_connection.py, shared/database.py, shared/process_utils.py, tests/* |
| **수정(게이트)** | `pyproject.toml`(select +B +SIM, per-file-ignores tests +B017) |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `ruff check . --select B,SIM` 0 errors (per-file-ignore 적용 후) | ruff |
| AC2 | src의 B905/B025/B007 코드 수정(noqa 남발 없이) | diff |
| AC3 | tests/** per-file-ignore에 B017 추가, src엔 B017 없음 | pyproject + grep |
| AC4 | select에 B, SIM 추가 — 게이트가 신규 위반 차단 | pyproject |
| AC5 | SIM 변환이 동작 보존(특히 SIM105 contextlib.suppress, SIM102/108) | 376 green |
| AC6 | 376 green + ruff 클린 + CI green | pytest/Actions |
| AC7 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **B905 zip strict 의미 변화**: `strict=True`는 길이 불일치 시 raise. 기존이 의도적으로 짧은 쪽에 맞췄다면 `strict=False` 명시가 정답. 각 호출의 의도 확인 후 결정(대부분 동일 길이 → strict=True 안전).
- **B025 중복 except**: db_maintenance.py 2곳 — 같은 예외를 두 번 잡는 구조라면 병합. 의미 보존 주의.
- **SIM105 contextlib.suppress 남용 금지**: try/except pass가 로깅·주석을 동반하면 suppress 전환이 의도를 가린다. **순수 무음 pass만** 전환, 나머지는 보존(필요시 noqa).
- **SIM102/108 가독성**: collapsible-if/ternary가 항상 더 읽기 좋은 건 아님 — 복잡 조건은 보존 판단.
- **테스트 코드 SIM**: tests/*의 SIM도 게이트 대상이 되나, 픽스처 패턴 등 관용은 per-file 검토.
- 커밋 분리([[feedback_commit_style]]): (a) src B 수정, (b) SIM 수정, (c) 게이트 확장 + per-file-ignore, (d) docs.

## 7. Out-of-band Notes

- 잔여 후속: R7(E501 + ruff format), C901(complexity baseline).
- 메모리 참조: [[project_lint_ramp_r3_r4]](R3→R5 램프 이력·stale §0 주의), [[feedback_commit_style]], [[feedback_powershell_text_mangling]](비ASCII noqa 사유는 Edit로)
