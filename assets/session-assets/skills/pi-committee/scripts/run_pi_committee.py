#!/usr/bin/env python3
"""Locate the bundled MMS parent adapter and delegate without global writes."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _runner_from_root(root: Path) -> Path | None:
    candidate = root.expanduser().resolve() / "scripts" / "pi_committee_parent.py"
    return candidate if candidate.is_file() else None


def _locate_runner() -> Path:
    explicit = str(os.environ.get("MMS_PI_COMMITTEE_ROOT") or "").strip()
    if explicit:
        candidate = _runner_from_root(Path(explicit))
        if candidate:
            return candidate
        raise RuntimeError("MMS_PI_COMMITTEE_ROOT has no scripts/pi_committee_parent.py")

    source = Path(__file__).resolve()
    for parent in source.parents:
        candidate = _runner_from_root(parent)
        if candidate:
            return candidate

    for command in ("mmf", "mmd", "mmg", "mmm", "mms"):
        executable = shutil.which(command)
        if not executable:
            continue
        resolved = Path(executable).resolve()
        for parent in (resolved.parent, *resolved.parents):
            candidate = _runner_from_root(parent)
            if candidate:
                return candidate
    raise RuntimeError("cannot locate the MMS Pi committee parent adapter")


def main() -> int:
    try:
        runner = _locate_runner()
    except RuntimeError as exc:
        error = {"schema": "mms.pi_committee.skill_error.v1", "status": "error", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    os.execv(sys.executable, [sys.executable, str(runner), *sys.argv[1:]])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
