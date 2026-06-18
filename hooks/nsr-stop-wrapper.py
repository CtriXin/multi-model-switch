#!/usr/bin/env python3
"""Bundled opt-in wrapper for the NSR Stop hook.

MMS installs this file with the channel payload. The hook is injected into
Claude/Codex sessions by default, but it only delegates to nsr-loop-hook.py when
NSR is explicitly enabled for the current repo via nsrctl.py or NSR_ENABLED=1.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOOP_HOOK = Path(os.environ.get("NSR_LOOP_HOOK") or SCRIPT_DIR / "nsr-loop-hook.py")
NSRCTL = SCRIPT_DIR / "nsrctl.py"
STOP_EVENT_NAMES = {"stop"}
EVENT_KEYS = ("hook_event_name", "hookEventName", "event_name", "event")


def load_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def event_name(payload: dict) -> str:
    for key in EVENT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def is_stop_event(payload: dict) -> bool:
    name = event_name(payload)
    return not name or name in STOP_EVENT_NAMES


def cwd_from_payload(payload: dict) -> str:
    for key in ("cwd", "workspace", "project_dir"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return os.getcwd()


def marker_path(cwd: str) -> Path | None:
    if not NSRCTL.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(NSRCTL), "status", cwd],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    if ": " not in text:
        return None
    return Path(text.split(": ", 1)[1])


def allow_stop() -> int:
    sys.stdout.write("{}\n")
    return 0


def allow_event(host: str) -> int:
    if host == "codex":
        sys.stdout.write("{}\n")
    else:
        sys.stdout.write(json.dumps({"continue": True}) + "\n")
    return 0


def run_loop(raw: str) -> subprocess.CompletedProcess[str] | None:
    if not LOOP_HOOK.exists():
        sys.stderr.write(f"[nsr] loop hook missing: {LOOP_HOOK}\n")
        return None
    try:
        return subprocess.run(
            [sys.executable, str(LOOP_HOOK)],
            input=raw,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("NSR_HOOK_TIMEOUT", "900")),
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        sys.stderr.write(f"[nsr] loop hook failed open: {exc}\n")
        return None


def main() -> int:
    host = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    raw = sys.stdin.read()
    payload = load_payload(raw)

    # MMS may register the same wrapper for compact/session events. NSR's new
    # engine is a Stop hook only, so non-Stop events must stay no-op/fail-open.
    if not is_stop_event(payload):
        return allow_event(host)

    cwd = cwd_from_payload(payload)
    active_by_env = os.environ.get("NSR_ENABLED") == "1"
    marker = marker_path(cwd)
    if not active_by_env and marker is None:
        return allow_stop()

    result = run_loop(raw)
    if result is None:
        return allow_stop()

    if result.stderr:
        sys.stderr.write(result.stderr)
    stdout = result.stdout.strip() or "{}"
    sys.stdout.write(stdout + "\n")

    try:
        decision = json.loads(stdout)
    except json.JSONDecodeError:
        decision = {}
    if marker is not None and decision == {}:
        marker.unlink(missing_ok=True)
        sys.stderr.write(f"[nsr] disabled after allow stop: {marker}\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
