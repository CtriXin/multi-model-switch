#!/usr/bin/env python3
"""Install handover/offduty/onduty skill surfaces globally.

Legacy command symlinks are removed when they are managed by this installer so
the same name does not appear twice in command/skill pickers.
"""

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
LEGACY_COMMAND_NAMES = ("offduty.md", "onduty.md")
LEGACY_COMMAND_TARGETS = {
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
        if path.is_dir():
            return _merge_into_existing_dir(path, target)
        return {"path": str(path), "target": str(target), "status": "skipped_existing_non_symlink"}
    path.symlink_to(target)
    return {"path": str(path), "target": str(target), "status": "created_symlink"}


def _merge_into_existing_dir(path: Path, target: Path) -> dict[str, str]:
    """When *path* is a real directory (e.g. ``~/.claude/skills/``), symlink
    individual entries from *target* into it so that skills installed via this
    package become visible even when the parent directory is not a symlink."""
    merged = 0
    skipped = 0
    if target.is_dir():
        for item in target.iterdir():
            dst = path / item.name
            if dst.exists() or dst.is_symlink():
                skipped += 1
                continue
            try:
                dst.symlink_to(item)
                merged += 1
            except OSError:
                skipped += 1
    return {
        "path": str(path),
        "target": str(target),
        "status": f"merged_into_existing_dir (+{merged} -{skipped})",
    }


def is_managed_legacy_command_symlink(path: Path) -> bool:
    expected = LEGACY_COMMAND_TARGETS.get(path.name)
    if expected is None:
        return False
    return readlink_path(path) == expected.resolve(strict=False)


def cleanup_legacy_command(path: Path) -> dict[str, str]:
    if path.is_symlink():
        if is_managed_legacy_command_symlink(path):
            path.unlink()
            return {"path": str(path), "status": "removed_legacy_command_symlink"}
        return {"path": str(path), "status": "skipped_existing_unmanaged"}
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        if MARKER not in text:
            return {"path": str(path), "status": "skipped_existing_unmanaged"}
        path.unlink()
        return {"path": str(path), "status": "removed_legacy_managed_command_file"}
    return {"path": str(path), "status": "ok_absent"}


def main() -> int:
    results: list[dict[str, str]] = []
    for directory in skill_dirs():
        results.append(ensure_dir_symlink(directory / SKILL_NAME, ROOT))
        for name, target in ALIAS_SKILLS.items():
            results.append(ensure_dir_symlink(directory / name, target))
    for directory in command_dirs():
        for name in LEGACY_COMMAND_NAMES:
            results.append(cleanup_legacy_command(directory / name))
    failed = {
        "skipped_existing_non_symlink",
        "skipped_existing_unmanaged",
    }
    ok = all(item["status"] not in failed for item in results)
    print(json.dumps({"ok": ok, "root": str(ROOT), "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
