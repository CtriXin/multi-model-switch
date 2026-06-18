#!/usr/bin/env python3
"""Enable/disable/status helper for local NSR Stop-hook wrapper."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=10)


def marker_path(cwd: str | Path) -> Path:
    root = Path(cwd).expanduser().resolve()
    result = run_git(root, ["rev-parse", "--git-path", "nsr/enabled"])
    if result.returncode == 0 and result.stdout.strip():
        path = Path(result.stdout.strip())
        if not path.is_absolute():
            top = run_git(root, ["rev-parse", "--show-toplevel"])
            base = Path(top.stdout.strip()).resolve() if top.returncode == 0 and top.stdout.strip() else root
            path = base / path
        return path
    return root / ".agent.local" / "nsr" / "enabled"


def enable(cwd: str) -> int:
    marker = marker_path(cwd)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("enabled\n", encoding="utf-8")
    print(f"NSR enabled: {marker}")
    return 0


def disable(cwd: str) -> int:
    marker = marker_path(cwd)
    marker.unlink(missing_ok=True)
    print(f"NSR disabled: {marker}")
    return 0


def status(cwd: str) -> int:
    marker = marker_path(cwd)
    active = marker.exists()
    print(f"NSR {'enabled' if active else 'disabled'}: {marker}")
    return 0 if active else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["enable", "disable", "status"])
    parser.add_argument("cwd", nargs="?", default=".")
    args = parser.parse_args()
    if args.action == "enable":
        return enable(args.cwd)
    if args.action == "disable":
        return disable(args.cwd)
    return status(args.cwd)


if __name__ == "__main__":
    raise SystemExit(main())
