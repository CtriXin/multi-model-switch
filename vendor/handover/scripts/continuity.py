#!/usr/bin/env python3
"""Offduty/onduty continuity helper for repo-local handover files.

This script keeps fresh-session pickup small while preserving enough task,
artifact, and git evidence to continue real work after restart or machine switch.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from handover_current import append_jsonl, paths, prepend_handoff, read_json, sha256, write_json


STATUS_VALUES = {
    "active",
    "parked",
    "done",
    "blocked",
    "stale",
    "archived",
    "running",
    "waiting",
    "request_human",
    "failed",
}
KEEP_VALUES = {"yes", "revisit", "no", "archive"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def now_stamp() -> str:
    return dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def clean(value: object, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def short_hash(value: object, length: int = 8) -> str:
    text = clean(value, "-")
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def safe_slug(value: str, default: str = "task", max_len: int = 64) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", clean(value).lower()).strip("-._")
    slug = slug or default
    if len(slug) <= max_len:
        return slug
    suffix = short_hash(value)
    keep = max(8, max_len - len(suffix) - 1)
    return f"{slug[:keep].rstrip('-._')}-{suffix}"


def safe_task_id(value: str) -> str:
    return safe_slug(value, "task", 48)


def project_root(root: str) -> Path:
    raw = Path(root).expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(raw), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return raw


def run_git(root: Path, args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, result.stdout.rstrip()


def git_meta(root: Path) -> dict[str, Any]:
    def out(args: list[str]) -> str:
        code, text = run_git(root, args)
        return text if code == 0 else ""

    status = out(["status", "--short"])
    changed: list[str] = []
    for line in status.splitlines():
        path = line[3:] if len(line) > 3 else line
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            changed.append(path)
    return {
        "is_git": bool(out(["rev-parse", "--git-dir"])),
        "branch": out(["branch", "--show-current"]),
        "head": out(["rev-parse", "--short", "HEAD"]),
        "status_short": status,
        "changed_files": sorted(set(changed)),
        "diff_stat": out(["diff", "--stat"]),
        "cached_diff_stat": out(["diff", "--cached", "--stat"]),
    }


def detect_cli() -> str:
    if os.environ.get("CODEX_THREAD_ID"):
        return "codex"
    if os.environ.get("CLAUDE_SESSION_ID"):
        return "claude-code"
    if os.environ.get("OPENCODE_SESSION_ID"):
        return "opencode"
    if os.environ.get("MMS_SESSION_PACKET_JSON"):
        return "mms"
    return clean(os.environ.get("AGENT_CLI"), "script")


def detect_model(cli: str = "") -> str:
    model = ""
    cli = clean(cli) or detect_cli()
    model_keys_by_cli = {
        "codex": ("CODEX_MODEL", "AGENT_MODEL", "MMS_MODEL_NAME", "OPENAI_MODEL", "MODEL_NAME"),
        "claude-code": ("CLAUDE_MODEL", "ANTHROPIC_MODEL", "AGENT_MODEL", "MMS_MODEL_NAME", "MODEL_NAME"),
        "opencode": ("OPENCODE_MODEL", "AGENT_MODEL", "MMS_MODEL_NAME", "MODEL_NAME"),
        "mms": ("MMS_MODEL_NAME", "AGENT_MODEL", "MODEL_NAME"),
        "script": (
            "AGENT_MODEL",
            "MODEL_NAME",
            "MMS_MODEL_NAME",
            "CODEX_MODEL",
            "CLAUDE_MODEL",
            "OPENCODE_MODEL",
            "OPENAI_MODEL",
            "ANTHROPIC_MODEL",
        ),
    }
    for key in model_keys_by_cli.get(cli, model_keys_by_cli["script"]):
        if clean(os.environ.get(key)):
            model = clean(os.environ.get(key))
            break
    if not model:
        return "unknown"
    for key in (
        "CODEX_REASONING_EFFORT",
        "MMS_REASONING_EFFORT",
        "AGENT_REASONING_EFFORT",
        "OPENCODE_REASONING_EFFORT",
        "CLAUDE_REASONING_EFFORT",
    ):
        effort = clean(os.environ.get(key))
        if effort and effort.lower() not in model.lower():
            return f"{model} {effort}"
    return model


def model_family(model: str) -> str:
    value = clean(model, "unknown").lower()
    families = [
        ("openai", ("gpt-", "o1", "o3", "o4", "o5", "codex", "openai")),
        ("anthropic", ("claude", "anthropic")),
        ("qwen", ("qwen",)),
        ("kimi", ("kimi", "moonshot")),
        ("deepseek", ("deepseek",)),
        ("minimax", ("minimax",)),
        ("mimo", ("mimo",)),
        ("google", ("gemini", "google")),
        ("zhipu", ("glm", "zhipu")),
    ]
    for family, needles in families:
        if any(needle in value for needle in needles):
            return family
    return "unknown"


def commit_email_hint(model: str, family: str) -> str:
    model_slug = safe_slug(clean(model, "unknown").split()[0], "unknown", 64)
    family_slug = safe_slug(clean(family, "unknown"), "unknown", 32)
    return f"{model_slug}@{family_slug}.com"


def detect_session_id() -> str:
    for key in ("CODEX_THREAD_ID", "CLAUDE_SESSION_ID", "OPENCODE_SESSION_ID", "LOOOP_SESSION_ID", "MMS_SESSION_ID", "AGENT_SESSION_ID"):
        value = safe_slug(clean(os.environ.get(key)), "")
        if value:
            return value
    return f"session-{now_stamp()}"


def plan_paths(root: Path) -> dict[str, Path]:
    p = paths(root)
    p["packet"] = p["plan"] / "packet.json"
    p["sessions"] = p["plan"] / "sessions"
    p["archive"] = p["plan"] / "archive"
    p["diffs"] = p["plan"] / "diffs"
    p["onduty"] = p["plan"] / "onduty-brief.md"
    return p


def agent_paths(root: Path) -> dict[str, Path]:
    base = root / ".agent.local" / "continuity"
    return {
        "base": base,
        "active": base / "active.json",
        "pickup_json": base / "pickup.json",
        "pickup_md": base / "pickup.md",
        "checkpoints": base / "checkpoints",
        "sessions": base / "sessions",
        "indexes": base / "indexes",
        "diffs": base / "diffs",
        "lifeboat": base / "lifeboat",
        "archive": base / "archive",
    }


def rel_ref(root: Path, path: Path) -> str:
    try:
        return f"./{path.relative_to(root)}"
    except ValueError:
        return str(path)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{short_hash(now_iso(), 6)}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{short_hash(now_iso(), 6)}")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def ensure_agent_local_guard(root: Path) -> None:
    guard = root / ".agent.local" / ".gitignore"
    if not guard.exists():
        guard.parent.mkdir(parents=True, exist_ok=True)
        guard.write_text("*\n!.gitignore\n", encoding="utf-8")
    code, exclude = run_git(root, ["rev-parse", "--git-path", "info/exclude"])
    if code == 0 and clean(exclude):
        exclude_path = Path(exclude)
        if not exclude_path.is_absolute():
            exclude_path = root / exclude_path
        existing = exclude_path.read_text(encoding="utf-8", errors="replace") if exclude_path.exists() else ""
        existing_lines = set(existing.splitlines())
        missing = [item for item in (".agent.local/", ".ai/continuity/") if item not in existing_lines]
        if missing:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            suffix = "" if existing.endswith("\n") or not existing else "\n"
            exclude_path.write_text(existing + suffix + "\n".join(missing) + "\n", encoding="utf-8")


def resolve_layout(root: Path, requested: str, *, write: bool) -> str:
    if requested in {"agent-local", "legacy-ai-plan"}:
        return requested
    if write:
        return "agent-local"
    ap = agent_paths(root)
    if ap["active"].exists() or ap["pickup_md"].exists() or ap["checkpoints"].exists():
        return "agent-local"
    lp = plan_paths(root)
    if lp["current"].exists() or lp["packet"].exists() or lp["handoff"].exists():
        return "legacy-ai-plan"
    return "agent-local"


def active_task(root: Path) -> str:
    active = read_json(agent_paths(root)["active"]) or {}
    return clean(active.get("task_id")) if isinstance(active, dict) else ""


def should_write_active(root: Path, task_id: str, scope: str) -> bool:
    if scope == "main":
        return True
    if scope == "side":
        return False
    current = active_task(root)
    return not current or current == task_id


def write_agent_diff_snapshot(root: Path, task_id: str, session_id: str, mode: str) -> str:
    if mode != "patch":
        return ""
    meta = git_meta(root)
    if not meta["status_short"]:
        return ""
    diff_dir = agent_paths(root)["diffs"]
    diff_dir.mkdir(parents=True, exist_ok=True)
    path = diff_dir / f"{now_stamp()}-{safe_task_id(task_id)}-{safe_slug(session_id, 'session', 40)}.patch"
    parts = ["# git status --short", meta["status_short"], "", "# git diff --binary"]
    _, unstaged = run_git(root, ["diff", "--binary"])
    _, staged = run_git(root, ["diff", "--cached", "--binary"])
    parts.extend([unstaged, "", "# git diff --cached --binary", staged])
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return rel_ref(root, path)


def existing_current_task(root: Path) -> str:
    current = plan_paths(root)["current"]
    if not current.exists():
        return ""
    text = current.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^Task ID:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def should_write_main(root: Path, task_id: str, scope: str) -> bool:
    if scope == "main":
        return True
    if scope == "side":
        return False
    owner = read_json(plan_paths(root)["owner"])
    current_task = existing_current_task(root)
    if not owner and not current_task:
        return True
    if clean(owner.get("task_id") if owner else "") == task_id:
        return True
    if current_task == task_id:
        return True
    return False


def archive_text(root: Path, name: str, text: str) -> Path:
    month = dt.datetime.now().astimezone().strftime("%Y-%m")
    archive_dir = plan_paths(root)["archive"] / month
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{safe_slug(name)}-{now_stamp()}.md"
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def split_handoff_entries(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    title = "# Handoff"
    if lines and lines[0].startswith("# Handoff"):
        title = lines[0]
        body = "\n".join(lines[1:]).lstrip()
    else:
        body = text
    matches = list(re.finditer(r"(?m)^## ", body))
    if not matches:
        return title, [body.strip()] if body.strip() else []
    entries: list[str] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        entry = body[match.start():end].strip()
        if entry:
            entries.append(entry)
    return title, entries


def rotate_handoff(root: Path, max_entries: int) -> str:
    handoff = plan_paths(root)["handoff"]
    if not handoff.exists() or max_entries <= 0:
        return ""
    title, entries = split_handoff_entries(handoff.read_text(encoding="utf-8", errors="replace"))
    if len(entries) <= max_entries:
        return ""
    keep = entries[:max_entries]
    old = entries[max_entries:]
    archive_path = archive_text(root, "handoff-rollup", "# Archived Handoff Entries\n\n" + "\n\n".join(old))
    handoff.write_text(title.rstrip() + "\n\n" + "\n\n".join(keep).rstrip() + "\n", encoding="utf-8")
    return str(archive_path)


def docs_for(root: Path) -> list[str]:
    names = ["AGENTS.md", "CLAUDE.md", "README.md", "RTK.md"]
    return [name for name in names if (root / name).exists()]


def infer_work_type(args: argparse.Namespace, meta: dict[str, Any]) -> str:
    explicit = clean(getattr(args, "work_type", ""))
    if explicit:
        return explicit
    haystack = " ".join(
        [
            clean(args.task_id),
            clean(args.title),
            clean(args.summary),
            clean(args.next_action),
            clean(meta.get("branch")),
        ]
    ).lower()
    buckets = [
        ("bugfix", ("bug", "fix", "repair", "error", "fail", "timeout", "crash", "404", "500", "regression")),
        ("feature", ("feature", "implement", "add", "new", "ship", "build", "support")),
        ("explore", ("explore", "research", "investigate", "spike", "try", "probe", "experiment")),
        ("review", ("review", "audit", "inspect", "gate", "risk")),
        ("plan", ("plan", "design", "proposal", "roadmap", "spec")),
    ]
    for label, needles in buckets:
        if any(needle in haystack for needle in needles):
            return label
    return "work"


def write_diff_snapshot(root: Path, task_id: str, session_id: str, mode: str) -> str:
    if mode != "patch":
        return ""
    meta = git_meta(root)
    if not meta["status_short"]:
        return ""
    diff_dir = plan_paths(root)["diffs"]
    diff_dir.mkdir(parents=True, exist_ok=True)
    path = diff_dir / f"{now_stamp()}-{safe_task_id(task_id)}-{safe_slug(session_id, 'session', 40)}.patch"
    parts = ["# git status --short", meta["status_short"], "", "# git diff --binary"]
    _, unstaged = run_git(root, ["diff", "--binary"])
    _, staged = run_git(root, ["diff", "--cached", "--binary"])
    parts.extend([unstaged, "", "# git diff --cached --binary", staged])
    path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return str(path.relative_to(root))


def md_list(items: list[str], empty: str = "-") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- `{item}`" for item in items)


def unique_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = clean(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def tail_text(text: object, limit: int = 20) -> str:
    if isinstance(text, bytes):
        value = text.decode("utf-8", errors="replace")
    else:
        value = clean(text)
    lines = value.strip().splitlines()
    return "\n".join(lines[-limit:])


def extract_attempt_rows(text: str) -> list[str]:
    match = re.search(r"(?ms)^## Attempt Log\n(.*?)(?=^## |\Z)", text)
    if not match:
        return []
    rows: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "---" in stripped or "Time" in stripped:
            continue
        rows.append(stripped)
    return rows


def extract_checkpoint_rows(text: str) -> list[str]:
    match = re.search(r"(?ms)^## Checkpoints\n(.*?)(?=^## |\Z)", text)
    if not match:
        return []
    rows: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            rows.append(stripped)
    return rows


def build_progress(args: argparse.Namespace, root: Path, meta: dict[str, Any], diff_ref: str, write_main: bool) -> tuple[Path, str]:
    p = plan_paths(root)
    progress = p["progress"] / f"{safe_task_id(args.task_id)}.md"
    old = progress.read_text(encoding="utf-8", errors="replace") if progress.exists() else ""
    attempts = extract_attempt_rows(old)
    attempt = clean(args.attempt) or clean(args.summary) or "offduty checkpoint"
    attempt_result = clean(args.attempt_result) or clean(args.status)
    keep = clean(args.keep, "yes")
    note = clean(args.note) or clean(args.summary) or "checkpoint"
    attempts.append(f"| {args.timestamp} | {attempt} | {attempt_result} | {keep} | {note} |")
    attempts = attempts[-args.max_progress_attempts :]

    checkpoints = extract_checkpoint_rows(old)
    changed = meta["changed_files"]
    checkpoint = (
        f"- {args.timestamp} | status={args.status} | scope={'main' if write_main else 'side'} | "
        f"changed={len(changed)} | session={args.session_id} | model={args.model} | cwd={args.cwd} | next={args.next_action}"
    )
    checkpoints.append(checkpoint)
    archived_note = ""
    if len(checkpoints) > args.max_progress_checkpoints:
        old_rows = checkpoints[: -args.max_progress_checkpoints]
        checkpoints = checkpoints[-args.max_progress_checkpoints :]
        archived = archive_text(root, f"{args.task_id}-progress-checkpoints", "# Archived Progress Checkpoints\n\n" + "\n".join(old_rows))
        archived_note = f"- Archived checkpoints: `{archived.relative_to(root)}`\n"

    validation = args.validation or []
    refs = args.ref or []
    doc_refs = docs_for(root)
    evidence_items = []
    if meta.get("branch") or meta.get("head"):
        evidence_items.append(f"git `{meta.get('branch') or '-'}@{meta.get('head') or '-'}`")
    if meta.get("diff_stat"):
        evidence_items.append("unstaged diff stat captured")
    if meta.get("cached_diff_stat"):
        evidence_items.append("cached diff stat captured")
    if diff_ref:
        evidence_items.append(f"patch snapshot `{diff_ref}`")

    content = f"""# Progress — {args.task_id}

- Title: {args.title}
- Task ID: {args.task_id}
- Run ID: {args.run_id}
- Session ID: {args.session_id}
- Session Hash: {args.session_hash}
- Checkpoint Hash: {args.checkpoint_hash}
- Agent: {args.agent}
- CLI: {args.cli}
- Model: {args.model}
- Model Name: {args.model}
- Model Family: {args.model_family}
- Commit Email Hint: {args.commit_email_hint}
- Status: {args.status}
- Work Type: {args.work_type}
- CWD: {args.cwd}
- Root: {root}
- Started: {args.timestamp}
- Updated: {args.timestamp}
- Current owner: {'self' if write_main else 'side-session'}

## Summary
- Current truth: {args.summary}
- Scope: {'main' if write_main else 'side'}
- Work type: {args.work_type}
- Branch: {meta.get('branch') or '-'}
- HEAD: {meta.get('head') or '-'}
- Changed files: {len(changed)}
- CWD: {args.cwd}
- Root: {root}
- Session: {args.session_id} ({args.session_hash})
- Model: {args.model}
- Model Family: {args.model_family}
- Commit Email Hint: {args.commit_email_hint}

## Current Truth
{args.summary}

## Attempt Log
| Time | Attempt | Result | Keep? | Note |
|---|---|---|---|---|
{chr(10).join(attempts)}

## Decisions
{md_list(args.decision or [], 'none recorded')}

## Evidence
- Docs: {', '.join(f'`{item}`' for item in doc_refs) or '-'}
- Git status: {'dirty' if meta['status_short'] else 'clean'}
- Diff evidence: {diff_ref or args.diff_mode}
{md_list(evidence_items, 'none')}

## Changed Files
{md_list(changed, 'none')}

## Validation
{md_list(validation, 'not run')}

## Next Action
- {args.next_action}

## Risks / Blockers
{md_list(args.risk or [], 'none recorded')}

## References
{md_list(refs, 'none')}

## Checkpoints
{chr(10).join(checkpoints)}
{archived_note}
## Handoff
- `current.md` updated: {'yes' if write_main else 'no'}
- `packet.json` updated: {'yes' if write_main else 'no'}
- latest offduty entry prepended to `./.ai/plan/handoff.md`
"""
    progress.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text(content, encoding="utf-8")
    return progress, archived_note


def write_current(args: argparse.Namespace, root: Path, meta: dict[str, Any], progress_ref: str, diff_ref: str) -> None:
    p = plan_paths(root)
    owner = {
        "claimed_at": args.timestamp,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "owner": args.agent,
        "cli": args.cli,
        "model": args.model,
        "model_name": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "cwd": args.cwd,
        "root": str(root),
        "status": args.status,
        "next_action": args.next_action,
        "current_sha_at_claim": sha256(p["current"]),
    }
    write_json(p["owner"], owner)
    append_jsonl(p["audit"], {"event": "continuity_claim", **owner})
    changed = meta["changed_files"]
    current = f"""# Current

Timestamp: {args.timestamp}
Owner: {args.agent}
CLI: {args.cli}
Model: {args.model}
Model Name: {args.model}
Model Family: {args.model_family}
Commit Email Hint: {args.commit_email_hint}
Task ID: {args.task_id}
Run ID: {args.run_id}
Session ID: {args.session_id}
Session Hash: {args.session_hash}
Checkpoint Hash: {args.checkpoint_hash}
CWD: {args.cwd}
Root: {root}
Status: {args.status}
Work Type: {args.work_type}
Goal: {args.title}

## TL;DR
- {args.summary}
- Changed files: {len(changed)}
- Git: `{meta.get('branch') or '-'}@{meta.get('head') or '-'}`

## Next Action
1. {args.next_action}

## Changed This Round
{md_list(changed, 'none')}

## Verification
{md_list(args.validation or [], 'not run')}

## Blockers / Risks
{md_list(args.risk or [], 'none recorded')}

## Pointers
- `./.ai/plan/packet.json`
- `./.ai/plan/handoff.md`
- `{progress_ref}`
{f'- `{diff_ref}`' if diff_ref else ''}
"""
    p["current"].parent.mkdir(parents=True, exist_ok=True)
    p["current"].write_text(current, encoding="utf-8")


def write_packet(args: argparse.Namespace, root: Path, meta: dict[str, Any], progress_ref: str, diff_ref: str) -> None:
    p = plan_paths(root)
    read_order = [
        "./AGENTS.md" if (root / "AGENTS.md").exists() else "",
        "./README.md" if (root / "README.md").exists() else "",
        "./.ai/plan/packet.json",
        "./.ai/plan/current.md",
        "./.ai/plan/handoff.md",
        progress_ref,
    ]
    if diff_ref:
        read_order.append(diff_ref)
    packet = {
        "schema_version": "handover-continuity-packet.v1",
        "updated": args.timestamp,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "cwd": args.cwd,
        "root": str(root),
        "goal": args.title,
        "status": args.status,
        "work_type": args.work_type,
        "owner": args.agent,
        "cli": args.cli,
        "model": args.model,
        "model_name": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "next_action": args.next_action,
        "constraints": args.constraint or [],
        "refs": [item for item in read_order if item],
        "changed_files": meta["changed_files"],
        "git": {
            "branch": meta.get("branch"),
            "head": meta.get("head"),
            "dirty": bool(meta.get("status_short")),
            "diff_stat": meta.get("diff_stat"),
            "cached_diff_stat": meta.get("cached_diff_stat"),
        },
        "diff_ref": diff_ref,
        "read_order": [item for item in read_order if item],
        "writeback_required": [
            "side sessions write .ai/plan/progress/<task-id>.md or .ai/plan/sessions/<session-id>.jsonl",
            "only supervisor/offduty updates current.md and packet.json",
            "rotate handoff.md; archive old entries under .ai/plan/archive/",
        ],
    }
    write_json(p["packet"], packet)


def write_session_event(args: argparse.Namespace, root: Path, meta: dict[str, Any], progress_ref: str, diff_ref: str, write_main: bool) -> Path:
    p = plan_paths(root)
    event = {
        "timestamp": args.timestamp,
        "event": "offduty",
        "task_id": args.task_id,
        "run_id": args.run_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "agent": args.agent,
        "cli": args.cli,
        "model": args.model,
        "model_name": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "cwd": args.cwd,
        "root": str(root),
        "status": args.status,
        "work_type": args.work_type,
        "scope": "main" if write_main else "side",
        "summary": args.summary,
        "next_action": args.next_action,
        "git": {
            "branch": meta.get("branch"),
            "head": meta.get("head"),
            "dirty": bool(meta.get("status_short")),
            "changed_files": meta.get("changed_files", []),
        },
        "progress_ref": progress_ref,
        "diff_ref": diff_ref,
    }
    path = p["sessions"] / f"{safe_slug(args.session_id, 'session', 40)}.jsonl"
    append_jsonl(path, event)
    return path


def write_handoff_entry(args: argparse.Namespace, root: Path, meta: dict[str, Any], progress_ref: str, diff_ref: str, write_main: bool) -> None:
    changed = meta["changed_files"]
    refs = ["./.ai/plan/packet.json" if write_main else "", "./.ai/plan/current.md" if write_main else "", progress_ref, diff_ref]
    refs = [ref for ref in refs if ref]
    entry = f"""## {args.timestamp} | agent={args.agent} | cli={args.cli} | model={args.model} | task={args.task_id}
- TL;DR: {args.summary}
- Status: {args.status}; scope={'main' if write_main else 'side'}; git={'dirty' if meta['status_short'] else 'clean'} `{meta.get('branch') or '-'}@{meta.get('head') or '-'}`
- CWD: `{args.cwd}`
- Root: `{root}`
- Session: `{args.session_id}` hash=`{args.session_hash}` checkpoint=`{args.checkpoint_hash}`
- Type: {args.work_type}
- Next action: {args.next_action}
- Changed files: {', '.join('`' + item + '`' for item in changed[:12]) if changed else 'none'}{f' (+{len(changed)-12} more)' if len(changed) > 12 else ''}
- Validation: {'; '.join(args.validation) if args.validation else 'not run'}
- Risks / open questions: {'; '.join(args.risk) if args.risk else 'none recorded'}
- References: {', '.join('`' + ref + '`' for ref in refs)}"""
    prepend_handoff(plan_paths(root)["handoff"], entry)


def cmd_offduty_legacy(args: argparse.Namespace) -> int:
    args.cwd = str(Path(args.cwd).expanduser().resolve()) if clean(args.cwd) else str(Path.cwd().resolve())
    root = project_root(args.root)
    args.timestamp = now_iso()
    args.session_id = safe_slug(args.session_id or detect_session_id(), "session", 64)
    args.session_hash = short_hash(args.session_id, 10)
    args.cli = clean(args.cli, detect_cli())
    args.model = clean(args.model, detect_model(args.cli))
    args.model_family = model_family(args.model)
    args.commit_email_hint = commit_email_hint(args.model, args.model_family)
    args.agent = clean(args.agent, "agent")
    args.status = clean(args.status, "active").lower()
    if args.status not in STATUS_VALUES:
        print(f"unsupported status: {args.status}", file=sys.stderr)
        return 2
    args.keep = clean(args.keep, "yes").lower()
    if args.keep not in KEEP_VALUES:
        print(f"unsupported keep: {args.keep}", file=sys.stderr)
        return 2
    meta = git_meta(root)
    inferred = args.title or args.summary or existing_current_task(root) or clean(meta.get("branch")) or "continuity-checkpoint"
    args.task_id = safe_task_id(args.task_id or inferred)
    args.title = clean(args.title, inferred)
    args.summary = clean(args.summary, args.title)
    args.next_action = clean(args.next_action, "read packet/current/progress, then continue the next bounded slice")
    args.run_id = clean(args.run_id, args.session_id)
    args.work_type = infer_work_type(args, meta)
    args.checkpoint_hash = short_hash(f"{root}|{args.cwd}|{args.session_id}|{args.task_id}|{args.timestamp}", 10)

    p = plan_paths(root)
    for key in ("plan", "progress", "sessions", "archive"):
        p[key].mkdir(parents=True, exist_ok=True)

    write_main = should_write_main(root, args.task_id, args.scope)
    diff_ref = write_diff_snapshot(root, args.task_id, args.session_id, args.diff_mode)
    progress_path, _ = build_progress(args, root, meta, diff_ref, write_main)
    progress_ref = f"./{progress_path.relative_to(root)}"
    write_session_event(args, root, meta, progress_ref, diff_ref, write_main)
    write_handoff_entry(args, root, meta, progress_ref, diff_ref, write_main)
    archived_handoff = rotate_handoff(root, args.max_handoff_entries)
    if write_main:
        write_current(args, root, meta, progress_ref, diff_ref)
        write_packet(args, root, meta, progress_ref, diff_ref)

    result = {
        "ok": True,
        "action": "offduty",
        "cwd": args.cwd,
        "root": str(root),
        "scope": "main" if write_main else "side",
        "task_id": args.task_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "model": args.model,
        "model_name": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "progress": progress_ref,
        "current_updated": write_main,
        "packet_updated": write_main,
        "handoff": "./.ai/plan/handoff.md",
        "diff_ref": diff_ref,
        "archived_handoff": archived_handoff,
        "next": "run onduty in a fresh session and follow packet read_order",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def latest_handoff_entry(root: Path) -> str:
    handoff = plan_paths(root)["handoff"]
    if not handoff.exists():
        return ""
    _, entries = split_handoff_entries(handoff.read_text(encoding="utf-8", errors="replace"))
    return entries[0] if entries else ""


def first_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[:limit]


def progress_summaries(root: Path, limit: int) -> list[str]:
    progress_dir = plan_paths(root)["progress"]
    if not progress_dir.exists():
        return []
    files = sorted(progress_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)
    rows: list[str] = []
    for path in files[:limit]:
        text = path.read_text(encoding="utf-8", errors="replace")
        status = re.search(r"^- Status:\s*(.+)$", text, re.MULTILINE)
        model = re.search(r"^- Model(?: Name)?:\s*(.+)$", text, re.MULTILINE)
        session = re.search(r"^- Session ID:\s*(.+)$", text, re.MULTILINE)
        cwd = re.search(r"^- CWD:\s*(.+)$", text, re.MULTILINE)
        next_action = re.search(r"(?ms)^## Next Action\n-\s*(.+?)(?=\n## |\Z)", text)
        rows.append(
            f"- `{path.relative_to(root)}` status={status.group(1).strip() if status else '-'} "
            f"model={model.group(1).strip() if model else '-'} session={session.group(1).strip() if session else '-'} "
            f"cwd={cwd.group(1).strip() if cwd else '-'} next={next_action.group(1).strip() if next_action else '-'}"
        )
    return rows


def build_onduty(root: Path, max_progress: int) -> str:
    p = plan_paths(root)
    meta = git_meta(root)
    packet = read_json(p["packet"]) or {}
    read_order = packet.get("read_order") if isinstance(packet.get("read_order"), list) else []
    if not read_order:
        read_order = [item for item in ["./AGENTS.md" if (root / "AGENTS.md").exists() else "", "./README.md" if (root / "README.md").exists() else "", "./.ai/plan/current.md", "./.ai/plan/handoff.md"] if item]
    current_lines = first_lines(p["current"], 40)
    latest = latest_handoff_entry(root)
    rows = progress_summaries(root, max_progress)
    status = meta["status_short"] or "clean"
    return f"""# Onduty Brief

Generated: {now_iso()}
Root: `{root}`
Git: `{meta.get('branch') or '-'}@{meta.get('head') or '-'}`; status={'dirty' if meta['status_short'] else 'clean'}

## Session Metadata
- CWD: `{packet.get('cwd') or '-'}`
- Root: `{packet.get('root') or root}`
- Session ID: `{packet.get('session_id') or '-'}`
- Session Hash: `{packet.get('session_hash') or '-'}`
- Checkpoint Hash: `{packet.get('checkpoint_hash') or '-'}`
- Model Name: `{packet.get('model_name') or packet.get('model') or '-'}`
- Model Family: `{packet.get('model_family') or '-'}`
- Commit Email Hint: `{packet.get('commit_email_hint') or '-'}`

## Start Here
{md_list([str(item) for item in read_order], 'no packet/current refs found')}

## Packet Next Action
- {packet.get('next_action') or '-'}

## Current Snapshot
```text
{chr(10).join(current_lines) if current_lines else 'current.md missing'}
```

## Latest Handoff
```text
{latest if latest else 'handoff.md missing or empty'}
```

## Active Progress Files
{chr(10).join(rows) if rows else '- none'}

## Git Status
```text
{status}
```

## Diff Stat
```text
{meta.get('diff_stat') or meta.get('cached_diff_stat') or 'no diff stat'}
```

## Continue Rule
- Read only Start Here by default.
- Open progress files only for touched task ids.
- Open archive only for old decision/debug provenance.
- If git is dirty and no patch ref exists in packet/progress, inspect `git diff` before editing.
"""


def cmd_onduty_legacy(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    brief = build_onduty(root, args.max_progress)
    if args.write:
        path = plan_paths(root)["onduty"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(brief, encoding="utf-8")
        print(str(path))
    else:
        print(brief)
    return 0


def cmd_status_legacy(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    p = plan_paths(root)
    meta = git_meta(root)
    _, entries = split_handoff_entries(p["handoff"].read_text(encoding="utf-8", errors="replace")) if p["handoff"].exists() else ("# Handoff", [])
    progress_count = len(list(p["progress"].glob("*.md"))) if p["progress"].exists() else 0
    data = {
        "root": str(root),
        "current_exists": p["current"].exists(),
        "packet_exists": p["packet"].exists(),
        "handoff_entries": len(entries),
        "progress_files": progress_count,
        "git_dirty": bool(meta["status_short"]),
        "changed_files": meta["changed_files"],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def checkpoint_paths(root: Path, task_prefix: str = "", limit: int = 20) -> list[Path]:
    base = agent_paths(root)["checkpoints"]
    if not base.exists():
        return []
    paths_found = [p for p in base.glob("*/*.json") if not task_prefix or p.parent.name.startswith(task_prefix)]
    return sorted(paths_found, key=lambda item: item.stat().st_mtime, reverse=True)[:limit]


def load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def recent_checkpoint_rows(root: Path, limit: int = 8, task_prefix: str = "") -> list[str]:
    rows: list[str] = []
    for path in checkpoint_paths(root, task_prefix, limit):
        data = load_checkpoint(path)
        identity = data.get("identity", {}) if isinstance(data.get("identity"), dict) else {}
        state = data.get("state", {}) if isinstance(data.get("state"), dict) else {}
        git = data.get("git", {}) if isinstance(data.get("git"), dict) else {}
        rows.append(
            f"- `{rel_ref(root, path)}` status={state.get('status') or '-'} "
            f"task={identity.get('task_id') or path.parent.name} "
            f"model={identity.get('model') or '-'} session={identity.get('session_id') or '-'} "
            f"git={'dirty' if git.get('dirty') else 'clean'} next={state.get('next_action') or '-'}"
        )
    return rows


def lifeboat_paths(root: Path, limit: int = 8) -> list[Path]:
    base = agent_paths(root)["lifeboat"]
    if not base.exists():
        return []
    return sorted(base.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]


def recent_lifeboat_rows(root: Path, limit: int = 4) -> list[str]:
    rows: list[str] = []
    for path in lifeboat_paths(root, limit):
        data = load_checkpoint(path)
        identity = data.get("identity", {}) if isinstance(data.get("identity"), dict) else {}
        state = data.get("state", {}) if isinstance(data.get("state"), dict) else {}
        pointers = data.get("pointers", {}) if isinstance(data.get("pointers"), dict) else {}
        bkc = data.get("bkc", {}) if isinstance(data.get("bkc"), dict) else {}
        rows.append(
            f"- `{rel_ref(root, path)}` task={identity.get('task_id') or '-'} "
            f"model={identity.get('model') or '-'} session={identity.get('session_id') or '-'} "
            f"next={state.get('next_action') or '-'} md=`{pointers.get('lifeboat_md_ref') or '-'}` "
            f"bkc={bkc.get('status') or 'not-run'}"
        )
    return rows


def bkc_session_selector(args: argparse.Namespace) -> str:
    cli = clean(args.cli).lower()
    session_id = clean(args.session_id)
    if not session_id:
        return ""
    if cli == "codex":
        return f"codex:{session_id}"
    if cli in {"claude", "claude-code"}:
        return f"claude:{session_id}"
    return ""


def run_bkc_checkpoint(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    mode = clean(getattr(args, "bkc", "auto"), "auto")
    result: dict[str, Any] = {
        "schema": "agent.continuity.bkc.v1",
        "mode": mode,
        "status": "skipped",
        "pack_ref": "",
        "session_selector": "",
        "preset": clean(getattr(args, "bkc_preset", "standard"), "standard"),
        "output": clean(getattr(args, "bkc_output", "file"), "file"),
    }
    if mode == "off":
        result["status"] = "skipped_disabled"
        return result
    selector = bkc_session_selector(args)
    result["session_selector"] = selector
    if not selector:
        result["status"] = "skipped_unsupported_cli"
        result["reason"] = f"no bkc selector for cli={clean(args.cli) or '-'}"
        return result
    cmd_path = shutil.which("bkc") or shutil.which("bk")
    if not cmd_path:
        result["status"] = "skipped_missing_command"
        result["reason"] = "bkc/bk not found on PATH"
        return result

    if Path(cmd_path).name == "bk":
        command = [cmd_path, "c", selector]
    else:
        command = [cmd_path, selector]
    command.extend(["--output", result["output"], "--preset", result["preset"], "--no-copy"])
    timeout = max(5, int(getattr(args, "bkc_timeout", 45) or 45))
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        result.update(
            {
                "returncode": proc.returncode,
                "elapsed_ms": elapsed_ms,
                "command": " ".join(command),
                "stdout_tail": tail_text(stdout),
                "stderr_tail": tail_text(stderr),
            }
        )
        file_match = re.search(r"(?m)^file\s+(.+?)\s*$", stdout)
        if not file_match:
            file_match = re.search(r"(/[^ \n]+/\.ai/continuity/[^ \n]+\.md)", stdout + "\n" + stderr)
        if file_match:
            pack = Path(file_match.group(1).strip()).expanduser()
            result["pack_ref"] = rel_ref(root, pack.resolve()) if pack.exists() else file_match.group(1).strip()
        combined = f"{stdout}\n{stderr}".lower()
        if proc.returncode != 0:
            result["status"] = "failed"
        elif "找不到 session" in combined or "session not found" in combined or "not found" in combined:
            result["status"] = "failed_not_found"
        elif result.get("pack_ref"):
            result["status"] = "succeeded"
        else:
            result["status"] = "failed_no_pack"
        return result
    except subprocess.TimeoutExpired as exc:
        result.update(
            {
                "status": "timeout",
                "returncode": None,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "command": " ".join(command),
                "stdout_tail": tail_text(exc.stdout or ""),
                "stderr_tail": tail_text(exc.stderr or ""),
                "reason": f"bkc timed out after {timeout}s",
            }
        )
        return result
    except Exception as exc:  # pragma: no cover - defensive local-tool wrapper.
        result.update({"status": "failed", "reason": str(exc), "command": " ".join(command)})
        return result


def write_agent_lifeboat(
    args: argparse.Namespace,
    root: Path,
    meta: dict[str, Any],
    diff_ref: str,
    active_update: bool,
    bkc: dict[str, Any],
) -> dict[str, Any]:
    ap = agent_paths(root)
    stamp = now_stamp()
    name = f"{stamp}-{safe_task_id(args.task_id)}-{safe_slug(args.session_id, 'session', 40)}"
    json_path = ap["lifeboat"] / f"{name}.json"
    md_path = ap["lifeboat"] / f"{name}.md"
    refs = unique_items([*(args.ref or []), diff_ref, bkc.get("pack_ref") if isinstance(bkc, dict) else ""])
    data = {
        "schema": "agent.continuity.lifeboat.v1",
        "timestamp": args.timestamp,
        "identity": {
            "task_id": args.task_id,
            "run_id": args.run_id,
            "session_id": args.session_id,
            "session_hash": args.session_hash,
            "checkpoint_hash": args.checkpoint_hash,
            "agent": args.agent,
            "cli": args.cli,
            "model": args.model,
            "model_name": args.model,
            "model_family": args.model_family,
            "commit_email_hint": args.commit_email_hint,
        },
        "state": {
            "title": args.title,
            "summary": args.summary,
            "status": args.status,
            "scope": "main" if active_update else "side",
            "work_type": args.work_type,
            "cwd": args.cwd,
            "root": str(root),
            "next_action": args.next_action,
        },
        "decisions": args.decision or [],
        "validation": args.validation or [],
        "risks": args.risk or [],
        "constraints": args.constraint or [],
        "refs": refs,
        "docs": docs_for(root),
        "git": {
            "is_git": meta.get("is_git"),
            "branch": meta.get("branch"),
            "head": meta.get("head"),
            "dirty": bool(meta.get("status_short")),
            "changed_files": meta.get("changed_files", []),
            "status_short": meta.get("status_short"),
            "diff_stat": meta.get("diff_stat"),
            "cached_diff_stat": meta.get("cached_diff_stat"),
        },
        "bkc": bkc,
        "pointers": {
            "lifeboat_json_ref": rel_ref(root, json_path),
            "lifeboat_md_ref": rel_ref(root, md_path),
            "diff_ref": diff_ref,
            "bkc_pack_ref": bkc.get("pack_ref") if isinstance(bkc, dict) else "",
        },
        "recovery_order": [
            rel_ref(root, md_path),
            rel_ref(root, json_path),
            rel_ref(root, agent_paths(root)["pickup_md"]),
            rel_ref(root, agent_paths(root)["active"]),
        ],
    }
    atomic_write_json(json_path, data)
    status = meta["status_short"] or "clean"
    md = f"""# Continuity Lifeboat

Generated: {args.timestamp}
Schema: `agent.continuity.lifeboat.v1`
Root: `{root}`

## Resume First
- Task ID: `{args.task_id}`
- Status: `{args.status}`
- Scope: `{'main' if active_update else 'side'}`
- Current truth: {args.summary}
- Next action: {args.next_action}
- CWD: `{args.cwd}`
- Session: `{args.session_id}` hash=`{args.session_hash}`
- Model: `{args.model}` family=`{args.model_family}`

## Durable Refs
{md_list(refs, 'none')}

## Decisions
{md_list(args.decision or [], 'none recorded')}

## Validation
{md_list(args.validation or [], 'not run')}

## Risks / Constraints
{md_list(unique_items([*(args.risk or []), *(args.constraint or [])]), 'none recorded')}

## BKC Backup
- Status: `{bkc.get('status') if isinstance(bkc, dict) else 'not-run'}`
- Pack: `{bkc.get('pack_ref') if isinstance(bkc, dict) and bkc.get('pack_ref') else '-'}`
- Selector: `{bkc.get('session_selector') if isinstance(bkc, dict) and bkc.get('session_selector') else '-'}`

## Git Status
```text
{status}
```

## Diff Stat
```text
{meta.get('diff_stat') or meta.get('cached_diff_stat') or 'no diff stat'}
```

## Recovery Rule
- Use this file when native resume, `bkc`, or generated pickup is missing/stale.
- Then open `pickup.md`, `active.json`, and the matching checkpoint if present.
- Do not ask for old chat before checking repo-local continuity and lifeboat.
"""
    atomic_write_text(md_path, md)
    return {
        "schema": "agent.continuity.lifeboat_ref.v1",
        "status": "written",
        "json_ref": rel_ref(root, json_path),
        "md_ref": rel_ref(root, md_path),
    }


def build_agent_checkpoint(
    args: argparse.Namespace,
    root: Path,
    meta: dict[str, Any],
    diff_ref: str,
    active_update: bool,
    lifeboat: dict[str, Any] | None = None,
    bkc: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    ap = agent_paths(root)
    lifeboat = lifeboat or {}
    bkc = bkc or {}
    previous_active = read_json(ap["active"]) or {}
    checkpoint_path = (
        ap["checkpoints"]
        / safe_task_id(args.task_id)
        / f"{now_stamp()}-{safe_slug(args.session_id, 'session', 40)}.json"
    )
    docs = docs_for(root)
    read_order = [
        f"./{name}" for name in ("AGENTS.md", "CLAUDE.md", "README.md", "RTK.md") if (root / name).exists()
    ]
    read_order.extend(
        [
            rel_ref(root, ap["pickup_md"]),
            rel_ref(root, ap["active"]),
            rel_ref(root, checkpoint_path),
        ]
    )
    extra_refs = unique_items(
        [
            lifeboat.get("md_ref") if isinstance(lifeboat, dict) else "",
            lifeboat.get("json_ref") if isinstance(lifeboat, dict) else "",
            bkc.get("pack_ref") if isinstance(bkc, dict) else "",
        ]
    )
    read_order.extend(extra_refs)
    checkpoint = {
        "schema": "agent.continuity.checkpoint.v1",
        "timestamp": args.timestamp,
        "identity": {
            "task_id": args.task_id,
            "run_id": args.run_id,
            "session_id": args.session_id,
            "session_hash": args.session_hash,
            "checkpoint_hash": args.checkpoint_hash,
            "agent": args.agent,
            "cli": args.cli,
            "model": args.model,
            "model_name": args.model,
            "model_family": args.model_family,
            "commit_email_hint": args.commit_email_hint,
        },
        "state": {
            "title": args.title,
            "summary": args.summary,
            "status": args.status,
            "scope": "main" if active_update else "side",
            "work_type": args.work_type,
            "next_action": args.next_action,
            "cwd": args.cwd,
            "root": str(root),
        },
        "attempt": {
            "text": clean(args.attempt) or clean(args.summary) or "offduty checkpoint",
            "result": clean(args.attempt_result) or clean(args.status),
            "keep": args.keep,
            "note": clean(args.note) or clean(args.summary) or "checkpoint",
        },
        "decisions": args.decision or [],
        "validation": args.validation or [],
        "risks": args.risk or [],
        "constraints": args.constraint or [],
        "refs": unique_items([*(args.ref or []), *extra_refs]),
        "read_order": unique_items(read_order),
        "docs": docs,
        "git": {
            "is_git": meta.get("is_git"),
            "branch": meta.get("branch"),
            "head": meta.get("head"),
            "dirty": bool(meta.get("status_short")),
            "changed_files": meta.get("changed_files", []),
            "diff_stat": meta.get("diff_stat"),
            "cached_diff_stat": meta.get("cached_diff_stat"),
        },
        "pointers": {
            "checkpoint_ref": rel_ref(root, checkpoint_path),
            "active_ref": rel_ref(root, ap["active"]),
            "pickup_json_ref": rel_ref(root, ap["pickup_json"]),
            "pickup_md_ref": rel_ref(root, ap["pickup_md"]),
            "diff_ref": diff_ref,
            "lifeboat_json_ref": lifeboat.get("json_ref") if isinstance(lifeboat, dict) else "",
            "lifeboat_md_ref": lifeboat.get("md_ref") if isinstance(lifeboat, dict) else "",
            "bkc_pack_ref": bkc.get("pack_ref") if isinstance(bkc, dict) else "",
            "previous_active_checkpoint_ref": previous_active.get("checkpoint_ref") if isinstance(previous_active, dict) else "",
        },
        "lifeboat": lifeboat,
        "bkc": bkc,
        "writeback_required": [
            "write future shift checkpoints under .agent.local/continuity/checkpoints/<task-id>/",
            "write session events under .agent.local/continuity/sessions/<session-id>.jsonl",
            "update active.json only from main/supervisor/offduty scope",
        ],
    }
    atomic_write_json(checkpoint_path, checkpoint)
    return checkpoint_path, checkpoint


def write_agent_session_event(
    args: argparse.Namespace,
    root: Path,
    meta: dict[str, Any],
    checkpoint_ref: str,
    diff_ref: str,
    active_update: bool,
    lifeboat: dict[str, Any] | None = None,
    bkc: dict[str, Any] | None = None,
) -> Path:
    ap = agent_paths(root)
    lifeboat = lifeboat or {}
    bkc = bkc or {}
    event = {
        "schema": "agent.continuity.session_event.v1",
        "timestamp": args.timestamp,
        "event": "offduty",
        "task_id": args.task_id,
        "run_id": args.run_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "agent": args.agent,
        "cli": args.cli,
        "model": args.model,
        "model_name": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "cwd": args.cwd,
        "root": str(root),
        "status": args.status,
        "work_type": args.work_type,
        "scope": "main" if active_update else "side",
        "summary": args.summary,
        "next_action": args.next_action,
        "git": {
            "branch": meta.get("branch"),
            "head": meta.get("head"),
            "dirty": bool(meta.get("status_short")),
            "changed_files": meta.get("changed_files", []),
        },
        "checkpoint_ref": checkpoint_ref,
        "diff_ref": diff_ref,
        "lifeboat_ref": lifeboat.get("md_ref") if isinstance(lifeboat, dict) else "",
        "bkc_pack_ref": bkc.get("pack_ref") if isinstance(bkc, dict) else "",
        "bkc_status": bkc.get("status") if isinstance(bkc, dict) else "",
    }
    path = ap["sessions"] / f"{safe_slug(args.session_id, 'session', 40)}.jsonl"
    append_jsonl(path, event)
    return path


def write_agent_active(
    args: argparse.Namespace,
    root: Path,
    checkpoint_ref: str,
    lifeboat: dict[str, Any] | None = None,
    bkc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ap = agent_paths(root)
    lifeboat = lifeboat or {}
    bkc = bkc or {}
    active = {
        "schema": "agent.continuity.active.v1",
        "updated": args.timestamp,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "checkpoint_ref": checkpoint_ref,
        "pickup_ref": rel_ref(root, ap["pickup_md"]),
        "status": args.status,
        "work_type": args.work_type,
        "next_action": args.next_action,
        "model": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "cwd": args.cwd,
        "root": str(root),
        "lifeboat_ref": lifeboat.get("md_ref") if isinstance(lifeboat, dict) else "",
        "bkc_pack_ref": bkc.get("pack_ref") if isinstance(bkc, dict) else "",
        "bkc_status": bkc.get("status") if isinstance(bkc, dict) else "",
    }
    atomic_write_json(ap["active"], active)
    return active


def render_agent_pickup(
    root: Path,
    active: dict[str, Any],
    checkpoint: dict[str, Any],
    meta: dict[str, Any],
    recent_rows: list[str],
    include_lifeboat: bool = True,
) -> tuple[dict[str, Any], str]:
    ap = agent_paths(root)
    identity = checkpoint.get("identity", {}) if isinstance(checkpoint.get("identity"), dict) else {}
    state = checkpoint.get("state", {}) if isinstance(checkpoint.get("state"), dict) else {}
    lifeboat = checkpoint.get("lifeboat", {}) if isinstance(checkpoint.get("lifeboat"), dict) else {}
    bkc = checkpoint.get("bkc", {}) if isinstance(checkpoint.get("bkc"), dict) else {}
    read_order = checkpoint.get("read_order") if isinstance(checkpoint.get("read_order"), list) else []
    if not read_order:
        read_order = [
            item
            for item in [
                "./AGENTS.md" if (root / "AGENTS.md").exists() else "",
                "./CLAUDE.md" if (root / "CLAUDE.md").exists() else "",
                rel_ref(root, ap["active"]),
                active.get("checkpoint_ref") or "",
            ]
            if item
        ]
    pickup = {
        "schema": "agent.continuity.pickup.v1",
        "generated": now_iso(),
        "root": str(root),
        "active": active,
        "checkpoint": {
            "task_id": identity.get("task_id"),
            "session_id": identity.get("session_id"),
            "checkpoint_hash": identity.get("checkpoint_hash"),
            "summary": state.get("summary"),
            "status": state.get("status"),
            "next_action": state.get("next_action"),
            "checkpoint_ref": active.get("checkpoint_ref"),
        },
        "read_order": read_order,
        "git": {
            "branch": meta.get("branch"),
            "head": meta.get("head"),
            "dirty": bool(meta.get("status_short")),
            "changed_files": meta.get("changed_files", []),
            "diff_stat": meta.get("diff_stat") or meta.get("cached_diff_stat"),
        },
        "lifeboat": lifeboat,
        "bkc": bkc,
        "recent_checkpoints": recent_rows,
    }
    status = meta["status_short"] or "clean"
    lifeboat_section = ""
    if include_lifeboat:
        lifeboat_section = f"""
## Lifeboat / BKC Backup
- Lifeboat MD: `{lifeboat.get('md_ref') or active.get('lifeboat_ref') or '-'}`
- Lifeboat JSON: `{lifeboat.get('json_ref') or '-'}`
- BKC status: `{bkc.get('status') or active.get('bkc_status') or 'not-run'}`
- BKC pack: `{bkc.get('pack_ref') or active.get('bkc_pack_ref') or '-'}`
"""
    md = f"""# Onduty Pickup

Generated: {pickup['generated']}
Root: `{root}`
Git: `{meta.get('branch') or '-'}@{meta.get('head') or '-'}`; status={'dirty' if meta['status_short'] else 'clean'}
Schema: `agent.continuity.v1`

## Start Here
{md_list([str(item) for item in read_order], 'no active refs found')}

## Active Pointer
- Task ID: `{active.get('task_id') or '-'}`
- Status: `{active.get('status') or '-'}`
- Session: `{active.get('session_id') or '-'}`
- Model: `{active.get('model') or '-'}`
- Model Family: `{active.get('model_family') or '-'}`
- Commit Email Hint: `{active.get('commit_email_hint') or '-'}`
- Checkpoint: `{active.get('checkpoint_ref') or '-'}`

## Pickup Snapshot
- Current truth: {state.get('summary') or '-'}
- Work type: {state.get('work_type') or '-'}
- CWD: `{state.get('cwd') or '-'}`
- Next action: {state.get('next_action') or '-'}

## Recent Checkpoints
{chr(10).join(recent_rows) if recent_rows else '- none'}
{lifeboat_section}

## Git Status
```text
{status}
```

## Diff Stat
```text
{meta.get('diff_stat') or meta.get('cached_diff_stat') or 'no diff stat'}
```

## Continue Rule
- Read only Start Here by default.
- Open the active checkpoint for details; open other checkpoints only for the same task or explicit user hint.
- If git is dirty, inspect `git diff` before editing.
- Do not ask for old chat; checkpoints and git evidence are the source of truth.
"""
    return pickup, md


def write_agent_pickup(root: Path, active: dict[str, Any], checkpoint: dict[str, Any], meta: dict[str, Any]) -> tuple[Path, Path]:
    ap = agent_paths(root)
    recent_rows = recent_checkpoint_rows(root, limit=8)
    pickup, md = render_agent_pickup(root, active, checkpoint, meta, recent_rows)
    atomic_write_json(ap["pickup_json"], pickup)
    atomic_write_text(ap["pickup_md"], md)
    return ap["pickup_json"], ap["pickup_md"]


def prepare_agent_args(args: argparse.Namespace, root: Path) -> tuple[dict[str, Any], bool, str]:
    args.cwd = str(Path(args.cwd).expanduser().resolve()) if clean(args.cwd) else str(Path.cwd().resolve())
    args.timestamp = now_iso()
    args.session_id = safe_slug(args.session_id or detect_session_id(), "session", 64)
    args.session_hash = short_hash(args.session_id, 10)
    args.cli = clean(args.cli, detect_cli())
    args.model = clean(args.model, detect_model(args.cli))
    args.model_family = model_family(args.model)
    args.commit_email_hint = commit_email_hint(args.model, args.model_family)
    args.agent = clean(args.agent, "agent")
    args.status = clean(args.status, "active").lower()
    if args.status not in STATUS_VALUES:
        raise ValueError(f"unsupported status: {args.status}")
    args.keep = clean(args.keep, "yes").lower()
    if args.keep not in KEEP_VALUES:
        raise ValueError(f"unsupported keep: {args.keep}")
    meta = git_meta(root)
    inferred = args.title or args.summary or active_task(root) or clean(meta.get("branch")) or "continuity-checkpoint"
    args.task_id = safe_task_id(args.task_id or inferred)
    args.title = clean(args.title, inferred)
    args.summary = clean(args.summary, args.title)
    args.next_action = clean(args.next_action, "read pickup and active checkpoint, then continue the next bounded slice")
    args.run_id = clean(args.run_id, args.session_id)
    args.work_type = infer_work_type(args, meta)
    args.checkpoint_hash = short_hash(f"{root}|{args.cwd}|{args.session_id}|{args.task_id}|{args.timestamp}", 10)
    active_update = should_write_active(root, args.task_id, args.scope)
    return meta, active_update, args.task_id


def cmd_offduty_agent(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    ensure_agent_local_guard(root)
    try:
        meta, active_update, _ = prepare_agent_args(args, root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    ap = agent_paths(root)
    for key in ("base", "checkpoints", "sessions", "indexes", "lifeboat", "archive"):
        ap[key].mkdir(parents=True, exist_ok=True)
    diff_ref = write_agent_diff_snapshot(root, args.task_id, args.session_id, args.diff_mode)
    bkc = run_bkc_checkpoint(args, root)
    lifeboat = {} if getattr(args, "no_lifeboat", False) else write_agent_lifeboat(args, root, meta, diff_ref, active_update, bkc)
    checkpoint_path, checkpoint = build_agent_checkpoint(args, root, meta, diff_ref, active_update, lifeboat, bkc)
    checkpoint_ref = rel_ref(root, checkpoint_path)
    session_path = write_agent_session_event(args, root, meta, checkpoint_ref, diff_ref, active_update, lifeboat, bkc)
    active = read_json(ap["active"]) or {}
    pickup_json = ap["pickup_json"]
    pickup_md = ap["pickup_md"]
    if active_update:
        active = write_agent_active(args, root, checkpoint_ref, lifeboat, bkc)
        pickup_json, pickup_md = write_agent_pickup(root, active, checkpoint, meta)
    bkc_required_failed = clean(getattr(args, "bkc", "auto")) == "required" and bkc.get("status") != "succeeded"

    result = {
        "ok": not bkc_required_failed,
        "action": "offduty",
        "layout": "agent-local",
        "cwd": args.cwd,
        "root": str(root),
        "scope": "main" if active_update else "side",
        "task_id": args.task_id,
        "session_id": args.session_id,
        "session_hash": args.session_hash,
        "checkpoint_hash": args.checkpoint_hash,
        "model": args.model,
        "model_name": args.model,
        "model_family": args.model_family,
        "commit_email_hint": args.commit_email_hint,
        "continuity": rel_ref(root, ap["base"]),
        "checkpoint": checkpoint_ref,
        "session_log": rel_ref(root, session_path),
        "active_updated": active_update,
        "active": rel_ref(root, ap["active"]) if active_update else active.get("checkpoint_ref", ""),
        "pickup_json": rel_ref(root, pickup_json) if active_update else "",
        "pickup_md": rel_ref(root, pickup_md) if active_update else "",
        "lifeboat": lifeboat,
        "bkc": bkc,
        "diff_ref": diff_ref,
        "next": "run onduty in a fresh session and follow pickup.md plus the active checkpoint",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if bkc_required_failed else 0


def build_onduty_agent(root: Path, max_progress: int, task_prefix: str = "", include_lifeboat: bool = True) -> str:
    ap = agent_paths(root)
    meta = git_meta(root)
    active = read_json(ap["active"]) or {}
    checkpoint: dict[str, Any] = {}
    checkpoint_ref = clean(active.get("checkpoint_ref") if isinstance(active, dict) else "")
    if checkpoint_ref:
        raw = checkpoint_ref[2:] if checkpoint_ref.startswith("./") else checkpoint_ref
        checkpoint = load_checkpoint(root / raw)
    recent_rows = recent_checkpoint_rows(root, max_progress, task_prefix)
    if active and checkpoint:
        _, md = render_agent_pickup(root, active, checkpoint, meta, recent_rows, include_lifeboat=include_lifeboat)
        return md
    status = meta["status_short"] or "clean"
    lifeboat_section = ""
    if include_lifeboat:
        lifeboat_rows = recent_lifeboat_rows(root, limit=4)
        lifeboat_section = f"""
## Lifeboat / BKC Backup
{chr(10).join(lifeboat_rows) if lifeboat_rows else '- none'}
"""
    return f"""# Onduty Pickup

Generated: {now_iso()}
Root: `{root}`
Schema: `agent.continuity.v1`

## Start Here
- No active continuity pointer found.
- Run `offduty` at a shift boundary, or inspect recent checkpoints below.

## Active Pointer
- missing

## Recent Checkpoints
{chr(10).join(recent_rows) if recent_rows else '- none'}
{lifeboat_section}

## Git Status
```text
{status}
```

## Diff Stat
```text
{meta.get('diff_stat') or meta.get('cached_diff_stat') or 'no diff stat'}
```
"""


def cmd_onduty_agent(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    brief = build_onduty_agent(
        root,
        args.max_progress,
        clean(getattr(args, "task_prefix", "")),
        include_lifeboat=not getattr(args, "no_lifeboat", False),
    )
    if args.write:
        path = agent_paths(root)["pickup_md"]
        atomic_write_text(path, brief)
        print(str(path))
    else:
        print(brief)
    return 0


def cmd_status_agent(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    ap = agent_paths(root)
    meta = git_meta(root)
    checkpoints = checkpoint_paths(root, limit=100000)
    lifeboats = lifeboat_paths(root, limit=100000)
    sessions = list(ap["sessions"].glob("*.jsonl")) if ap["sessions"].exists() else []
    active = read_json(ap["active"]) or {}
    data = {
        "root": str(root),
        "layout": "agent-local",
        "continuity": rel_ref(root, ap["base"]),
        "active_exists": ap["active"].exists(),
        "pickup_exists": ap["pickup_md"].exists(),
        "active_task_id": active.get("task_id") if isinstance(active, dict) else "",
        "active_checkpoint": active.get("checkpoint_ref") if isinstance(active, dict) else "",
        "active_lifeboat": active.get("lifeboat_ref") if isinstance(active, dict) else "",
        "active_bkc_status": active.get("bkc_status") if isinstance(active, dict) else "",
        "lifeboat_files": len(lifeboats),
        "checkpoint_files": len(checkpoints),
        "session_files": len(sessions),
        "git_dirty": bool(meta["status_short"]),
        "changed_files": meta["changed_files"],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_offduty(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    layout = resolve_layout(root, args.layout, write=True)
    if layout == "legacy-ai-plan":
        return cmd_offduty_legacy(args)
    return cmd_offduty_agent(args)


def cmd_onduty(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    layout = resolve_layout(root, args.layout, write=False)
    if layout == "legacy-ai-plan":
        return cmd_onduty_legacy(args)
    return cmd_onduty_agent(args)


def cmd_status(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    layout = resolve_layout(root, args.layout, write=False)
    if layout == "legacy-ai-plan":
        return cmd_status_legacy(args)
    return cmd_status_agent(args)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="project root, default cwd or git root")


def add_layout(parser: argparse.ArgumentParser) -> None:
    default = clean(os.environ.get("AGENT_CONTINUITY_LAYOUT"), "auto")
    if default not in {"auto", "agent-local", "legacy-ai-plan"}:
        default = "auto"
    parser.add_argument("--layout", choices=["auto", "agent-local", "legacy-ai-plan"], default=default)
    parser.add_argument("--legacy-ai-plan", action="store_const", dest="layout", const="legacy-ai-plan", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repo-local offduty/onduty continuity helper. Bare offduty works; flags are optional overrides."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    bkc_default = clean(os.environ.get("AGENT_CONTINUITY_BKC"), "auto")
    if bkc_default not in {"auto", "off", "required"}:
        bkc_default = "auto"

    off = sub.add_parser("offduty", help="write a bounded continuation checkpoint")
    add_common(off)
    add_layout(off)
    off.add_argument("--task-id", default="")
    off.add_argument("--title", default="")
    off.add_argument("--summary", default="")
    off.add_argument("--next-action", default="")
    off.add_argument("--status", default="active")
    off.add_argument("--work-type", default="", help=argparse.SUPPRESS)
    off.add_argument("--scope", choices=["auto", "main", "side"], default="auto")
    off.add_argument("--agent", default="")
    off.add_argument("--cli", default="")
    off.add_argument("--model", default="")
    off.add_argument("--run-id", default="")
    off.add_argument("--session-id", default="")
    off.add_argument("--cwd", default="", help=argparse.SUPPRESS)
    off.add_argument("--attempt", default="")
    off.add_argument("--attempt-result", default="")
    off.add_argument("--keep", choices=sorted(KEEP_VALUES), default="yes")
    off.add_argument("--note", default="")
    off.add_argument("--decision", action="append")
    off.add_argument("--validation", action="append")
    off.add_argument("--risk", action="append")
    off.add_argument("--constraint", action="append")
    off.add_argument("--ref", action="append")
    off.add_argument("--diff-mode", choices=["none", "stat", "patch"], default="stat")
    off.add_argument("--no-lifeboat", action="store_true", help="skip the extra markdown/json lifeboat backup")
    off.add_argument("--bkc", choices=["auto", "off", "required"], default=bkc_default)
    off.add_argument("--bkc-preset", choices=["compact", "standard", "extended", "full"], default="standard")
    off.add_argument("--bkc-output", choices=["file"], default="file", help=argparse.SUPPRESS)
    off.add_argument("--bkc-timeout", type=int, default=45)
    off.add_argument("--max-handoff-entries", type=int, default=20)
    off.add_argument("--max-progress-attempts", type=int, default=20)
    off.add_argument("--max-progress-checkpoints", type=int, default=12)
    off.set_defaults(func=cmd_offduty)

    on = sub.add_parser("onduty", help="print or write a fresh-session pickup brief")
    add_common(on)
    add_layout(on)
    on.add_argument("--write", action="store_true")
    on.add_argument("--max-progress", type=int, default=8)
    on.add_argument("--task-prefix", default="", help="filter checkpoint list by task id prefix")
    on.add_argument("--no-lifeboat", action="store_true", help="hide lifeboat/bkc backup refs from the pickup view")
    on.set_defaults(func=cmd_onduty)

    status = sub.add_parser("status", help="show continuity footprint")
    add_common(status)
    add_layout(status)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
