# archive-cutoff-automation Gap Analysis

> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-01
> **Match Rate**: 100% (8/8 AC PASS)
> **Iterations**: 1 (QA 중 파서 관용성 보강)

---

## 1. AC 대비 검증

| AC | 기준 | 결과 | 근거 |
|----|------|------|------|
| AC1 | Date/Status 파싱 | ✅ | `parse_report_metadata`, QA에서 24개 리포트 파싱 |
| AC2 | cutoff 정책(월초/--cutoff/--age-days/--today) | ✅ | `compute_cutoff` 3분기 + 테스트 |
| AC3 | cutoff 이전 선별 + 문서 존재 표시 | ✅ | `build_plan`, `P D A R` 뱃지 |
| AC4 | 목표 경로 archive/YYYY-MM/<slug>/ | ✅ | 완료월별 분류(2026-04/05/02) |
| AC5 | dry-run 기본 + --json | ✅ | `render_text`/`render_json`, 파일 미변경 검증 |
| AC6 | --apply 이동 + skip existing | ✅ | `apply_moves`, mover 주입 테스트 |
| AC7 | 미파싱/비완료 제외 + 사유 | ✅ | SKIPPED 5건 사유 표기 |
| AC8 | ruff 0 + pytest pass | ✅ | ruff All checks passed, 21 passed |

## 2. Iteration 내역 (Check→Act)

QA(실제 docs dry-run) 1차에서 **상태/날짜 헤더 포맷 편차**를 발견:
- 완료일: `**Date**` 외 `**Completed**`, `**Completion Date**` 변형 존재.
- 완료상태: `**Status**` 외 `**PDCA Phase**`, 값은 `Complete`, `✅ Complete (...)` 변형.

→ Design의 엄격 매칭(`status == "completed"`)을 **관용 매칭**으로 보강:
- `_DATE_RE` 에 3개 필드명 alternation 추가.
- `_is_completed()` 헬퍼로 `"complet"` 부분일치(대소문자 무시) 판정.
- 보강 후 ELIGIBLE 11 → 19로 정상화(5월 사이클 9건 + 2월 1건 추가 인식), R4(당월)는 보존.

## 3. 발견된 부가 가치 (드리프트 탐지)

`_INDEX.md`(2026-04)엔 "아카이브 완료"로 기록된 `critical-fixes`, `docs-sync`,
`products-refactor`, `security-hardening-v3` 가 활성 `04-report/`에 `P D A R`로 잔존 →
**인덱스-파일시스템 드리프트를 도구가 정량 노출**. 본 사이클의 핵심 동기를 실증.

## 4. 잔여/후속 (Deferred)

- **실제 `--apply` 실행**: 19사이클×~4파일 대량 이동은 되돌리기 어려워 운영자 명시 승인 몫.
- **`_INDEX.md` 자동 갱신**(v2 후보): 이동과 동시에 인덱스 항목 생성/이동.
- **레거시 standalone 리포트**(production-data-hub-*, server-api-smoke 등): 비표준 헤더 →
  의도적 flat 유지분이므로 자동 처리 대상에서 제외(현 동작이 정답).
- **CI 통합**: 월초 dry-run 리포트를 알림으로.
