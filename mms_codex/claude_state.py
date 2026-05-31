"""Codex helpers that consume sanitized Claude state."""

from __future__ import annotations

import copy
import os


def sync_codex_session_claude_json(session_home, *, disabled_session_surfaces=None):
    """Seed isolated Codex HOME with the real user's MCP-capable .claude.json."""
    import json as _json
    import mms_launchers as _launchers

    real_json = _launchers._real_user_path(".claude.json")
    if not os.path.exists(real_json):
        return

    session_json = os.path.join(session_home, ".claude.json")
    if os.path.islink(session_json):
        return

    try:
        with open(real_json, "r", encoding="utf-8") as f:
            loaded = _json.load(f)
        if not isinstance(loaded, dict):
            return
        data = _launchers._sanitize_codex_claude_state_payload(loaded)
        if isinstance(data.get("mcpServers"), dict):
            data["mcpServers"] = _launchers._normalize_session_mcp_servers(
                data.get("mcpServers"),
                disabled_session_surfaces=disabled_session_surfaces,
            )
            if not data["mcpServers"]:
                data.pop("mcpServers", None)
    except Exception:
        return

    if os.path.exists(session_json):
        try:
            with open(session_json, "r", encoding="utf-8") as f:
                existing = _json.load(f)
            if isinstance(existing, dict):
                # Keep per-session metadata stable while inheriting global MCP servers.
                if "firstStartTime" in existing:
                    data["firstStartTime"] = existing["firstStartTime"]
                if "bypassPermissionsModeAccepted" in existing:
                    data["bypassPermissionsModeAccepted"] = existing["bypassPermissionsModeAccepted"]
        except Exception:
            pass

    with _launchers.locked_state_file(session_json):
        _launchers.atomic_write_json(session_json, data, mode=0o600)


def strip_codex_mcp_server_blocks(config_text, disabled_session_surfaces=None):
    import re
    import mms_launchers as _launchers

    disabled_names = _launchers._normalize_session_surface_disabled(disabled_session_surfaces).get("mcp", set())
    if not disabled_names:
        return config_text
    text = str(config_text or "")
    header_pattern = re.compile(
        r'^\[mcp_servers\.(?:"([^"]+)"|([A-Za-z0-9_-]+))(?:\.[^\]]+)?\]\s*$',
        flags=re.MULTILINE,
    )
    spans = []
    for match in header_pattern.finditer(text):
        name = match.group(1) or match.group(2)
        if name not in disabled_names:
            continue
        next_header = re.search(r'^\[', text[match.end():], flags=re.MULTILINE)
        end = match.end() + next_header.start() if next_header else len(text)
        spans.append((match.start(), end))
    if not spans:
        return text
    chunks = []
    cursor = 0
    for start, end in spans:
        chunks.append(text[cursor:start])
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)


def append_codex_mcp_servers_from_claude_json(config_text, *, disabled_session_surfaces=None):
    """Translate Claude-style mcpServers into Codex [mcp_servers.*] sections."""
    import json as _json
    import re
    import mms_launchers as _launchers

    config_text = _launchers._strip_codex_mcp_server_blocks(config_text, disabled_session_surfaces)

    real_json = _launchers._real_user_path(".claude.json")
    try:
        if os.path.exists(real_json):
            with open(real_json, "r", encoding="utf-8") as f:
                loaded = _json.load(f)
        else:
            loaded = {}
        servers = loaded.get("mcpServers", {}) if isinstance(loaded, dict) else {}
    except Exception:
        servers = {}

    servers = copy.deepcopy(servers) if isinstance(servers, dict) else {}
    enabled_codex_plugins = _launchers._enabled_real_codex_plugin_names()
    for name, spec in _launchers._installed_claude_plugin_mcp_servers().items():
        if (
            isinstance(spec, dict)
            and isinstance(spec.get("url"), str)
            and spec.get("url").strip()
            and str(name or "").strip().lower() in enabled_codex_plugins
        ):
            continue
        servers.setdefault(name, copy.deepcopy(spec))
    hive_spec = _launchers._default_hive_session_mcp_server()
    if isinstance(hive_spec, dict) and str(hive_spec.get("command") or "").strip():
        servers.setdefault("hive", hive_spec)
    pilot_spec = _launchers._default_pilot_session_mcp_server()
    if isinstance(pilot_spec, dict) and str(pilot_spec.get("command") or "").strip():
        servers.setdefault("pilot", pilot_spec)
    servers = _launchers._normalize_session_mcp_servers(
        servers,
        disabled_session_surfaces=disabled_session_surfaces,
    )

    if not servers:
        return config_text

    existing = set()
    pattern = re.compile(r'^\[mcp_servers\.(?:"([^"]+)"|([A-Za-z0-9_-]+))\]\s*$', flags=re.MULTILINE)
    for match in pattern.finditer(config_text):
        existing.add(match.group(1) or match.group(2))

    blocks = []
    for name, spec in servers.items():
        if name in existing or not isinstance(spec, dict):
            continue

        section_name = _launchers._toml_bare_key(name)
        lines = [f"[mcp_servers.{section_name}]"]

        url = spec.get("url")
        command = spec.get("command")
        if isinstance(url, str) and url.strip():
            lines.append(f"url = {_launchers._toml_quote(url)}")
            bearer_token_env_var = spec.get("bearer_token_env_var")
            if isinstance(bearer_token_env_var, str) and bearer_token_env_var.strip():
                lines.append(f"bearer_token_env_var = {_launchers._toml_quote(bearer_token_env_var)}")
        elif isinstance(command, str) and command.strip():
            lines.append(f"command = {_launchers._toml_quote(command)}")
            args = spec.get("args")
            if isinstance(args, list):
                rendered_args = ", ".join(_launchers._toml_quote(arg) for arg in args)
                lines.append(f"args = [{rendered_args}]")
            env = spec.get("env")
            if isinstance(env, dict):
                env_lines = []
                for env_key in sorted(env):
                    env_value = env[env_key]
                    if isinstance(env_value, (str, int, float, bool)):
                        env_lines.append(f"{_launchers._toml_bare_key(env_key)} = {_launchers._toml_quote(env_value)}")
                if env_lines:
                    lines.append("")
                    lines.append(f"[mcp_servers.{section_name}.env]")
                    lines.extend(env_lines)
        else:
            continue

        blocks.append("\n".join(lines))

    if not blocks:
        return config_text

    config_text = config_text.rstrip()
    if config_text:
        config_text += "\n\n"
    return config_text + "\n\n".join(blocks) + "\n"
