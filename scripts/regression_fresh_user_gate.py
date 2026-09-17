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
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
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
    "tests/test_mms_release_version.py",
    "tests/test_mms_web_context_evidence.py",
    "tests/test_mms_web_recipe_contract.py",
    "tests/test_mms_web_updates.py",
    "tests/test_mms_web_update_safety.py",
    "tests/test_mms_web_update_coordinator.py",
    "tests/test_mms_web_update_transaction.py",
    "tests/test_mms_web_install_lock.py",
    "tests/test_mms_web_starter_skills.py",
    "tests/test_mms_web_local_files.py",
    "tests/test_mms_web_workspace_search.py",
    "tests/test_mms_web_model_settings.py",
    "tests/test_mms_web_merge_regressions.py",
    "tests/test_mms_channel_switch_contract.py",
    "tests/test_mms_session_owner_forward_compat.py",
    "tests/test_pi_vision_relay.py",
    "tests/test_mms_web_project_materials.py",
    "tests/test_mms_web_context_flow.py",
    "tests/test_mms_web_artifact_history.py",
    "tests/test_mms_web_artifact_flow.py",
    "tests/test_mms_web_standalone_settings.py",
    "tests/test_web_config_root_adoption.py",
    "tests/test_claude_hardening_regressions.py",
    "tests/test_claude_isolation.py",
    "tests/test_codex_history_growth.py",
    "tests/test_codex_hook_trust_contract.py",
    "tests/test_cleanup_dirty_install.py",
    "tests/test_confirm_preview.py",
    "tests/test_mms_resume_command.py",
    "tests/test_reset_mms_install.py",
    "tests/test_install_script_paths.py",
    "tests/test_npx_installer_package.py",
    "tests/test_nsr_bundled_wrapper.py",
    "tests/test_hook_retirement.py",
    "tests/test_owned_superset_hook.py",
    "tests/test_pi_launcher.py",
    "tests/test_mms_installer_runtime.py",
    "tests/test_command_smoke.py",
]

_QUICK_PYTEST_TARGETS = [
    "tests/test_mms_web_starter_skills.py",
    "tests/test_claude_hardening_regressions.py::test_build_claude_session_settings_respects_session_nsr_toggle",
    "tests/test_claude_hardening_regressions.py::test_build_codex_session_hooks_respects_session_nsr_toggle",
    "tests/test_claude_hardening_regressions.py::test_claude_gateway_env_does_not_restore_project_scoped_resume_pointer_on_new_launch",
    "tests/test_claude_hardening_regressions.py::test_claude_gateway_env_does_not_restore_cross_model_resume_pointer_on_new_launch",
    "tests/test_mms_resume_command.py::test_handle_resume_command_passes_claude_resume_args_and_project",
    "tests/test_install_script_paths.py",
    "tests/test_npx_installer_package.py",
    "tests/test_nsr_bundled_wrapper.py",
    "tests/test_hook_retirement.py",
    "tests/test_owned_superset_hook.py",
    "tests/test_pi_launcher.py::test_glint_pi_bridge_requires_glint_pane_and_managed_extension",
    "tests/test_pi_launcher.py::test_launch_pi_adds_glint_bridge_as_explicit_extension",
    "tests/test_pi_launcher.py::test_pi_isolated_gateway_loads_global_policy_and_project_context",
    "tests/test_pi_launcher.py::test_pi_policy_missing_is_optional_and_global_override_wins",
    "tests/test_pi_launcher.py::test_pi_policy_copy_fails_explicitly_and_cannot_target_global",
]

_SCENARIO_MATRIX = [
    {
        "id": "pi-isolated-global-policy",
        "state": "fresh isolated Pi agentDir, host AGENTS policy, project outside real HOME",
        "coverage": "native Pi context loader receives global policy plus project context; auth is not inherited and session edits do not write home",
    },
    {
        "id": "fresh-mmf-preview-root",
        "state": "empty HOME, no MMS env",
        "coverage": "mmf uses ~/.config/mms-next under the fresh user home",
    },
    {
        "id": "shared-config-root-default",
        "state": "empty HOME with no MMS env; a channel pinned to the legacy root; a fresh Pilot state root",
        "coverage": "mms defaults to the same ~/.config/mms-next root as mmf, a pinned channel stays on the legacy root in stable mode, and Pilot shares the default root "
                    "(adoption of an existing Web-owned config is covered by tests/test_web_config_root_adoption.py)",
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
        "id": "retired-automatic-hooks",
        "state": "old NSR toggles/markers and managed NSR/Map/CodeGraph registrations",
        "coverage": "automatic wrappers no-op without reading stdin/state; managed merge does not revive them; explicit tools remain available",
    },
    {
        "id": "resume-explicit-only",
        "state": "old Claude project pointers and explicit mms resume",
        "coverage": "new launch does not consume stale project resume, explicit resume still works",
    },
    {
        "id": "retired-optional-pack-cleanup",
        "state": "upgrade from a version that installed RTK/BrainKeeper/Map/CodeGraph/token-saver/TOON/ops-env-safe/ECC/OMC",
        "coverage": "install unbinds every MMS-written leftover, preserves user-owned lookalikes, backs up Claude settings, and uninstalls no third-party binary",
    },
    {
        "id": "retired-builtin-commands",
        "state": "a machine where an older version wrote offduty/onduty/handover and /nsr into all five agent homes",
        "coverage": "a new install writes none of them and takes back the 20 entries MMS wrote, while same-named user files and foreign symlinks survive",
    },
    {
        "id": "npx-install-entry",
        "state": "a machine with Node.js invokes the npm installer",
        "coverage": "stable release resolution, parameter precedence, matching script/source refs, pinned downloads and temporary cleanup on success/failure",
    },
    {
        "id": "install-entry-parity",
        "state": "the same install reached by curl and by the npm wrapper, which pins --ref to the release it resolved",
        "coverage": "both print the same one-line headline; a genuinely pinned older ref or a dev/canary channel still prints the full version overview",
    },
    {
        "id": "one-question-install",
        "state": "installer run with no arguments, with and without a terminal",
        "coverage": "nothing that changes the install is asked; stable channel and shell PATH are the defaults; the only question offers to open MMS Web, which starts detached with a real config root, falls back off a taken port, reuses a running instance, and is skipped without a terminal",
    },
    {
        "id": "pi-btw-bundled-extension",
        "state": "fresh HOME with no MMS env; a bundled Pi /btw extension, then a pi-btw in the real home, in the project, in the session's own agent dir, then pi_btw = false",
        "coverage": "MMS injects its own /btw bundle into every Pi it starts, stays out of the way only when the session really loads another pi-btw (project settings, or an agent tree it is pointed at), keeps injecting past an isolated-away global one, and honours the preference",
    },
    {
        "id": "codex-hook-trust-and-history",
        "state": "isolated Codex gateway with inherited/global hook and bounded resume state",
        "coverage": "hook trust does not reprompt and bounded resume/history is preserved safely",
    },
    {
        "id": "fresh-root-launch-never-reaches-capability-fail-closed",
        "state": "empty HOME, fresh ~/.config/mms-next, no published bundle",
        "coverage": "a bare launch stops at the v2 guidance instead of reaching the opencode capability fail-closed path, so a fresh install without a bundle cannot crash the launcher with CapabilityBundleError",
    },
    {
        "id": "channel-switch-round-trip",
        "state": "one shared state root: the newer line writes a bot, a schedule, bot memory, bot-owned sessions and its update/ui caches; the 4.x line then boots on it; the newer line reads it back",
        "coverage": "downgrade boots clean (bootstrap 200, no 5xx, no traceback), every bots/ file is untouched byte-for-byte and by mtime, sessions whose owner this line does not know stay out of the list and refuse detail by id while plain web sessions are unaffected, and the upgrade back still finds bot, schedule and memory at schema 2 with no load error; recorded known costs: whatsNewSeenVersion keeps the newer line's version so this line's release notes stay hidden, and the cached update tag still points at the newer line so the update status offers it again",
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


def _smoke_shared_config_root_default() -> None:
    """One root serves both entrances, and a pinned channel still opts out."""
    with tempfile.TemporaryDirectory(prefix="mms-shared-root-") as tmp:
        home = Path(tmp).resolve() / "home"
        home.mkdir()
        shared_root = home / ".config" / "mms-next"
        legacy_root = home / ".config" / "mms"

        completed = _run(
            "fresh mms config root",
            [sys.executable, str(ROOT_DIR / "mms"), "config", "root", "--json"],
            env=_env_for_home(home),
        )
        payload = json.loads(completed.stdout)
        if payload.get("config_root") != str(shared_root):
            raise SystemExit(f"fresh mms root mismatch: {payload.get('config_root')} != {shared_root}")
        if payload.get("mode") != "preview":
            raise SystemExit(f"fresh mms mode mismatch: {payload!r}")

        # A stale shell export or the retired mmd/mmm wrapper env pointing at
        # the legacy root must not drag a process back there: the pin is
        # redirected to the shared root and the mode stays preview.
        pinned_env = _env_for_home(home)
        pinned_env["MMS_CONFIG_ROOT"] = str(legacy_root)
        pinned_env["MMS_CONFIG_ROOT_MODE"] = "stable"
        completed = _run(
            "retired legacy stable pin",
            [sys.executable, str(ROOT_DIR / "mms"), "config", "root", "--json"],
            env=pinned_env,
        )
        payload = json.loads(completed.stdout)
        if payload.get("config_root") != str(shared_root):
            raise SystemExit(f"legacy pin not redirected: {payload.get('config_root')} != {shared_root}")
        if payload.get("mode") != "preview":
            raise SystemExit(f"legacy stable pin still honoured: {payload!r}")

        probe = (
            "import json,sys;"
            "from pathlib import Path;"
            "from mms_web.runtime import default_config_root;"
            "print(json.dumps({'fresh': str(default_config_root(Path(sys.argv[1])))}))"
        )
        fresh_state = home / ".local" / "share" / "mms-web"
        completed = _run(
            "pilot default config root",
            [sys.executable, "-c", probe, str(fresh_state)],
            env=_env_for_home(home),
        )
        roots = json.loads(completed.stdout)
        if roots.get("fresh") != str(shared_root):
            raise SystemExit(f"pilot fresh root mismatch: {roots.get('fresh')} != {shared_root}")


def _smoke_fresh_root_launch_stops_at_guidance() -> None:
    """A bundle-less fresh root must exit with guidance, not a crash.

    T8c phase-2 ruling 2: the opencode capability resolver fails closed when
    the latest-approved bundle is missing. This scenario proves the real launch
    path never reaches that state — runtime config only exists once a bundle
    is published, so a bare launch on a fresh root stops at the v2 guidance.
    """
    with tempfile.TemporaryDirectory(prefix="mms-fresh-launch-") as tmp:
        home = Path(tmp).resolve() / "home"
        home.mkdir()
        completed = subprocess.run(
            [sys.executable, str(ROOT_DIR / "mms")],
            cwd=ROOT_DIR,
            env=_env_for_home(home),
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )
        output = completed.stdout + completed.stderr
        print(output, end="")
        if completed.returncode != 2:
            raise SystemExit(f"fresh launch exit code mismatch: {completed.returncode} != 2")
        if "Preview root uses v2 DB truth" not in output:
            raise SystemExit("fresh launch did not print the v2 guidance")
        if "CapabilityBundleError" in output or "Traceback" in output:
            raise SystemExit("fresh launch crashed instead of stopping at the guidance")


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
        for event_name in ("PermissionRequest", "PreToolUse", "PostToolUse", "PreCompact", "PostCompact", "Stop"):
            if hook_path in _hook_commands(payload, event_name):
                raise SystemExit(f"{cli} NSR still attached to noisy {event_name} hook")


_PI_BTW_PROBE = """
import json, os, sys
from pathlib import Path

import mms_pi_support

logs = []
cwd = sys.argv[1]


def resolve(runtime=None, env=None):
    return mms_pi_support.pi_btw_extension_path(env or {}, runtime, cwd, log=logs.append)


def record(expect_btw, label, env=None, expect_log=None):
    path = resolve(env=env)
    injected = bool(path)
    print(json.dumps({"label": label, "injected": injected, "expected": expect_btw,
                      "logs": list(logs)}))
    seen = list(logs)
    logs.clear()
    if injected != expect_btw:
        raise SystemExit(f"{label}: injected={injected}, expected={expect_btw}")
    if path and Path(path).name != "index.ts":
        raise SystemExit(f"{label}: unexpected extension path {path}")
    if expect_log and not any(expect_log in line for line in seen):
        raise SystemExit(f"{label}: no log line mentioning {expect_log}: {seen!r}")


record(True, "clean fresh home")

agent_dir = Path.home() / ".pi" / "agent"
settings = agent_dir / "settings.json"
settings.parent.mkdir(parents=True, exist_ok=True)
settings.write_text(json.dumps({"packages": ["npm:pi-usage-hub", "npm:@narumitw/pi-btw@0.58.1"]}),
                    encoding="utf-8")
# MMS gives the session its own PI_CODING_AGENT_DIR, so this copy is never
# loaded: skipping here would leave the session with no /btw at all.
record(True, "upstream pi-btw in the real home, session isolated",
       expect_log="PI_CODING_AGENT_DIR")
# ... and the one case where that same file really is loaded.
record(False, "session pointed at the agent tree that carries pi-btw",
       env={"PI_CODING_AGENT_DIR": str(agent_dir)}, expect_log="\u4e0d\u91cd\u590d\u6ce8\u5165")
saved = json.loads(settings.read_text(encoding="utf-8"))
if saved["packages"][0] != "npm:pi-usage-hub":
    raise SystemExit("the read-only check rewrote the user's Pi settings")
settings.unlink()

project = Path(cwd) / ".pi" / "settings.json"
project.parent.mkdir(parents=True, exist_ok=True)
project.write_text(json.dumps({"packages": [{"source": "git:github.com/CtriXin/pi-btw@v0.59.0-fork.1"}]}),
                   encoding="utf-8")
record(False, "fork installed by the project", expect_log="\u4e0d\u91cd\u590d\u6ce8\u5165")
project.unlink()

record(True, "both installs removed")

preferences = Path.home() / ".config" / "mms-next" / "preferences.toml"
preferences.parent.mkdir(parents=True, exist_ok=True)
preferences.write_text("[launch.cli.pi]" + chr(10) + "pi_btw = false" + chr(10), encoding="utf-8")
if resolve():
    raise SystemExit("pi_btw = false did not reach the launcher")
if not any("pi_btw" in line for line in logs):
    raise SystemExit("a disabled preference logged nothing: " + repr(logs))
logs.clear()
preferences.write_text("[launch.cli.pi]" + chr(10) + "pi_btw = true" + chr(10), encoding="utf-8")
if not resolve():
    raise SystemExit("pi_btw = true should inject the bundled extension")
if resolve(runtime={"pi_btw": False}):
    raise SystemExit("the launch overlay must win over the preferences default")
logs.clear()
preferences.unlink()
"""


def _smoke_pi_btw_bundled_extension() -> None:
    """Every Pi MMS starts carries /btw, and MMS steps aside when it is already there."""
    _run("pi-btw bundle check", [sys.executable, str(ROOT_DIR / "scripts" / "sync_pi_btw.py"), "--check"])
    with tempfile.TemporaryDirectory(prefix="mms-pi-btw-") as tmp:
        home = Path(tmp).resolve() / "home"
        project = Path(tmp).resolve() / "project"
        home.mkdir()
        project.mkdir()
        _run(
            "pi-btw injection matrix",
            [sys.executable, "-c", _PI_BTW_PROBE, str(project)],
            env=_env_for_home(home),
        )


# -- channel switch ---------------------------------------------------------
#
# The owner-defined release model is two install lines over one shared state
# root: the 4.x stable line (no Bot workspace) and the newer line that has
# one. Users can move both ways, so each line must tolerate state written by
# the other. This scenario drives the round trip for real: the peer line is
# extracted from the local git refs and its own code writes the state root,
# then this checkout boots a real server on it.

_CHANNEL_SWITCH_WRITE_PROBE = """
import json, sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])  # the newer line's tree; cwd would win otherwise
state_root = Path(sys.argv[2])
from mms_version import VERSION
from mms_web.bots import BotRuntime
from mms_web.bot_memory import BotMemoryStore
from mms_web.ui_preferences import UiPreferences


class _Executor:
    def available(self):
        return True

    def validate(self, bot):
        return {}


runtime = BotRuntime(state_root=state_root, executor=_Executor())
bot = runtime.create_bot({"name": "Gate Bot", "description": "channel switch gate",
                          "systemPrompt": "keep the gate honest"})
task = runtime.create_task({"botId": bot["id"], "prompt": "ping the gate",
                            "runAt": "2099-01-01T00:00:00+00:00"})
BotMemoryStore(state_root).remember(bot["id"], "the gate bot likes regression tests")
UiPreferences(state_root).read(seed_version=VERSION)
print(json.dumps({"version": VERSION, "botId": bot["id"], "taskId": task["id"],
                  "runAt": task["runAt"], "loadError": runtime._load_error}))
"""

_CHANNEL_SWITCH_VERIFY_PROBE = """
import json, sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])  # the newer line's tree; cwd would win otherwise
state_root = Path(sys.argv[2])
expected = json.loads(sys.argv[3])
from mms_web.bots import BotRuntime
from mms_web.bot_memory import BotMemoryStore


class _Executor:
    def available(self):
        return True

    def validate(self, bot):
        return {}


raw = json.loads((state_root / "bots" / "state.json").read_text())
if raw.get("schema") != 2:
    raise SystemExit(f"bot store schema drifted: {raw.get('schema')!r}")
runtime = BotRuntime(state_root=state_root, executor=_Executor())
if runtime._load_error:
    raise SystemExit(f"bot store no longer loads after the round trip: {runtime._load_error}")
bots = {bot["id"]: bot for bot in runtime.list_bots()}
if expected["botId"] not in bots:
    raise SystemExit(f"bot missing after the round trip: {sorted(bots)}")
tasks = runtime.list_tasks(bot_id=expected["botId"])
if not any(task["id"] == expected["taskId"] and task.get("runAt") for task in tasks):
    raise SystemExit("scheduled task lost across the round trip")
notes = json.dumps(BotMemoryStore(state_root).get(expected["botId"]), ensure_ascii=False)
if "regression" not in notes:
    raise SystemExit("bot memory note lost across the round trip")
print(json.dumps({"bots": len(bots), "tasks": len(tasks), "schema": raw["schema"]}))
"""


def _version_of(tree: Path) -> str:
    text = (tree / "mms_version.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("VERSION = "):
            return line.split('"')[1]
    raise SystemExit(f"cannot read VERSION from {tree}")


def _extract_peer_line(dest: Path) -> Path:
    """Materialize the other install line's code from local git refs."""
    current_major = int(_version_of(ROOT_DIR).split(".")[0])
    ref = "origin/dev" if current_major <= 4 else "origin/main"
    archive = subprocess.run(
        ["git", "-C", str(ROOT_DIR), "archive", "--format=tar", ref],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise SystemExit(f"cannot extract peer line {ref}: {archive.stderr.decode(errors='replace')}")
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        # Source files only: the repo carries symlinks that point outside the
        # destination, and this gate never needs them.
        tar.extractall(dest, filter=lambda member, _path: member if (member.isdir() or member.isreg()) else None)
    peer_major = int(_version_of(dest).split(".")[0])
    if peer_major == current_major:
        raise SystemExit(
            f"peer ref {ref} is also {current_major}.x; the two install lines are not where this gate expects them"
        )
    return dest


def _write_session_file(state_root: Path, session_id: str, **meta_extra) -> None:
    sessions_dir = state_root / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": session_id,
        "title": f"title-{session_id}",
        "workspaceId": "ws-1",
        "harness": "pi",
        "modelName": "fake-model",
        "providerName": "fake-provider",
        "channel": "default",
        "createdAt": "2026-09-16T00:00:00+00:00",
        "updatedAt": "2026-09-16T00:00:00+00:00",
    }
    meta.update(meta_extra)
    (sessions_dir / f"{session_id}.json").write_text(
        json.dumps({"schema": 1, "session": meta, "state": "idle", "events": []}),
        encoding="utf-8",
    )


def _snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _http_json(port: int, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, OSError):
        return 0, {}


def _smoke_channel_switch_round_trip() -> None:
    """Newer line writes the state root; the 4.x line boots on it; the newer line reads it back."""
    current_version = _version_of(ROOT_DIR)
    with tempfile.TemporaryDirectory(prefix="mms-channel-switch-") as tmp:
        base = Path(tmp).resolve()
        home = base / "home"
        home.mkdir()
        peer_tree = _extract_peer_line(base / "peer")
        peer_version = _version_of(peer_tree)
        # The 4.x stable line has no Bot workspace; the newer line writes it.
        # This gate flows into the newer line unchanged, so either side of the
        # checkout must drive the same round trip.
        if int(current_version.split(".")[0]) <= 4:
            stable_tree, newer_tree, newer_version = ROOT_DIR, peer_tree, peer_version
        else:
            stable_tree, newer_tree, newer_version = peer_tree, ROOT_DIR, current_version
        print(f"[gate] channel switch: stable line {_version_of(stable_tree)}, newer line {newer_version}", flush=True)
        newer_env = _env_for_home(home)
        newer_env["PYTHONPATH"] = str(newer_tree)

        state_root = base / "state"
        config_root = base / "config"
        config_root.mkdir()
        static_root = base / "static"
        static_root.mkdir()
        (static_root / "index.html").write_text("<h1>MMS</h1>", encoding="utf-8")

        # Upgrade: the peer line's own code writes its records into the shared
        # state root (bot, one scheduled task, one memory note, ui flags).
        completed = _run(
            "newer line writes its state",
            [sys.executable, "-c", _CHANNEL_SWITCH_WRITE_PROBE, str(newer_tree), str(state_root)],
            env=newer_env,
        )
        written = json.loads(completed.stdout.strip().splitlines()[-1])
        if written.get("loadError"):
            raise SystemExit(f"newer line could not write its own store: {written}")

        # The peer line also owns sessions in the shared sessions/ directory:
        # one marked with the owner this line does not know, one plain chat.
        _write_session_file(state_root, "sess-foreign-1", owner="bot", botId=written["botId"])
        _write_session_file(state_root, "sess-web-1")
        # ... and its update check cache still points at the newer line's tag.
        updates_dir = state_root / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        newer_tag = f"v{newer_version}"
        (updates_dir / "check.json").write_text(
            json.dumps({"checkedAt": time.time(), "latest": {"tag": newer_tag, "notes": ""}, "error": ""}),
            encoding="utf-8",
        )
        bots_snapshot = _snapshot_tree(state_root / "bots")
        ui_prefs_before = (state_root / "ui-preferences.json").read_bytes()
        check_cache_before = (updates_dir / "check.json").read_bytes()

        # Downgrade: the 4.x line boots a real server on that state root.
        port = _free_port()
        server_env = _env_for_home(home)
        server_env["PYTHONPATH"] = str(stable_tree)
        # Keep the background release check off the network so the cached tag
        # stays exactly what the newer line left behind.
        server_env["MMS_WEB_UPDATE_CHECK"] = "0"
        output: list[str] = []
        process = subprocess.Popen(
            [
                sys.executable, "-m", "mms_web",
                "--port", str(port),
                "--state-root", str(state_root),
                "--config-root", str(config_root),
                "--static-root", str(static_root),
            ],
            cwd=stable_tree,
            env=server_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        collector = threading.Thread(target=lambda: output.extend(process.stdout), daemon=True)
        collector.start()
        try:
            booted = False
            for _ in range(60):
                if process.poll() is not None:
                    break
                status, _payload = _http_json(port, "/api/v1/bootstrap")
                if status == 200:
                    booted = True
                    break
                time.sleep(0.5)
            if not booted:
                raise SystemExit(
                    "the 4.x line did not boot on the newer-written state root:\n" + "".join(output)
                )

            status, payload = _http_json(port, "/api/v1/sessions")
            if status != 200:
                raise SystemExit(f"session list failed after downgrade: {status}")
            listed = {row.get("id") for row in payload.get("sessions", [])}
            if "sess-foreign-1" in listed:
                raise SystemExit("a session owned by something this line does not know leaked into the list")
            if "sess-web-1" not in listed:
                raise SystemExit("a plain web session was hidden after downgrade")
            status, _payload = _http_json(port, "/api/v1/sessions/sess-foreign-1")
            if status != 404:
                raise SystemExit(f"foreign-owned session still opens by id: {status}")
            status, _payload = _http_json(port, "/api/v1/sessions/sess-web-1")
            if status != 200:
                raise SystemExit(f"plain web session no longer opens: {status}")

            # Known costs, asserted so a future fix turns them green instead of
            # silently changing: the newer line's version stays stamped as seen,
            # and the cached update tag still offers the newer line back.
            status, payload = _http_json(port, "/api/v1/ui-preferences")
            seen = str(payload.get("whatsNewSeenVersion") or "")
            if seen != newer_version:
                raise SystemExit(f"whatsNewSeenVersion after downgrade: {seen!r} != {newer_version!r}")
            print(f"[gate] known cost: this line's release notes stay hidden (seen={seen})", flush=True)
            status, payload = _http_json(port, "/api/v1/update")
            latest_tag = str((payload.get("latest") or {}).get("tag") or "")
            if latest_tag != newer_tag or not payload.get("updateAvailable"):
                raise SystemExit(
                    f"cached update tag after downgrade: {latest_tag!r}, available={payload.get('updateAvailable')}"
                )
            print(f"[gate] known cost: update status still offers the newer line ({latest_tag})", flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
            collector.join(timeout=5)
        transcript = "".join(output)
        if "Traceback" in transcript:
            raise SystemExit(f"server logged a traceback on the newer-written state root:\n{transcript}")

        # The other line's subtree must be exactly as it was left: the 4.x
        # line does not know it, so it must not touch it.
        after = _snapshot_tree(state_root / "bots")
        if after != bots_snapshot:
            changed = sorted(set(after) ^ set(bots_snapshot))
            changed += sorted(
                key for key in set(after) & set(bots_snapshot) if after[key] != bots_snapshot[key]
            )
            raise SystemExit(f"downgrade touched the peer line's files: {changed}")
        if (state_root / "ui-preferences.json").read_bytes() != ui_prefs_before:
            raise SystemExit("downgrade rewrote ui-preferences.json")
        if (updates_dir / "check.json").read_bytes() != check_cache_before:
            raise SystemExit("downgrade rewrote the cached update check")

        # Upgrade back: the newer line still finds everything it wrote.
        _run(
            "newer line reads its state back",
            [
                sys.executable, "-c", _CHANNEL_SWITCH_VERIFY_PROBE,
                str(newer_tree), str(state_root),
                json.dumps({"botId": written["botId"], "taskId": written["taskId"]}),
            ],
            env=newer_env,
        )



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
    _smoke_shared_config_root_default()
    _smoke_fresh_root_launch_stops_at_guidance()
    _smoke_legacy_install_state_matrix()
    _smoke_repeatable_install_dry_run()
    _smoke_pi_btw_bundled_extension()
    # The channel-switch round trip extracts the peer line and boots a real
    # server, so it stays in the full gate only; --quick skips it.
    if not args.quick:
        _smoke_channel_switch_round_trip()
    _smoke_nsr_low_noise_hook_matrix()

    pytest_targets = _QUICK_PYTEST_TARGETS if args.quick else _PYTEST_TARGETS
    _run("pytest", [*_pytest_command(), "-q", *pytest_targets])
    print("[gate] fresh-user regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
