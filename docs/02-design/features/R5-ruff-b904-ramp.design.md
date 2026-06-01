# R5-ruff-b904-ramp — Design

> **Cycle**: R5-ruff-b904-ramp
> **PDCA Phase**: Design
> **Date**: 2026-06-01
> **Plan**: [[R5-ruff-b904-ramp.plan]]

## 0. 정정 노트 (§0 자동삽입분 무효화 — git 증거 기반, 2026-06-01)

> Design 단계에 "B904는 처음부터 0건이라 §2의 7건은 이미 반영돼 있었고 변환 불필요" 라고
> 주장하는 §0가 자동 삽입됐으나, **이는 사실과 다르다.** 그 주장은 *7건을 실제로 수정한
> 이후* 시점의 `--no-cache` 측정(0건)을 "처음부터 0이었다"로 오독한 것이다.

**실측 증거 (git diff, [[feedback_agent_verification]] 원칙)**:

- Do 진입 직전 측정: `ruff check . --select B904 --statistics` → **7 B904** (위반 7건).
- §4 순서대로 7곳을 Edit로 수정 (각 Edit의 `old_string`에는 `from`이 **없었고** 정상 매칭됨 → 수정 전 코드에 `from`이 없었다는 결정적 증거).
- 수정 후 `git diff api/ shared/` → 신규 추가 라인 7개:
  - `) from e` ×1, `... detail=str(e)) from e` ×4, `) from None` ×1, `...cannot resolve ({e})") from e` ×1 = **6 `from e` + 1 `from None`**.
- 수정 후 측정: `ruff check . --select B904` → 0건. ← 이 0이 §0가 오독한 값.

**결론**: §2 매핑표는 자동삽입 §0의 주장과 달리 **실제로 이번 R5 세션에서 적용한 변환 명세가 맞다.** R5의 실코드 diff는 "pyproject 1줄"이 아니라 **7건 예외 체이닝 + 게이트 1규칙**이다. (캐시 함정 경고 자체는 유효 → 게이트 검증은 캐시 무관하게 `All checks passed` 확인함.)

## 1. 정책 — `from err` vs `from None` 결정 기준

B904는 두 가지 명시적 형태를 허용한다. 어느 쪽을 쓸지는 **원본 예외가 디버깅에 유용한가**로 가른다.

| 형태 | 효과(`__cause__`) | 트레이스백 | 적용 기준 |
|---|---|---|---|
| `raise New(...) from err` | 원본을 명시적 원인으로 연결 | `The above exception was the direct cause of...` | **타입이 바뀌거나** 원본 메시지/스택이 진단에 유용할 때 (기본 선택) |
| `raise New(...) from None` | 원인 체인 억제 | 원본 스택 숨김 | **동일 타입을 사용자 친화 메시지로 재포장**하여 원본이 순수 노이즈일 때만 |

**원칙**: 기본은 `from err`(원인 보존이 운영·디버깅에 유리, 정보 손실 0). `from None`은 *"같은 타입을 더 친절한 문구로 갈아끼우는"* 순수 재포장 — 즉 원본 스택이 사용자에게도 개발자에게도 가치가 없을 때만 좁게 사용한다. ([[feedback_default_shadowing]] 정신과 동일하게, 암묵 동작(`__context__`)을 명시 의도로 끌어올리는 것이 목표.)

### 1.1 변수명 규칙

- 기존에 `as e`가 있는 자리는 **`e` 유지**(파일 내 관례 보존, 불필요한 diff 회피).
- `except`에 변수가 없던 자리는 해당 파일의 기존 관례를 따른다. 두 대상 파일 모두 인근에서 `e`를 쓰므로 **`as e` 추가**로 통일(`exc` 신규 도입 안 함).

## 2. 7건 1:1 매핑 (변환 명세)

| # | 위치 | Before | After | 결정 | 근거 |
|---|---|---|---|---|---|
| 1 | `api/_http_helpers.py:30-34` | `except ValueError:` / `raise HTTPException(400, ...)` | `except ValueError as e:` / `raise HTTPException(400, ...) from e` | **from e** | `ValueError`→`HTTPException` 타입 변환. 잘못된 날짜 입력의 원본 traceback은 운영 진단에 유용 |
| 2 | `api/_http_helpers.py:43-44` | `except ValueError as e:` / `raise HTTPException(400, str(e))` | `... from e` | **from e** | 타입 변환 + 원인 보존 |
| 3 | `api/_http_helpers.py:51-52` | `except ValueError as e:` / `raise HTTPException(400, str(e))` | `... from e` | **from e** | 타입 변환 + 원인 보존 |
| 4 | `api/routers/notifications.py:69-70` | `except ValueError as e:` / `raise HTTPException(400, str(e))` | `... from e` | **from e** | store 검증 실패 → 400. 원본 보존 |
| 5 | `api/routers/notifications.py:97-98` | `except ValueError as e:` / `raise HTTPException(400, str(e))` | `... from e` | **from e** | 동일 패턴 |
| 6 | `shared/validators.py:31-34` | `except ValueError:` / `raise ValueError(f"Invalid {field}...")` | `except ValueError:` / `raise ValueError(...) from None` | **from None** | `ValueError`→`ValueError` **동일 타입** 재포장. `fromisoformat`의 원본 메시지(`Invalid isoformat string`)는 친절 메시지로 대체하는 것이 목적 → 원본은 노이즈. 변수 추가 불필요 |
| 7 | `shared/validators.py:161-164` | `except (OSError, RuntimeError) as e:` / `raise ValueError(f"...({e})")` | `... from e` | **from e** | `OSError/RuntimeError`→`ValueError` 타입 변환. 메시지에 `{e}` 이미 사용 → 원인 명시 일관 |

**요약**: 6건 `from e`, 1건(`validators.py:32`) `from None`. 유일한 `from None`은 "동일 타입 + 원본 노이즈"라는 명확한 기준을 충족하는 단일 케이스다.

## 3. 게이트 변경 (pyproject.toml)

```toml
# Before
select = ["F", "BLE001", "I", "UP"]
# After
select = ["F", "BLE001", "I", "UP", "B904"]
```

- **`B` 전체가 아니라 `B904` 단일 규칙만** 편입한다. `B008`(FastAPI `Depends` 기본인자)·`B905`(zip strict) 등 나머지 `B`는 별도 수정/검토가 필요하므로 R6로 미룬다.
- select에 규칙군(`B`)이 아닌 단일 코드(`B904`)를 넣으면 ruff는 그 규칙만 활성화 → 안전하게 1건씩 ramp 가능.
- 주석으로 "R5: B904만 단일 편입, B 나머지는 R6" 의도를 명시한다.

## 4. 구현 순서 (Do)

1. `shared/validators.py` 2건 수정 (32 → `from None`, 164 → `from e`)
2. `api/_http_helpers.py` 3건 수정 (31 → `as e`+`from e`, 44/52 → `from e`)
3. `api/routers/notifications.py` 2건 수정 (70/98 → `from e`)
4. `pyproject.toml` select에 `B904` 추가 + 주석
5. 게이트 검증: `ruff check . --select F,BLE001,I,UP,B904` → 0
6. import smoke + pytest 회귀

**커밋 분리** ([[feedback_commit_style]]): (a) 코드 변환 3파일, (b) 게이트 설정 1파일.

## 5. 영향도 / 회귀 분석

| 항목 | 영향 |
|---|---|
| 발생 예외 타입 | **불변** (HTTPException/ValueError 그대로) |
| status code / detail 메시지 | **불변** (텍스트 동일) |
| `__cause__` 메타데이터 | 변경 (암묵 `__context__` → 명시 `__cause__`/`None`) |
| 공개 API / 스키마 | **불변** |
| 기존 테스트 | status/detail만 검사 → **영향 0**. `test_input_validation`, `test_notifications`, `test_sql_validation`로 실증 |

## 6. 테스트 전략 (Check/QA)

- **게이트**: `ruff check . --select F,BLE001,I,UP,B904` → 0 errors (AC2)
- **import smoke**: `python -c "import api._http_helpers, api.routers.notifications, shared.validators"` (AC4)
- **회귀 pytest**: 검증 경로 집중 — `tests/test_input_validation.py`, `tests/test_notifications.py`, `tests/test_sql_validation.py` + 전체 스위트 (AC5/AC6)
- **잔여 통계**: `ruff check . --select B,SIM,E501 --statistics` 재기록 (AC7)
