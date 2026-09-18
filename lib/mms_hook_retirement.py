#!/usr/bin/env python3
"""Recognize retired MMS automatic hooks; explicitly plan/apply JSON cleanup.

No config discovery, launcher initialization, subprocesses or marker operations.
CLI output contains only paths, locators and hashes, never settings contents.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import tempfile

_NAMES = {
    "nsr-codex-hook.sh", "nsr-claude-hook.sh", "nsr-stop-wrapper.py",
    "nsr-builtin-hook.py", "claude-map-auto-index.sh",
    "claude-codegraph-auto-index.sh",
}
_ALIASES = {"map-auto-index.sh", "codegraph-auto-index.sh"}


def is_retired_automatic_hook(command: object) -> bool:
    if not isinstance(command, str):
        return False
    try:
        args = shlex.split(command)
    except ValueError:
        return False
    if not args:
        return False
    # One observed MMS-owned absolute home assignment is supported; no env
    # command, extra assignments, expansion, substitution or shell grammar.
    if args[0].startswith("MMS_REAL_HOME="):
        owner_home = args.pop(0).split("=", 1)[1]
        if (not Path(owner_home).is_absolute() or ".." in Path(owner_home).parts
                or any(char in owner_home for char in "$`;|&<>\n\r")):
            return False
        if not args:
            return False
    # Accept only a direct script or a simple interpreter invocation, not shell
    # pipelines, arbitrary -c programs, similarly named files or explicit CLIs.
    if Path(args[0]).name in {"bash", "sh", "python", "python3"}:
        args = args[1:]
    if not args:
        return False
    script = Path(args[0])
    if not script.is_absolute() or ".." in script.parts:
        return False
    if len(args) > 1 and not (script.name in {"nsr-stop-wrapper.py", "nsr-builtin-hook.py"}
                             and args[1:] in (["codex"], ["claude"])):
        return False
    parts = script.parts
    owned = (".mms" in parts and parts[-3:-1] == (".mms", "hooks")) or (
        "multi-model-switch" in parts and script.parent.name == "hooks")
    if owned and script.name in _NAMES:
        return True
    return parts[-3:-1] == (".claude", "hooks") and script.name in _ALIASES


def cleanup_payload(payload: object) -> tuple[object, list[dict]]:
    result = copy.deepcopy(payload)
    removed = []
    if not isinstance(result, dict) or not isinstance(result.get("hooks"), dict):
        return result, removed
    for event, groups in list(result["hooks"].items()):
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for gi, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            kept = []
            for hi, hook in enumerate(group["hooks"]):
                if isinstance(hook, dict) and hook.get("type", "command") == "command" and is_retired_automatic_hook(hook.get("command")):
                    removed.append({"event": event, "group": gi, "hook": hi,
                                    "command_sha256": hashlib.sha256(hook["command"].encode()).hexdigest()})
                else:
                    kept.append(hook)
            if kept or len(kept) == len(group["hooks"]):
                group["hooks"] = kept
                kept_groups.append(group)
        if kept_groups or len(kept_groups) == len(groups):
            result["hooks"][event] = kept_groups
        else:
            result["hooks"].pop(event)
    return result, removed


def process_file(path: Path, *, apply=False, expected_sha256=None, backup_dir=None) -> dict:
    if path.is_symlink():
        raise ValueError("symlink settings are not modified; choose the reviewed real file")
    if not path.exists():
        return {"path": str(path), "status": "missing", "removed": []}
    before = path.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    data, removed = cleanup_payload(json.loads(before))
    result = {"path": str(path), "status": "planned" if removed else "unchanged",
              "before_sha256": before_hash, "removed": removed}
    if not apply:
        return result
    if expected_sha256 != before_hash:
        raise ValueError("settings changed since review: expected SHA256 does not match")
    if not removed:
        return result
    if backup_dir is None:
        raise ValueError("--backup-dir is required for apply")
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(backup_dir.stat().st_mode) & 0o077:
        raise ValueError("backup directory must be private (0700)")
    backup = backup_dir / f"{path.name}.{before_hash}.before"
    with backup.open("xb") as out:
        os.chmod(backup, 0o600)
        out.write(before)
    after = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.retired-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), stat.S_IMODE(path.stat().st_mode))
            out.write(after)
        if hashlib.sha256(path.read_bytes()).hexdigest() != before_hash:
            raise ValueError("settings changed during cleanup; no replacement made")
        os.replace(raw, path)
    finally:
        Path(raw).unlink(missing_ok=True)
    result.update(status="applied", after_sha256=hashlib.sha256(after).hexdigest(), backup=str(backup))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Explicit CAS apply; default only prints a cleanup plan")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.apply and (len(args.file) != 1 or not args.expected_sha256 or not args.backup_dir):
        parser.error("apply requires one --file, --expected-sha256 and --backup-dir")
    try:
        reports = [process_file(p, apply=args.apply, expected_sha256=args.expected_sha256,
                                backup_dir=args.backup_dir) for p in args.file]
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}))
        return 2
    print(json.dumps({"schema": "mms.retired-hooks-cleanup.v1", "files": reports}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
