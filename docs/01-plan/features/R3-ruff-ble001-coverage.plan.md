# R3-ruff-ble001-coverage — Plan

> **Cycle**: R3-ruff-ble001-coverage
> **PDCA Phase**: Plan
> **Date**: 2026-05-28
> **Predecessors**: [[except-exception-refactor-r2]] (R2-1, 46→23, 50%↓) 보고서에서 예고한 "R3: ruff BLE001 활성화(정적 차단 도입)"
> **Round**: R3 (정적 게이트 도입)

## 1. Background

R2-1에서 핵심 영역(api/shared/dashboard)의 `except Exception`을 수동으로 23곳까지 줄이고 무음 swallow를 0으로 만들었다. 그러나 **수동 정리는 회귀를 막지 못한다** — 새 코드에서 다시 `except Exception:`이 들어와도 차단 장치가 없다. R3는 이를 **정적 게이트(ruff BLE001)** 로 고정한다.

또한 ruff를 **처음 도입**하면서 현재 코드베이스의 린트 부채를 1회 측정해 베이스라인으로 기록하고, `pytest-cov`로 테스트 커버리지 베이스라인도 함께 확정한다 (3종 묶음).

### 도입 즉시 발견된 실제 잠복 버그 (ruff F 게이트의 가치 입증)

측정 중 `ruff --select F` 가 **7건의 undefined-name(F821)** 을 발견했고, 그중 4건은 R2-1 narrowing이 남긴 실제 버그였다:

| 위치 | 패턴 | 위험 |
|---|---|---|
| `api/tools/items.py:101,166` | `except (sqlite3.Error, KeyError)` 인데 **`import sqlite3` 누락** | 예외 발생 시 except 절 평가에서 `NameError` → 원래 에러를 가리고 핸들러 자체가 깨짐 |
| `api/tools/summary.py:163,224` | 동일 | 동일 |
| `shared/validators.py:167` | `Path` 미import(별칭 `_P`만 존재) | 해당 분기 진입 시 `NameError` |
| `scripts/perf_smoke.py:43` | `requests` 미import | 실행 시 `NameError` |
| `tools/db_watcher.py:56` | `sqlite3` 미import | 동일 |

→ R3는 게이트 도입과 동시에 이 잠복 버그들을 제거한다.

### 측정된 린트 현황 (webcloring-pdf 제외, in-scope dirs)

| 규칙군 | 건수 | R3 처리 방침 |
|---|---|---|
| **F** (pyflakes 실오류) | 35 | **게이트 enforce** — 전부 수정 (F401×22 autofix, F821×7 버그수정, F841×3, F541×2, F811×1) |
| **BLE001** (blind-except) | 8 (전부 tools/scripts/manager.py) | **게이트 enforce** — narrow 또는 `# noqa: BLE001`+사유 |
| E501 line-too-long | 226 | **미적용** (베이스라인 기록만, 노이즈 과다) |
| I001 unsorted-imports | 52 | 미적용 (향후 ramp) |
| UP006/045/035/037/007 등 | ~126 | 미적용 (향후 ramp) |
| B904/B905/B025/B007 | ~13 | 미적용 (향후 ramp, B904 우선 후보) |
| SIM105/102/108/117 | ~19 | 미적용 (향후 ramp) |

## 2. Goal

1. **ruff 도입** — `pyproject.toml`에 단일 소스로 ruff 설정. dev 의존성(requirements)에 ruff 명시.
2. **BLE001 게이트 green (repo-wide)** — webcloring-pdf 제외 전 영역에서 `ruff check --select F,BLE001` 0 errors. 신규 blind-except 회귀를 정적으로 차단.
3. **pytest-cov 베이스라인** — coverage 설정(pyproject) + 현재 커버리지 % 측정·기록 + 회귀 방지용 `--cov-fail-under` 권장 floor 문서화.
4. **잠복 버그 제거** — F821 7건(미import 등) 수정, F401 unused-import 정리.
5. **회귀 0** — 기존 pytest suite green 유지(기존 알려진 flaky 제외).

## 3. Non-Goals (defer)

- **E501/I/UP/SIM/B 적용** — 베이스라인 측정만, enforce는 향후 ramp 사이클(R4)에서 단계적.
- **R2-2 narrowing** — tools/scripts/manager.py의 `except Exception`을 narrow로 바꾸는 품질 작업은 R2-2 별도. R3는 게이트 통과를 위해 **`# noqa: BLE001`+사유**만 부여(또는 trivial한 곳만 narrow).
- **webcloring-pdf/** — submodule 분리 예정, ruff exclude로 전체 제외.
- **CI 파이프라인 작성** — 게이트 *명령*만 정의, GitHub Actions 등 외부 CI 연결은 별도.
- **pre-commit hook 설치** — 권장 명령만 문서화, 훅 설치는 사용자 환경 결정.

## 4. Dependencies

| 종류 | 항목 | 상태 |
|------|------|------|
| Tool | `ruff` 0.15.10 | ✅ 설치됨 |
| Tool | `pytest-cov` | ✅ 설치됨 |
| Tool | `pytest` 9.0.2 | ✅ |
| 신규 외부 런타임 의존성 | — | **0** (둘 다 dev-only) |

## 5. Scope (대상)

| 구분 | 대상 |
|---|---|
| **게이트 적용(enforce)** | `api/`, `shared/`, `dashboard/`, `tools/`, `scripts/`, `manager.py`, `tests/` |
| **per-file-ignore** | `tests/**` → BLE001 무시(테스트 catch-all 정당) |
| **전체 제외(exclude)** | `webcloring-pdf/`, `.venv*`, `.smoke-venv*`, `dist/`, `build/`, `docs/`, `logs/`, `.pytest_tmp/` |
| **enforce 규칙** | `F`(all), `BLE001` |
| **coverage source** | `api/`, `shared/` (핵심 백엔드) |

## 6. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | `pyproject.toml`에 `[tool.ruff]`+`[tool.ruff.lint]` 설정 존재, select=`F,BLE001`, target py312, webcloring-pdf exclude | 파일 검사 |
| AC2 | `ruff check api shared dashboard tools scripts manager.py tests --select F,BLE001` → **0 errors** | shell |
| AC3 | F821 7건 전부 수정(미import 추가) — 해당 모듈 import 성공 | `ruff --select F821` 0 + import 테스트 |
| AC4 | tools/scripts/manager.py의 BLE001 8건 → narrow 또는 `# noqa: BLE001`+1줄 사유 | `ruff --select BLE001` 0 |
| AC5 | `[tool.coverage.run]`/`[tool.coverage.report]` 설정 존재(source=api,shared) | 파일 검사 |
| AC6 | coverage 베이스라인 % 측정·보고서 기록, `--cov-fail-under` 권장 floor 명시 | 보고서 |
| AC7 | dev 의존성에 `ruff`, `pytest-cov` 명시(requirements) | 파일 검사 |
| AC8 | 기존 pytest 회귀 green(알려진 flaky tmpdir/rate-limit timing 제외) | pytest 실행 |
| AC9 | E501/I/UP/SIM/B 베이스라인 통계 보고서 기록(향후 ramp 근거) | 보고서 |
| AC10 | gap-detector match rate ≥ 90% | Check phase |

## 7. Constraints / Risks

- **F821 수정의 부수효과**: `import sqlite3` 추가로 R2가 의도한 narrowing이 *비로소* 동작 → 기존엔 NameError로 죽던 경로가 정상 error-dict 반환으로 바뀜. **동작 개선**이며 회귀 아님. (단 `# noqa: BLE001` 주석은 더 이상 BLE001을 유발하지 않으므로 무해 — 주석 정리는 R3 비범위.)
- **flaky full-suite**: 전체 pytest는 tmpdir 권한 race / rate-limiter 60초 timing으로 알려진 flaky 존재([[project_pytest_tmproot_strategy]], [[project_review_fixes_202604]]). → `--cov-fail-under`를 **기본 addopts에 넣지 않음**(opt-in). 커버리지 측정은 별도 명령으로.
- **scope creep 방지**: E501 등 226건을 건드리면 거대 diff. R3는 **F+BLE001만 enforce**, 나머지는 측정만.
- **deferred BLE001 noqa**: tools/scripts/manager.py에 noqa를 다는 것은 임시 부채 표식 — R2-2에서 narrow로 대체 예정임을 보고서에 명시.
- **호환성**: 런타임 동작/스키마 변경 0(F821 버그수정은 깨진 핸들러 복구). 외부 API 영향 없음.

## 8. Out-of-band Notes

- **연쇄 사이클 예고**:
  - R2-2: tools/scripts/manager.py `except Exception` narrow(품질) — R3의 noqa를 narrow로 대체
  - R4: ruff ramp — I(import정렬) → UP(pyupgrade) → B904 → SIM 단계적 enforce
  - CI: 게이트 명령을 GitHub Actions/pre-commit에 연결(별도)
- **게이트 명령(확정 예정, Design에서)**: `ruff check . --select F,BLE001`
- **메모리 참조**: [[project_except_refactor_r2]], [[feedback_commit_style]](레이어별 커밋 분리)
