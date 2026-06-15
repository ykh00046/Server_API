# R6-ruff-bugbear-sim-ramp Completion Report

> **Summary**: ruff 게이트를 `B`(bugbear 전체)+`SIM`(simplify)로 확장. 위반 41건 해소 — src B는 코드 수정(B025가 실버그 발견), tests B017은 per-file-ignore, SIM은 autofix+수동(contextlib.suppress 등).
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-15
> **Match Rate**: 100% (AC 7/7 PASS)
> **Status**: Completed

---

## 1. 변경 요약

| ID | 변경 | 커밋 |
|----|------|------|
| B-src | B905 strict=True(3) + B025 dup-except→Exception(2, 실버그) + B007 _ip(1) | a221e44 |
| SIM | SIM105→contextlib.suppress(17) + SIM117/300/102/108 autofix·수동 | dea22b3 |
| Gate | select +B +SIM, tests/** per-file-ignore +B017 | dea22b3 |

## 2. 검증 결과

- ✅ AC1~AC7 전부 PASS (**100%**)
- ✅ `ruff check .`(F/BLE001/I/UP/B/SIM) All checks passed
- ✅ 376 green, CI green
- ✅ src B는 코드 수정으로 해소(noqa 남발 없음), tests B017만 per-file-ignore

## 3. PDCA 메타데이터

```yaml
cycle: R6-ruff-bugbear-sim-ramp
phase: completed
match_rate: 100
plan: docs/archive/2026-06/R6-ruff-bugbear-sim-ramp/R6-ruff-bugbear-sim-ramp.plan.md
analysis: docs/archive/2026-06/R6-ruff-bugbear-sim-ramp/R6-ruff-bugbear-sim-ramp.analysis.md
report: docs/archive/2026-06/R6-ruff-bugbear-sim-ramp/R6-ruff-bugbear-sim-ramp.report.md
duration_h: 1.0
trigger: R3→R5 린트 램프 후속 (잔여 B+SIM)
```

## 4. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| E501(line-too-long, 110건) + `ruff format` 도입 | R7-ruff-format-e501 | Medium |
| C901(complexity) baseline 임계값 게이트 | R8-ruff-complexity | Low |
| dashboard 렌더 streamlit AppTest / kpi·watcher 순수로직 측정 | coverage-blindspots-v2 | Medium |

## 5. Lessons Learned

- **린트 램프가 실버그를 잡는다** — B025(duplicate-except)가 db_maintenance.py의 도달 불가 `except sqlite3.Error` 중복 블록을 드러냈다. 주석 의도(IO 등 broad catch)와 코드가 어긋난 죽은 핸들러였고, `except Exception`으로 의도 복원. 스타일 규칙이 의미 버그를 표면화한 사례.
- **autofix는 연쇄를 만든다** — SIM105→contextlib.suppress가 manager에서 새 중첩 `with`(SIM117)를 만들었다. autofix 적용 후 반드시 재검사로 2차 위반을 포착할 것.
- **autofix가 건너뛴 것에 의도가 있다** — SIM105 5건은 `pass # 설명` / `# type: ignore`을 가져 autofix가 보류. 주석을 `with` 위로 옮겨 수동 변환하면 합리적 근거를 잃지 않는다.
- **broad는 코드와 테스트에서 다르게 취급** — 프로덕션 broad catch/raises는 수정 대상이지만, 테스트의 `pytest.raises(Exception)`는 "예외 발생 여부"만 보는 관용이라 per-file-ignore가 옳다. 같은 규칙이라도 맥락이 처리를 가른다.
