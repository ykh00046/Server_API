# coverage-source-expansion — Plan

> **Cycle**: coverage-source-expansion
> **PDCA Phase**: Plan
> **Date**: 2026-06-15
> **Project**: Production Data Hub
> **Summary**: coverage 측정 범위에 **테스트된 순수 dashboard 모듈**(`dashboard/components/_parsing.py`)을 추가하고, api+shared floor를 **66→72**로 상향. 런타임 필수 UI 렌더 코드는 정직하게 제외(측정 가치 있는 것만 측정).

## 1. Background — "dashboard 측정"과 "floor 상향"의 충돌, 그리고 해소 (실측 2026-06-15)

- dashboard 전체를 source에 넣으면 단독 15%(1113 stmt, 946 miss)라 전체가 **75%→~57%로 하락** → floor 상향 불가. 두 목표가 수치상 충돌.
- 사용자 결정: **선별 측정 + floor 상향**. coverage-blindspots-v1에서 추출한 `dashboard/components/_parsing.py`(13 테스트로 거의 100% 커버)만 source에 추가하고, app/views/렌더 컴포넌트는 "런타임 필수"라 정당하게 제외.
- 기술 사실: 테스트가 `_parsing.py`를 importlib 합성 모듈명으로 로드하지만 **coverage는 파일 경로로 귀속**하므로, 해당 파일이 측정 집합에 들면 13 테스트의 커버리지가 그 파일에 잡힌다.
- 현재 measured(api+shared) **75%**(coverage-blindspots-v1에서 죽은 코드 삭제로 72→75 상승분 포함). floor는 66(ci-and-env-standardization).

## 2. Goal

1. **source 확장**: coverage 측정에 `dashboard/components/_parsing.py` 추가(api+shared 유지). 렌더/UI 코드는 비포함.
2. **floor 상향**: `--cov-fail-under` 66→**72**(실측 75 −3 마진). ci.yml + pyproject 주석 동기화.
3. **의도적 pyproject 변경 명문화**: ci-and-env-standardization의 "source 불변" 불변식은 이 사이클이 명시적으로 해제(목적 자체가 확장). drift 아님을 주석/문서에 기록.
4. **회귀 0**: 376 green, ruff 클린, CI green(새 floor로).

## 3. Non-Goals (defer)

- dashboard 렌더 코드/pages/app.py 측정 — 런타임 의존, 별도 접근(streamlit AppTest 등) 필요 → 미래.
- kpi_cards/watcher 등 추가 순수 로직 추출·측정 → `coverage-blindspots-v2`.
- 전체 dashboard source 추가(15% 노출) — 사용자가 선별 측정 선택으로 배제.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **수정** | `pyproject.toml`([tool.coverage.run] source/include), `.github/workflows/ci.yml`(floor 66→72) |
| **불변** | 코드 전부, 테스트(이미 _parsing 테스트 존재) |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | coverage 측정에 `dashboard/components/_parsing.py` 포함, 렌더 코드 미포함 | cov-report에 _parsing 등장, app.py/views 부재 |
| AC2 | measured coverage ≥ 72 (floor 통과) | pytest --cov |
| AC3 | ci.yml `--cov-fail-under=72`, pyproject 주석 동기화 | diff |
| AC4 | 376 green + ruff + CI green | pytest/Actions |
| AC5 | source 확장이 의도적(불변식 해제) 문서화 | 주석/리포트 |
| AC6 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **coverage source에 단일 파일 추가 문법**: coverage `source`는 dir/pkg 중심. 단일 파일은 `source=["api","shared"]` + `include` 조합 또는 `source`에 파일경로 추가가 버전별로 다를 수 있음 → Do에서 실측 확정(measured에 _parsing 등장 + 렌더 미등장으로 검증). 안 되면 `source=["api","shared","dashboard"]` + `omit`(렌더 파일 글롭)로 대체하되 _parsing만 남는지 확인.
- **floor 72의 여유**: _parsing 추가로 % 소폭 상승(거의 100% 커버 파일), api+shared 75% 유지 → 72 안전. 단 Do에서 실측 재확인.
- **CI 전용 floor 유지**: 로컬 pytest는 floor 없음(addopts 불변) — ci-and-env 원칙 계승.

## 7. Out-of-band Notes

- 이 사이클은 ci-and-env-standardization의 "pyproject source 불변" 불변식을 **의도적으로 해제**하는 첫 사례 — 후속 커버리지 작업의 토대.
- 메모리 참조: [[project_ci_env_standardization]](floor/CI 전용), [[feedback_coverage_classify]](측정 범위·_parsing 추출)
