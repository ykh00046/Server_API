# coverage-blindspots-v2 Completion Report

> **Summary**: dashboard kpi_cards 순수함수 5개에 단위 테스트를 붙이고 coverage 측정에 포함(88%), tools watcher의 load_state/save_state 단위 테스트(test-only). 렌더/run_check IO는 v1 원칙대로 제외.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-15
> **Match Rate**: 100% (AC 7/7 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 커밋 |
|----|------|------|
| T1 | test_kpi_cards.py(9 케이스) + test_watcher_state.py(4 케이스) | f12e36d |
| T2 | pyproject omit에서 kpi_cards.py 제거 → 측정 포함(88%) | c50bdcf |

## 2. 검증 결과

- ✅ AC1~AC7 전부 PASS (**100%**)
- ✅ kpi_cards.py **88%** 측정(순수함수 커버, render 렌더부만 미커버)
- ✅ measured **75→76.30%**, floor 72 통과(4pp 마진, 미상향)
- ✅ **376→389 tests** green, ruff clean, CI green
- ✅ watcher.py는 source 미추가(run_check IO 미측정으로 floor 보호 — test-only)

## 3. PDCA 메타데이터

```yaml
cycle: coverage-blindspots-v2
phase: completed
match_rate: 100
plan: docs/archive/2026-06/coverage-blindspots-v2/coverage-blindspots-v2.plan.md
analysis: docs/archive/2026-06/coverage-blindspots-v2/coverage-blindspots-v2.analysis.md
report: docs/archive/2026-06/coverage-blindspots-v2/coverage-blindspots-v2.report.md
duration_h: 0.6
trigger: coverage-blindspots-v1 후속 (watcher/kpi 순수 로직)
```

## 4. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| dashboard 렌더(render_kpi_cards 등) streamlit AppTest 측정 | dashboard-apptest-v1 | Low |
| watcher run_check 상태전이 추출+측정 | watcher-refactor | Low |
| C901 complexity baseline | R8-ruff-complexity | Low |
| (사용자) webcloring-pdf SEPARATION.md outward 실행 | — | 사용자 |

## 5. Lessons Learned

- **순수/비순수 경계가 측정 단위를 정한다** — kpi_cards는 순수함수가 다수라 측정 시 88%로 깔끔히 올랐지만, watcher는 load/save(순수)와 run_check(IO)가 한 파일에 섞여 통째 측정이 불가. 같은 "blindspot"이라도 파일의 순수도가 측정 포함 여부를 가른다.
- **test-only도 정당한 결과** — watcher load/save는 측정 %에 안 잡혀도(파일 미포함) 회귀 가드라는 본질 가치는 동일. 커버리지 숫자에 집착해 IO 파일을 통째 넣어 floor를 무너뜨리는 것보다 낫다.
- **importlib 격리 로드의 재사용** — _parsing에서 확립한 "streamlit-import는 되나 순수함수만 호출" 패턴을 kpi_cards에 그대로 적용. 패키지 __init__의 무거운 import 체인을 우회하는 표준 수단으로 정착.
- **floor는 올릴 수 있어도 자제** — 76%가 됐지만 floor 72 유지. 측정 추가분으로 즉시 인플레하면 다음 변경의 여유가 사라진다. 마진은 의도적 자산.
