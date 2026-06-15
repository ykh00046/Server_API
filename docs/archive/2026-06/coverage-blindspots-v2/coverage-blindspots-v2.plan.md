# coverage-blindspots-v2 — Plan

> **Cycle**: coverage-blindspots-v2
> **PDCA Phase**: Plan
> **Date**: 2026-06-15
> **Project**: Production Data Hub
> **Summary**: dashboard `kpi_cards.py` 순수 함수(5개)에 단위 테스트를 붙이고 coverage 측정에 포함. `tools/watcher.py`의 `load_state`/`save_state`도 단위 테스트(상태 fallback/roundtrip). 측정 가치 있는 순수 로직만 측정 — 렌더/IO 오케스트레이션은 제외(v1 원칙 계승).

## 1. Background (실측 2026-06-15)

coverage-blindspots-v1에서 "0% 파일은 분류(삭제 vs 테스트)" 통찰로 죽은 코드 삭제 + _parsing 추출·측정했고, coverage-source-expansion에서 `source=api,shared,dashboard` + omit-화이트리스트로 _parsing만 측정(floor 72). v2는 **남은 순수 로직**을 같은 패턴으로 측정.

- **kpi_cards.py**(dashboard): `calculate_kpis`/`get_sparkline_data`/`get_sparkline_for_top_product`/`_format_number`/`_has_signal` — 전부 DataFrame/스칼라 입력 **순수 함수, IO·streamlit 0**. 현재 omit 화이트리스트에 포함돼 미측정. 테스트도 없음.
- **watcher.py**(tools): `load_state`(파일 없음/손상 JSON → 기본 dict fallback), `save_state`(write roundtrip)는 단위 테스트 가능. 단 `run_check`는 DB(`check_and_heal_indexes`/`run_analyze`)+FS+time 결합 오케스트레이션 → 단위 부적합(통째 측정 시 floor 붕괴).
- `render_kpi_cards`(kpi_cards)는 `st.metric` 호출이라 런타임 필요 → 측정 제외(렌더부).

## 2. Goal

1. **kpi_cards 순수 함수 테스트**: `tests/test_kpi_cards.py` 신규 — calculate_kpis(빈/정상/단일제품), get_sparkline_data(패딩/빈), get_sparkline_for_top_product, _format_number(K/M 경계), _has_signal. streamlit 비의존(importlib 격리 로드, _parsing 선례).
2. **kpi_cards.py 측정 포함**: pyproject omit 화이트리스트에서 `dashboard/components/kpi_cards.py` 제거 → 측정 대상. `render_kpi_cards`(렌더부)는 측정되나 미커버 — 순수 함수가 다수라 파일 전체 커버리지는 높게 유지(목표 파일 ≥75%).
3. **watcher load/save 테스트**: `tests/test_watcher_state.py` 신규 — load_state(missing→default, corrupt JSON→default), save_state(roundtrip), tmp_path + monkeypatch STATE_FILE. **watcher.py는 coverage source에 미추가**(run_check 미측정 — test-only, floor 보호).
4. **floor 유지/소폭**: 측정 추가로 % 영향 실측. floor 72 유지(또는 여유 시 상향 판단). pyproject source/floor 변경은 신중.
5. **회귀 0 + CI green**.

## 3. Non-Goals (defer)

- `run_check`/`run_daemon` 측정·테스트 — IO 오케스트레이션, 추출 비용 큼.
- `render_kpi_cards` 렌더 테스트(streamlit AppTest) — 별도 `dashboard-apptest-v1`.
- watcher.py를 coverage source에 추가 — run_check 미측정이라 floor 붕괴 위험, test-only로.
- floor 대폭 상향 — 측정 추가분으로 인플레 금지.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **신규 테스트** | `tests/test_kpi_cards.py`, `tests/test_watcher_state.py` |
| **수정** | `pyproject.toml`(omit에서 kpi_cards.py 제거) |
| **불변** | kpi_cards.py/watcher.py 코드(테스트만 추가), floor(원칙적 유지) |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | test_kpi_cards.py — 5개 순수함수 ≥8 케이스 green | pytest |
| AC2 | test_watcher_state.py — load/save ≥4 케이스(missing/corrupt/roundtrip) green | pytest |
| AC3 | kpi_cards.py가 coverage 측정에 포함(cov-report 등장), 파일 ≥75% | cov-report |
| AC4 | watcher.py는 source 미포함(run_check 미측정으로 floor 안전) | cov-report 부재 확인 |
| AC5 | 전체 measured coverage ≥ 72(floor 유지) | pytest --cov |
| AC6 | 376+ 기존 + 신규 green, ruff 클린, CI green | pytest/Actions |
| AC7 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **kpi_cards 측정이 % 낮출 위험**: `render_kpi_cards`(렌더부, ~25 stmt) 미커버가 파일을 끌어내림. 순수 함수(~40 stmt)가 다수라 파일 ≥75% 예상이나 Do에서 실측. 전체 floor 72 위협 시 floor 미상향 + 파일 커버리지만 확보.
- **streamlit import 회피**: kpi_cards.py는 `import streamlit as st`가 top-level → importlib 격리 로드(_parsing/test_webhook_admin_ui 선례)로 streamlit 끌어오되, 순수 함수 호출엔 streamlit 런타임 불필요(import만 됨, 호출 안 함). 단 `render_kpi_cards`는 테스트 안 함.
- **watcher STATE_FILE 격리**: 모듈 상수 STATE_FILE을 monkeypatch 또는 tmp 경로 주입. load_state가 STATE_FILE을 런타임 조회하는지 확인(import 시 바인딩이면 monkeypatch 주의 — [[feedback_default_shadowing]]).
- 커밋 분리([[feedback_commit_style]]): (a) 테스트 추가, (b) pyproject 측정 포함, (c) docs.

## 7. Out-of-band Notes

- v1/expansion 패턴 계승: "측정 가치 있는 순수 로직만, 렌더/IO 제외".
- 후속: `dashboard-apptest-v1`(렌더 테스트), run_check 리팩터+측정.
- 메모리 참조: [[feedback_coverage_classify]], [[project_ci_env_standardization]], [[feedback_default_shadowing]]
