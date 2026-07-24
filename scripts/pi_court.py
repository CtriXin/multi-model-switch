#!/usr/bin/env python3
"""CLI for the opt-in role-aware Pi court."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_pi_committee
import mms_pi_court


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a role-aware, read-only Pi court without OpenCode.")
    parser.add_argument("--config-root", required=True)
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--task")
    task.add_argument("--task-file")
    parser.add_argument("--cwd", default=".")
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--profile", choices=tuple(mms_pi_court.BUILTIN_PROFILES), default=mms_pi_court.DEFAULT_PROFILE)
    profiles.add_argument("--profile-file")
    parser.add_argument("--agent-spec-root")
    parser.add_argument("--family", action="append", default=[])
    parser.add_argument("--add-family", action="append", default=[])
    parser.add_argument("--add-model", action="append", default=[])
    parser.add_argument("--model", action="append", default=[], help="Exact model pool; repeat to preserve order.")
    parser.add_argument("--seat-model", action="append", default=[], metavar="SEAT=MODEL")
    parser.add_argument("--max-seats-per-model", type=int)
    parser.add_argument("--require", action="append", default=["text"], dest="required_capabilities")
    parser.add_argument("--max-concurrency", type=int, default=mms_pi_committee.DEFAULT_MAX_CONCURRENCY)
    parser.add_argument("--timeout", type=int, default=mms_pi_committee.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--kimi-attempt-timeout",
        type=int,
        default=mms_pi_committee.DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-bundle-age-days",
        type=int,
        default=mms_pi_committee.DEFAULT_MAX_BUNDLE_AGE_DAYS,
    )
    parser.add_argument("--idle-timeout", type=int, default=mms_pi_committee.DEFAULT_IDLE_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=mms_pi_committee.DEFAULT_MAX_OUTPUT_BYTES)
    parser.add_argument("--max-repeated-events", type=int, default=mms_pi_committee.DEFAULT_MAX_REPEATED_EVENTS)
    parser.add_argument("--committee-timeout", type=int, default=mms_pi_committee.DEFAULT_COMMITTEE_TIMEOUT_SECONDS)
    parser.add_argument("--quorum-successes", type=int, default=mms_pi_committee.DEFAULT_QUORUM_SUCCESSES)
    parser.add_argument("--quorum-grace", type=int, default=mms_pi_committee.DEFAULT_QUORUM_GRACE_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output")
    return parser


def task_text(args: argparse.Namespace) -> str:
    return args.task if args.task is not None else Path(args.task_file).expanduser().read_text(encoding="utf-8")


def seat_models(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise mms_pi_court.CourtError("--seat-model must use SEAT=MODEL")
        seat, model = (part.strip() for part in value.split("=", 1))
        if not seat or not model:
            raise mms_pi_court.CourtError("--seat-model must use non-empty SEAT=MODEL")
        if seat in result:
            raise mms_pi_court.CourtError(f"duplicate --seat-model override: {seat}")
        result[seat] = model
    return result


def court_kwargs(args: argparse.Namespace) -> dict:
    frontier = tuple(args.family or mms_pi_committee.DEFAULT_FRONTIER_FAMILIES) + tuple(args.add_family)
    return {
        "config_root": args.config_root,
        "task": task_text(args),
        "cwd": args.cwd,
        "profile": args.profile or mms_pi_court.DEFAULT_PROFILE,
        "profile_file": args.profile_file,
        "agent_spec_root": args.agent_spec_root,
        "explicit_models": args.model,
        "frontier_families": frontier,
        "additional_models": args.add_model,
        "required_capabilities": args.required_capabilities,
        "seat_model_overrides": seat_models(args.seat_model),
        "max_seats_per_model": args.max_seats_per_model,
        "max_concurrency": args.max_concurrency,
        "timeout_seconds": args.timeout,
        "kimi_attempt_timeout_seconds": args.kimi_attempt_timeout,
        "max_bundle_age_days": args.max_bundle_age_days,
        "idle_timeout_seconds": args.idle_timeout,
        "max_output_bytes": args.max_output_bytes,
        "max_repeated_events": args.max_repeated_events,
        "committee_timeout_seconds": args.committee_timeout,
        "quorum_successes": args.quorum_successes,
        "quorum_grace_seconds": args.quorum_grace,
        "dry_run": args.dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = mms_pi_court.run_court(**court_kwargs(args))
    except (mms_pi_court.CourtError, OSError, ValueError) as exc:
        error = {"schema": "mms.pi_court.error.v1", "status": "error", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result.get("status") in {"success", "dry_run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
