"""Archive cutoff 자동 산출 — 완료된 PDCA 사이클의 아카이브 대상/cutoff 판별 CLI.

완료된 사이클은 ``docs/04-report/<slug>.report.md`` 헤더의 ``**Date**`` / ``**Status**``
메타데이터로 식별한다. cutoff 이전(완료월 < cutoff)에 완료된 ``Completed`` 사이클을
아카이브 대상으로 선별하고, 4종 문서(plan/design/analysis/report)의 존재 여부와
목표 경로 ``docs/archive/YYYY-MM/<slug>/`` 를 산출한다.

기본은 dry-run(읽기 전용). ``--apply`` 일 때만 실제 파일을 이동한다.

설계: ``docs/02-design/features/archive-cutoff-automation.design.md``
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# ----------------------------------------------------------------------------
# 메타데이터 파싱
# ----------------------------------------------------------------------------

# 리포트 헤더 포맷은 사이클마다 편차가 크다(report-generator 버전/수기 차이).
# 완료일: **Date** / **Completed** / **Completion Date**
# 완료상태: **Status** / **PDCA Phase**, 값은 Completed / Complete / "✅ Complete (...)"
_DATE_RE = re.compile(
    r"\*\*(?:Date|Completed|Completion Date)\*\*:\s*(\d{4})-(\d{2})-(\d{2})"
)
_STATUS_RE = re.compile(r"\*\*(?:Status|PDCA Phase)\*\*:\s*([^\n<]+)")
_MATCH_RE = re.compile(r"\*\*Match Rate\*\*:\s*([^\n<]+)")


def _is_completed(status: str | None) -> bool:
    """완료 상태 판정 — 'Completed'/'Complete'/'✅ Complete (...)' 모두 수용."""
    return status is not None and "complet" in status.lower()

_DOC_LAYOUT = {
    "plan": ("01-plan/features", ".plan.md"),
    "design": ("02-design/features", ".design.md"),
    "analysis": ("03-analysis", ".analysis.md"),
    "report": ("04-report", ".report.md"),
}


@dataclass(frozen=True)
class ReportMeta:
    """리포트 헤더에서 추출한 메타데이터."""

    date: date | None
    status: str | None
    match_rate: str | None


@dataclass
class Cycle:
    """하나의 완료 사이클(리포트 기준)."""

    slug: str
    report_path: Path
    meta: ReportMeta


@dataclass
class CyclePlan:
    """대상 선별 결과 + 이동 계획."""

    cycle: Cycle
    eligible: bool
    reason: str = ""
    target_dir: Path | None = None
    docs: dict[str, Path] = field(default_factory=dict)


def parse_report_metadata(text: str) -> ReportMeta:
    """리포트 본문에서 Date/Status/Match Rate 를 관용 파싱. 실패 필드는 None."""
    parsed_date: date | None = None
    m = _DATE_RE.search(text)
    if m:
        try:
            parsed_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            parsed_date = None  # 13월 등 비정상 값은 unknown 으로 취급

    status_m = _STATUS_RE.search(text)
    status = status_m.group(1).strip() if status_m else None

    match_m = _MATCH_RE.search(text)
    match_rate = match_m.group(1).strip() if match_m else None

    return ReportMeta(date=parsed_date, status=status, match_rate=match_rate)


# ----------------------------------------------------------------------------
# 탐색
# ----------------------------------------------------------------------------


def discover_cycles(report_dir: Path) -> list[Cycle]:
    """``report_dir`` 의 ``*.report.md`` 를 사이클로 변환. slug 사전순 정렬."""
    cycles: list[Cycle] = []
    for report_path in sorted(report_dir.glob("*.report.md")):
        slug = report_path.name[: -len(".report.md")]
        try:
            text = report_path.read_text(encoding="utf-8")
        except OSError as exc:
            # 읽을 수 없는 리포트는 메타데이터 미상으로 기록(크래시 금지).
            print(f"warning: {report_path} 읽기 실패: {exc}", file=sys.stderr)
            cycles.append(Cycle(slug, report_path, ReportMeta(None, None, None)))
            continue
        cycles.append(Cycle(slug, report_path, parse_report_metadata(text)))
    return cycles


def find_sibling_docs(slug: str, docs_root: Path) -> dict[str, Path]:
    """slug 에 해당하는 4종 문서 중 실제 존재하는 것만 반환."""
    found: dict[str, Path] = {}
    for kind, (subdir, suffix) in _DOC_LAYOUT.items():
        candidate = docs_root / subdir / f"{slug}{suffix}"
        if candidate.is_file():
            found[kind] = candidate
    return found


# ----------------------------------------------------------------------------
# cutoff 산출 + 선별
# ----------------------------------------------------------------------------


def compute_cutoff(
    today: date,
    cutoff: str | None = None,
    age_days: int | None = None,
) -> date:
    """cutoff 날짜 산출. 우선순위: cutoff > age_days > 현재 월의 1일."""
    if cutoff is not None:
        parts = cutoff.split("-")
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError) as exc:
            raise ValueError(f"잘못된 --cutoff 형식: {cutoff!r} (YYYY-MM-DD)") from exc
    if age_days is not None:
        return today - timedelta(days=age_days)
    return today.replace(day=1)


def build_plan(cycles: list[Cycle], cutoff: date, docs_root: Path) -> list[CyclePlan]:
    """각 사이클의 대상 여부/사유/목표 경로/문서 목록을 산출."""
    plans: list[CyclePlan] = []
    for cycle in cycles:
        meta = cycle.meta
        docs = find_sibling_docs(cycle.slug, docs_root)

        if not _is_completed(meta.status):
            plans.append(
                CyclePlan(cycle, False, f"status={meta.status or 'unknown'}", docs=docs)
            )
            continue
        if meta.date is None:
            plans.append(CyclePlan(cycle, False, "date unparsed", docs=docs))
            continue
        if meta.date >= cutoff:
            plans.append(CyclePlan(cycle, False, "after cutoff", docs=docs))
            continue

        target = docs_root / "archive" / f"{meta.date:%Y-%m}" / cycle.slug
        plans.append(CyclePlan(cycle, True, "", target_dir=target, docs=docs))
    return plans


# ----------------------------------------------------------------------------
# 이동 실행
# ----------------------------------------------------------------------------

Mover = Callable[[Path, Path], object]


def _default_mover(src: Path, dst: Path) -> None:
    shutil.move(str(src), str(dst))


def apply_moves(
    plans: list[CyclePlan],
    mover: Mover = _default_mover,
) -> list[tuple[Path, Path]]:
    """eligible plan 의 문서를 목표 경로로 이동. 목표 존재 시 skip. 수행된 이동 목록 반환."""
    moved: list[tuple[Path, Path]] = []
    for plan in plans:
        if not plan.eligible or plan.target_dir is None:
            continue
        plan.target_dir.mkdir(parents=True, exist_ok=True)
        for src in plan.docs.values():
            dst = plan.target_dir / src.name
            if dst.exists():
                print(f"skip (이미 존재): {dst}", file=sys.stderr)
                continue
            mover(src, dst)
            moved.append((src, dst))
    return moved


# ----------------------------------------------------------------------------
# 출력
# ----------------------------------------------------------------------------

_KIND_ORDER = ("plan", "design", "analysis", "report")
_KIND_LABEL = {"plan": "P", "design": "D", "analysis": "A", "report": "R"}


def _docs_badge(docs: dict[str, Path]) -> str:
    return " ".join(_KIND_LABEL[k] if k in docs else "·" for k in _KIND_ORDER)


def render_text(plans: list[CyclePlan], cutoff: date) -> str:
    """사람이 읽는 텍스트 리포트."""
    eligible = [p for p in plans if p.eligible]
    skipped = [p for p in plans if not p.eligible]
    lines: list[str] = []
    lines.append(f"Archive cutoff: {cutoff:%Y-%m-%d} (완료월 < cutoff 인 Completed 사이클이 대상)")
    lines.append("")
    lines.append(f"ELIGIBLE ({len(eligible)})")
    if eligible:
        lines.append(f"  {'slug':<34}{'완료일':<12}{'P D A R':<9} -> target")
        for p in eligible:
            d = f"{p.cycle.meta.date:%Y-%m-%d}" if p.cycle.meta.date else "-"
            rel = p.target_dir.as_posix() if p.target_dir else "-"
            lines.append(f"  {p.cycle.slug:<34}{d:<12}{_docs_badge(p.docs):<9} -> {rel}/")
    else:
        lines.append("  (없음)")
    lines.append("")
    lines.append(f"SKIPPED ({len(skipped)})")
    for p in skipped:
        d = f"{p.cycle.meta.date:%Y-%m-%d}" if p.cycle.meta.date else "-"
        lines.append(f"  {p.cycle.slug:<34}{d:<12}{p.reason}")
    return "\n".join(lines)


def render_json(plans: list[CyclePlan], cutoff: date) -> str:
    """기계 판독 JSON."""
    payload = {
        "cutoff": cutoff.isoformat(),
        "cycles": [
            {
                "slug": p.cycle.slug,
                "date": p.cycle.meta.date.isoformat() if p.cycle.meta.date else None,
                "status": p.cycle.meta.status,
                "eligible": p.eligible,
                "reason": p.reason,
                "target_dir": p.target_dir.as_posix() if p.target_dir else None,
                "docs": {k: v.as_posix() for k, v in sorted(p.docs.items())},
            }
            for p in plans
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def _default_docs_root() -> Path:
    return Path(__file__).resolve().parent.parent / "docs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archive_cutoff",
        description="완료된 PDCA 사이클의 아카이브 cutoff/대상을 자동 산출한다.",
    )
    parser.add_argument("--docs-root", type=Path, default=None, help="docs 루트 경로")
    parser.add_argument("--cutoff", default=None, help="명시 cutoff (YYYY-MM-DD)")
    parser.add_argument("--age-days", type=int, default=None, help="today-N 일을 cutoff 로")
    parser.add_argument("--today", default=None, help="기준일 주입 (YYYY-MM-DD, 재현용)")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--apply", action="store_true", help="실제 이동 수행(기본 dry-run)")
    args = parser.parse_args(argv)

    docs_root = args.docs_root or _default_docs_root()
    if not (docs_root / "04-report").is_dir():
        print(f"error: {docs_root}/04-report 디렉터리를 찾을 수 없습니다.", file=sys.stderr)
        return 2

    if args.today is not None:
        try:
            ty = [int(x) for x in args.today.split("-")]
            today = date(ty[0], ty[1], ty[2])
        except (ValueError, IndexError):
            print(f"error: 잘못된 --today 형식: {args.today!r}", file=sys.stderr)
            return 2
    else:
        today = date.today()

    try:
        cutoff = compute_cutoff(today, args.cutoff, args.age_days)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cycles = discover_cycles(docs_root / "04-report")
    plans = build_plan(cycles, cutoff, docs_root)

    if args.apply:
        moved = apply_moves(plans)
        print(f"이동 완료: {len(moved)}개 파일")
        for src, dst in moved:
            print(f"  {src.as_posix()} -> {dst.as_posix()}")
        return 0

    print(render_json(plans, cutoff) if args.json else render_text(plans, cutoff))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
