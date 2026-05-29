"""Hook command classifiers shared by launcher and settings helpers."""

from __future__ import annotations

import os
import shlex


def _has_marker(command_text, markers):
    command_text = str(command_text or "").strip().lower()
    if not command_text:
        return False
    return any(marker in command_text for marker in markers)


def is_caveman_hook_command(command_text):
    markers = (
        "caveman-activate.js",
        "caveman-mode-tracker.js",
        "caveman mode active",
    )
    return _has_marker(command_text, markers)


def is_codex_rtk_hook_command(command_text):
    markers = (
        "codex-rtk-rewrite.sh",
        "rtk-rewrite.sh",
        "rtk rewrite",
    )
    return _has_marker(command_text, markers)


def is_ecc_hook_command(command_text):
    markers = (
        "plugin-hook-bootstrap.js",
        "run-with-flags.js",
        "run-with-flags-shell.sh",
        "session-start-bootstrap.js",
        "pre-bash-dispatcher.js",
        "post-bash-dispatcher.js",
        "quality-gate.js",
        "stop-format-typecheck.js",
        "continuous-learning-v2/hooks/observe.sh",
        "everything-claude-code",
    )
    return _has_marker(command_text, markers)


def is_omc_hook_command(command_text):
    markers = (
        "oh-my-claudecode",
        "keyword-detector.mjs",
        "skill-injector.mjs",
        "session-start.mjs",
        "project-memory-session.mjs",
        "wiki-session-start.mjs",
        "setup-init.mjs",
        "setup-maintenance.mjs",
        "pre-tool-enforcer.mjs",
        "permission-handler.mjs",
        "post-tool-verifier.mjs",
        "project-memory-posttool.mjs",
        "post-tool-rules-injector.mjs",
        "post-tool-use-failure.mjs",
        "subagent-tracker.mjs",
        "verify-deliverables.mjs",
        "project-memory-precompact.mjs",
        "wiki-pre-compact.mjs",
        "context-guard-stop.mjs",
        "persistent-mode.mjs",
        "code-simplifier.mjs",
        "session-end.mjs",
        "wiki-session-end.mjs",
    )
    return _has_marker(command_text, markers)


def is_mms_managed_hook_command(command_text):
    markers = (
        "claude-feishu-webfetch-guard.sh",
        "hive-compact-hook.sh",
        "brainkeeper-session-start-hook.sh",
        "brainkeeper-session-end-hook.sh",
        "brainkeeper-token-monitor-hook.sh",
        "mindkeeper-session-start-hook.sh",
        "mindkeeper-session-end-hook.sh",
        "mindkeeper-token-monitor-hook.sh",
        "claude-codegraph-auto-index.sh",
        "mms-resume-hint.sh",
        "xmem-session-start-hook.sh",
        "xmem-session-end-hook.sh",
        "xmem-gateway-hook.sh",
        "claude-map-auto-index.sh",
        "nsr-claude-hook.sh",
        "nsr-codex-hook.sh",
        "nsr-builtin-hook.py",
        "scmp_hook.py --host codex",
        "caveman-activate.js",
        "caveman-mode-tracker.js",
        "everything-claude-code",
        "oh-my-claudecode",
    )
    return _has_marker(command_text, markers)


def is_legacy_loop_hook_command(command_text):
    markers = (
        "looop",
        "bugloop",
        "nightly-fix",
        "nightly-debug",
    )
    return _has_marker(command_text, markers)


def is_nsr_hook_command(command_text):
    command_text = str(command_text or "").strip().lower()
    if not command_text:
        return False
    if any(
        marker in command_text
        for marker in (
            "nsr-claude-hook.sh",
            "nsr-codex-hook.sh",
            "nsr-builtin-hook.py",
            "non-stop-run",
            "looop.deprecated",
            "mms_nsr",
        )
    ):
        return True
    if (
        ("codex_hook.py" in command_text or "claude_hook.py" in command_text)
        and ("nsr" in command_text or "non-stop" in command_text or "looop" in command_text)
    ):
        return True
    return False


def is_loop_family_hook_command(command_text):
    import mms_launchers as _launchers

    return _launchers._is_legacy_loop_hook_command(command_text) or _launchers._is_nsr_hook_command(command_text)


def is_looop_hook_command(command_text):
    import mms_launchers as _launchers

    # Backward-compatible alias for older tests/callers.
    return _launchers._is_legacy_loop_hook_command(command_text)


def hook_command_targets_exist(command_text):
    command_text = str(command_text or "").strip()
    if not command_text:
        return True
    try:
        parts = shlex.split(command_text)
    except ValueError:
        parts = command_text.split()
    if not parts:
        return True

    candidates = []
    first = parts[0]
    if os.path.isabs(first):
        candidates.append(first)

    runner = os.path.basename(first)
    if runner in {"bash", "sh", "zsh", "node", "python", "python3"}:
        for token in parts[1:]:
            if token.startswith("-"):
                continue
            if os.path.isabs(token):
                candidates.append(token)
            break

    if not candidates:
        return True
    return all(os.path.exists(candidate) for candidate in candidates)


def mcp_command_has_path(command):
    command = str(command or "").strip()
    return bool(command and (os.path.isabs(command) or os.sep in command))
