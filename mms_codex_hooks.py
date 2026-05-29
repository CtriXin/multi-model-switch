"""Codex session hook payload builders."""

from __future__ import annotations

import json
import os
import shlex


def _launchers():
    import mms_launchers as _module

    return _module


def caveman_codex_activate_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-activate.js")
    if not os.path.isfile(script_path):
        return ""
    return (
        "CAVEMAN_HOOK_COMPACT=1 "
        "CAVEMAN_HOOK_EVENT=SessionStart "
        'CLAUDE_CONFIG_DIR="$HOME/.codex" '
        f"node {json.dumps(script_path)}"
    )


def caveman_codex_hook_payload(caveman_root):
    command = _launchers()._caveman_codex_activate_command(caveman_root)
    if command:
        return {
            "type": "command",
            "command": command,
            "timeout": 5,
            "statusMessage": "Loading caveman [CAVEMAN]",
        }
    hooks_path = os.path.join(caveman_root, ".codex", "hooks.json")
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        for group in ((payload.get("hooks") or {}).get("SessionStart") or []):
            if str(group.get("matcher") or "").strip() != "startup|resume":
                continue
            for hook in group.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command") or "").strip()
                if command:
                    return dict(hook)
    except Exception:
        pass
    context = (
        "CAVEMAN MODE ACTIVE (lite). No filler/hedging. Keep full sentences. "
        "Code/commits/security: write normal. Off: stop caveman/normal mode."
    )
    payload = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "type": "command",
        "command": f"printf '%s' {shlex.quote(payload)}",
        "timeout": 5,
        "statusMessage": "Loading caveman mode",
    }


def codex_shell_hook_payload(command_text, *, timeout=None, status_message=None):
    command_text = str(command_text or "").strip()
    if not command_text:
        return {}
    payload = {"type": "command", "command": command_text}
    if timeout is not None:
        payload["timeout"] = timeout
    if status_message:
        payload["statusMessage"] = str(status_message)
    return payload


def codex_caveman_session_hook(caveman_root):
    hook_payload = _launchers()._caveman_codex_hook_payload(caveman_root)
    return _launchers()._codex_shell_hook_payload(
        hook_payload.get("command"),
        timeout=hook_payload.get("timeout"),
        status_message=hook_payload.get("statusMessage"),
    )


def configure_codex_caveman_hooks(hooks_data, *, enable_caveman=False):
    hooks_data = _launchers()._filter_hook_commands(hooks_data, _launchers()._is_loop_family_hook_command)
    hooks_data = _launchers()._filter_hook_commands(hooks_data, _launchers()._is_codex_rtk_hook_command)
    if not enable_caveman:
        return _launchers()._filter_hook_commands(hooks_data, _launchers()._is_caveman_hook_command)

    caveman_root = _launchers()._resolve_caveman_root()
    replacement = _launchers()._codex_caveman_session_hook(caveman_root) if caveman_root else {}
    replaced = False
    configured = {}

    for event_name, groups in (hooks_data if isinstance(hooks_data, dict) else {}).items():
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            hook_items = group.get("hooks")
            if not isinstance(hook_items, list):
                kept_groups.append(dict(group))
                continue
            kept_hooks = []
            for hook in hook_items:
                if not isinstance(hook, dict):
                    kept_hooks.append(hook)
                    continue
                command = str(hook.get("command") or "")
                if _launchers()._is_caveman_hook_command(command):
                    existing_compact = "CAVEMAN_HOOK_COMPACT=1" in command and str(event_name) == "SessionStart"
                    if not replaced and str(event_name) == "SessionStart" and (existing_compact or replacement):
                        # MMS session owns caveman activation. Do not preserve
                        # inherited/global caveman hooks, or SessionStart can
                        # emit duplicate caveman context in Codex.
                        kept_hooks.append(dict(replacement) if replacement else dict(hook))
                        replaced = True
                    continue
                kept_hooks.append(dict(hook))
            if kept_hooks:
                next_group = dict(group)
                next_group["hooks"] = kept_hooks
                kept_groups.append(next_group)
        if kept_groups:
            configured[event_name] = kept_groups

    if not replaced and replacement:
        configured = _launchers()._append_shell_command_hook(
            configured,
            "SessionStart",
            replacement.get("command"),
            matcher="startup|resume",
            timeout=replacement.get("timeout"),
            status_message=replacement.get("statusMessage"),
        )
    return configured


def configure_codex_nsr_hooks(hooks_data, *, enable_nsr=False):
    hooks_data = _launchers()._filter_hook_commands(hooks_data, _launchers()._is_loop_family_hook_command)
    if not enable_nsr or not _launchers()._nsr_available_for_cli("codex"):
        return hooks_data
    for event_name, matcher in (
        ("SessionStart", "startup|resume"),
        ("UserPromptSubmit", ""),
        ("PermissionRequest", "*"),
        ("PreToolUse", "*"),
        ("PostToolUse", "*"),
        ("PreCompact", ""),
        ("PostCompact", ""),
        ("Stop", ""),
    ):
        hooks_data = _launchers()._append_shell_command_hook(
            hooks_data,
            event_name,
            _launchers()._NSR_CODEX_HOOK,
            matcher=matcher,
            timeout=10,
            status_message="Loading NSR",
        )
    return hooks_data


def build_codex_session_hooks(base_hooks=None, *, enable_caveman=False, enable_nsr=False, disabled_session_surfaces=None):
    payload = dict(base_hooks) if isinstance(base_hooks, dict) else {}
    hooks_data = _launchers()._configure_codex_caveman_hooks(payload.get("hooks"), enable_caveman=enable_caveman)
    hooks_data = _launchers()._configure_codex_nsr_hooks(hooks_data, enable_nsr=enable_nsr)
    hooks_data = _launchers()._append_shell_command_hook(
        hooks_data,
        "SessionStart",
        _launchers()._XMEM_SESSION_START_HOOK,
        matcher="startup|resume",
        timeout=10,
        status_message="Syncing xmem",
    )
    hooks_data = _launchers()._append_shell_command_hook(
        hooks_data,
        "Stop",
        _launchers()._XMEM_SESSION_END_HOOK,
        matcher="",
        timeout=10,
        status_message="Closing xmem",
    )
    hooks_data = _launchers()._append_shell_command_hook(
        hooks_data,
        "UserPromptSubmit",
        _launchers()._XMEM_GATEWAY_HOOK,
        matcher="",
        timeout=10,
    )
    hooks_data = _launchers()._filter_hooks_by_disabled(hooks_data, disabled_session_surfaces)
    hooks_data = _launchers()._filter_missing_managed_hook_commands(hooks_data)
    if hooks_data:
        payload["hooks"] = hooks_data
    else:
        payload.pop("hooks", None)
    return payload
