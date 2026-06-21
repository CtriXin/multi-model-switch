"""Noninteractive Review Hub worker execution for MMS review-dispatch."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_DISPATCH_EXECUTE_SCHEMA = "mms.review_dispatch.execute.v1"


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or "review"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _review_hub_prompt(request_root: Path) -> str:
    return (
        f"/review-hub {request_root}\n\n"
        "Use the Review Hub request root above. Run the worker plan, delegate to the "
        "configured reviewer agents, and aggregate results. Do not edit source files."
    )


def _load_opencode_smoke_helper():
    helper = Path(__file__).resolve().parent / "scripts" / "smoke_opencode_profile.py"
    if not helper.exists():
        raise FileNotFoundError(f"missing OpenCode profile helper: {helper}")
    root = Path(__file__).resolve().parent
    for path in (root, root / "scripts"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
    spec = importlib.util.spec_from_file_location("mms_review_dispatch_smoke_opencode_profile", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load OpenCode profile helper: {helper}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _redacted_opencode_agents(payload: dict[str, Any]) -> dict[str, str]:
    agents = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    return {
        str(name): str(config.get("model") or "")
        for name, config in agents.items()
        if isinstance(config, dict)
    }


def _agent_for_worker(worker: dict[str, Any], opencode_payload: dict[str, Any]) -> str:
    agents = opencode_payload.get("agent") if isinstance(opencode_payload.get("agent"), dict) else {}
    model = str(worker.get("model_name") or "").strip()
    model_key = model.lower()
    candidates = []
    model_slug = str(worker.get("model_slug") or "").strip()
    if model_slug:
        candidates.append(f"review-{model_slug}")
    slot_root = Path(str(worker.get("slot_root") or ""))
    if slot_root.name:
        candidates.append(f"review-{slot_root.name}")
    if model:
        candidates.append(f"review-{_slugify(model)}")
    for candidate in candidates:
        if candidate in agents:
            return candidate
    for name, config in agents.items():
        if not str(name).startswith("review-") or name in {"review-hub-host", "review-hub-host-stable"}:
            continue
        if isinstance(config, dict) and str(config.get("model") or "").lower().endswith("/" + model_key):
            return str(name)
    available = ", ".join(sorted(str(name) for name in agents if str(name).startswith("review-")))
    expected = ", ".join(candidates) or "<none>"
    raise ValueError(
        f"no OpenCode review agent found for model={model or '<unknown>'}; "
        f"expected one of [{expected}], available=[{available or '<none>'}]"
    )


def _worker_prompt(request_root: Path, worker: dict[str, Any]) -> str:
    model = str(worker.get("model_name") or "").strip()
    slot_root = str(worker.get("slot_root") or "").strip()
    prompt_path = str(worker.get("prompt_path") or "").strip()
    manifest_path = str(worker.get("manifest_path") or "").strip()
    return (
        f"Review Hub worker mode for {request_root}.\n"
        f"You are the reviewer for model `{model}`.\n"
        f"Slot root: `{slot_root}`.\n"
        f"Prompt path: `{prompt_path}`.\n"
        f"Manifest path: `{manifest_path}`.\n\n"
        "Read the prompt and manifest from disk, run the preflight first, then execute that prompt exactly. "
        "Write only inside the assigned slot_root, especially slot_root/verify/*. "
        "Do not edit source files, do not write other reviewer slots, and do not run committee or debate workflows."
    )


def _execute_evidence_root(request_root: Path) -> Path:
    return request_root / "runner" / "mms-execute" / _now_stamp()


def _resolve_review_profile_for_execute(models: list[str], evidence_root: Path):
    smoke = _load_opencode_smoke_helper()
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        model_info, runtime = smoke._resolve_profile("review", review_models=models)
    _write_text(evidence_root / "profile-resolve.stdout.txt", stdout.getvalue())
    _write_text(evidence_root / "profile-resolve.stderr.txt", stderr.getvalue())
    return smoke, model_info, runtime


def _run_process_with_evidence(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, bool, str, str]:
    timed_out = False
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stderr = stderr + f"\nTIMEOUT after {timeout}s\n"
    except OSError as exc:
        returncode = 127
        stdout = ""
        stderr = str(exc)
    _write_text(stdout_path, stdout)
    _write_text(stderr_path, stderr)
    return returncode, timed_out, stdout, stderr


def execute_review_workers(
    *,
    root: Path,
    request_root: Path,
    models: list[str],
    workers: list[dict[str, Any]],
    mode: str,
    host_agent: str,
    host_timeout: int,
    worker_timeout: int,
) -> dict[str, Any]:
    evidence_root = _execute_evidence_root(request_root)
    evidence_root.mkdir(parents=True, exist_ok=True)
    try:
        smoke, model_info, runtime = _resolve_review_profile_for_execute(models, evidence_root)
    except Exception as exc:  # noqa: BLE001 - keep structured failure at CLI boundary
        return {
            "schema": REVIEW_DISPATCH_EXECUTE_SCHEMA,
            "ok": False,
            "mode": mode,
            "errors": [f"OpenCode review profile resolve failed: {exc}"],
            "evidence_root": str(evidence_root),
            "workers": [],
            "returncode": 1,
        }

    with tempfile.TemporaryDirectory(prefix="mms-review-dispatch-execute-") as tmp:
        env, _config_path, opencode_payload = smoke._build_temp_env(runtime, model_info, Path(tmp))
        redacted = {
            "request_root": str(request_root),
            "default_agent": opencode_payload.get("default_agent"),
            "default_model": opencode_payload.get("model"),
            "agents": _redacted_opencode_agents(opencode_payload),
        }
        redacted_path = evidence_root / "opencode-config.redacted.json"
        _write_json(redacted_path, redacted)

        if mode == "host":
            prompt = _review_hub_prompt(request_root).rstrip() + "\n\nRun reviewers and aggregate results. Do not edit source files."
            stdout_path = evidence_root / "opencode-host.stdout.txt"
            stderr_path = evidence_root / "opencode-host.stderr.txt"
            cmd = ["opencode", "run", "--pure", "--agent", host_agent, prompt]
            returncode, timed_out, stdout, stderr = _run_process_with_evidence(
                cmd,
                cwd=root,
                env=env,
                timeout=host_timeout,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            return {
                "schema": REVIEW_DISPATCH_EXECUTE_SCHEMA,
                "ok": returncode == 0,
                "mode": "host",
                "evidence_root": str(evidence_root),
                "opencode_config_redacted_path": str(redacted_path),
                "returncode": returncode,
                "timed_out": timed_out,
                "command": ["opencode", "run", "--pure", "--agent", host_agent, "<prompt>"],
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "stdout_tail": stdout[-1200:],
                "stderr_tail": stderr[-1200:],
            }

        results: list[dict[str, Any]] = []
        for index, worker in enumerate(workers, start=1):
            if not isinstance(worker, dict):
                continue
            model_slug = Path(str(worker.get("slot_root") or f"worker-{index}")).name or f"worker-{index}"
            stdout_path = evidence_root / f"opencode-worker-{index:02d}-{model_slug}.stdout.txt"
            stderr_path = evidence_root / f"opencode-worker-{index:02d}-{model_slug}.stderr.txt"
            try:
                agent = _agent_for_worker(worker, opencode_payload)
            except ValueError as exc:
                agent = ""
                returncode = 127
                timed_out = False
                stdout = ""
                stderr = str(exc)
                _write_text(stdout_path, stdout)
                _write_text(stderr_path, stderr + "\n")
            else:
                worker_env = dict(env)
                worker_env["REVIEW_HUB_MODEL"] = str(worker.get("model_name") or "")
                worker_env["MULTI_REVIEW_REVIEWER"] = str(worker.get("model_name") or "")
                worker_env["REVIEW_HUB_REQUEST_ROOT"] = str(request_root)
                worker_env["MMS_MODEL_NAME"] = str(worker.get("model_name") or "")
                cmd = ["opencode", "run", "--pure", "--agent", agent, _worker_prompt(request_root, worker)]
                returncode, timed_out, stdout, stderr = _run_process_with_evidence(
                    cmd,
                    cwd=root,
                    env=worker_env,
                    timeout=worker_timeout,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )
            results.append(
                {
                    "order": index,
                    "model": worker.get("model_name"),
                    "agent": agent,
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "command": ["opencode", "run", "--pure", "--agent", agent, "<prompt>"] if agent else [],
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "stdout_tail": stdout[-1200:],
                    "stderr_tail": stderr[-1200:],
                }
            )

    errors = []
    for item in results:
        if item.get("returncode") == 0:
            continue
        detail = str(item.get("stderr_tail") or "").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        errors.append(f"opencode worker failed: model={item.get('model')} exit={item.get('returncode')}{suffix}")
    return {
        "schema": REVIEW_DISPATCH_EXECUTE_SCHEMA,
        "ok": not errors and bool(results),
        "mode": "workers",
        "evidence_root": str(evidence_root),
        "opencode_config_redacted_path": str(redacted_path),
        "worker_count": len(results),
        "workers": results,
        "errors": errors,
        "returncode": 0 if not errors and results else 1,
    }
