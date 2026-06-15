# R6-ruff-bugbear-sim-ramp — Gap Analysis

> **Cycle**: R6-ruff-bugbear-sim-ramp
> **PDCA Phase**: Check
> **Date**: 2026-06-15
> **Plan**: [[R6-ruff-bugbear-sim-ramp.plan]]
> **Match Rate**: **100%** (AC 7/7)

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | `ruff check . --select B,SIM` 0 errors | per-file-ignore 적용 후 0 (전체 게이트 All checks passed) | ✅ |
| AC2 | src B905/B025/B007 수정(noqa 남발 없이) | B905 strict=True 3곳, B025 dup-except→Exception 2곳(실버그), B007 `_ip` 1곳 — 전부 코드 수정 | ✅ |
| AC3 | tests B017 per-file-ignore, src B017 0 | `tests/**`=[F401,BLE001,B017], src에 B017 없음 | ✅ |
| AC4 | select에 B, SIM 추가 | `select=["F","BLE001","I","UP","B","SIM"]` | ✅ |
| AC5 | SIM 변환 동작 보존 | SIM105 17건 contextlib.suppress(주석 보존), SIM117/300/102/108 autofix+수동. 376 green | ✅ |
| AC6 | 376 green + ruff + CI | 376 passed, All checks passed, CI(아래) | ✅ |
| AC7 | match rate ≥ 90% | 100% | ✅ |

## 처리 내역 (41건)

| 규칙 | 수 | 처리 |
|------|---:|------|
| B905 | 3 | `strict=True` 명시(전부 동일 길이) |
| B025 | 2 | **실버그 수정** — db_maintenance 중복 `except sqlite3.Error`(도달 불가)를 주석 의도대로 `except Exception`(IO 등 마지막 안전망)으로 |
| B007 | 1 | rate_limiter `ip`→`_ip` |
| B017 | 3 | tests per-file-ignore(broad raises 관용) |
| SIM105 | 17 | `contextlib.suppress`(12 autofix + 5 수동, 주석 `with` 위로 보존) |
| SIM117 | 7+1 | autofix(+ suppress 변환이 만든 manager 중첩 with 1건 추가 병합) |
| SIM102 | 4 | 중첩 if→`and`(수동, 가독성 보존 래핑) |
| SIM108 | 3 | if/else→삼항(autofix) |
| SIM300 | 1 | autofix |

## 부수 발견

- **B025가 실버그를 잡음**: db_maintenance.py의 두 함수에서 `except sqlite3.Error`가 중복돼 두 번째 블록이 도달 불가였다. 주석은 "sqlite3.Error 외(IO 등) 마지막 안전망"이라 의도는 broad catch였으나 코드가 잘못 작성됨 → `except Exception`으로 수정해 의도 복원. 린트 램프가 죽은 예외 핸들러를 드러낸 사례.
- **suppress 변환의 연쇄**: SIM105→contextlib.suppress가 manager에서 `with lock: with suppress():` 중첩(SIM117)을 새로 만들어 추가 병합 필요. autofix 후 재검사로 포착.

## 권장 조치

없음 — **100% → Report.** 후속 R7: E501(110건) + `ruff format`, C901(complexity baseline).
