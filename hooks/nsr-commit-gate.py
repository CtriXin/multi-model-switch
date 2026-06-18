#!/usr/bin/env python3
"""Conservative pre-commit safety gate for agent-created commits.

This does not create commits. It only answers: "is the current dirty tree safe
enough for an agent to commit without asking a human first?"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_FILE_BYTES = int(os.environ.get("NSR_COMMIT_GATE_MAX_FILE_BYTES", "5000000"))

GENERATED_PARTS = {
    ".cache",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".turbo",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
}

SECRET_NAMES = {
    ".env",
    ".env.local",
    ".netrc",
    "credentials",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}

SECRET_SUFFIXES = {
    ".crt",
    ".db",
    ".der",
    ".key",
    ".kubeconfig",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}

LOCKFILES = {
    "Cargo.lock",
    "Pipfile.lock",
    "bun.lockb",
    "composer.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "yarn.lock",
}

SECRET_PATTERNS = [
    ("private key block", re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws access key", re.compile(rb"\bA(KIA|SIA)[A-Z0-9]{16}\b")),
    ("github token", re.compile(rb"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{30,}\b")),
    ("github fine-grained token", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("openai-style api key", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    (
        "secret-like assignment",
        re.compile(
            rb"(?i)\b(api[_-]?key|access[_-]?key|secret|token|password|passwd|private[_-]?key)"
            rb"\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{12,}"
        ),
    ),
]


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def git_root(repo: Path) -> Path:
    result = run_git(repo, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "not a git repository")
    return Path(result.stdout.strip())


def dirty_paths(repo: Path) -> list[str]:
    result = run_git(repo, ["status", "--porcelain=v1", "-z"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")

    items = [item for item in result.stdout.split("\0") if item]
    paths: list[str] = []
    i = 0
    while i < len(items):
        entry = items[i]
        status = entry[:2]
        path = entry[3:]
        if path:
            paths.append(path)
        if status[0] in {"R", "C"} and i + 1 < len(items):
            i += 1
            paths.append(items[i])
        i += 1
    return sorted(dict.fromkeys(paths))


def path_reason(path: str, full_path: Path, *, max_file_bytes: int = MAX_FILE_BYTES) -> str:
    parts = set(Path(path).parts)
    name = Path(path).name
    lowered = name.lower()

    if parts.intersection(GENERATED_PARTS):
        return "generated/cache path"
    if lowered in SECRET_NAMES or lowered.startswith(".env."):
        return "secret or local config file"
    if name in LOCKFILES:
        return "dependency lockfile changed; review manually"
    if any(lowered.endswith(suffix) for suffix in SECRET_SUFFIXES):
        return "secret/binary credential-like file"
    if full_path.exists() and full_path.is_symlink():
        return "symlink; review target manually"
    if full_path.exists() and full_path.is_file() and full_path.stat().st_size > max_file_bytes:
        return f"file larger than {max_file_bytes} bytes"
    return ""


def safe_repo_path(root: Path, rel_path: str) -> Path | None:
    full_path = (root / rel_path).resolve()
    try:
        full_path.relative_to(root.resolve())
    except ValueError:
        return None
    return full_path


def read_file_bytes(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes:
    with open(path, "rb") as f:
        return f.read(limit + 1)


def content_reason(data: bytes) -> str:
    if b"\0" in data[:4096]:
        return "binary file; review manually"
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            return label
    return ""


def scan(repo: str | Path = ".") -> dict[str, object]:
    root = git_root(Path(repo))
    paths = dirty_paths(root)
    blocked: list[dict[str, str]] = []

    for rel_path in paths:
        full_path = safe_repo_path(root, rel_path)
        if full_path is None:
            blocked.append({"path": rel_path, "reason": "path escapes repo root"})
            continue

        reason = path_reason(rel_path, full_path)
        if reason:
            blocked.append({"path": rel_path, "reason": reason})
            continue

        if not full_path.exists() or not full_path.is_file():
            continue
        try:
            data = read_file_bytes(full_path)
        except OSError:
            blocked.append({"path": rel_path, "reason": "file could not be read"})
            continue
        reason = content_reason(data)
        if reason:
            blocked.append({"path": rel_path, "reason": reason})

    return {
        "ok": not blocked,
        "repo_root": str(root),
        "dirty_files": paths,
        "blocked": blocked,
    }


def format_text(result: dict[str, object]) -> str:
    blocked = result["blocked"]
    dirty = result["dirty_files"]
    if not blocked:
        return f"OK: commit gate passed for {len(dirty)} dirty file(s)."

    lines = ["BLOCK: commit gate found unsafe changes:"]
    for item in blocked:
        lines.append(f"- {item['path']}: {item['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Git repo or subdirectory to scan")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        result = scan(args.repo)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        error = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
