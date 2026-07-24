#!/usr/bin/env python3
"""Dispatch Pi Court or convert a saved court result into a parent packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_pi_court
import mms_pi_court_parent
from pi_court import build_parser as build_court_parser
from pi_court import court_kwargs


def build_parser() -> argparse.ArgumentParser:
    parser = build_court_parser()
    parser.description = "Dispatch Pi Court and emit a role-aware packet for the current parent."
    for action in parser._actions:
        if action.dest == "config_root":
            action.required = False
    for group in parser._mutually_exclusive_groups:
        if {action.dest for action in group._group_actions} == {"task", "task_file"}:
            group.required = False
    source = parser.add_argument_group("saved result")
    source.add_argument("--result")
    parser.add_argument("--compact", action="store_true")
    return parser


def _load_result(path: str) -> dict:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise mms_pi_court_parent.CourtParentError("court result JSON must be an object")
    return payload


def _packet(args: argparse.Namespace) -> dict:
    if args.result:
        if args.task or args.task_file:
            raise mms_pi_court_parent.CourtParentError("--result cannot be combined with --task or --task-file")
        return mms_pi_court_parent.build_parent_packet(_load_result(args.result))
    if not args.config_root:
        raise mms_pi_court_parent.CourtParentError("--config-root is required when dispatching a task")
    if not args.task and not args.task_file:
        raise mms_pi_court_parent.CourtParentError("--task or --task-file is required when dispatching")
    return mms_pi_court_parent.run_parent_court(**court_kwargs(args))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = _packet(args)
    except (json.JSONDecodeError, mms_pi_court.CourtError, mms_pi_court_parent.CourtParentError, OSError, ValueError) as exc:
        error = {"schema": "mms.pi_court.parent_error.v1", "status": "error", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    rendered = json.dumps(packet, ensure_ascii=False, indent=None if args.compact else 2) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if packet.get("status") in {"success", "partial", "dry_run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
