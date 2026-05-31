"""OpenCode launch preflight helpers."""

from __future__ import annotations

import subprocess
from time import perf_counter

from mms_opencode.config import (
    OPENCODE_BYPASS_FLAG,
    OPENCODE_LAUNCH_PREFLIGHT_PROMPT,
    opencode_preflight_timeout,
)


def _compact_output(value):
    return " ".join(str(value or "").split())[:500]


def opencode_run_preflight(
    env,
    agent,
    model_ref,
    timeout=None,
    bypass=True,
    *,
    subprocess_run=None,
    perf_counter_fn=None,
    preflight_timeout=None,
):
    timeout_fn = preflight_timeout or opencode_preflight_timeout
    timeout = int(timeout or timeout_fn())
    cmd = ["opencode", "run", "--pure"]
    if bool(bypass):
        cmd.append(OPENCODE_BYPASS_FLAG)
    if agent:
        cmd += ["--agent", agent]
    cmd += ["-m", model_ref, OPENCODE_LAUNCH_PREFLIGHT_PROMPT]
    now = perf_counter_fn or perf_counter
    run = subprocess_run or subprocess.run
    started = now()
    try:
        completed = run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        combined = f"{completed.stdout}\n{completed.stderr}"
        return {
            "ok": completed.returncode == 0 and "OK" in combined.upper(),
            "returncode": completed.returncode,
            "elapsed_sec": round(now() - started, 3),
            "stdout": _compact_output(completed.stdout),
            "stderr": _compact_output(completed.stderr),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": "not_found",
            "elapsed_sec": round(now() - started, 3),
            "stdout": "",
            "stderr": "opencode not found",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": "timeout",
            "elapsed_sec": timeout,
            "stdout": _compact_output(exc.stdout),
            "stderr": _compact_output(exc.stderr),
        }


def opencode_select_launch_candidate(
    runtime,
    routes,
    model,
    env,
    *,
    launch_candidates,
    launch_preflight_enabled,
    run_preflight,
    bypass_enabled,
    console,
):
    candidates = launch_candidates(runtime, routes, model)
    if not candidates:
        return "", "", []
    if not launch_preflight_enabled(runtime):
        first = candidates[0]
        return first["model_ref"], first.get("agent") or "", []

    checks = []
    console.print("[dim]OpenCode Agent preflight: 检查 primary builder route...[/dim]")
    for candidate in candidates:
        check = run_preflight(
            env,
            candidate.get("agent") or "",
            candidate.get("model_ref") or "",
            bypass=bypass_enabled(runtime),
        )
        check.update(
            {
                "route_key": candidate.get("route_key"),
                "model_ref": candidate.get("model_ref"),
                "agent": candidate.get("agent") or "",
            }
        )
        checks.append(check)
        if check.get("ok"):
            if candidate.get("route_key") != candidates[0].get("route_key"):
                console.print(
                    f"[yellow]OpenCode primary route failed; using fallback "
                    f"{candidate.get('route_key')} ({candidate.get('model_ref')}).[/yellow]"
                )
            return candidate["model_ref"], candidate.get("agent") or "", checks
        console.print(
            f"[yellow]⚠ OpenCode route {candidate.get('route_key')} "
            f"preflight failed: {check.get('returncode')}[/yellow]"
        )

    return "", "", checks


__all__ = [
    "opencode_run_preflight",
    "opencode_select_launch_candidate",
]
