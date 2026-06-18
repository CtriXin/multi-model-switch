#!/usr/bin/env python3
"""Pre-push fresh-user regression gate for MMS.

This gate intentionally runs with MMS session/config environment variables
removed, then exercises the installed-user surfaces most likely to diverge
from a developer worktree.

Each fixed production regression should either add a scenario here or add a
pytest target that is reachable from this gate. The point is to test complete
user-visible flows across install states, not only isolated helper functions.
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
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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

_PY_COMPILE_TARGETS = [
    "mms",
    "mmf",
    "mms_core.py",
    "mms_launchers.py",
    "mms_session_index.py",
    "mms_state_io.py",
    "mms_config_web.py",
]

_PYTEST_TARGETS = [
    "tests/test_claude_hardening_regressions.py",
    "tests/test_claude_isolation.py",
    "tests/test_codex_history_growth.py",
    "tests/test_codex_hook_trust_contract.py",
    "tests/test_cleanup_dirty_install.py",
    "tests/test_confirm_preview.py",
    "tests/test_mms_resume_command.py",
    "tests/test_reset_mms_install.py",
    "tests/test_install_script_paths.py",
    "tests/test_nsr_bundled_wrapper.py",
    "tests/test_mms_installer_runtime.py",
    "tests/test_command_smoke.py",
]

_QUICK_PYTEST_TARGETS = [
    "tests/test_claude_hardening_regressions.py::test_build_claude_session_settings_respects_session_nsr_toggle",
    "tests/test_claude_hardening_regressions.py::test_build_codex_session_hooks_respects_session_nsr_toggle",
    "tests/test_claude_hardening_regressions.py::test_claude_gateway_env_does_not_restore_project_scoped_resume_pointer_on_new_launch",
    "tests/test_claude_hardening_regressions.py::test_claude_gateway_env_does_not_restore_cross_model_resume_pointer_on_new_launch",
    "tests/test_mms_resume_command.py::test_handle_resume_command_passes_claude_resume_args_and_project",
    "tests/test_install_script_paths.py",
    "tests/test_nsr_bundled_wrapper.py",
]

_SCENARIO_MATRIX = [
    {
        "id": "fresh-mmf-preview-root",
        "state": "empty HOME, no MMS env",
        "coverage": "mmf uses ~/.config/mms-next under the fresh user home",
    },
    {
        "id": "legacy-dirty-install-cleanup",
        "state": "gateway session contains leaked .mms/.nvm/.local/bin and stale ccs",
        "coverage": "cleanup removes only MMS-owned leaked artifacts and preserves unrelated user CLI links",
    },
    {
        "id": "reset-reinstall-state",
        "state": "real HOME contains previous mms/mmf/mmc/ccs/mmslogs and shell rc marker",
        "coverage": "reset removes retired/owned MMS surfaces so reinstall starts clean",
    },
    {
        "id": "repeatable-install-dry-run",
        "state": "same fresh HOME, installer invoked twice",
        "coverage": "install plan is repeatable and does not write during --dry-run",
    },
    {
        "id": "nsr-low-noise-hooks",
        "state": "NSR enabled for Claude/Codex session hooks",
        "coverage": "NSR stays on Stop/compact hooks, bundled payload no-ops non-Stop events, and is absent from high-frequency tool hooks",
    },
    {
        "id": "resume-explicit-only",
        "state": "old Claude project pointers and explicit mms resume",
        "coverage": "new launch does not consume stale project resume, explicit resume still works",
    },
    {
        "id": "codex-hook-trust-and-history",
        "state": "isolated Codex gateway with inherited/global hook and bounded resume state",
        "coverage": "hook trust does not reprompt and bounded resume/history is preserved safely",
    },
]


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _SCRUB_ENV_KEYS:
        env.pop(key, None)
    env["PYTHONPATH"] = str(ROOT_DIR)
    return env


def _env_for_home(home: Path) -> dict[str, str]:
    env = _base_env()
    env["HOME"] = str(home)
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


def _smoke_fresh_mmf_config_root() -> None:
    with tempfile.TemporaryDirectory(prefix="mms-fresh-user-") as tmp:
        home = Path(tmp).resolve() / "home"
        home.mkdir()
        env = _env_for_home(home)
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


def _safe_symlink(target: Path | str, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.unlink()
    except FileNotFoundError:
        pass
    link.symlink_to(target)


def _smoke_legacy_install_state_matrix() -> None:
    with tempfile.TemporaryDirectory(prefix="mms-install-state-") as tmp:
        home = Path(tmp).resolve() / "home"
        bin_dir = home / ".local" / "bin"
        session_home = home / ".config" / "mms" / "codex-gateway" / "s" / "12345"
        leaked_bin = session_home / ".mms" / "bin"
        leaked_bin.mkdir(parents=True)
        (session_home / ".nvm").mkdir(parents=True)
        (session_home / ".config" / "mms").mkdir(parents=True)
        (session_home / ".local" / "bin").mkdir(parents=True)
        _safe_symlink(leaked_bin / "mms", session_home / ".local" / "bin" / "mms")
        _safe_symlink(leaked_bin / "mmf", session_home / ".local" / "bin" / "mmf")
        _safe_symlink(leaked_bin / "mmc", session_home / ".local" / "bin" / "mmc")
        _safe_symlink(leaked_bin / "ccs", session_home / ".local" / "bin" / "ccs")
        _safe_symlink(leaked_bin / "mms", bin_dir / "mms")
        _safe_symlink(leaked_bin / "ccs", bin_dir / "ccs")
        _safe_symlink("/usr/bin/true", bin_dir / "claude")

        env = _env_for_home(home)
        _run(
            "cleanup dirty gateway install",
            ["bash", str(ROOT_DIR / "scripts" / "cleanup_dirty_install.sh"), "--apply", "--home", str(session_home)],
            env=env,
        )
        for path in (
            session_home / ".mms",
            session_home / ".nvm",
            session_home / ".config" / "mms",
            session_home / ".local" / "bin" / "mms",
            bin_dir / "mms",
            bin_dir / "ccs",
        ):
            if path.exists() or path.is_symlink():
                raise SystemExit(f"dirty cleanup left MMS-owned artifact: {path}")
        if not (bin_dir / "claude").is_symlink():
            raise SystemExit("dirty cleanup removed unrelated user claude link")

        mms_home = home / ".mms"
        mms_home.mkdir(parents=True)
        for name in ("mms", "mmf", "mmc", "ccs", "mmslogs"):
            (mms_home / name).write_text("#!/bin/sh\n", encoding="utf-8")
            _safe_symlink(mms_home / name, bin_dir / name)
        _safe_symlink("/usr/bin/true", bin_dir / "codex")
        zshrc = home / ".zshrc"
        zshrc.write_text(
            'export PATH="/opt/homebrew/bin:$PATH"\n'
            "# Added by MMS\n"
            'export PATH="$HOME/.local/bin:$PATH"\n'
            "alias ll='ls -la'\n",
            encoding="utf-8",
        )

        _run(
            "reset previous install before reinstall",
            [
                "bash",
                str(ROOT_DIR / "scripts" / "reset_mms_install.sh"),
                "--apply",
                "--include-shell-rc",
                "--home",
                str(home),
            ],
            env=env,
        )
        for path in (
            mms_home,
            home / ".config" / "mms",
            bin_dir / "mms",
            bin_dir / "mmf",
            bin_dir / "mmc",
            bin_dir / "ccs",
            bin_dir / "mmslogs",
        ):
            if path.exists() or path.is_symlink():
                raise SystemExit(f"reset left MMS-owned artifact: {path}")
        if not (bin_dir / "codex").is_symlink():
            raise SystemExit("reset removed unrelated user codex link")
        rc_text = zshrc.read_text(encoding="utf-8")
        if "# Added by MMS" in rc_text or 'export PATH="$HOME/.local/bin:$PATH"' in rc_text:
            raise SystemExit("reset did not remove the MMS shell rc marker block")
        if "alias ll='ls -la'" not in rc_text:
            raise SystemExit("reset removed unrelated shell rc content")


def _smoke_repeatable_install_dry_run() -> None:
    with tempfile.TemporaryDirectory(prefix="mms-install-dry-run-") as tmp:
        home = Path(tmp).resolve() / "home"
        home.mkdir()
        env = _env_for_home(home)
        for attempt in (1, 2):
            completed = _run(
                f"install dry-run attempt {attempt}",
                ["bash", str(ROOT_DIR / "install.sh"), "--dry-run", "--lang", "en"],
                env=env,
            )
            if "DRY RUN" not in completed.stdout or "dry-run complete" not in completed.stdout:
                raise SystemExit("install dry-run did not report dry-run completion")
            if str(home / ".mms") not in completed.stdout:
                raise SystemExit("install dry-run did not plan against the simulated HOME")
            if (home / ".mms").exists() or (home / ".config" / "mms").exists():
                raise SystemExit("install --dry-run wrote MMS files")


def _hook_commands(payload: dict, event_name: str) -> list[str]:
    hooks = payload.get("hooks") if isinstance(payload.get("hooks"), dict) else {}
    commands: list[str] = []
    for group in hooks.get(event_name, []) or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("hooks", []) or []:
            if isinstance(item, dict):
                commands.append(str(item.get("command") or ""))
    return commands


def _smoke_nsr_low_noise_hook_matrix() -> None:
    import mms_launchers

    payloads = {
        "claude": (mms_launchers._build_claude_session_settings({}, enable_nsr=True), mms_launchers._NSR_CLAUDE_HOOK),
        "codex": (mms_launchers._build_codex_session_hooks({}, enable_nsr=True), mms_launchers._NSR_CODEX_HOOK),
    }
    for cli, (payload, hook_path) in payloads.items():
        for event_name in ("PermissionRequest", "PreToolUse", "PostToolUse"):
            if hook_path in _hook_commands(payload, event_name):
                raise SystemExit(f"{cli} NSR still attached to noisy {event_name} hook")
        for event_name in ("PreCompact", "PostCompact", "Stop"):
            if hook_path not in _hook_commands(payload, event_name):
                raise SystemExit(f"{cli} NSR missing required {event_name} hook")


def _print_scenarios() -> None:
    print("[gate] scenario matrix:")
    for item in _SCENARIO_MATRIX:
        print(f"[gate]   - {item['id']}: {item['coverage']} ({item['state']})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pre-push fresh-user MMS regression gate.")
    parser.add_argument("--quick", action="store_true", help="Run the smaller gate used during tight iteration.")
    parser.add_argument("--list-scenarios", action="store_true", help="Print the scenario matrix and exit.")
    args = parser.parse_args()

    if args.list_scenarios:
        _print_scenarios()
        return 0

    _print_scenarios()
    _run("py_compile", [sys.executable, "-m", "py_compile", *_PY_COMPILE_TARGETS])
    _smoke_fresh_mmf_config_root()
    _smoke_legacy_install_state_matrix()
    _smoke_repeatable_install_dry_run()
    _smoke_nsr_low_noise_hook_matrix()

    pytest_targets = _QUICK_PYTEST_TARGETS if args.quick else _PYTEST_TARGETS
    _run("pytest", [*_pytest_command(), "-q", *pytest_targets])
    print("[gate] fresh-user regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
