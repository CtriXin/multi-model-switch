"""Mission Control -> OpenCode Review Hub dispatch helper."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mms_opencode_profiles import OPENCODE_REVIEW_HUB_SPECS


REVIEW_DISPATCH_SCHEMA = "mms.review_dispatch.v1"
BLOCKED_READINESS_STATES = {
    "blocked-source",
    "needs-info",
    "out-of-scope-review",
    "ready-for-human",
}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or "review"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _first_existing(root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None


def _mission_context(root: Path) -> dict[str, Any]:
    readiness_path = _first_existing(root, [".mission/readiness.json", "readiness.json"])
    agent_brief_path = _first_existing(root, [".mission/agent-brief.md", "agent-brief.md"])
    mission_prd_path = _first_existing(root, [".mission/mission-prd.md", "mission-prd.md"])
    check_spec_path = _first_existing(
        root,
        [
            ".work-gate/state/check-spec.json",
            "work-gate/state/check-spec.json",
            ".work-gate/check-spec.json",
            "check-spec.json",
        ],
    )
    readiness = _read_json(readiness_path) if readiness_path else {}
    state = str(readiness.get("state") or readiness.get("readiness") or "").strip()
    return {
        "readiness_path": str(readiness_path) if readiness_path else "",
        "readiness_state": state,
        "agent_brief_path": str(agent_brief_path) if agent_brief_path else "",
        "mission_prd_path": str(mission_prd_path) if mission_prd_path else "",
        "check_spec_path": str(check_spec_path) if check_spec_path else "",
        "missing": [
            label
            for label, path in [
                ("readiness", readiness_path),
                ("agent_brief", agent_brief_path),
                ("check_spec", check_spec_path),
            ]
            if path is None
        ],
    }


def _default_review_models() -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for spec in OPENCODE_REVIEW_HUB_SPECS:
        if not isinstance(spec, dict):
            continue
        agent = str(spec.get("agent") or "").strip()
        if not agent.startswith("review-"):
            continue
        for model in spec.get("models") or ():
            model_name = str(model or "").strip()
            if model_name and model_name not in seen:
                seen.add(model_name)
                models.append(model_name)
                break
    return models or ["gpt-5.4", "qwen3.7-max", "kimi-k2.6"]


def _review_hub_binary() -> str:
    binary = shutil.which("review-hub")
    if not binary:
        raise FileNotFoundError("review-hub executable not found in PATH")
    return binary


def _run_review_hub(args: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    command = [_review_hub_binary()] + args
    if dry_run:
        return {"ok": True, "dry_run": True, "command": command}
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "review-hub failed: "
            + " ".join(shlex.quote(part) for part in command)
            + "\n"
            + (completed.stderr or completed.stdout or "").strip()
        )
    output = (completed.stdout or "").strip()
    if not output:
        return {"ok": True, "command": command}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"review-hub returned non-JSON output: {output[:500]}") from exc
    if isinstance(payload, dict):
        payload.setdefault("command", command)
        return payload
    return {"ok": True, "command": command, "output": payload}


def _build_request_args(
    *,
    root: Path,
    request_root: Path,
    request_id: str,
    title: str,
    summary: str,
    phase: str,
    adapter: str,
    focus: list[str],
    models: list[str],
    context: dict[str, Any],
) -> list[str]:
    args = [
        "request",
        "--root",
        str(root),
        "--out-dir",
        str(request_root),
        "--request-id",
        request_id,
        "--title",
        title,
        "--summary",
        summary,
        "--phase",
        phase,
        "--adapter",
        adapter,
        "--write",
    ]
    for item in focus:
        args.extend(["--focus", item])
    for path_key in ("agent_brief_path", "mission_prd_path", "check_spec_path"):
        path = context.get(path_key)
        if path:
            args.extend(["--context-path", path])
    for model in models:
        args.extend(["--model", model])
    return args


def _build_worker_plan_args(request_root: Path, models: list[str], runner: str, agent: str) -> list[str]:
    args = [
        "worker-plan",
        "--request",
        str(request_root),
        "--runner",
        runner,
        "--agent",
        agent,
        "--write",
    ]
    for model in models:
        args.extend(["--model", model])
    return args


def _mms_script_path() -> Path:
    return Path(__file__).resolve().with_name("mms")


def _opencode_launch_command(request_root: Path) -> list[str]:
    return [
        sys.executable,
        str(_mms_script_path()),
        "opencode",
        "--profile",
        "review",
    ]


def _review_hub_prompt(request_root: Path) -> str:
    return (
        f"/review-hub {request_root}\n\n"
        "Use the Review Hub request root above. Run the worker plan, delegate to the "
        "configured reviewer agents, and aggregate results. Do not edit source files."
    )


def _fake_reviewer_outputs(request_root: Path, workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for worker in workers:
        model = str(worker.get("model_name") or "").strip()
        slot_root = Path(str(worker.get("slot_root") or ""))
        if not model or not slot_root:
            continue
        verify_root = slot_root / "verify"
        _write_text(verify_root / "00-preflight.md", f"# Preflight\n\nModel: `{model}`\nStatus: pass\n")
        _write_text(
            verify_root / "01-checks.md",
            f"# Checks\n\n- pass: review-dispatch request was readable for `{model}`.\n",
        )
        _write_json(verify_root / "02-failures.json", {"model": model, "failures": []})
        _write_json(verify_root / "03-residual-risks.json", {"model": model, "residual_risks": []})
        _write_text(
            verify_root / "04-final-verdict.md",
            f"# Final Verdict\n\nVerdict: pass\n\nFake reviewer result for `{model}`.\n",
        )
        results.append({"model": model, "slot_root": str(slot_root), "verify_root": str(verify_root)})
    return results


def build_review_dispatch(
    *,
    root: Path,
    title: str,
    summary: str,
    phase: str,
    models: list[str],
    out_dir: Path | None,
    request_id: str | None,
    adapter: str,
    focus: list[str],
    fake_run: bool,
    dry_run: bool,
    launch: bool,
    allow_incomplete: bool,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists():
        return {"ok": False, "errors": [f"root does not exist: {root}"]}

    context = _mission_context(root)
    errors: list[str] = []
    if context["missing"] and not allow_incomplete:
        errors.append("missing Mission Control artifacts: " + ", ".join(context["missing"]))
    state = str(context.get("readiness_state") or "").strip()
    if state in BLOCKED_READINESS_STATES:
        errors.append(f"readiness state blocks dispatch: {state}")
    if errors:
        return {"ok": False, "root": str(root), "context": context, "errors": errors}

    models = [str(model).strip() for model in models if str(model).strip()]
    if not models:
        models = _default_review_models()
    request_id = request_id or f"{_now_stamp()}-{_slugify(title)}"
    request_root = (
        out_dir.resolve()
        if out_dir
        else root / ".mission" / "review-dispatch" / "opencode" / request_id
    )
    request_args = _build_request_args(
        root=root,
        request_root=request_root,
        request_id=request_id,
        title=title,
        summary=summary,
        phase=phase,
        adapter=adapter,
        focus=focus,
        models=models,
        context=context,
    )
    worker_args = _build_worker_plan_args(request_root, models, "opencode", "review-hub-host")
    launch_command = _opencode_launch_command(request_root)

    payload: dict[str, Any] = {
        "schema": REVIEW_DISPATCH_SCHEMA,
        "ok": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "request_id": request_id,
        "request_root": str(request_root),
        "phase": phase,
        "models": models,
        "context": context,
        "review_hub_request_command": [_review_hub_binary()] + request_args if shutil.which("review-hub") else request_args,
        "review_hub_worker_plan_command": [_review_hub_binary()] + worker_args if shutil.which("review-hub") else worker_args,
        "opencode_launch_command": launch_command,
        "review_hub_prompt": _review_hub_prompt(request_root),
        "opencode_profile": "review",
        "fake_run": fake_run,
        "dry_run": dry_run,
        "launched": False,
    }
    if dry_run:
        return payload

    request_result = _run_review_hub(request_args)
    worker_plan = _run_review_hub(worker_args)
    payload["review_hub_request"] = request_result
    payload["worker_plan"] = worker_plan

    fake_results: list[dict[str, Any]] = []
    aggregate_result: dict[str, Any] | None = None
    workers = worker_plan.get("workers") if isinstance(worker_plan.get("workers"), list) else []
    if fake_run:
        fake_results = _fake_reviewer_outputs(request_root, workers)
        aggregate_result = _run_review_hub(["aggregate", "--request", str(request_root), "--write"])
        payload["fake_results"] = fake_results
        payload["aggregate"] = aggregate_result

    if launch:
        completed = subprocess.run(launch_command, text=True, check=False)
        payload["launched"] = True
        payload["launch_returncode"] = completed.returncode
        if completed.returncode != 0:
            payload["ok"] = False
            payload.setdefault("errors", []).append(f"OpenCode launch failed with exit code {completed.returncode}")

    _write_json(request_root / "mms-review-dispatch.json", payload)
    return payload


def handle_review_dispatch_command(argv: list[str], *, command_name: str = "mms") -> int:
    parser = argparse.ArgumentParser(
        prog=f"{command_name} review-dispatch",
        description="Create a Mission Control Review Hub request and prepare/launch the OpenCode review profile.",
    )
    parser.add_argument("--root", required=True, help="Mission Control artifact root or repo root")
    parser.add_argument("--title", default="Mission Control review dispatch")
    parser.add_argument("--summary", default="Review Mission Control packet and gate evidence before closeout.")
    parser.add_argument("--phase", choices=["pre", "mid", "post"], default="post")
    parser.add_argument("--adapter", default="mms-opencode")
    parser.add_argument("--focus", action="append", default=["code", "verification"])
    parser.add_argument("--model", action="append", default=[], help="Reviewer model; repeat for multiple models")
    parser.add_argument("--out-dir", help="Override Review Hub request root")
    parser.add_argument("--request-id", help="Stable request id")
    parser.add_argument("--allow-incomplete", action="store_true", help="Do not fail on missing Mission Control artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Print planned request/worker/OpenCode commands without writing")
    parser.add_argument("--fake-run", action="store_true", help="Write fake per-model reviewer outputs and aggregate them")
    parser.add_argument("--launch", action="store_true", help="Launch MMS OpenCode review profile after writing request artifacts")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        payload = build_review_dispatch(
            root=Path(args.root),
            title=args.title,
            summary=args.summary,
            phase=args.phase,
            models=args.model,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            request_id=args.request_id,
            adapter=args.adapter,
            focus=args.focus,
            fake_run=args.fake_run,
            dry_run=args.dry_run,
            launch=args.launch,
            allow_incomplete=args.allow_incomplete,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should return a structured error
        payload = {"schema": REVIEW_DISPATCH_SCHEMA, "ok": False, "errors": [str(exc)]}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if payload.get("ok"):
            print(f"review-dispatch ready: {payload.get('request_root')}")
            print("OpenCode command:")
            print(" ".join(shlex.quote(str(part)) for part in payload.get("opencode_launch_command", [])))
            if payload.get("aggregate"):
                print(f"aggregate: {payload['aggregate'].get('aggregate_path')}")
        else:
            print("review-dispatch failed", file=sys.stderr)
            for item in payload.get("errors", []):
                print(f"- {item}", file=sys.stderr)
    return 0 if payload.get("ok") else 2


__all__ = [
    "REVIEW_DISPATCH_SCHEMA",
    "build_review_dispatch",
    "handle_review_dispatch_command",
]
