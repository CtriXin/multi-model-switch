"""Config guard, snapshot, and JSON helper functions."""

from __future__ import annotations

import json
import os


def confirm_guard_accept_from_tui(
    cfg,
    *,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    confirm_startup_snapshot_drift,
    console,
):
    config_path = config_write_target_path()
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []
    if not diff_lines:
        console.print("[green]当前快照没有 drift，不需要 accept。[/green]")
        return False
    return confirm_startup_snapshot_drift(
        diff_lines,
        accepted_path=accepted_path,
        latest_path=latest_path,
    )


def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def save_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


def render_mms_config_agents_guard():
    return """# AGENTS.md

This folder stores the real MMS user config.

## MMS Config Human Gate

- Any agent, any repo, any automation touching this folder must stop and require human confirmation before write.
- Before every write, create a timestamped backup first. Never overwrite in place without a backup.
- Applies to the whole MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and any account state under this folder.
- Agents may inspect, diff, and propose changes, but must not auto-apply user config edits without human confirmation.
- Any proposed change must show target path, affected fields/files, before/after values, and reason.
- If the process is running inside an isolated HOME or gateway session, still resolve and protect the real user config under `~/.config/mms`.
"""


def render_mms_config_claude_guard():
    return """# CLAUDE.md

This folder stores the real MMS user config.

## Claude Hard Rule

- Claude must treat this folder as human-only config.
- Claude must never auto-write MMS user config without explicit human confirmation.
- Before every write, Claude must create a timestamped backup first.
- Claude may only inspect, explain, and generate manual diffs for changes to this folder until the human confirms.
- This applies to the full MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and account state files.
- If Claude is about to touch these files, it must stop and report the exact path, intended change, before/after values, and reason.
"""


def snapshot_diff_lines(previous_snapshot, current_snapshot, *, is_snapshot_ignored_file):
    diffs = []
    previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    current_snapshot = current_snapshot if isinstance(current_snapshot, dict) else {}

    previous_defaults = previous_snapshot.get("defaults") or {}
    current_defaults = current_snapshot.get("defaults") or {}
    if previous_defaults != current_defaults:
        diffs.append("default route/account changed")

    previous_accounts = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    current_accounts = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    for account_id in sorted(set(previous_accounts) | set(current_accounts)):
        previous_entry = previous_accounts.get(account_id)
        current_entry = current_accounts.get(account_id)
        if previous_entry is None:
            diffs.append(f"account added: {account_id}")
            continue
        if current_entry is None:
            diffs.append(f"account removed: {account_id}")
            continue
        field_labels = {
            "cli": "cli",
            "enabled": "enabled",
            "home_dir": "home_dir",
            "priority": "priority",
            "claude_1m_mode": "claude_1m_mode",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
            "identity_sha256": "identity",
        }
        for field_name, field_label in field_labels.items():
            if field_name == "identity_sha256":
                previous_value = previous_entry.get(field_name, "")
                current_value = current_entry.get(field_name, "")
            else:
                previous_value = previous_entry.get(field_name)
                current_value = current_entry.get(field_name)
            if field_name == "identity_sha256" and field_name not in previous_entry:
                continue
            if previous_value != current_value:
                if field_name == "proxy_sha256":
                    old_value = previous_entry.get("proxy_fingerprint")
                    new_value = current_entry.get("proxy_fingerprint")
                elif field_name == "identity_sha256":
                    old_value = previous_entry.get("identity_fingerprint")
                    new_value = current_entry.get("identity_fingerprint")
                else:
                    old_value = previous_entry.get(field_name)
                    new_value = current_entry.get(field_name)
                diffs.append(f"account {account_id} {field_label}: {old_value} -> {new_value}")

    previous_providers = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    current_providers = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    for provider_id in sorted(set(previous_providers) | set(current_providers)):
        previous_entry = previous_providers.get(provider_id)
        current_entry = current_providers.get(provider_id)
        if previous_entry is None:
            diffs.append(f"provider added: {provider_id}")
            continue
        if current_entry is None:
            diffs.append(f"provider removed: {provider_id}")
            continue
        field_labels = {
            "enabled": "enabled",
            "priority": "priority",
            "models_endpoint": "models_endpoint",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
        }
        for field_name, field_label in field_labels.items():
            if previous_entry.get(field_name) != current_entry.get(field_name):
                old_value = previous_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else previous_entry.get(field_name)
                new_value = current_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else current_entry.get(field_name)
                diffs.append(f"provider {provider_id} {field_label}: {old_value} -> {new_value}")

    previous_files = {
        str(item.get("path") or ""): item
        for item in previous_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    current_files = {
        str(item.get("path") or ""): item
        for item in current_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    for path in sorted(set(previous_files) | set(current_files)):
        if os.path.basename(str(path or "")) == ".claude.json":
            continue
        previous_entry = previous_files.get(path)
        current_entry = current_files.get(path)
        if previous_entry is None:
            diffs.append(f"file added: {path}")
            continue
        if current_entry is None:
            diffs.append(f"file removed: {path}")
            continue
        if bool(previous_entry.get("exists")) != bool(current_entry.get("exists")):
            diffs.append(f"file presence changed: {path}")
            continue
        if previous_entry.get("sha256") != current_entry.get("sha256"):
            diffs.append(f"file changed: {path}")
    return diffs
