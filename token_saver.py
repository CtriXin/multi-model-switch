from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import re
import shlex
import subprocess
import sys
from typing import Sequence

import mms_context
import mms_toon


DEFAULT_THRESHOLD_CHARS = 4000
DEFAULT_THRESHOLD_LINES = 120
DEFAULT_SNIPPET_CHARS = 1100
CONTEXT_ALIASES = {"put", "search", "show", "list", "path", "stats", "gain"}
SIGNAL_MARKERS = (
    "assertionerror",
    "exception",
    "failed",
    "failure",
    "fatal",
    "no such file",
    "not found",
    "panic",
    "permission denied",
    "segmentation fault",
    "timed out",
    "traceback",
)


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


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _command_tags(command: Sequence[str]) -> list[str]:
    if not command:
        return []
    program = os.path.basename(str(command[0] or ""))
    tags = [f"cmd:{program}"] if program else []
    joined = " ".join(str(item).lower() for item in command)
    if program in {"pytest", "vitest", "jest"} or "pytest" in joined:
        tags.append("test")
    if program in {"npm", "pnpm", "yarn"} and any(marker in joined for marker in (" test", " vitest", " jest")):
        tags.append("test")
    if program in {"tsc", "eslint", "biome", "ruff", "mypy"}:
        tags.append("lint")
    if program == "git":
        tags.append("git")
    return _dedupe(tags)


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


def _signal_lines(text: str, *, max_lines: int = 10, radius: int = 1) -> list[tuple[int, str]]:
    lines = str(text or "").splitlines()
    if not lines:
        return []
    selected: list[tuple[int, str]] = []
    seen: set[int] = set()
    for index, line in enumerate(lines):
        lower = line.lower()
        if not any(marker in lower for marker in SIGNAL_MARKERS) and not re.search(r"\b(error|failures?)\b", lower):
            continue
        start = max(0, index - radius)
        end = min(len(lines), index + radius + 1)
        for pos in range(start, end):
            if pos in seen:
                continue
            seen.add(pos)
            selected.append((pos + 1, lines[pos]))
            if len(selected) >= max_lines:
                return selected
    return selected


def _format_signal_snippet(text: str, *, limit: int) -> str:
    rows = _signal_lines(text)
    if not rows:
        return ""
    output = ["[token-saver: signal lines]"]
    for line_no, line in rows:
        value = line.rstrip()
        if len(value) > 180:
            value = value[:177].rstrip() + "..."
        output.append(f"L{line_no}: {value}")
    snippet = "\n".join(output)
    if len(snippet) <= limit:
        return snippet
    return snippet[: max(0, limit - 3)].rstrip() + "..."


def _summary_snippet(text: str, limit: int = DEFAULT_SNIPPET_CHARS) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    signal = _format_signal_snippet(value, limit=max(160, limit // 2))
    if signal:
        tail_size = max(180, limit - len(signal) - 90)
        omitted = max(0, len(value) - tail_size)
        return (
            signal
            + f"\n...\n[token-saver: full output stored; omitted about {omitted} chars]\n...\n"
            + value[-tail_size:].lstrip()
        )
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
    print(f"snippet_chars: {len(str(payload.get('display_snippet') or ''))}")
    print(f"approx_saved_chars: {payload.get('saved_chars') or 0}")
    print(f"approx_gain: {payload.get('gain_pct') or 0}%")
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
    tags.extend(_command_tags(command))
    tags.extend(["token-saver", f"exit:{completed.returncode}"])
    display_snippet = _summary_snippet(output, args.snippet_chars)
    visible_chars = len(display_snippet)
    record = mms_context.put_context(
        output,
        title=title,
        kind=args.kind or "tool-output",
        tags=_dedupe(tags),
        store_dir=args.store_dir,
        visible_chars=visible_chars,
    )
    payload = asdict(record)
    saved_chars = max(0, len(output) - visible_chars)
    gain_pct = round((saved_chars / len(output) * 100), 1) if output else 0.0
    payload.update(
        {
            "stored": True,
            "ref": f"{mms_context.REF_PREFIX}{record.id}",
            "exit_code": completed.returncode,
            "command": command,
            "store_dir": str(mms_context._store_dir(args.store_dir)),
            "display_snippet": display_snippet,
            "visible_chars": visible_chars,
            "saved_chars": saved_chars,
            "gain_pct": gain_pct,
            "threshold_chars": threshold_chars,
            "threshold_lines": threshold_lines,
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

    for name in ("stats", "gain"):
        stats = subparsers.add_parser(name, help="Show estimated context-saving gain for stored refs.")
        stats.add_argument("--limit", type=int, default=mms_context.DEFAULT_STATS_LIMIT, help="Top records to show.")
        stats.add_argument("--kind", default="", help="Only include records with this kind.")
        stats.add_argument("--tag", default="", help="Only include records with this tag.")
        stats.add_argument("--all-stores", action="store_true", help="Include discovered MMS session stores.")
        stats.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        stats.set_defaults(func=lambda args: mms_context.main(_context_stats_argv(args)))

    return parser


def _context_stats_argv(args: argparse.Namespace) -> list[str]:
    argv = ["stats", "--limit", str(args.limit)]
    if args.kind:
        argv.extend(["--kind", args.kind])
    if args.tag:
        argv.extend(["--tag", args.tag])
    if args.all_stores:
        argv.append("--all-stores")
    if args.json:
        argv.append("--json")
    return argv


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0].startswith("--") and values[0] != "--help":
        values = ["run", *values]
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
