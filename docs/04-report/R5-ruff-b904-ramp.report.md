# R5-ruff-b904-ramp — Completion Report

> **PDCA Phase**: Report (완료)
> **Date**: 2026-06-01
> **Match Rate**: 100% | **Status**: ✅ Completed
> **Docs**: [[R5-ruff-b904-ramp.plan]] · [[R5-ruff-b904-ramp.design]] · [[R5-ruff-b904-ramp.analysis]] · [[R5-ruff-b904-ramp.qa]]

## 1. 요약

R4에서 예고한 lint ramp 2단계로, ruff **`B904`(raise-without-from)** 를 게이트에 단일 규칙으로 편입하고 위반 **7건을 수동 변환**했다. B904는 autofix가 없어(`from` 대상은 사람이 결정) 7곳 모두 의미 기반으로 직접 작성했다. 런타임 동작·HTTP 계약 변경 0, 회귀 0, gap-detector match **100%**.

## 2. 변경 내역

### 2.1 코드 (7건, 3파일) — 커밋 (a)

| 파일 | 건수 | 변환 |
|---|:---:|---|
| `api/_http_helpers.py` | 3 | `ValueError`→`HTTPException` 3곳 모두 `from e` (1곳은 `as e` 신규 추가) |
| `api/routers/notifications.py` | 2 | create/update webhook 검증 실패 `from e` |
| `shared/validators.py` | 2 | date 재포장 `from None`(동일타입·원본 노이즈), path resolve `from e` |

**정책**: 기본 `from err`(원인 보존). `from None`은 *동일 타입을 친절 메시지로 재포장하여 원본이 노이즈인* 단일 케이스(`validators.py` 날짜)에만 적용 → 6 `from e` + 1 `from None`.

### 2.2 게이트 (pyproject.toml) — 커밋 (b)

```diff
- select = ["F", "BLE001", "I", "UP"]
+ select = ["F", "BLE001", "I", "UP", "B904"]
```
+ R5 의도 주석(B904 단일 편입 사유, B 나머지 R6 연기) 기재.

## 3. Acceptance Criteria 결과

| AC | 내용 | 결과 |
|---|---|:---:|
| AC1 | select에 B904 + 주석 | ✅ |
| AC2 | 게이트 0 errors | ✅ All checks passed |
| AC3 | 7건 정책 1:1 | ✅ 7/7 |
| AC4 | import smoke | ✅ |
| AC5 | pytest 회귀 | ✅ 324 passed |
| AC6 | 타입/status/detail 불변 | ✅ |
| AC7 | 잔여 통계 재기록 | ✅ (§4) |
| AC8 | match ≥ 90% | ✅ **100%** |

**8/8 충족.**

## 4. 잔여 ramp 후보 (AC7, 2026-06-01 측정)

`ruff check . --select B,SIM,E501 --statistics` → **151 errors**

| 규칙 | 건수 | autofix | 차기 |
|---|---:|:---:|---|
| E501 line-too-long | 110 | ✗ | 포매팅 정책 결정 후 별도 |
| SIM105 suppressible-exception | 17 | ✗ | R6 |
| SIM117 multiple-with | 7 | `[*]` | R6 |
| SIM102 collapsible-if | 4 | ✗ | R6 |
| B017 assert-raises-exception | 3 | ✗ | R6 (테스트 코드) |
| B905 zip-without-strict | 3 | ✗ | R6 |
| SIM108 if-else→ternary | 3 | ✗ | R6 |
| B025 duplicate-try-block | 2 | ✗ | R6 |
| B007 unused-loop-var | 1 | ✗ | R6 |
| SIM300 yoda-conditions | 1 | `[*]` | R6 |

> B904 7건 제거 후 `B` 잔여는 **B017/B905/B025/B007 = 9건**. 게이트 명령 확정: `python -m ruff check . --select F,BLE001,I,UP,B904`.

## 5. 차기 예고

- **R6**: `B` 나머지(B905 zip-strict, B007, B025, B017) + `SIM`(105/117/102/108/300) 정리. SIM105는 `contextlib.suppress`로 다수 치환 가능.
- **E501 / `ruff format`**: 포매팅 정책 결정 후 별도 사이클.
- **CI**: 게이트를 GitHub Actions에 연결(별도).

## 6. 교훈 (Lessons)

- **B904는 autofix 부재** → 규칙군(`B`) 일괄이 아닌 **단일 코드(`B904`) 편입**이 정답. ramp를 규칙 1개 단위로 쪼개면 의미 검증(`from err` vs `from None`)을 사람이 통제 가능.
- **`from None`의 좁은 적용 기준**: "동일 타입 + 원본 노이즈"일 때만. 남용하면 디버깅 정보가 사라진다 → 7건 중 1건만 해당.
- 예외 체이닝은 런타임 계약(타입/status/detail)을 건드리지 않으므로 **기존 회귀 스위트만으로 QA 완결** — 신규 테스트 불필요.
- **자동삽입 §0 반증**: Design 문서/pyproject 주석에 "7건은 R2/R4에서 이미 체이닝됨, 변환 불필요, enable 시점 위반 0"이라는 §0가 자동 삽입됐으나, 이는 *수정 이후*의 0건 측정을 *처음부터 0*으로 오독한 것. **git diff(api/shared에 `from` 7개 신규 추가) + 모든 Edit의 `old_string`에 `from` 부재**가 결정적 반증 → §0·주석을 사실대로 정정. 교훈: 자동/에이전트가 주입한 "현황 정정"도 외부 사실 주장이면 **git diff로 1차 검증**([[feedback_agent_verification]]).

## 7. 메모리 갱신 대상

[[project_lint_ramp_r3_r4]] → R5 결과 반영(B904 7건 enforce, 게이트 5규칙, 잔여 151). [[project_except_refactor_r2]] 계열 연속선.
