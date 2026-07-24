#!/usr/bin/env python3
"""CLI that returns a Host-ready Pi executor parent packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_pi_executor
import mms_pi_executor_parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Pi executor candidates and package admissible patches for Host intake.")
    parser.add_argument("--config-root", help="Explicit verified MMS config root; required unless --result is used.")
    parser.add_argument("--pack", help="executor.pack.v1 JSON; required unless --result is used.")
    parser.add_argument("--target-repo", help="Target git repository; required unless --result is used.")
    parser.add_argument("--model", action="append", default=[], help="Exact logical model; repeat for independent candidates.")
    parser.add_argument("--result", help="Build a parent packet from a saved raw executor result without provider calls.")
    parser.add_argument("--max-concurrency", type=int, default=mms_pi_executor.DEFAULT_MAX_CONCURRENCY)
    parser.add_argument("--timeout", type=int, default=mms_pi_executor.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--idle-timeout", type=int, default=mms_pi_executor.DEFAULT_IDLE_TIMEOUT_SECONDS)
    parser.add_argument("--validation-timeout", type=int, default=mms_pi_executor.DEFAULT_VALIDATION_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-bytes", type=int, default=mms_pi_executor.DEFAULT_MAX_OUTPUT_BYTES)
    parser.add_argument("--max-repeated-events", type=int, default=mms_pi_executor.DEFAULT_MAX_REPEATED_EVENTS)
    parser.add_argument("--max-patch-bytes", type=int, default=mms_pi_executor.DEFAULT_MAX_PATCH_BYTES)
    parser.add_argument("--executor-timeout", type=int, default=mms_pi_executor.DEFAULT_EXECUTOR_TIMEOUT_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", help="Parent packet JSON path; required for live execution.")
    parser.add_argument("--artifact-dir", help="Patch directory; defaults next to --output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.result:
            raw = json.loads(Path(args.result).expanduser().read_text(encoding="utf-8"))
            packet = mms_pi_executor_parent.build_parent_packet(raw, source="saved")
        else:
            missing = [name for name, value in (("--config-root", args.config_root), ("--pack", args.pack), ("--target-repo", args.target_repo)) if not value]
            if not args.model:
                missing.append("--model")
            if missing:
                raise mms_pi_executor.ExecutorError("missing required arguments: " + ", ".join(missing))
            if not args.dry_run and not args.output:
                raise mms_pi_executor.ExecutorError("--output is required for live execution")
            output = Path(args.output).expanduser().resolve() if args.output else None
            artifacts = Path(args.artifact_dir).expanduser().resolve() if args.artifact_dir else (output.parent / f"{output.stem}-patches" if output else None)
            packet = mms_pi_executor_parent.run_parent_executor(
                config_root=args.config_root,
                pack_path=args.pack,
                target_repo=args.target_repo,
                explicit_models=args.model,
                artifact_dir=artifacts,
                max_concurrency=args.max_concurrency,
                timeout_seconds=args.timeout,
                idle_timeout_seconds=args.idle_timeout,
                validation_timeout_seconds=args.validation_timeout,
                max_output_bytes=args.max_output_bytes,
                max_repeated_events=args.max_repeated_events,
                max_patch_bytes=args.max_patch_bytes,
                executor_timeout_seconds=args.executor_timeout,
                dry_run=args.dry_run,
            )
    except (mms_pi_executor.ExecutorError, mms_pi_executor_parent.ExecutorParentError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": "mms.pi_executor.parent_error.v1", "status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    rendered = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if packet.get("status") in {
        "ready_for_intake",
        "saved_result_requires_host_revalidation",
        "dry_run",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
