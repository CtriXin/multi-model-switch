#!/usr/bin/env python3
"""Pre-push fresh-user regression gate for MMS.

This gate intentionally runs with MMS session/config environment variables
removed, then exercises the installed-user surfaces most likely to diverge
from a developer worktree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

_SCRUB_ENV_KEYS = {
    "MMS_CONFIG_ROOT",
    "MMS_CONFIG_DIR",
    "MMS_REAL_HOME",
    "REAL_HOME",
    "ORIGINAL_HOME",
    "XDG_CONFIG_HOME",
    "MMS_SESSION_HOME",
    "MMS_SOFT_HOME",
    "MMS_HOME_ISOLATION_MODE",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "ANTHROPIC_MODEL",
    "MMS_MODEL_NAME",
    "CLAUDE_CODE_SUBAGENT_MODEL",
}

_PY_COMPILE_TARGET_GROUPS = [
    ("mms",),
    ("mmf",),
    ("mms_core.py",),
    ("mms_launchers.py",),
    ("mms_session_index.py", "mms_session/index.py"),
    ("mms_state_io.py", "mms_runtime/state_io.py"),
    ("mms_config_web.py", "mms_config/web.py"),
]

_PYTEST_TARGETS = [
    "tests/test_claude_hardening_regressions.py",
    "tests/test_claude_isolation.py",
    "tests/test_mms_resume_command.py",
    "tests/test_install_script_paths.py",
    "tests/test_mms_installer_runtime.py",
    "tests/test_command_smoke.py",
]

_QUICK_PYTEST_TARGETS = [
    "tests/test_claude_hardening_regressions.py::test_claude_gateway_env_does_not_restore_project_scoped_resume_pointer_on_new_launch",
    "tests/test_claude_hardening_regressions.py::test_claude_gateway_env_does_not_restore_cross_model_resume_pointer_on_new_launch",
    "tests/test_mms_resume_command.py::test_handle_resume_command_passes_claude_resume_args_and_project",
    "tests/test_install_script_paths.py",
]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _SCRUB_ENV_KEYS:
        env.pop(key, None)
    env["PYTHONPATH"] = str(ROOT_DIR)
    return env


def _run(label: str, argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    print(f"[gate] {label}: {' '.join(argv)}", flush=True)
    completed = subprocess.run(
        argv,
        cwd=ROOT_DIR,
        env=env or _base_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed


def _pytest_command() -> list[str]:
    pytest_bin = shutil.which("pytest")
    if pytest_bin:
        return [pytest_bin]
    return [sys.executable, "-m", "pytest"]


def _py_compile_targets() -> list[str]:
    targets = []
    for candidates in _PY_COMPILE_TARGET_GROUPS:
        for candidate in candidates:
            if (ROOT_DIR / candidate).exists():
                targets.append(candidate)
                break
        else:
            raise SystemExit(f"missing py_compile target from candidates: {candidates!r}")
    return targets


def _smoke_fresh_mmf_config_root() -> None:
    with tempfile.TemporaryDirectory(prefix="mms-fresh-user-") as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        env = _base_env()
        env["HOME"] = str(home)
        completed = _run(
            "fresh mmf config root",
            [sys.executable, str(ROOT_DIR / "mmf"), "config", "root", "--json"],
            env=env,
        )
        payload = json.loads(completed.stdout)
        expected_root = str(home / ".config" / "mms-next")
        if payload.get("command") != "mmf":
            raise SystemExit(f"fresh mmf command mismatch: {payload!r}")
        if payload.get("mode") != "preview":
            raise SystemExit(f"fresh mmf mode mismatch: {payload!r}")
        if payload.get("config_root") != expected_root:
            raise SystemExit(f"fresh mmf root mismatch: {payload.get('config_root')} != {expected_root}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pre-push fresh-user MMS regression gate.")
    parser.add_argument("--quick", action="store_true", help="Run the smaller gate used during tight iteration.")
    args = parser.parse_args()

    _run("py_compile", [sys.executable, "-m", "py_compile", *_py_compile_targets()])
    _smoke_fresh_mmf_config_root()

    pytest_targets = _QUICK_PYTEST_TARGETS if args.quick else _PYTEST_TARGETS
    _run("pytest", [*_pytest_command(), "-q", *pytest_targets])
    print("[gate] fresh-user regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
