"""MMS noninteractive multi-review launcher handshake.

This command is intentionally a contract/validation surface first. It proves
that a Moebius-launched reviewer process can find the expected environment, but
it does not call models or write review files until a later explicit execution
mode exists.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_LAUNCH_CONTRACT_SCHEMA = "mms.review_launch_contract.v1"
REVIEW_LAUNCH_VALIDATION_SCHEMA = "mms.review_launch_validation.v1"
REQUIRED_ENV = [
    "MOEBIUS_RUN_ID",
    "MOEBIUS_RUN_DIR",
    "MOEBIUS_REPO_ROOT",
    "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG",
    "MOEBIUS_REVIEW_DISPATCH_GATE",
    "MOEBIUS_REVIEW_DISPATCH_PLAN",
    "MOEBIUS_REVIEWER_ID",
    "MOEBIUS_REVIEW_EXPECTED_OUTPUT",
    "MULTI_REVIEW_REVIEWER",
    "MOEBIUS_REVIEW_PACK",
]
WRAPPER_ONLY_IDS = {"agent", "claude-code", "cli", "codex", "default", "local", "mms", "reviewer", "unknown"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"json root must be an object: {path}")
    return data


def _resolve(path: str, repo_root: Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else repo_root / candidate


def build_review_launch_contract(command_name: str = "mms") -> dict[str, Any]:
    return {
        "schema": REVIEW_LAUNCH_CONTRACT_SCHEMA,
        "generated_at": _now(),
        "command": f"{command_name} review-launch",
        "purpose": "noninteractive multi-review reviewer launcher handshake",
        "model_dispatch_implemented": False,
        "review_file_write_implemented": False,
        "required_env": REQUIRED_ENV,
        "identity_contract": {
            "reviewer_id": "MOEBIUS_REVIEWER_ID",
            "multi_review_reviewer_must_equal_reviewer_id": True,
            "expected_output": "MOEBIUS_REVIEW_EXPECTED_OUTPUT",
            "gemini_cli_compat_identity_allowed": True,
            "wrapper_only_ids_rejected": sorted(WRAPPER_ONLY_IDS),
        },
        "modes": {
            "--contract-json": "print this local contract and exit",
            "--validate-env": "validate Moebius reviewer-launch environment and exit without model calls",
            "default": "fail closed until model dispatch mode is explicitly implemented",
        },
        "boundaries": [
            "No model calls.",
            "No review file writes.",
            "No review intake or gate clear.",
            "No Pilot, Ant, Hive, addon, deploy, browser, IM, webhook, daemon, or product repo action.",
        ],
    }


def validate_review_launch_env(env: dict[str, str] | None = None) -> dict[str, Any]:
    effective_env = dict(env or os.environ)
    missing = [name for name in REQUIRED_ENV if not str(effective_env.get(name) or "").strip()]
    errors: list[str] = []
    warnings: list[str] = []
    if missing:
        errors.append("missing required env: " + ", ".join(missing))

    reviewer_id = str(effective_env.get("MOEBIUS_REVIEWER_ID") or "").strip()
    multi_review_reviewer = str(effective_env.get("MULTI_REVIEW_REVIEWER") or "").strip()
    repo_root_ref = str(effective_env.get("MOEBIUS_REPO_ROOT") or "").strip()
    expected_output_ref = str(effective_env.get("MOEBIUS_REVIEW_EXPECTED_OUTPUT") or "").strip()
    gate_ref = str(effective_env.get("MOEBIUS_REVIEW_DISPATCH_GATE") or "").strip()

    if reviewer_id and reviewer_id in WRAPPER_ONLY_IDS:
        errors.append(f"reviewer id is a wrapper/tool id, not a model identity: {reviewer_id}")
    if reviewer_id and multi_review_reviewer and reviewer_id != multi_review_reviewer:
        errors.append("MULTI_REVIEW_REVIEWER must match MOEBIUS_REVIEWER_ID")

    repo_root = Path(repo_root_ref).expanduser() if repo_root_ref else Path(".")
    if repo_root_ref and not repo_root.exists():
        errors.append(f"MOEBIUS_REPO_ROOT does not exist: {repo_root}")

    expected_output = _resolve(expected_output_ref, repo_root) if expected_output_ref else None
    if expected_output is not None and reviewer_id:
        try:
            output_rel = expected_output.resolve().relative_to(repo_root.resolve())
        except (OSError, ValueError):
            errors.append("MOEBIUS_REVIEW_EXPECTED_OUTPUT must stay under MOEBIUS_REPO_ROOT")
            output_rel = Path("")
        expected_prefix = Path(".ai") / "reviews" / reviewer_id
        if output_rel.parts and not str(output_rel).startswith(str(expected_prefix) + os.sep):
            errors.append(f"expected output must be under {expected_prefix}")

    gate_status = ""
    if gate_ref:
        try:
            gate = _read_json(_resolve(gate_ref, repo_root))
            gate_status = str(gate.get("gate_status") or "")
            if gate_status != "approved":
                errors.append("review-dispatch gate must be approved before launch")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"cannot read review-dispatch gate: {exc}")

    if reviewer_id == "gemini-cli":
        warnings.append("gemini-cli compatibility identity is accepted when path/header exactly match")

    return {
        "schema": REVIEW_LAUNCH_VALIDATION_SCHEMA,
        "validated_at": _now(),
        "ok": not errors,
        "status": "ready_for_future_dispatch" if not errors else "blocked",
        "reviewer_id": reviewer_id,
        "expected_output": expected_output_ref,
        "gate_status": gate_status,
        "errors": errors,
        "warnings": warnings,
        "model_calls": 0,
        "review_file_writes": 0,
    }


def _print_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload.get("schema") == REVIEW_LAUNCH_CONTRACT_SCHEMA:
        print(f"{payload['command']} — {payload['purpose']}")
        print("Modes: --contract-json, --validate-env")
        print("Model dispatch: not implemented")
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_review_launch_command(argv: list[str], *, command_name: str = "mms") -> int:
    parser = argparse.ArgumentParser(
        prog=f"{command_name} review-launch",
        description=(
            "MMS review-launch — noninteractive multi-review reviewer launcher. "
            "Reads Moebius reviewer env, validates identity/output contract, and "
            "fails closed before model dispatch is implemented."
        ),
    )
    parser.add_argument("--contract-json", action="store_true", help="print the local review-launch contract JSON")
    parser.add_argument("--validate-env", action="store_true", help="validate Moebius reviewer-launch env without model calls")
    parser.add_argument("--json", action="store_true", help="print JSON for validation/default output")
    parser.add_argument(
        "--allow-model-call",
        action="store_true",
        help="reserved future latch; currently still fails closed and calls no models",
    )
    args = parser.parse_args(argv)

    if args.contract_json:
        _print_payload(build_review_launch_contract(command_name), json_output=True)
        return 0

    if args.validate_env:
        result = validate_review_launch_env()
        _print_payload(result, json_output=args.json or True)
        return 0 if result["ok"] else 2

    result = validate_review_launch_env()
    result["status"] = "blocked_model_dispatch_not_implemented"
    result["errors"] = [
        *result.get("errors", []),
        "MMS review-launch model dispatch is not implemented in this handshake phase",
    ]
    if args.allow_model_call:
        result["errors"].append("--allow-model-call is reserved but not active yet")
    _print_payload(result, json_output=args.json or True)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(handle_review_launch_command(os.sys.argv[1:]))
