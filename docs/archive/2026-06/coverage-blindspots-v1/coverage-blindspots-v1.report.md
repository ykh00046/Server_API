# coverage-blindspots-v1 Completion Report

> **Summary**: 커버리지 사각지대를 2종으로 구분 처리 — (A) measured 영역의 죽은 코드 91 stmt 삭제(72%→75%), (B) unmeasured이지만 brittle한 AI 표/SSE 파서를 streamlit-free 모듈로 추출하고 13개 characterization 테스트로 회귀 가드 추가.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-14
> **Match Rate**: 100% (AC 8/8 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| A | 미사용 utils 패키지 삭제(import 0건 실측) — measured coverage 72%→75% | `shared/utils/` 전체 | eeb0bc4 |
| B1 | AI 표/SSE 파서를 streamlit-free 모듈로 추출(로직 1:1) | `dashboard/components/_parsing.py`(신규), `ai_section.py` | dee7c6f |
| B2 | characterization 테스트 13건(표 7 + SSE 6), importlib 격리 로드 | `tests/test_ai_table_parse.py`, `tests/test_sse_parse.py` | dee7c6f |

## 2. 핵심 통찰 — "71% 커버리지"의 진실

검토의 "1,100+줄 무검증" 지적을 실측하니 **두 개의 다른 문제**였다:
- **measured(api+shared) 영역**: 0% 파일의 정체는 "테스트 없음"이 아니라 **죽은 코드**(아무도 import 안 함). → 삭제가 정답(테스트 아님).
- **unmeasured(dashboard) 영역**: coverage source에 애초에 없어 "71%"가 측정조차 안 함. brittle 로직(마크다운 표/SSE 파싱)은 추출+테스트로 가드.

## 3. 검증 결과

- ✅ AC1~AC8 전부 PASS (**100%**)
- ✅ measured coverage **72% → 75%** (91 stmt 죽은 코드 분모 제거)
- ✅ **376 passed** (363 + 신규 13), ruff All checks passed, **CI run green**
- ✅ 리팩터 동작 보존: 파서 로직 1:1 이전, ai_section은 `json` import만 제거. characterization 테스트가 공백 제거 한계까지 현재 동작 고정

## 4. PDCA 메타데이터

```yaml
cycle: coverage-blindspots-v1
phase: completed
match_rate: 100
plan: docs/archive/2026-06/coverage-blindspots-v1/coverage-blindspots-v1.plan.md
design: docs/archive/2026-06/coverage-blindspots-v1/coverage-blindspots-v1.design.md
analysis: docs/archive/2026-06/coverage-blindspots-v1/coverage-blindspots-v1.analysis.md
report: docs/archive/2026-06/coverage-blindspots-v1/coverage-blindspots-v1.report.md
duration_h: 1.0
trigger: 2026-06-10 전체 검토 "dashboard/manager/tools 무검증" 후속
```

## 5. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| watcher.py(run_check 상태전이)/kpi_cards(calculate_kpis) 순수 로직 테스트 | coverage-blindspots-v2 | Medium |
| coverage source에 dashboard/ 추가 + floor 상향(75→72 등 보수값) | coverage-source-expansion | Medium |
| webcloring-pdf submodule 분리 + 의존성 이관 | webcloring-pdf-separation | Medium |
| R6 린트 램프 (B나머지+SIM) | R6-ruff-bugbear-sim-ramp | Medium |
| 마크다운 표 파서 공백 제거 한계 개선(셀 내부 공백 보존) | (B2 보너스) | Low |

## 6. Lessons Learned

- **0% 커버리지 파일은 "테스트 대상"이 아니라 "분류 대상"** — 죽은 코드인지 미검증 live 코드인지 먼저 가른다. 죽은 코드를 테스트하면 커버리지만 부풀고 유지비가 늘 뿐. 이번엔 삭제가 테스트보다 정답이었다(72→75% 상승은 삭제의 결과).
- **"71%"의 함정** — 커버리지 숫자는 source 범위에 갇힌다. dashboard가 source 밖이면 대시보드를 한 줄도 안 짜도 71%가 나온다. 숫자를 인용할 땐 범위를 함께 말해야 오해가 없다.
- **추출이 테스트가능성을 만든다** — brittle 파싱이 `st.download_button`/httpx 스트림과 한 함수에 엉켜 있어 테스트 불가였다. streamlit-free 모듈로 분리하니 importlib 격리 로드로 런타임 없이 13케이스를 고정. 추출은 리팩터인 동시에 테스트 인프라다.
- **characterization부터** — "있어야 할 동작"이 아니라 "지금 하는 동작"을 먼저 고정하면 추출이 안전하다. 알려진 결함(공백 제거)은 테스트에 명시 + 후속으로 분리해 "수정"과 "이전"을 섞지 않았다.
