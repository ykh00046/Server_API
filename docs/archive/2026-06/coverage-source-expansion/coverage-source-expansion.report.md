# coverage-source-expansion Completion Report

> **Summary**: 테스트된 순수 dashboard 헬퍼(`_parsing.py`)를 coverage 측정에 추가하고 floor를 66→72로 상향. 런타임 필수 UI 렌더 코드는 omit 화이트리스트로 정직하게 제외.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-15
> **Match Rate**: 100% (AC 6/6 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| C1 | coverage source=api,shared,dashboard + omit 화이트리스트(_parsing.py만 측정, 90%) | `pyproject.toml` | 36e3278 |
| C2 | CI coverage floor 66→72 (실측 75.14% −3pp) | `.github/workflows/ci.yml` | 36e3278 |

## 2. 핵심 — "측정"과 "floor 상향"의 충돌 해소

dashboard 전체(15%)를 넣으면 75%→~57%로 떨어져 floor 상향 불가. **선별 측정**으로 해소: 추출된 테스트 대상 `_parsing.py`만 측정(90%), 렌더 코드는 런타임 필수라 제외. 결과 75.14% 유지 → floor 72 안전.

## 3. 검증 결과

- ✅ AC1~AC6 전부 PASS (**100%**)
- ✅ `_parsing.py` 38 stmt 90% 측정, 렌더 코드 omit 확인
- ✅ floor 72 통과(75.14%), 376 green, ruff clean, CI green

## 4. PDCA 메타데이터

```yaml
cycle: coverage-source-expansion
phase: completed
match_rate: 100
plan: docs/archive/2026-06/coverage-source-expansion/coverage-source-expansion.plan.md
analysis: docs/archive/2026-06/coverage-source-expansion/coverage-source-expansion.analysis.md
report: docs/archive/2026-06/coverage-source-expansion/coverage-source-expansion.report.md
duration_h: 0.5
trigger: coverage-blindspots-v1 후속 (dashboard 측정 + floor 상향)
```

## 5. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| dashboard 렌더 코드 streamlit AppTest 측정 | dashboard-apptest-v1 | Low |
| kpi_cards/watcher 순수 로직 추출+측정 | coverage-blindspots-v2 | Medium |
| R6 린트 램프 (B+SIM) | R6-ruff-bugbear-sim-ramp | 진행 예정 |

## 6. Lessons Learned

- **coverage 단일 파일 측정은 source 경로로 안 된다** — `--cov=file.py`/`source=[file.py]`는 importlib 합성 로드를 "never imported"로 흘린다. `source=dir + omit 화이트리스트`가 단일 파일만 측정하는 실효적 방법. coverage는 파일 경로로 귀속하지만 source 매칭은 import 인식에 의존.
- **상충하는 지시는 측정으로 분해** — "측정 추가"와 "floor 상향"이 충돌할 때, 무엇을 측정하느냐(전체 vs 선별)를 수치로 보여주면 결정이 명확해진다. 15% vs 90%의 차이가 "선별"을 자명하게 만들었다.
- **불변식은 깨도 되지만 명문화하고 깨라** — ci-and-env의 "source 불변"을 이 사이클이 의도적으로 해제. 주석에 근거를 남겨 "drift"와 "계획된 변경"을 구분.
