"""Emit ``pip freeze`` restricted to the dependency closure of the requirements files.

Usage::

    python scripts/freeze_lock.py > requirements.lock.txt

A plain ``pip freeze`` lists everything in the venv, which on a developer
machine often includes the portal-only packages from
``webcloring-pdf/requirements.txt`` (selenium, webdriver-manager, ...). Those
were deliberately split out of the server lock in 2026-06, so the lock is
rebuilt here from the closure of ``requirements.txt`` + ``requirements-dev.txt``
over the installed metadata instead.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from importlib.metadata import distributions
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
REQ_FILES = ("requirements.txt", "requirements-dev.txt")
CONSTRAINTS = ROOT / "constraints.txt"


def _root_names(path: Path) -> list[str]:
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(canonicalize_name(Requirement(line).name))
    return names


def _closure(roots: list[str]) -> set[str]:
    installed = {canonicalize_name(d.metadata["Name"]): d for d in distributions()}
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen or name not in installed:
            continue
        seen.add(name)
        for spec in installed[name].requires or []:
            req = Requirement(spec)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            stack.append(canonicalize_name(req.name))
    return seen


def main() -> int:
    roots = [n for f in REQ_FILES for n in _root_names(ROOT / f)]
    keep = _closure(roots)
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    held = ""
    if CONSTRAINTS.exists():
        pins = [ln.strip() for ln in CONSTRAINTS.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")]
        held = ", ".join(pins) or "none"
    today = date.today().isoformat()
    print(f"# requirements.lock.txt -- generated {today} by scripts/freeze_lock.py")
    print(f"# Source: Python {sys.version.split()[0]}, closure of {' + '.join(REQ_FILES)}")
    print(
        "# Regenerate: pip install -U --upgrade-strategy eager -r requirements.txt"
        " -r requirements-dev.txt -c constraints.txt;"
        " python scripts/freeze_lock.py > requirements.lock.txt"
    )
    if held:
        print(f"#   constraints held on purpose: {held}")
    for line in freeze:
        if canonicalize_name(line.split("==", 1)[0]) in keep:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
