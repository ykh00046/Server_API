# archive-cutoff-automation Design

> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-01
> **Status**: Design
> **Plan**: `docs/01-plan/features/archive-cutoff-automation.plan.md`

---

## 1. 개요

`scripts/archive_cutoff.py` — stdlib 전용 단일 파일 CLI. 순수 함수 코어 + 얇은 CLI 래퍼로
구성해 테스트 가능성을 확보한다. 파일 이동 백엔드(mover)는 주입 가능하게 해 단위 테스트를
hermetic 하게 유지한다.

```
scripts/archive_cutoff.py
├─ dataclass  ReportMeta        # 파싱 결과 (date, status, match_rate)
├─ dataclass  Cycle             # slug, report_path, meta, 존재하는 doc 종류
├─ dataclass  CyclePlan         # cycle + eligible + target_dir + moves
├─ parse_report_metadata(text)            -> ReportMeta
├─ discover_cycles(report_dir)            -> list[Cycle]
├─ compute_cutoff(today, cutoff, age_days)-> date
├─ find_sibling_docs(slug, docs_root)     -> dict[str, Path]
├─ build_plan(cycles, cutoff, docs_root)  -> list[CyclePlan]
├─ apply_moves(plans, mover)              -> list[tuple[Path, Path]]
├─ render_text(plans, cutoff) / render_json(plans, cutoff)
└─ main(argv) -> int
```

## 2. 데이터 구조

```python
@dataclass(frozen=True)
class ReportMeta:
    date: date | None          # **Date**: 파싱 결과
    status: str | None         # **Status**:
    match_rate: str | None     # **Match Rate**: (참고용)

@dataclass
class Cycle:
    slug: str                  # report 파일명에서 ".report.md" 제거
    report_path: Path
    meta: ReportMeta

@dataclass
class CyclePlan:
    cycle: Cycle
    eligible: bool
    reason: str                # 비대상 사유 ("" if eligible)
    target_dir: Path | None    # docs/archive/YYYY-MM/<slug>/
    docs: dict[str, Path]      # {"plan":..., "design":..., "analysis":..., "report":...} 존재분만
```

## 3. 핵심 로직

### 3.1 메타데이터 파싱 — `parse_report_metadata`
리포트 헤더의 인용 블록에서 다음 라인을 관용 정규식으로 추출:
- `> **Date**: 2026-04-23` → `date(2026, 4, 23)` (`\*\*Date\*\*:\s*(\d{4})-(\d{2})-(\d{2})`)
- `> **Status**: Completed` → `"Completed"`
- `> **Match Rate**: 100% (...)` → 원문 문자열
파싱 실패 시 해당 필드는 `None`. 예외를 던지지 않는다(크래시 금지, AC7).

### 3.2 cutoff 산출 — `compute_cutoff(today, cutoff_str, age_days)`
우선순위:
1. `cutoff_str` 명시 → 그대로 파싱한 date.
2. `age_days` 명시 → `today - timedelta(days=age_days)`.
3. 기본 → 현재 월의 1일 (`today.replace(day=1)`).

규칙: 완료일이 **cutoff 미만(`<`)** 이면 대상. (현재 월 완료분은 보존.)
`today` 는 `--today` 로 주입 가능 → 결정론적 테스트. (워크플로 환경의 `date.today()`
제약과 무관하게 CLI 는 `date.today()` 기본, 테스트는 주입.)

### 3.3 sibling 문서 탐색 — `find_sibling_docs`
```
plan     : docs/01-plan/features/<slug>.plan.md
design   : docs/02-design/features/<slug>.design.md
analysis : docs/03-analysis/<slug>.analysis.md
report   : docs/04-report/<slug>.report.md
```
존재하는 것만 dict 에 담는다. report 는 항상 존재(탐색 출발점).

### 3.4 대상 선별 — `build_plan`
각 Cycle 에 대해:
- `meta.status != "Completed"` → `eligible=False`, reason="status=<x>".
- `meta.date is None` → `eligible=False`, reason="date unparsed".
- `meta.date >= cutoff` → `eligible=False`, reason="after cutoff".
- 그 외 → `eligible=True`, `target_dir = docs/archive/{date:%Y-%m}/{slug}/`.

### 3.5 이동 실행 — `apply_moves(plans, mover)`
eligible plan 의 각 doc 에 대해 `(src, target_dir/src.name)` 이동 계획 생성.
`mover(src, dst)` 주입(기본 `shutil.move`). 목표 파일이 이미 있으면 skip(로그).
target_dir 없으면 생성(`mkdir(parents=True, exist_ok=True)`).

## 4. CLI 인터페이스

```
python scripts/archive_cutoff.py [options]

--docs-root PATH     docs 루트 (기본: 저장소 docs/)
--cutoff YYYY-MM-DD  명시적 cutoff
--age-days N         today-N 일을 cutoff 로
--today YYYY-MM-DD   기준일 주입(테스트/재현용)
--json               JSON 출력
--apply              실제 이동 수행(기본 dry-run)
```

기본(dry-run) 텍스트 출력 예:
```
Archive cutoff: 2026-06-01 (policy: start-of-month)

ELIGIBLE (완료월 < cutoff)
  slug                         완료일       문서
  critical-fixes               2026-04-23   P D A R  -> docs/archive/2026-04/critical-fixes/
  ...
SKIPPED
  R4-import-pyupgrade-ramp     2026-05-..   after cutoff
  webhook-...                  -            date unparsed
```

`문서` 열: 존재하는 종류를 `P D A R` 로 표기, 누락은 `·`. 부분 이동/드리프트 가시화.

## 5. 종료 코드
- dry-run / `--apply` 정상 → 0.
- 인자 오류 → 2 (argparse 기본).
- (대상 0건도 0 — 에러 아님.)

## 6. 테스트 설계 (`tests/test_archive_cutoff.py`)

순수 함수 + tmp_path hermetic. 모든 테스트 `--today`/명시 cutoff 로 시간 비의존.

1. `parse_report_metadata`: 정상 헤더 → date/status/match_rate 추출.
2. `parse_report_metadata`: Date 누락 → None (no raise).
3. `compute_cutoff`: 기본(월초), `--cutoff`, `--age-days` 3분기.
4. `build_plan`: cutoff 이전 Completed → eligible.
5. `build_plan`: cutoff 이후 → skip "after cutoff".
6. `build_plan`: status != Completed → skip.
7. `build_plan`: date unparsed → skip.
8. `find_sibling_docs`: tmp docs 트리에서 4종/부분 탐지.
9. `apply_moves`: 주입 mover 로 호출 인자 검증 + 목표 존재 시 skip.
10. 통합: tmp docs 트리 구성 → dry-run 출력에 eligible slug 포함, 파일 미변경.
11. (가능 시) 실제 저장소 `docs/04-report` 대상 `discover_cycles` 가 예외 없이 동작.

## 7. 결정 사항 (자율 판단)
- **단일 파일 스크립트**(패키지화 X): 도구 성격, 의존성 최소화.
- **stdlib only**: rich/click 미도입 — argparse + 텍스트 테이블.
- **dry-run 기본**: 파괴적 작업 안전. `--apply` 필수.
- **`_INDEX.md` 갱신 제외**: 범위 명확화, 후속 v2.
- **mover 주입**: git mv vs shutil.move 논쟁 회피 + 테스트 hermetic. CLI 기본은 `shutil.move`
  (git 추적 파일은 git 이 rename 감지하므로 이력 보존에 충분).
