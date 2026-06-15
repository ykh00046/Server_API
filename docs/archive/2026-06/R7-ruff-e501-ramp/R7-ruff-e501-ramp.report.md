# R7-ruff-e501-ramp Completion Report

> **Summary**: ruff 게이트에 E501(line-too-long, 100) 추가. `ruff format` 미도입(사용자 결정 — 85파일 재포맷 회피). 99건 중 code/ascii ~45건 수동 래핑, 한글 프롬프트/UI·테스트 JSON 등 문자열 지배 파일은 per-file-ignore.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-15
> **Match Rate**: 100% (AC 7/7 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 커밋 |
|----|------|------|
| W | E501 코드 라인 ~45건 래핑(15파일): SQL paren+concat, f-string 분할, 시그니처/dict/list 줄바꿈, CSS 셀렉터 개행 | 1de6261 |
| G | select += E501, per-file-ignore E501(KOR-str 5파일 + tests/**) | 98d3867 |

## 2. 검증 결과

- ✅ AC1~AC7 전부 PASS (**100%**)
- ✅ 전체 ruff 게이트(F/BLE001/I/UP/B/SIM/E501) All checks passed
- ✅ 376 green(SQL concat 공백 보존을 쿼리 테스트가 입증), CI green
- ✅ code/ascii는 noqa 0건으로 래핑, 한글/JSON 문자열 파일만 면제

## 3. PDCA 메타데이터

```yaml
cycle: R7-ruff-e501-ramp
phase: completed
match_rate: 100
plan: docs/archive/2026-06/R7-ruff-e501-ramp/R7-ruff-e501-ramp.plan.md
analysis: docs/archive/2026-06/R7-ruff-e501-ramp/R7-ruff-e501-ramp.analysis.md
report: docs/archive/2026-06/R7-ruff-e501-ramp/R7-ruff-e501-ramp.report.md
duration_h: 1.5
trigger: R6 후속 (잔여 E501); ruff format은 사용자 결정으로 미도입
```

## 4. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| C901(complexity) baseline 임계값 게이트 | R8-ruff-complexity | Low |
| ruff format 도입 재검토(대규모 reformat) | (보류, 사용자 결정 시) | Low |
| dashboard 렌더 AppTest / kpi·watcher 순수로직 측정 | coverage-blindspots-v2 | Medium |
| (사용자) webcloring-pdf SEPARATION.md outward 실행 | — | 사용자 |

## 5. Lessons Learned

- **E501은 콘텐츠 규칙이지 구조 규칙이 아니다** — 위반의 절반이 한글 프롬프트/UI·docstring·테스트 JSON 등 "내용". 코드 구조가 길어서가 아니라 문자열이 길어서다. 콘텐츠 라인은 래핑하면 의미/가독성이 나빠지므로 per-file-ignore가 정답. "코드는 래핑, 콘텐츠는 면제"로 가르는 게 핵심.
- **ruff는 한글/이모지를 width 2로 센다** — 짧아 보이는 한글 라인도 E501. 한글 UI 파일을 억지로 래핑하면 width 때문에 다시 걸리거나 문장이 쪼개진다. 분류 단계에서 한글 검출로 미리 가른 게 헛수고를 막았다.
- **SQL 문자열 concat은 공백이 생명** — implicit concatenation(`"a " "b"`)에서 줄 끝/시작 공백을 빠뜨리면 `"ab"`가 되어 SQL이 깨진다. 쿼리 실행 테스트(376 green)가 이 미세 버그의 안전망.
- **format 없이 E501만**의 트레이드오프 — blame을 보존하지만 일관된 자동 포맷터가 없어 향후 래핑 스타일은 사람이 유지해야 한다. 사용자가 blame 보존을 우선해 내린 합리적 선택.
