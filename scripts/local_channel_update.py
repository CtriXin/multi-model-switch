#!/usr/bin/env python3
"""Local channel update reminders for maintainer wrappers.

This helper only touches git worktrees and ~/.local/state. It never writes the
real MMS config tree under ~/.config/mms.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SECONDS = {
    "always": 0,
    "daily": 24 * 60 * 60,
    "weekly": 7 * 24 * 60 * 60,
    "manual": 10**12,
}
REMIND_FOREGROUND_WAIT_SEC = 2
REMIND_BACKGROUND_STALE_SEC = 5 * 60


def real_home() -> Path:
    value = os.environ.get("MMS_REAL_HOME") or os.environ.get("REAL_HOME") or os.environ.get("ORIGINAL_HOME") or str(Path.home())
    for marker in ("/.config/mms-next", "/.config/mms"):
        if marker in value:
            value = value.split(marker, 1)[0]
    return Path(value).expanduser()


def state_path() -> Path:
    override = os.environ.get("MMS_LOCAL_CHANNEL_UPDATE_STATE")
    if override:
        return Path(override).expanduser()
    return real_home() / ".local" / "state" / "mms" / "channel-updates.json"


def load_state() -> dict:
    path = state_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def due(args: argparse.Namespace, state: dict) -> bool:
    if args.cadence == "always":
        return True
    interval = SECONDS.get(args.cadence, SECONDS["daily"])
    key = state_key(args)
    last = float(state.get(key, {}).get("last_check_ts") or 0)
    return now_ts() - last >= interval


def mark_checked(args: argparse.Namespace, state: dict, payload: dict | None = None) -> None:
    key = state_key(args)
    previous = state.get(key) if isinstance(state.get(key), dict) else {}
    preserved = {
        name: previous[name]
        for name in ("last_notice_signature", "last_notice_at")
        if name in previous
    }
    state[key] = {
        "last_check_ts": now_ts(),
        "last_check_at": datetime.now(timezone.utc).isoformat(),
        **preserved,
        **(payload or {}),
    }
    save_state(state)


def update_state_entry(args: argparse.Namespace, state: dict, patch: dict) -> None:
    key = state_key(args)
    entry = state.get(key) if isinstance(state.get(key), dict) else {}
    state[key] = {**entry, **patch}
    save_state(state)


def state_key(args: argparse.Namespace) -> str:
    root = str(Path(args.root).expanduser()) if args.root else args.public_entry or "public"
    return f"{args.command}:{args.kind}:{root}:{args.remote}:{args.branch}:{args.cadence}"


def git_bin() -> str:
    found = shutil.which("git") or "/usr/bin/git"
    return found


def run_git(root: str, *items: str, check: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [git_bin(), "-C", root, *items],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def git_text(root: str, *items: str) -> str:
    return run_git(root, *items).stdout.strip()


def fetch_remote(args: argparse.Namespace, *, timeout: float | None = None) -> tuple[bool, str]:
    if not args.root or not args.branch:
        return False, "missing root/branch"
    try:
        proc = run_git(args.root, "fetch", "--quiet", "--prune", args.remote, args.branch, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"git fetch timed out after {timeout:g}s"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "git fetch failed").strip()
    return True, ""


def worktree_dirty(root: str) -> bool:
    return bool(git_text(root, "status", "--porcelain"))


def ahead_behind(args: argparse.Namespace) -> dict:
    remote_ref = f"refs/remotes/{args.remote}/{args.branch}"
    head = git_text(args.root, "rev-parse", "--short", "HEAD")
    remote = git_text(args.root, "rev-parse", "--short", remote_ref)
    counts = git_text(args.root, "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}")
    left, right = [int(x) for x in counts.split()[:2]]
    return {"head": head, "remote": remote, "ahead": left, "behind": right, "remote_ref": remote_ref}


def update_check_result(args: argparse.Namespace) -> dict:
    ok, detail = fetch_remote(args)
    if not ok:
        return {"error": detail}
    return ahead_behind(args)


def update_message(args: argparse.Namespace, result: dict) -> tuple[str, bool]:
    if not isinstance(result, dict):
        return "", False
    if result.get("error"):
        return f"· {args.command} update check skipped: {result['error']}", True
    ahead = int(result.get("ahead") or 0)
    behind = int(result.get("behind") or 0)
    if behind and not ahead:
        return (
            f"· {args.command}/{args.branch} 有 {behind} 个远端更新；继续启动当前版本。"
            f"要更新请运行 `{args.command} update`。",
            False,
        )
    if ahead and behind:
        return (
            f"· {args.command}/{args.branch} 与 {args.remote}/{args.branch} 已分叉：ahead {ahead}, behind {behind}；"
            f"继续启动当前版本，需手动整理后再更新。",
            False,
        )
    if ahead:
        return f"· {args.command}/{args.branch} 本地领先 {ahead} 个 commit；继续启动当前版本，需要同步时先 push 或手动整理。", False
    return "", False


def print_update_message(args: argparse.Namespace, result: dict) -> None:
    message, is_error = update_message(args, result)
    if message:
        print(message, file=sys.stderr if is_error else sys.stdout)


def take_pending_result(args: argparse.Namespace, state: dict) -> dict | None:
    key = state_key(args)
    entry = state.get(key) if isinstance(state.get(key), dict) else {}
    pending = entry.pop("pending_result", None)
    entry.pop("pending_result_at", None)
    if pending is not None:
        state[key] = entry
        save_state(state)
    return pending if isinstance(pending, dict) else None


def store_background_result(args: argparse.Namespace, result: dict) -> None:
    state = load_state()
    update_state_entry(
        args,
        state,
        {
            "last_check_ts": now_ts(),
            "last_check_at": datetime.now(timezone.utc).isoformat(),
            "pending_result": dict(result),
            "pending_result_at": datetime.now(timezone.utc).isoformat(),
            "background_check_started_ts": 0,
            "background_check_started_at": "",
            **dict(result),
        },
    )


def background_check_inflight(args: argparse.Namespace, state: dict) -> bool:
    entry = state.get(state_key(args)) if isinstance(state.get(state_key(args)), dict) else {}
    try:
        started = float(entry.get("background_check_started_ts") or 0)
    except (TypeError, ValueError):
        started = 0
    return bool(started and now_ts() - started < REMIND_BACKGROUND_STALE_SEC)


def mark_background_check_started(args: argparse.Namespace) -> None:
    state = load_state()
    update_state_entry(
        args,
        state,
        {
            "background_check_started_ts": now_ts(),
            "background_check_started_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def background_check(args: argparse.Namespace) -> int:
    store_background_result(args, update_check_result(args))
    return 0


def spawn_background_check(args: argparse.Namespace) -> subprocess.Popen | None:
    mark_background_check_started(args)
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "background-check",
        "--command",
        args.command,
        "--kind",
        args.kind,
        "--root",
        args.root,
        "--branch",
        args.branch,
        "--remote",
        args.remote,
        "--cadence",
        args.cadence,
        "--public-entry",
        args.public_entry,
    ]
    try:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except Exception as exc:
        store_background_result(args, {"error": f"background check failed: {exc}"})
    return None


def public_remind(args: argparse.Namespace) -> int:
    state = load_state()
    if not due(args, state):
        return 0
    version_path = real_home() / ".config" / "mms" / "version.json"
    installed = "unknown"
    try:
        data = json.loads(version_path.read_text(encoding="utf-8"))
        installed = data.get("installed_ref") or data.get("installed_version") or "unknown"
    except Exception:
        pass
    print(f"· {args.command}/public 当前安装: {installed}；public copy 不自动更新，需要时手动运行 installer 或 `{args.command} update`。")
    mark_checked(args, state, {"installed_ref": installed})
    return 0


def remind(args: argparse.Namespace) -> int:
    if os.environ.get("MMS_LOCAL_UPDATE_SKIP") == "1":
        return 0
    if args.kind == "public":
        return public_remind(args)
    state = load_state()
    pending = take_pending_result(args, state)
    if pending:
        print_update_message(args, pending)
        state = load_state()
    if not due(args, state):
        return 0
    if background_check_inflight(args, state):
        return 0
    proc = spawn_background_check(args)
    if proc is None:
        return 0
    try:
        proc.wait(timeout=REMIND_FOREGROUND_WAIT_SEC)
    except subprocess.TimeoutExpired:
        return 0
    pending = take_pending_result(args, load_state())
    if pending:
        print_update_message(args, pending)
    return 0


def cached_notice(args: argparse.Namespace, info: dict) -> tuple[str, str]:
    ahead = int(info.get("ahead") or 0)
    behind = int(info.get("behind") or 0)
    head = str(info.get("head") or "")
    remote = str(info.get("remote") or "")
    if behind and not ahead:
        message = f"· {args.command}/{args.branch} 有 {behind} 个远端更新；运行 `{args.command} update` fast-forward。"
    elif ahead and behind:
        message = f"· {args.command}/{args.branch} 与 {args.remote}/{args.branch} 已分叉：ahead {ahead}, behind {behind}；不会自动更新。"
    elif ahead and os.environ.get("MMS_LOCAL_UPDATE_NOTIFY_AHEAD") == "1":
        message = f"· {args.command}/{args.branch} 本地领先 {ahead} 个 commit；需要同步时先 push 或手动整理。"
    else:
        return "", ""
    signature = f"{args.command}:{args.branch}:{head}:{remote}:{ahead}:{behind}"
    return message, signature


def cached_remind(args: argparse.Namespace) -> int:
    if os.environ.get("MMS_LOCAL_UPDATE_SKIP") == "1":
        return 0
    state = load_state()
    key = state_key(args)
    info = state.get(key)
    if not isinstance(info, dict):
        return 0
    message, signature = cached_notice(args, info)
    if not message or not signature:
        return 0
    if info.get("last_notice_signature") == signature:
        return 0
    print(message)
    info["last_notice_signature"] = signature
    info["last_notice_at"] = datetime.now(timezone.utc).isoformat()
    state[key] = info
    save_state(state)
    return 0


def update(args: argparse.Namespace) -> int:
    if args.kind == "public":
        print(f"{args.command}/public 不做启动时自动 pull；请用安装脚本或 release 流程更新 public copy。")
        return 0
    if worktree_dirty(args.root):
        print(f"拒绝更新 {args.command}: worktree 有未提交改动。", file=sys.stderr)
        return 2
    ok, detail = fetch_remote(args)
    if not ok:
        print(f"fetch 失败: {detail}", file=sys.stderr)
        return 2
    info = ahead_behind(args)
    ahead = info["ahead"]
    behind = info["behind"]
    if not behind:
        if ahead:
            print(f"{args.command}/{args.branch} 本地领先 {ahead} 个 commit；无需 fast-forward。")
        else:
            print(f"{args.command}/{args.branch} 已是最新: {info['head']}。")
        return 0
    if ahead:
        print(f"拒绝更新 {args.command}: 分支已分叉 ahead {ahead}, behind {behind}。只允许 fast-forward。", file=sys.stderr)
        return 2
    proc = run_git(args.root, "merge", "--ff-only", f"{args.remote}/{args.branch}", check=False)
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "fast-forward failed").strip(), file=sys.stderr)
        return proc.returncode or 2
    after = git_text(args.root, "rev-parse", "--short", "HEAD")
    print(f"{args.command}/{args.branch} 已 fast-forward 到 {after}。")
    return 0


def status(args: argparse.Namespace) -> int:
    payload = {"command": args.command, "kind": args.kind, "cadence": args.cadence}
    if args.kind == "public":
        payload["public_entry"] = args.public_entry
    else:
        ok, detail = fetch_remote(args) if args.fetch else (True, "")
        payload["fetch_ok"] = ok
        if detail:
            payload["fetch_detail"] = detail
        if ok:
            payload.update(ahead_behind(args))
        payload["root"] = args.root
        payload["branch"] = args.branch
        payload["dirty"] = worktree_dirty(args.root)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MMS local channel update helper")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("remind", "cached-remind", "update", "status", "background-check"):
        p = sub.add_parser(name)
        p.add_argument("--command", required=True)
        p.add_argument("--kind", choices=["worktree", "public"], default="worktree")
        p.add_argument("--root", default="")
        p.add_argument("--branch", default="")
        p.add_argument("--remote", default="origin")
        p.add_argument("--cadence", choices=sorted(SECONDS), default="daily")
        p.add_argument("--public-entry", default="")
        p.add_argument("--fetch", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "remind":
        return remind(args)
    if args.action == "cached-remind":
        return cached_remind(args)
    if args.action == "update":
        return update(args)
    if args.action == "status":
        return status(args)
    if args.action == "background-check":
        return background_check(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
