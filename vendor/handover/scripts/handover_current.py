#!/usr/bin/env python3
"""Generic guard for .ai/plan/current.md ownership.

Run from any project root or pass --root.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def project_root(args: argparse.Namespace) -> Path:
    return Path(args.root).expanduser().resolve()


def paths(root: Path) -> dict[str, Path]:
    plan = root / ".ai" / "plan"
    return {
        "plan": plan,
        "current": plan / "current.md",
        "handoff": plan / "handoff.md",
        "owner": plan / "current-owner.json",
        "audit": plan / "current-audit.jsonl",
        "progress": plan / "progress",
    }


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def parse_current(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    fields: dict[str, str] = {}
    patterns = {
        "timestamp": r"^(?:Timestamp|Last Updated):\s*(.+)$",
        "owner": r"^Owner:\s*(.+)$",
        "cli": r"^CLI:\s*(.+)$",
        "model": r"^Model:\s*(.+)$",
        "task_id": r"^Task ID:\s*(.+)$",
        "run_id": r"^Run ID:\s*(.+)$",
        "status": r"^Status:\s*(.+)$",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            fields[key] = match.group(1).strip()
    return fields


def prepend_handoff(path: Path, entry: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else "# Handoff\n"
    title = "# Handoff Log\n" if old.startswith("# Handoff Log") else "# Handoff\n"
    body = re.sub(r"^# Handoff(?: Log)?\n+", "", old, count=1)
    path.write_text(title + "\n" + entry.rstrip() + "\n\n" + body.lstrip(), encoding="utf-8")


def cmd_status(args: argparse.Namespace) -> int:
    root = project_root(args)
    p = paths(root)
    owner = read_json(p["owner"])
    current = parse_current(p["current"])
    print("handover current status")
    print(f"- root: {root}")
    print(f"- current_exists: {p['current'].exists()}")
    print(f"- current_sha: {sha256(p['current']) or '-'}")
    if p["current"].exists():
        print(f"- current_mtime: {dt.datetime.fromtimestamp(p['current'].stat().st_mtime).astimezone().isoformat(timespec='seconds')}")
    print(f"- current_owner_header: {current.get('owner', '-')}")
    print(f"- current_cli_header: {current.get('cli', '-')}")
    print(f"- current_model_header: {current.get('model', '-')}")
    print(f"- current_task_id_header: {current.get('task_id', '-')}")
    print(f"- current_status_header: {current.get('status', '-')}")
    if owner:
        print(f"- claimed_owner: {owner.get('owner', '-')}")
        print(f"- claimed_cli: {owner.get('cli', '-')}")
        print(f"- claimed_model: {owner.get('model', '-')}")
        print(f"- claimed_task_id: {owner.get('task_id', '-')}")
        print(f"- claimed_at: {owner.get('claimed_at', '-')}")
    else:
        print("- claimed_owner: none")
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    root = project_root(args)
    p = paths(root)
    p["plan"].mkdir(parents=True, exist_ok=True)
    p["progress"].mkdir(parents=True, exist_ok=True)
    record = {
        "claimed_at": now_iso(),
        "task_id": args.task_id,
        "run_id": args.run_id,
        "owner": args.owner,
        "cli": args.cli,
        "model": args.model,
        "status": args.status,
        "next_action": args.next_action,
        "current_sha_at_claim": sha256(p["current"]),
    }
    write_json(p["owner"], record)
    append_jsonl(p["audit"], {"event": "claim", **record})
    entry = f"""## {record['claimed_at']} | agent={args.owner} | cli={args.cli} | model={args.model} | task={args.task_id}
- TL;DR: Claimed top-level `current.md` ownership.
- Next action: {args.next_action}
- Scope / boundary: Only this owner should overwrite `current.md`; side sessions should write `progress/<task-id>.md`.
- Validation: current_sha_at_claim={record['current_sha_at_claim'] or '-'}
- Risk: If audit reports conflict, inspect `handoff.md` before continuing."""
    prepend_handoff(p["handoff"], entry)
    print(f"claimed current.md owner: {args.owner} ({args.cli}, {args.model}) task={args.task_id}")
    print(f"owner file: {p['owner']}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    root = project_root(args)
    p = paths(root)
    owner = read_json(p["owner"])
    current = parse_current(p["current"])
    findings: list[str] = []
    if not p["current"].exists():
        findings.append("current.md missing")
    if not owner:
        findings.append("no current-owner.json claim found")
    for key in ("owner", "cli", "model"):
        if current and not current.get(key):
            findings.append(f"current.md has no {key} header")
    if owner and current.get("owner") and owner.get("owner") != current.get("owner"):
        findings.append(f"owner mismatch: claim={owner.get('owner')} current={current.get('owner')}")
    if owner and current.get("cli") and owner.get("cli") != current.get("cli"):
        findings.append(f"cli mismatch: claim={owner.get('cli')} current={current.get('cli')}")
    if owner and current.get("model") and owner.get("model") != current.get("model"):
        findings.append(f"model mismatch: claim={owner.get('model')} current={current.get('model')}")
    result = {
        "event": "audit",
        "ts": now_iso(),
        "root": str(root),
        "current_sha": sha256(p["current"]),
        "current_header": current,
        "claimed_owner": owner,
        "findings": findings,
        "verdict": "CONFLICT_OR_INCOMPLETE" if findings else "OK",
    }
    append_jsonl(p["audit"], result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if findings else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard .ai/plan/current.md ownership")
    parser.add_argument("--root", default=".", help="project root, default cwd")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show current owner and current.md header")

    claim = sub.add_parser("claim", help="Claim top-level current.md ownership")
    claim.add_argument("--task-id", required=True)
    claim.add_argument("--run-id", default="")
    claim.add_argument("--owner", required=True)
    claim.add_argument("--cli", required=True)
    claim.add_argument("--model", required=True)
    claim.add_argument("--status", default="in_progress")
    claim.add_argument("--next-action", required=True)

    sub.add_parser("audit", help="Check claim/header consistency")

    args = parser.parse_args()
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "claim":
        return cmd_claim(args)
    if args.cmd == "audit":
        return cmd_audit(args)
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
