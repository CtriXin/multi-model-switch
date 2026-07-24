#!/usr/bin/env python3
"""Run Pi committee work or convert a saved result into a parent packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_pi_committee
import mms_pi_parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dispatch the isolated Pi committee and emit a lossless packet for the current Codex/Claude parent."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--result", help="Existing mms.pi_committee.result.v1 JSON; never launches Pi.")
    source.add_argument("--task", help="Committee mission text.")
    source.add_argument("--task-file", help="UTF-8 file containing the committee mission.")
    parser.add_argument("--config-root", help="Explicit MMS config root; required for task execution.")
    parser.add_argument("--cwd", default=".", help="Read-only inspection working directory for Pi workers.")
    parser.add_argument("--count", type=int)
    parser.add_argument("--min-families", type=int, default=mms_pi_committee.DEFAULT_MIN_FAMILIES)
    parser.add_argument(
        "--selection-profile",
        choices=("frontier", "balanced"),
        default=mms_pi_committee.DEFAULT_SELECTION_PROFILE,
    )
    parser.add_argument("--family", action="append", default=[], help="Replace default frontier families; repeat in order.")
    parser.add_argument("--add-family", action="append", default=[], help="Append a temporary frontier family.")
    parser.add_argument("--add-model", action="append", default=[], help="Append an exact temporary model.")
    parser.add_argument("--model", action="append", default=[], help="Fully override the lineup with exact models.")
    parser.add_argument("--require", action="append", default=["text"], dest="required_capabilities")
    parser.add_argument("--lens", action="append", default=[])
    parser.add_argument("--max-concurrency", type=int, default=mms_pi_committee.DEFAULT_MAX_CONCURRENCY)
    parser.add_argument("--timeout", type=int, default=mms_pi_committee.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--kimi-attempt-timeout",
        type=int,
        default=mms_pi_committee.DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
        help="Maximum seconds for one Kimi route attempt; 0 disables the per-route cap.",
    )
    parser.add_argument(
        "--max-bundle-age-days",
        type=int,
        default=mms_pi_committee.DEFAULT_MAX_BUNDLE_AGE_DAYS,
        help="Reject older timestamped bundles; 0 disables freshness enforcement.",
    )
    parser.add_argument("--idle-timeout", type=int, default=mms_pi_committee.DEFAULT_IDLE_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=mms_pi_committee.DEFAULT_MAX_OUTPUT_BYTES)
    parser.add_argument("--max-repeated-events", type=int, default=mms_pi_committee.DEFAULT_MAX_REPEATED_EVENTS)
    parser.add_argument(
        "--committee-timeout",
        type=int,
        default=mms_pi_committee.DEFAULT_COMMITTEE_TIMEOUT_SECONDS,
        help="Whole-committee budget; 0 auto-sizes by concurrency waves.",
    )
    parser.add_argument("--quorum-successes", type=int, default=mms_pi_committee.DEFAULT_QUORUM_SUCCESSES)
    parser.add_argument("--quorum-grace", type=int, default=mms_pi_committee.DEFAULT_QUORUM_GRACE_SECONDS)
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no Pi provider calls.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", help="Optional parent packet JSON path.")
    return parser


def _load_result(path: str) -> dict:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise mms_pi_parent.ParentPacketError("committee result JSON must be an object")
    return payload


def _task_text(args: argparse.Namespace) -> str:
    if args.task is not None:
        return args.task
    return Path(args.task_file).expanduser().read_text(encoding="utf-8")


def _build_packet(args: argparse.Namespace) -> dict:
    if args.result:
        return mms_pi_parent.build_parent_packet(_load_result(args.result))
    if not str(args.config_root or "").strip():
        raise mms_pi_parent.ParentPacketError("--config-root is required when dispatching a task")
    lenses = tuple(args.lens) if args.lens else mms_pi_committee.DEFAULT_LENSES
    frontier_families = tuple(args.family or mms_pi_committee.DEFAULT_FRONTIER_FAMILIES) + tuple(args.add_family)
    return mms_pi_parent.run_parent_committee(
        config_root=args.config_root,
        task=_task_text(args),
        cwd=args.cwd,
        count=args.count,
        min_families=args.min_families,
        explicit_models=args.model,
        selection_profile=args.selection_profile,
        frontier_families=frontier_families,
        additional_models=args.add_model,
        required_capabilities=args.required_capabilities,
        lenses=lenses,
        max_concurrency=args.max_concurrency,
        timeout_seconds=args.timeout,
        kimi_attempt_timeout_seconds=args.kimi_attempt_timeout,
        max_bundle_age_days=args.max_bundle_age_days,
        idle_timeout_seconds=args.idle_timeout,
        max_output_bytes=args.max_output_bytes,
        max_repeated_events=args.max_repeated_events,
        committee_timeout_seconds=args.committee_timeout,
        quorum_successes=args.quorum_successes,
        quorum_grace_seconds=args.quorum_grace,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = _build_packet(args)
    except (json.JSONDecodeError, mms_pi_committee.CommitteeError, mms_pi_parent.ParentPacketError, OSError, ValueError) as exc:
        error = {"schema": "mms.pi_committee.parent_error.v1", "status": "error", "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    indent = None if args.compact else 2
    rendered = json.dumps(packet, ensure_ascii=False, indent=indent) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if packet.get("status") in {"success", "partial", "dry_run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
