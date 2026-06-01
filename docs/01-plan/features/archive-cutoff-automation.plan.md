# archive-cutoff-automation Plan

> **Summary**: 완료된 PDCA 사이클의 아카이브 cutoff 날짜를 완료일 기준으로 자동 산출하고,
> 아카이브 대상(plan/design/analysis/report 4종)과 목표 경로를 판별하는 CLI 도구 도입.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-01
> **Level**: Dynamic
> **Status**: Planning

---

## 1. 문제 정의 (Problem)

PDCA 사이클이 완료되면 활성 디렉터리(`docs/01-plan`, `02-design`, `03-analysis`, `04-report`)의
문서를 `docs/archive/YYYY-MM/<slug>/` 로 **수동** 이동하고 `_INDEX.md` 를 손으로 갱신해 왔다.
이 방식의 결함:

- **드리프트**: `_INDEX.md` 에는 "아카이브 완료"로 기록됐지만 실제 파일은 `04-report/` 에 잔존하는
  사례가 존재(예: `critical-fixes`, `docs-sync`, `products-refactor`, `security-hardening-v3`).
  인덱스와 실제 파일 시스템이 불일치한다.
- **cutoff 판단의 주관성**: "이번 달 것은 남기고 지난달 완료분만 아카이브" 같은 규칙이 머릿속에만
  있어 매번 재현 가능하지 않다.
- **누락**: 4종 문서(plan/design/analysis/report) 중 일부만 옮겨지는 부분 이동이 발생할 수 있다.

현재 `04-report/` 에는 24개의 활성 리포트가 있고, 다수가 2026-04 완료분으로 이미 아카이브 대상이다.

## 2. 목표 (Goals)

1. 완료된 사이클을 `04-report/*.report.md` 의 메타데이터(`Date`, `Status`)로 자동 식별한다.
2. **cutoff 날짜를 자동 산출**한다(기본: 현재 월의 1일 → 이전 월 완료분이 대상).
3. 각 대상 사이클의 4종 문서 존재 여부를 점검하고, 완료월 기준 목표 경로
   `docs/archive/YYYY-MM/<slug>/` 를 제안한다.
4. 기본은 **dry-run**(읽기 전용 리포트), `--apply` 시에만 실제 이동을 수행한다.
5. 외부 의존성 없이(stdlib only) 동작하고, 기존 ruff 게이트(F/BLE001/I/UP)와 pytest 규약을 만족한다.

## 3. 범위 (Scope)

### In Scope
- `scripts/archive_cutoff.py` 신규 CLI 도구.
- 리포트 메타데이터 파서, cutoff 정책 계산, 대상 선별, 이동 계획 수립, (옵션) 이동 실행.
- `tests/test_archive_cutoff.py` 단위 + 통합 테스트.

### Out of Scope
- `_INDEX.md` 자동 재작성(이번 사이클은 "대상 판별 + 이동"까지. 인덱스 갱신은 후속 v2 후보).
- 활성 리포트 외 standalone 리포트(예: `*-2026-02-20.report.md`)의 강제 정리 — 동일 로직으로
  탐지는 하되 sibling 문서가 없으면 리포트 단독 처리로 graceful 하게 다룬다.
- CI 통합(후속).

## 4. 사용자 가치 (Value)

- 매월 아카이브 작업이 **1개 명령 dry-run → 확인 → `--apply`** 로 표준화된다.
- `_INDEX.md` 드리프트를 조기 탐지한다(인덱스엔 있는데 활성 파일이 남은 경우 = "미이동" 경고).
- cutoff 규칙이 코드로 고정되어 재현 가능해진다.

## 5. Acceptance Criteria

| ID | 기준 |
|----|------|
| AC1 | `04-report/*.report.md` 헤더의 `**Date**:` / `**Status**:` 를 파싱해 완료 사이클을 식별한다 |
| AC2 | 기본 cutoff = 실행 시점 월의 1일. `--cutoff YYYY-MM-DD`, `--age-days N`, `--today YYYY-MM-DD`(테스트용) 로 재정의 가능 |
| AC3 | cutoff 이전 완료분만 "대상"으로 선별하고, 각 대상의 plan/design/analysis/report 존재 여부를 표시한다 |
| AC4 | 완료월 기준 목표 경로 `docs/archive/YYYY-MM/<slug>/` 를 산출한다 |
| AC5 | 기본은 dry-run(파일 미변경). `--json` 으로 기계 판독 출력 지원 |
| AC6 | `--apply` 는 대상 문서를 목표 경로로 이동하고 이동 목록을 출력한다(목표 존재 시 skip) |
| AC7 | 날짜 파싱 실패/`Status != Completed` 사이클은 대상에서 제외하고 사유를 표시한다 |
| AC8 | `ruff check`(F/BLE001/I/UP) 0건, `pytest tests/test_archive_cutoff.py` 전부 통과 |

## 6. 리스크 / 완화

| 리스크 | 완화 |
|--------|------|
| 리포트 헤더 포맷 불일치 | 정규식 관용 파싱 + 실패 시 "unknown"으로 분류(크래시 금지) |
| 잘못된 파일 이동(파괴적) | 기본 dry-run, `--apply` 명시 필요, 목표 경로 존재 시 skip, mover 주입 가능(테스트 hermetic) |
| 시간 의존 테스트 불안정 | `--today` 주입으로 결정론적 테스트 |
