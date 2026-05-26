#!/usr/bin/env python3
"""Install handover/offduty/onduty skill and command surfaces globally."""

from __future__ import annotations

import json
import os
from pathlib import Path

MARKER = "<!-- Managed by shared-skills handover continuity installer -->"
ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "handover"
ALIAS_SKILLS = {
    "offduty": ROOT / "aliases" / "offduty",
    "onduty": ROOT / "aliases" / "onduty",
}
COMMAND_SOURCES = {
    "offduty.md": ROOT / "commands" / "offduty.md",
    "onduty.md": ROOT / "commands" / "onduty.md",
}


def home() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))).expanduser()


def skill_dirs() -> list[Path]:
    h = home()
    return [
        h / ".agents" / "skills",
        h / ".claude" / "skills",
        h / ".codex" / "skills",
        h / ".config" / "opencode" / "skills",
        h / ".opencode" / "skills",
    ]


def command_dirs() -> list[Path]:
    h = home()
    return [
        h / ".agents" / "commands",
        h / ".claude" / "commands",
        h / ".codex" / "commands",
        h / ".config" / "opencode" / "commands",
        h / ".opencode" / "commands",
    ]


def readlink_path(path: Path) -> Path:
    target = Path(os.readlink(path))
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve(strict=False)


def ensure_dir_symlink(path: Path, target: Path) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = target.resolve(strict=False)
    if path.is_symlink():
        if readlink_path(path) == target:
            return {"path": str(path), "target": str(target), "status": "ok"}
        path.unlink()
        path.symlink_to(target)
        return {"path": str(path), "target": str(target), "status": "updated_symlink"}
    if path.exists():
        return {"path": str(path), "target": str(target), "status": "skipped_existing_non_symlink"}
    path.symlink_to(target)
    return {"path": str(path), "target": str(target), "status": "created_symlink"}


def ensure_command_symlink(path: Path, target: Path) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = target.resolve(strict=False)
    if not target.exists():
        return {"path": str(path), "target": str(target), "status": "missing_source"}
    if path.is_symlink():
        if readlink_path(path) == target:
            return {"path": str(path), "target": str(target), "status": "ok"}
        path.unlink()
        path.symlink_to(target)
        return {"path": str(path), "target": str(target), "status": "updated_symlink"}
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        if MARKER not in text:
            return {"path": str(path), "target": str(target), "status": "skipped_existing_unmanaged"}
        path.unlink()
        path.symlink_to(target)
        return {"path": str(path), "target": str(target), "status": "replaced_managed_file_with_symlink"}
    path.symlink_to(target)
    return {"path": str(path), "target": str(target), "status": "created_symlink"}


def main() -> int:
    results: list[dict[str, str]] = []
    for directory in skill_dirs():
        results.append(ensure_dir_symlink(directory / SKILL_NAME, ROOT))
        for name, target in ALIAS_SKILLS.items():
            results.append(ensure_dir_symlink(directory / name, target))
    for directory in command_dirs():
        for name, target in COMMAND_SOURCES.items():
            results.append(ensure_command_symlink(directory / name, target))
    failed = {
        "missing_source",
        "skipped_existing_non_symlink",
        "skipped_existing_unmanaged",
    }
    ok = all(item["status"] not in failed for item in results)
    print(json.dumps({"ok": ok, "root": str(ROOT), "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
