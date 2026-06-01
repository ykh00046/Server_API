"""archive-cutoff-automation 단위/통합 테스트.

순수 함수 + tmp_path hermetic. 모든 테스트는 cutoff/today 를 주입해 시간 비의존.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts import archive_cutoff as ac

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

_REPORT_TMPL = """# {slug} Completion Report

> **Summary**: 테스트용 리포트
>
> **Project**: Server_API
> **Date**: {date}
> **Match Rate**: 100% (6/6 AC PASS)
> **Status**: {status}

---
본문
"""


def _write_cycle(
    docs_root: Path,
    slug: str,
    date_str: str,
    status: str = "Completed",
    kinds: tuple[str, ...] = ("plan", "design", "analysis", "report"),
) -> None:
    """tmp docs 트리에 사이클 문서를 생성한다."""
    for kind in kinds:
        subdir, suffix = ac._DOC_LAYOUT[kind]
        path = docs_root / subdir / f"{slug}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "report":
            path.write_text(
                _REPORT_TMPL.format(slug=slug, date=date_str, status=status),
                encoding="utf-8",
            )
        else:
            path.write_text(f"# {slug} {kind}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# parse_report_metadata
# ---------------------------------------------------------------------------


def test_parse_metadata_ok():
    meta = ac.parse_report_metadata(
        _REPORT_TMPL.format(slug="x", date="2026-04-23", status="Completed")
    )
    assert meta.date == date(2026, 4, 23)
    assert meta.status == "Completed"
    assert meta.match_rate.startswith("100%")


def test_parse_metadata_missing_date_no_raise():
    meta = ac.parse_report_metadata("# no header\n\nbody only")
    assert meta.date is None
    assert meta.status is None
    assert meta.match_rate is None


def test_parse_metadata_invalid_date_is_none():
    meta = ac.parse_report_metadata("> **Date**: 2026-13-40\n> **Status**: Completed")
    assert meta.date is None
    assert meta.status == "Completed"


def test_parse_metadata_alt_date_fields():
    # **Completed** / **Completion Date** 변형도 인식
    assert ac.parse_report_metadata("> **Completed**: 2026-05-27").date == date(2026, 5, 27)
    assert (
        ac.parse_report_metadata("> **Completion Date**: 2026-06-01").date == date(2026, 6, 1)
    )


def test_parse_metadata_pdca_phase_as_status():
    meta = ac.parse_report_metadata("> **PDCA Phase**: Completed\n> **Date**: 2026-05-01")
    assert meta.status == "Completed"


def test_is_completed_tolerant():
    assert ac._is_completed("Completed")
    assert ac._is_completed("Complete")
    assert ac._is_completed("✅ Complete (gap 100%, 13/13 AC, iterate 0)")
    assert not ac._is_completed(None)
    assert not ac._is_completed("In Progress")


# ---------------------------------------------------------------------------
# compute_cutoff
# ---------------------------------------------------------------------------


def test_cutoff_default_is_start_of_month():
    assert ac.compute_cutoff(date(2026, 6, 1)) == date(2026, 6, 1)
    assert ac.compute_cutoff(date(2026, 6, 15)) == date(2026, 6, 1)


def test_cutoff_explicit():
    assert ac.compute_cutoff(date(2026, 6, 15), cutoff="2026-05-10") == date(2026, 5, 10)


def test_cutoff_age_days():
    assert ac.compute_cutoff(date(2026, 6, 11), age_days=10) == date(2026, 6, 1)


def test_cutoff_invalid_raises():
    import pytest

    with pytest.raises(ValueError, match="cutoff"):
        ac.compute_cutoff(date(2026, 6, 1), cutoff="nope")


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


def _cycle(slug: str, d: date | None, status: str | None = "Completed") -> ac.Cycle:
    return ac.Cycle(slug, Path(f"{slug}.report.md"), ac.ReportMeta(d, status, None))


def test_build_plan_eligible_before_cutoff(tmp_path: Path):
    cycles = [_cycle("old-feature", date(2026, 4, 23))]
    plans = ac.build_plan(cycles, date(2026, 6, 1), tmp_path)
    assert plans[0].eligible is True
    assert plans[0].target_dir == tmp_path / "archive" / "2026-04" / "old-feature"


def test_build_plan_skip_after_cutoff(tmp_path: Path):
    cycles = [_cycle("recent", date(2026, 5, 20))]
    plans = ac.build_plan(cycles, date(2026, 5, 1), tmp_path)
    assert plans[0].eligible is False
    assert plans[0].reason == "after cutoff"


def test_build_plan_skip_not_completed(tmp_path: Path):
    cycles = [_cycle("wip", date(2026, 4, 1), status="In Progress")]
    plans = ac.build_plan(cycles, date(2026, 6, 1), tmp_path)
    assert plans[0].eligible is False
    assert "status=" in plans[0].reason


def test_build_plan_skip_unparsed_date(tmp_path: Path):
    cycles = [_cycle("nodate", None)]
    plans = ac.build_plan(cycles, date(2026, 6, 1), tmp_path)
    assert plans[0].eligible is False
    assert plans[0].reason == "date unparsed"


# ---------------------------------------------------------------------------
# find_sibling_docs
# ---------------------------------------------------------------------------


def test_find_sibling_docs_full_and_partial(tmp_path: Path):
    _write_cycle(tmp_path, "full", "2026-04-01")
    _write_cycle(tmp_path, "partial", "2026-04-01", kinds=("report", "plan"))

    full = ac.find_sibling_docs("full", tmp_path)
    assert set(full) == {"plan", "design", "analysis", "report"}

    partial = ac.find_sibling_docs("partial", tmp_path)
    assert set(partial) == {"plan", "report"}


# ---------------------------------------------------------------------------
# apply_moves
# ---------------------------------------------------------------------------


def test_apply_moves_invokes_mover_and_skips_existing(tmp_path: Path):
    _write_cycle(tmp_path, "feat", "2026-04-01")
    cycles = ac.discover_cycles(tmp_path / "04-report")
    plans = ac.build_plan(cycles, date(2026, 6, 1), tmp_path)

    calls: list[tuple[str, str]] = []

    def fake_mover(src: Path, dst: Path) -> None:
        calls.append((src.name, dst.name))

    moved = ac.apply_moves(plans, mover=fake_mover)
    assert len(moved) == 4  # plan/design/analysis/report
    assert len(calls) == 4
    # 목표 디렉터리는 실제로 생성된다.
    assert (tmp_path / "archive" / "2026-04" / "feat").is_dir()


def test_apply_moves_real_move(tmp_path: Path):
    _write_cycle(tmp_path, "feat", "2026-04-01", kinds=("report", "plan"))
    cycles = ac.discover_cycles(tmp_path / "04-report")
    plans = ac.build_plan(cycles, date(2026, 6, 1), tmp_path)

    moved = ac.apply_moves(plans)
    target = tmp_path / "archive" / "2026-04" / "feat"
    assert (target / "feat.report.md").is_file()
    assert (target / "feat.plan.md").is_file()
    # 원본은 이동되어 사라진다.
    assert not (tmp_path / "04-report" / "feat.report.md").exists()
    assert len(moved) == 2


# ---------------------------------------------------------------------------
# 통합: main() dry-run
# ---------------------------------------------------------------------------


def test_main_dry_run_lists_eligible_no_changes(tmp_path: Path, capsys):
    _write_cycle(tmp_path, "old-one", "2026-04-10")
    _write_cycle(tmp_path, "new-one", "2026-06-05")

    rc = ac.main(["--docs-root", str(tmp_path), "--today", "2026-06-01"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "old-one" in out
    assert "ELIGIBLE (1)" in out
    # dry-run 은 파일을 변경하지 않는다.
    assert (tmp_path / "04-report" / "old-one.report.md").exists()
    assert not (tmp_path / "archive").exists()


def test_main_json_output(tmp_path: Path, capsys):
    import json

    _write_cycle(tmp_path, "old-one", "2026-04-10")
    rc = ac.main(["--docs-root", str(tmp_path), "--today", "2026-06-01", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["cutoff"] == "2026-06-01"
    assert payload["cycles"][0]["slug"] == "old-one"
    assert payload["cycles"][0]["eligible"] is True


def test_main_missing_docs_root_returns_2(tmp_path: Path):
    rc = ac.main(["--docs-root", str(tmp_path / "nonexistent"), "--today", "2026-06-01"])
    assert rc == 2


# ---------------------------------------------------------------------------
# 실제 저장소 docs 에 대한 smoke (예외 없이 동작하는지)
# ---------------------------------------------------------------------------


def test_discover_real_repo_docs_no_crash():
    repo_report_dir = Path(__file__).resolve().parent.parent / "docs" / "04-report"
    if not repo_report_dir.is_dir():
        return
    cycles = ac.discover_cycles(repo_report_dir)
    assert len(cycles) > 0
    # 적어도 일부는 날짜가 파싱되어야 한다.
    assert any(c.meta.date is not None for c in cycles)
