# R4-import-pyupgrade-ramp — QA Report

> **Status**: PASS
> **Project**: Server_API
> **Date**: 2026-06-01
> **Design**: [[R4-import-pyupgrade-ramp]] (../02-design/features/R4-import-pyupgrade-ramp.design.md)
> **Method**: 정적 게이트 + import smoke + 전체 pytest (Zero Script QA 정신: 실제 명령 실행 결과로 판정)

## 1. 검증 매트릭스 결과

| # | 명령 | 기대 | 결과 | 판정 |
|---|---|---|---|:---:|
| V1 | `python -m ruff check . --select F,BLE001,I,UP` | 0 errors | `All checks passed!` | ✅ |
| V2 | `python -m ruff check . --select UP035` | 0 (R4 포함) | `All checks passed!` | ✅ |
| V3 | `python -c "import api.tools.items, api.tools.summary, shared.validators, tools.db_watcher"` | 예외 없음 | `SMOKE OK` | ✅ |
| V4 | `python -m pytest -q` | 306 passed | 306 passed (재실행) | ✅ |
| V5 | `git diff --stat` | import/annotation 국한 | 67 files, +302/-298, 로직 변경 0 | ✅ |

## 2. Flaky 테스트 처리

`tests/test_notifications_bulk_retry.py::test_requeued_delivery_is_dispatched_by_worker`

| 항목 | 내용 |
|---|---|
| 증상 | 1차 full-suite 실행에서 `assert _status_of(did) == "queued"` 가 `'success'` 로 실패 |
| 원인 | webhook dispatch worker가 백그라운드에서 재시도를 이미 처리(`queued`→`success`)한 **타이밍 레이스**. 전체 suite 실행 순서에서만 발현. |
| R4 관련성 | **없음** — 이 테스트 파일·대상 런타임 동작은 R4에서 불변(import 순서·annotation만 변경). |
| 검증 | 단독 실행 **5/5 passed**, full-suite 재실행 **306 passed**. 비결정적 flaky로 확정. |
| 후속 | worker 레이스 안정화는 R4 비범위. notifications 테스트 격리 강화 별도 후보(메모리 [[project_pytest_tmproot_strategy]] 계열). |

## 3. 적용 규모

| 항목 | 값 |
|---|---:|
| 변경 파일 | 67 |
| I001 import 정렬 | 62건 |
| UP safe autofix | 121건 |
| UP035 unsafe autofix | 19건 |
| 파생 F401 해소 | 28건 |
| 런타임/스키마/공개 API 변경 | **0** |

## 4. 잔여 ramp baseline (post-R4)

명령: `python -m ruff check . --select E501,SIM,B --statistics`

| 규칙 | 건수 | 차기 |
|---|---:|---|
| E501 line-too-long | 110 | 포매팅 정책 결정 후 별도 |
| SIM105 suppressible-exception | 17 | R6 |
| B904 raise-without-from | 7 | **R5 우선** |
| SIM117 multiple-with | 7 | R6 |
| B017/B905/B025/B007 | 9 | R5 |
| SIM102/108/300 | 8 | R6 |

**합계 158** (R3 시점 360 → R4에서 I/UP 202건 회수, 잔여 158).

## 5. 판정

**PASS** — 게이트 green, import smoke green, pytest 306 passed(회귀 0), diff가 기계 변환에 국한. AC1–AC7 충족.
