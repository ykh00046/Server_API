# archive-cutoff-automation Completion Report

> **Summary**: 완료된 PDCA 사이클의 아카이브 cutoff/대상을 완료일 기준으로 자동 산출하는
> stdlib CLI 도구(`scripts/archive_cutoff.py`) 신규 도입. dry-run 기본, 완료월별 분류,
> 문서 누락/드리프트 가시화.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-01
> **Match Rate**: 100% (8/8 AC PASS)
> **Status**: Completed
> **Iterations**: 1

---

## 1. 변경 요약

| 변경 | 파일 | 효과 |
|------|------|------|
| Archive cutoff CLI 신규 | `scripts/archive_cutoff.py` (신규, 약 280줄) | 완료일 기반 cutoff/대상 자동 산출, dry-run 기본 |
| 테스트 신규 | `tests/test_archive_cutoff.py` (신규, 21 tests) | 파서/cutoff/선별/이동/CLI/실저장소 smoke |
| Plan/Design/Analysis | `docs/01-plan`,`02-design`,`03-analysis` | PDCA 문서 3종 |

## 2. 핵심 동작

```
python scripts/archive_cutoff.py [--today YYYY-MM-DD] [--cutoff …] [--age-days N] [--json] [--apply]
```

- 완료 사이클을 `04-report/*.report.md` 헤더로 식별(관용 파서: `Date`/`Completed`/
  `Completion Date`, `Status`/`PDCA Phase`, `Completed`/`Complete`/`✅ Complete (...)`).
- cutoff 기본 = 실행 월의 1일 → 이전 월 완료분만 대상(당월 보존).
- 완료월 기준 `docs/archive/YYYY-MM/<slug>/` 목표 경로 산출 + 4종 문서 존재 뱃지(`P D A R`).
- **기본 dry-run**(파일 미변경), `--apply` 시에만 `shutil.move`(mover 주입 가능).

## 3. 검증 결과

- ✅ `pytest tests/test_archive_cutoff.py -q` → **21 passed**
- ✅ `ruff check .` (F/BLE001/I/UP) → **All checks passed**
- ✅ 실제 docs dry-run(`--today 2026-06-01`): ELIGIBLE **19** / SKIPPED **5**
  - 2026-04/05/02 완료분이 완료월별로 정확 분류, R4(2026-06-01)는 `after cutoff`로 보존.
  - `_INDEX.md` 아카이브 기록과 활성 파일 잔존 **드리프트 정량 노출**(critical-fixes 등 4건).
  - 비표준 헤더 레거시 리포트 5건은 추측 없이 안전 제외.

## 4. PDCA 메타데이터

- **Plan**: `docs/01-plan/features/archive-cutoff-automation.plan.md`
- **Design**: `docs/02-design/features/archive-cutoff-automation.design.md`
- **Analysis**: `docs/03-analysis/archive-cutoff-automation.analysis.md`
- **Iteration**: QA에서 헤더 포맷 편차 발견 → 파서 관용성 보강(엄격 매칭 → 부분일치) 1회.

## 5. 후속 작업 (Deferred)

| 항목 | 비고 |
|------|------|
| 실제 `--apply` 일괄 이동 | 19사이클×~4파일, 되돌리기 어려워 **운영자 명시 승인** 필요 |
| `_INDEX.md` 자동 갱신 (v2) | 이동과 동시에 인덱스 항목 생성 |
| CI 월초 dry-run 알림 | cutoff 리포트 정기 노출 |
| 레거시 flat 리포트 정리 | 의도적 flat 유지분 — 현 제외 동작 유지 |
