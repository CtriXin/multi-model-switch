#!/usr/bin/env python3
"""CLI for the opt-in dynamic Pi committee sidecar."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_pi_committee


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run isolated, runtime-bound Pi committee members without OpenCode or global config writes."
    )
    parser.add_argument("--config-root", required=True, help="Explicit MMS config root containing a verified latest-approved bundle.")
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--task", help="Committee mission text.")
    task.add_argument("--task-file", help="UTF-8 file containing the committee mission.")
    parser.add_argument("--cwd", default=".", help="Read-only inspection working directory for Pi workers.")
    parser.add_argument("--count", type=int, help="Member count; defaults to all frontier families, 4 for balanced, or all explicit models.")
    parser.add_argument("--min-families", type=int, default=mms_pi_committee.DEFAULT_MIN_FAMILIES)
    parser.add_argument(
        "--selection-profile",
        choices=("frontier", "balanced"),
        default=mms_pi_committee.DEFAULT_SELECTION_PROFILE,
        help="frontier chooses one current champion per target family; balanced uses generic diversity ranking.",
    )
    parser.add_argument("--family", action="append", default=[], help="Replace the default frontier family list; repeat in desired order.")
    parser.add_argument("--add-family", action="append", default=[], help="Append a temporary frontier family for this mission.")
    parser.add_argument("--add-model", action="append", default=[], help="Append an exact temporary model after frontier champions.")
    parser.add_argument("--model", action="append", default=[], help="Fully override the lineup with exact logical models; repeat to preserve order.")
    parser.add_argument("--require", action="append", default=["text"], dest="required_capabilities")
    parser.add_argument("--lens", action="append", default=[], help="Optional lens list; repeat for multiple members.")
    parser.add_argument("--max-concurrency", type=int, default=mms_pi_committee.DEFAULT_MAX_CONCURRENCY)
    parser.add_argument(
        "--timeout",
        type=int,
        default=mms_pi_committee.DEFAULT_TIMEOUT_SECONDS,
        help="Per-member wall budget in seconds; shared by route attempts.",
    )
    parser.add_argument(
        "--kimi-attempt-timeout",
        type=int,
        default=mms_pi_committee.DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
        help="Maximum seconds for one Kimi route attempt; 0 lets one route use the whole member budget.",
    )
    parser.add_argument(
        "--max-bundle-age-days",
        type=int,
        default=mms_pi_committee.DEFAULT_MAX_BUNDLE_AGE_DAYS,
        help="Fail closed when a timestamped latest-approved bundle is older; 0 disables freshness enforcement.",
    )
    parser.add_argument("--idle-timeout", type=int, default=mms_pi_committee.DEFAULT_IDLE_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=mms_pi_committee.DEFAULT_MAX_OUTPUT_BYTES)
    parser.add_argument("--max-repeated-events", type=int, default=mms_pi_committee.DEFAULT_MAX_REPEATED_EVENTS)
    parser.add_argument(
        "--committee-timeout",
        type=int,
        default=mms_pi_committee.DEFAULT_COMMITTEE_TIMEOUT_SECONDS,
        help="Whole-committee budget; 0 auto-sizes by member wall budget and concurrency waves.",
    )
    parser.add_argument(
        "--quorum-successes",
        type=int,
        default=mms_pi_committee.DEFAULT_QUORUM_SUCCESSES,
        help="Cancel remaining workers after this many successes plus grace; 0 disables early stop.",
    )
    parser.add_argument("--quorum-grace", type=int, default=mms_pi_committee.DEFAULT_QUORUM_GRACE_SECONDS)
    parser.add_argument("--dry-run", action="store_true", help="Verify bundle and emit the dynamic plan without launching Pi.")
    parser.add_argument("--output", help="Optional result JSON path. Parent directories are created locally.")
    return parser


def _task_text(args: argparse.Namespace) -> str:
    if args.task is not None:
        return args.task
    return Path(args.task_file).expanduser().read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lenses = tuple(args.lens) if args.lens else mms_pi_committee.DEFAULT_LENSES
    frontier_families = tuple(args.family or mms_pi_committee.DEFAULT_FRONTIER_FAMILIES) + tuple(args.add_family)
    try:
        result = mms_pi_committee.run_committee(
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
    except (mms_pi_committee.CommitteeError, OSError, ValueError) as exc:
        print(json.dumps({"schema": "mms.pi_committee.error.v1", "status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
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
