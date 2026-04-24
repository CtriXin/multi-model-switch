from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import shlex
import subprocess
import sys
from typing import Sequence

import mms_context
import mms_toon


DEFAULT_THRESHOLD_CHARS = 6000
DEFAULT_THRESHOLD_LINES = 160
DEFAULT_SNIPPET_CHARS = 900
CONTEXT_ALIASES = {"put", "search", "show", "list", "path"}


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _line_count(text: str) -> int:
    return text.count("\n") + (1 if text else 0)


def _clean_command(command: Sequence[str]) -> list[str]:
    values = [str(item) for item in command]
    if values and values[0] == "--":
        values = values[1:]
    return values


def _command_title(command: Sequence[str]) -> str:
    if not command:
        return "token-saver command"
    try:
        value = shlex.join(list(command))
    except (TypeError, ValueError):
        value = " ".join(str(item) for item in command)
    return value[:160]


def _should_store(
    text: str,
    *,
    always_store: bool,
    never_store: bool,
    threshold_chars: int,
    threshold_lines: int,
) -> bool:
    if never_store:
        return False
    if always_store:
        return True
    return len(text) >= threshold_chars or _line_count(text) >= threshold_lines


def _summary_snippet(text: str, limit: int = DEFAULT_SNIPPET_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    head_size = max(120, limit // 2)
    tail_size = max(120, limit - head_size - 80)
    omitted = max(0, len(value) - head_size - tail_size)
    return (
        value[:head_size].rstrip()
        + f"\n...\n[token-saver: omitted {omitted} chars]\n...\n"
        + value[-tail_size:].lstrip()
    )


def _print_stored_summary(payload: dict[str, object]) -> None:
    print("token-saver: stored command output")
    print(f"ref: {payload['ref']}")
    print(f"exit_code: {payload['exit_code']}")
    print(f"chars: {payload['chars']}")
    print(f"lines: {payload['lines']}")
    print("snippet:")
    snippet = str(payload.get("display_snippet") or "").strip()
    if snippet:
        print(snippet)


def _cmd_run(args: argparse.Namespace) -> int:
    command = _clean_command(args.command)
    if not command:
        print("token-saver: missing command after `run --`", file=sys.stderr)
        return 2

    completed = subprocess.run(
        command,
        cwd=args.cwd or None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        check=False,
    )
    output = completed.stdout or ""
    threshold_chars = args.threshold_chars
    if threshold_chars is None:
        threshold_chars = _env_int("TOKEN_SAVER_THRESHOLD_CHARS", DEFAULT_THRESHOLD_CHARS)
    threshold_lines = args.threshold_lines
    if threshold_lines is None:
        threshold_lines = _env_int("TOKEN_SAVER_THRESHOLD_LINES", DEFAULT_THRESHOLD_LINES)

    store = _should_store(
        output,
        always_store=bool(args.always_store),
        never_store=bool(args.never_store),
        threshold_chars=threshold_chars,
        threshold_lines=threshold_lines,
    )

    if not store:
        if args.json:
            print(
                json.dumps(
                    {
                        "stored": False,
                        "exit_code": completed.returncode,
                        "chars": len(output),
                        "lines": _line_count(output),
                        "output": output,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif output:
            print(output, end="" if output.endswith("\n") else "\n")
        return int(completed.returncode)

    title = args.title or _command_title(command)
    tags = list(args.tag or [])
    tags.extend(["token-saver", f"exit:{completed.returncode}"])
    record = mms_context.put_context(
        output,
        title=title,
        kind=args.kind or "tool-output",
        tags=tags,
        store_dir=args.store_dir,
    )
    payload = asdict(record)
    payload.update(
        {
            "stored": True,
            "ref": f"{mms_context.REF_PREFIX}{record.id}",
            "exit_code": completed.returncode,
            "command": command,
            "store_dir": str(mms_context._store_dir(args.store_dir)),
            "display_snippet": _summary_snippet(output, args.snippet_chars),
        }
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_stored_summary(payload)
    return int(completed.returncode)


def _cmd_toon(args: argparse.Namespace) -> int:
    argv = [args.path, "--auto"]
    if args.stats:
        argv.append("--stats")
    return mms_toon.main(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="token-saver",
        description="Unified helper for compact agent-facing output.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a command and store long output as a context ref.")
    run.add_argument("--title", default="", help="Stored context title.")
    run.add_argument("--kind", default="tool-output", help="Stored context kind.")
    run.add_argument("--tag", action="append", default=[], help="Repeatable stored context tag.")
    run.add_argument("--store-dir", default=None, help="Override context store directory.")
    run.add_argument("--cwd", default="", help="Run command from this directory.")
    run.add_argument("--threshold-chars", type=int, default=None, help="Store output at or above this char count.")
    run.add_argument("--threshold-lines", type=int, default=None, help="Store output at or above this line count.")
    run.add_argument("--snippet-chars", type=int, default=DEFAULT_SNIPPET_CHARS, help="Snippet chars to print when stored.")
    run.add_argument("--always-store", action="store_true", help="Always store command output.")
    run.add_argument("--never-store", action="store_true", help="Never store command output.")
    run.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command after `--`.")
    run.set_defaults(func=_cmd_run)

    toon = subparsers.add_parser("toon", help="Convert JSON to TOON when it is shorter.")
    toon.add_argument("path", nargs="?", default="-", help="JSON file path, or stdin.")
    toon.add_argument("--stats", action="store_true", help="Print format stats to stderr.")
    toon.set_defaults(func=_cmd_toon)

    return parser


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] in CONTEXT_ALIASES:
        return mms_context.main(values)
    parser = build_parser()
    args = parser.parse_args(values)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as exc:
        print(f"token-saver: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
