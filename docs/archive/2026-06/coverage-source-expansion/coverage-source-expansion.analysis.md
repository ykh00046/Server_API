# coverage-source-expansion — Gap Analysis

> **Cycle**: coverage-source-expansion
> **PDCA Phase**: Check
> **Date**: 2026-06-15
> **Plan**: [[coverage-source-expansion.plan]]
> **Match Rate**: **100%** (AC 6/6)

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | _parsing.py 측정 포함, 렌더 코드 미포함 | cov-report: `dashboard/components/_parsing.py 38 stmt 90%`. app.py/views/렌더 컴포넌트 미등장(omit) | ✅ |
| AC2 | measured ≥ 72 | **75.14%** (floor 72 통과) | ✅ |
| AC3 | ci.yml floor 72, pyproject 주석 동기화 | `--cov-fail-under=72` + ci.yml/pyproject 주석 갱신 | ✅ |
| AC4 | 376 green + ruff + CI | 376 passed, ruff clean, CI(아래) | ✅ |
| AC5 | source 확장 의도적 문서화 | pyproject [tool.coverage.run] 주석 + ci.yml 주석에 "불변식 해제" 명기 | ✅ |
| AC6 | match rate ≥ 90% | 100% | ✅ |

## 구현 노트 — coverage 단일파일 측정의 함정

- `--cov=dashboard/components/_parsing.py` 및 `source=[".../_parsing.py"]`는 **"module never imported"** 경고로 측정 실패. 테스트가 importlib 합성 모듈명으로 로드해 coverage의 source-파일 매칭이 인식 못 함.
- 해결: `source=["api","shared","dashboard"]` + **omit 화이트리스트**(렌더 파일 전부 명시 제외) → `_parsing.py`만 측정에 남음(90%). 새 dashboard 파일은 omit에서 빼야 측정됨 → "측정할 것만 측정" 의도 명시적.
- `_parsing.py` 90%(미커버: parse_markdown_table의 except 분기·empty 분기, SSE 한 분기) — 정직한 수치.

## pyproject 불변식 변경 (의도적)

ci-and-env-standardization AC8의 "coverage source 불변"은 이 사이클이 **목적상 해제**. drift가 아니라 계획된 확장 — pyproject/ci.yml 주석에 근거 기록. 후속 커버리지 작업(coverage-blindspots-v2)의 토대.

## 권장 조치

없음 — **100% → Report.** 후속: dashboard 렌더 코드의 런타임 테스트(streamlit AppTest), kpi/watcher 순수 로직 추가 측정.
